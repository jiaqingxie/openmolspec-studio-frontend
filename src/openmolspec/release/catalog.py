"""Build molecule-level full and strictly aligned OpenMolSpec catalogs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import numpy as np
import pandas as pd

from .common import atomic_json, output_dir, resolve_path, stable_digest


CATALOG_VERSION = "1.1.0"
STRICT_ALIGN_DEFINITION = (
    "frequency parser success with frequencies, IR and Raman present, and NMR "
    "parser success for the same sample_id"
)


def _missing_contains(value: Any, field: str) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and np.isnan(value):
        return False
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return field == value
    try:
        return field in value
    except TypeError:
        return False


def _processing_status(path: Path, prefix: str) -> pd.DataFrame:
    columns = ["sample_id", "status", "error_type", "missing_fields", "quality_flags"]
    frame = pd.read_parquet(path, columns=columns)
    if frame["sample_id"].duplicated().any():
        raise ValueError(f"duplicate sample_id values in {path}")
    return frame.rename(columns={
        "status": f"{prefix}_status",
        "error_type": f"{prefix}_error_type",
        "missing_fields": f"{prefix}_missing_fields",
        "quality_flags": f"{prefix}_quality_flags",
    })


def _best_rows(records: pd.DataFrame, mask: pd.Series, score: pd.Series) -> pd.DataFrame:
    candidates = records.loc[mask, ["inchikey", "sample_id", "source_dataset"]].copy()
    candidates["_score"] = score.loc[mask].astype(int).to_numpy()
    candidates = candidates.sort_values(
        ["inchikey", "_score", "source_dataset", "sample_id"],
        ascending=[True, False, True, True],
        kind="mergesort",
    )
    return candidates.drop_duplicates("inchikey", keep="first").set_index("inchikey")


def build_catalog(
    config: Mapping[str, Any],
    *,
    manifest_path: Optional[str] = None,
    frequency_report_path: Optional[str] = None,
    nmr_report_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Create record, full-molecule and strict-align Parquet tables.

    ``full`` is molecular-identity unique. It retains independent sample IDs for
    the best frequency and NMR records. ``align`` is a subset whose modalities
    coexist on one source record, preventing accidental cross-conformer pairing.
    """

    paths = config["inputs"]
    manifest_file = resolve_path(config, manifest_path or paths["manifest"])
    frequency_file = resolve_path(config, frequency_report_path or paths["frequency_report"])
    nmr_file = resolve_path(config, nmr_report_path or paths["nmr_report"])
    destination = output_dir(config) / "catalog"
    destination.mkdir(parents=True, exist_ok=True)

    manifest_columns = [
        "sample_id", "source_dataset", "source_id", "smiles", "canonical_smiles",
        "inchikey", "scaffold", "label_status", "available_modalities",
        "frequency_file_hash", "nmr_file_hash",
    ]
    records = pd.read_parquet(manifest_file, columns=manifest_columns)
    if records["sample_id"].duplicated().any():
        raise ValueError("manifest sample_id values must be unique")
    records = records.merge(_processing_status(frequency_file, "frequency"), on="sample_id", how="left")
    records = records.merge(_processing_status(nmr_file, "nmr"), on="sample_id", how="left")

    records["frequency_parsed"] = records["frequency_status"].eq("success")
    records["frequencies_present"] = records["frequency_parsed"] & ~records["frequency_missing_fields"].map(
        lambda value: _missing_contains(value, "freq") or _missing_contains(value, "frequencies")
    )
    records["ir_present"] = records["frequency_parsed"] & ~records["frequency_missing_fields"].map(
        lambda value: _missing_contains(value, "ir") or _missing_contains(value, "ir_spectrum")
    )
    records["raman_present"] = records["frequency_parsed"] & ~records["frequency_missing_fields"].map(
        lambda value: _missing_contains(value, "raman") or _missing_contains(value, "raman_spectrum")
    )
    records["spectrum_complete"] = (
        records["frequencies_present"] & records["ir_present"] & records["raman_present"]
    )
    records["nmr_present"] = records["nmr_status"].eq("success")
    records["strict_align"] = records["spectrum_complete"] & records["nmr_present"]
    records["identity_valid"] = records["inchikey"].notna() & records["inchikey"].astype(str).str.len().gt(0)
    records["inchikey_connectivity"] = records["inchikey"].str.slice(0, 14)
    records["molecule_id"] = records["inchikey"].map(
        lambda value: f"OMS-{stable_digest(str(value))[:20]}" if pd.notna(value) else None
    )

    valid = records.loc[records["identity_valid"]].copy()
    score = (
        valid["strict_align"].astype(int) * 100
        + valid["spectrum_complete"].astype(int) * 10
        + valid["nmr_present"].astype(int) * 5
        + valid["frequency_parsed"].astype(int)
    )
    representative = _best_rows(valid, pd.Series(True, index=valid.index), score)
    frequency_best = _best_rows(valid, valid["spectrum_complete"], score)
    nmr_best = _best_rows(valid, valid["nmr_present"], score)
    align_best = _best_rows(valid, valid["strict_align"], score)

    grouped = valid.groupby("inchikey", sort=True, observed=True)
    full = grouped.agg(
        canonical_smiles=("canonical_smiles", "first"),
        smiles=("smiles", "first"),
        scaffold=("scaffold", "first"),
        inchikey_connectivity=("inchikey_connectivity", "first"),
        record_count=("sample_id", "size"),
        source_count=("source_dataset", "nunique"),
        has_frequency=("frequency_parsed", "max"),
        has_ir=("ir_present", "max"),
        has_raman=("raman_present", "max"),
        has_nmr=("nmr_present", "max"),
        has_strict_align=("strict_align", "max"),
    ).reset_index()
    source_datasets = grouped["source_dataset"].agg(
        lambda values: sorted({str(value) for value in values})
    )
    full["source_datasets"] = full["inchikey"].map(source_datasets)
    full["molecule_id"] = full["inchikey"].map(lambda value: f"OMS-{stable_digest(value)[:20]}")
    full["representative_sample_id"] = full["inchikey"].map(representative["sample_id"])
    full["representative_source"] = full["inchikey"].map(representative["source_dataset"])
    full["frequency_sample_id"] = full["inchikey"].map(frequency_best["sample_id"])
    full["frequency_source"] = full["inchikey"].map(frequency_best["source_dataset"])
    full["nmr_sample_id"] = full["inchikey"].map(nmr_best["sample_id"])
    full["nmr_source"] = full["inchikey"].map(nmr_best["source_dataset"])
    full["align_sample_id"] = full["inchikey"].map(align_best["sample_id"])
    full["align_source"] = full["inchikey"].map(align_best["source_dataset"])
    full["catalog_version"] = CATALOG_VERSION
    full = full.sort_values("molecule_id", kind="mergesort").reset_index(drop=True)
    align = full.loc[full["has_strict_align"]].copy().reset_index(drop=True)

    records.to_parquet(destination / "records.parquet", index=False)
    full.to_parquet(destination / "full.parquet", index=False)
    align.to_parquet(destination / "align.parquet", index=False)

    summary = {
        "catalog_version": CATALOG_VERSION,
        "identity_key": "full InChIKey (stereochemistry/protonation preserved)",
        "strict_align_definition": STRICT_ALIGN_DEFINITION,
        "input_records": int(len(records)),
        "identity_valid_records": int(records["identity_valid"].sum()),
        "full_unique_molecules": int(len(full)),
        "align_unique_molecules": int(len(align)),
        "strict_align_records": int(records["strict_align"].sum()),
        "frequency_parsed_records": int(records["frequency_parsed"].sum()),
        "complete_spectrum_records": int(records["spectrum_complete"].sum()),
        "nmr_parsed_records": int(records["nmr_present"].sum()),
        "unresolved_identity_records": int((~records["identity_valid"]).sum()),
        "files": {
            "records": "records.parquet",
            "full": "full.parquet",
            "align": "align.parquet",
        },
    }
    atomic_json(destination / "summary.json", summary)
    return summary
