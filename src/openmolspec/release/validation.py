"""Fast, non-destructive release-gate validation over catalog metadata."""

from __future__ import annotations

from typing import Any, Dict, Mapping

import pandas as pd

from .common import atomic_json, output_dir, resolve_path


VALIDATION_VERSION = "1.1.0"


def validate_release(config: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate the configured release files and record contracts."""
    root = output_dir(config)
    records = pd.read_parquet(root / "catalog" / "records.parquet")
    full = pd.read_parquet(root / "catalog" / "full.parquet")
    align = pd.read_parquet(root / "catalog" / "align.parquet")
    assignments = pd.read_parquet(root / "splits" / "assignments.parquet")
    align_split = pd.read_parquet(root / "splits" / "align_split.parquet")
    full_split = pd.read_parquet(root / "splits" / "full_split.parquet")
    destination = root / "validation"
    destination.mkdir(parents=True, exist_ok=True)

    checks = []

    def add(name: str, passed: bool, observed: Any, expected: Any) -> None:
        checks.append({"check": name, "passed": bool(passed), "observed": observed, "expected": expected})

    add("record_sample_id_unique", records["sample_id"].is_unique, records["sample_id"].nunique(), len(records))
    add("full_inchikey_unique", full["inchikey"].is_unique, full["inchikey"].nunique(), len(full))
    add("full_molecule_id_unique", full["molecule_id"].is_unique, full["molecule_id"].nunique(), len(full))
    add("align_is_full_subset", set(align["molecule_id"]).issubset(set(full["molecule_id"])), len(align), "subset")
    add("align_rows_strict", bool(align["has_strict_align"].all()), int(align["has_strict_align"].sum()), len(align))
    add("align_sample_ids_present", align["align_sample_id"].notna().all(), int(align["align_sample_id"].notna().sum()), len(align))
    add("split_assignment_complete", len(assignments) == len(full), len(assignments), len(full))
    add("split_assignment_unique", assignments["molecule_id"].is_unique, assignments["molecule_id"].nunique(), len(assignments))

    train_keys = set(assignments.loc[assignments["split"].eq("train"), "inchikey"])
    holdout_keys = set(assignments.loc[assignments["split"].isin(("validation", "test")), "inchikey"])
    add("full_train_holdout_leakage", not bool(train_keys & holdout_keys), len(train_keys & holdout_keys), 0)

    for catalog_name, frame in (("align", align_split), ("full", full_split)):
        train_scaffolds = set(frame.loc[frame["split"].eq("train"), "split_scaffold"])
        validation_scaffolds = set(frame.loc[frame["split"].eq("validation"), "split_scaffold"])
        test_scaffolds = set(frame.loc[frame["split"].eq("test"), "split_scaffold"])
        overlap = (
            (train_scaffolds & validation_scaffolds)
            | (train_scaffolds & test_scaffolds)
            | (validation_scaffolds & test_scaffolds)
        )
        add(f"{catalog_name}_scaffold_disjoint", not overlap, len(overlap), 0)

    for split_name in ("validation", "test"):
        align_ids = set(align_split.loc[align_split["split"].eq(split_name), "molecule_id"])
        full_ids = set(full_split.loc[full_split["split"].eq(split_name), "molecule_id"])
        add(
            f"shared_{split_name}_identities",
            align_ids == full_ids,
            len(align_ids ^ full_ids),
            0,
        )

    requested_train = config["release"]["splits"].get("align_train_count")
    if requested_train is not None:
        observed_train = int(align_split["split"].eq("train").sum())
        add("align_train_exact_count", observed_train == int(requested_train), observed_train, requested_train)

    add(
        "record_source_columns_present",
        {"source_dataset", "source_id"}.issubset(records.columns),
        sorted({"source_dataset", "source_id"} & set(records.columns)),
        ["source_dataset", "source_id"],
    )
    molecule_source_columns = {
        "source_datasets", "representative_source", "frequency_source", "nmr_source", "align_source"
    }
    add(
        "molecule_source_columns_present",
        molecule_source_columns.issubset(full.columns),
        sorted(molecule_source_columns & set(full.columns)),
        sorted(molecule_source_columns),
    )

    source = records.groupby("source_dataset", observed=True).agg(
        records=("sample_id", "size"),
        frequency_parsed=("frequency_parsed", "sum"),
        complete_spectrum=("spectrum_complete", "sum"),
        nmr_parsed=("nmr_present", "sum"),
        strict_align=("strict_align", "sum"),
    ).reset_index()
    for field in ("frequency_parsed", "complete_spectrum", "nmr_parsed", "strict_align"):
        source[f"{field}_rate"] = source[field] / source["records"]
    source.to_parquet(destination / "success_by_source.parquet", index=False)

    errors = []
    for modality in ("frequency", "nmr"):
        subset = records.loc[records[f"{modality}_status"].eq("failed")]
        table = subset.groupby(["source_dataset", f"{modality}_error_type"], dropna=False).size().rename("count").reset_index()
        table["modality"] = modality
        table = table.rename(columns={f"{modality}_error_type": "error_type"})
        errors.append(table)
    pd.concat(errors, ignore_index=True).to_parquet(destination / "parser_errors.parquet", index=False)

    check_table = pd.DataFrame(checks)
    # Parquet columns require one stable dtype; checks intentionally compare
    # both numerical counts and textual invariants such as "subset".
    check_table["observed"] = check_table["observed"].map(str)
    check_table["expected"] = check_table["expected"].map(str)
    check_table.to_parquet(destination / "release_checks.parquet", index=False)
    summary = {
        "validation_version": VALIDATION_VERSION,
        "non_destructive": True,
        "release_gate_pass": bool(check_table["passed"].all()),
        "checks_passed": int(check_table["passed"].sum()),
        "checks_total": int(len(check_table)),
        "full_unique_molecules": int(len(full)),
        "align_unique_molecules": int(len(align)),
        "strict_align_records": int(records["strict_align"].sum()),
        "frequency_success": int(records["frequency_parsed"].sum()),
        "complete_spectrum_success": int(records["spectrum_complete"].sum()),
        "nmr_success": int(records["nmr_present"].sum()),
        "failed_frequency": int(records["frequency_status"].eq("failed").sum()),
        "failed_nmr": int(records["nmr_status"].eq("failed").sum()),
        "deep_validation_command": (
            "python -m openmolspec.quality.stats --output <release>/validation/publication "
            "--cache-dir <release>/cache/validation [use the versioned paths from the release config]"
        ),
    }
    atomic_json(destination / "summary.json", summary)
    if not summary["release_gate_pass"]:
        failed = check_table.loc[~check_table["passed"], "check"].tolist()
        raise RuntimeError(f"release validation failed: {failed}")
    return summary
