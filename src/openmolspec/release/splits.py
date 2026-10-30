"""Scaffold-disjoint official train/validation/test splits for OpenMolSpec."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Set

import pandas as pd

from .common import atomic_json, output_dir, stable_digest


SPLIT_VERSION = "1.1.0"
PARTITIONS = ("train", "validation", "test")


def _scaffold_keys(frame: pd.DataFrame) -> pd.Series:
    """Return split keys while keeping all acyclic molecules in one group."""

    scaffold = frame["scaffold"].astype("string")
    missing = scaffold.isna() | scaffold.str.strip().eq("")
    scaffold = scaffold.mask(missing, "__MISSING__:" + frame["inchikey"].astype(str))
    return scaffold.astype(str)


def _take_exact_scaffold_groups(
    groups: pd.DataFrame,
    target: int,
    *,
    excluded: Set[str],
) -> Set[str]:
    """Select complete scaffold groups whose molecule counts sum to target."""

    selected: Set[str] = set()
    remaining = target
    for row in groups.itertuples(index=False):
        scaffold = str(row.split_scaffold)
        size = int(row.molecule_count)
        if scaffold in excluded or size > remaining:
            continue
        selected.add(scaffold)
        remaining -= size
        if remaining == 0:
            break
    if remaining:
        raise ValueError(
            f"cannot construct an exact {target:,}-molecule scaffold holdout; "
            f"{remaining:,} molecules remain"
        )
    return selected


def _assign_scaffold_holdout(
    align: pd.DataFrame,
    seed: int,
    validation: int,
    test: int,
) -> pd.DataFrame:
    if validation < 1 or test < 1:
        raise ValueError("validation and test counts must be positive")
    if validation + test >= len(align):
        raise ValueError("validation + test must be smaller than the align catalog")

    assignment = align[["molecule_id", "inchikey", "scaffold"]].copy()
    assignment["split_scaffold"] = _scaffold_keys(assignment)
    groups = assignment.groupby("split_scaffold", observed=True).size().rename(
        "molecule_count"
    ).reset_index()
    groups["_order"] = groups["split_scaffold"].map(
        lambda value: stable_digest(value, seed)
    )
    groups = groups.sort_values("_order", kind="mergesort").drop(columns="_order")

    test_scaffolds = _take_exact_scaffold_groups(groups, test, excluded=set())
    validation_scaffolds = _take_exact_scaffold_groups(
        groups, validation, excluded=test_scaffolds
    )
    assignment["split"] = "train"
    assignment.loc[assignment["split_scaffold"].isin(test_scaffolds), "split"] = "test"
    assignment.loc[
        assignment["split_scaffold"].isin(validation_scaffolds), "split"
    ] = "validation"
    return assignment


def _overlap(left: pd.DataFrame, right: pd.DataFrame, field: str) -> int:
    return len(set(left[field].dropna()) & set(right[field].dropna()))


def build_splits(config: Mapping[str, Any]) -> Dict[str, Any]:
    release_root = output_dir(config)
    catalog_dir = release_root / "catalog"
    destination = release_root / "splits"
    destination.mkdir(parents=True, exist_ok=True)
    full = pd.read_parquet(catalog_dir / "full.parquet")
    align = pd.read_parquet(catalog_dir / "align.parquet")
    options = config["release"]["splits"]
    seed = int(options.get("seed", 2025))
    validation_count = int(options.get("validation_count", 20_000))
    test_count = int(options.get("test_count", 20_000))
    requested_train = options.get("align_train_count")

    align_assignment = _assign_scaffold_holdout(
        align, seed, validation_count, test_count
    )
    observed_train = int(align_assignment["split"].eq("train").sum())
    if requested_train is not None and observed_train != int(requested_train):
        raise ValueError(
            f"align train count is {observed_train:,}, expected {int(requested_train):,}"
        )

    split_by_molecule = align_assignment.set_index("molecule_id")["split"]
    heldout_scaffolds = set(
        align_assignment.loc[
            align_assignment["split"].isin(("validation", "test")), "split_scaffold"
        ]
    )
    full_assignment = full[[
        "molecule_id", "inchikey", "scaffold", "representative_source",
        "source_datasets",
    ]].copy()
    full_assignment["split_scaffold"] = _scaffold_keys(full_assignment)
    full_assignment["split"] = full_assignment["molecule_id"].map(split_by_molecule)
    full_assignment["is_align"] = full_assignment["split"].notna()
    full_assignment["split"] = full_assignment["split"].fillna("train")

    # Keep full and align holdouts identical without leaking a held-out scaffold
    # through a partial-modality molecule in full training.
    blocked = (
        full_assignment["split"].eq("train")
        & full_assignment["split_scaffold"].isin(heldout_scaffolds)
    )
    full_assignment.loc[blocked, "split"] = "excluded"

    align_out = align.merge(
        align_assignment[["molecule_id", "split_scaffold", "split"]],
        on="molecule_id",
        how="left",
    )
    full_out = full.merge(
        full_assignment[["molecule_id", "split_scaffold", "split"]],
        on="molecule_id",
        how="left",
    )
    align_out.to_parquet(destination / "align_split.parquet", index=False)
    full_out.to_parquet(destination / "full_split.parquet", index=False)
    full_assignment.to_parquet(destination / "assignments.parquet", index=False)

    leakage_rows = []
    for catalog_name, frame in (("align", align_out), ("full", full_out)):
        partitions = {
            name: frame.loc[frame["split"].eq(name)] for name in PARTITIONS
        }
        for field in ("molecule_id", "inchikey", "split_scaffold"):
            for left, right in (
                ("train", "validation"), ("train", "test"), ("validation", "test")
            ):
                leakage_rows.append({
                    "catalog": catalog_name,
                    "identity": field,
                    "left_split": left,
                    "right_split": right,
                    "overlap_count": _overlap(partitions[left], partitions[right], field),
                })
    leakage = pd.DataFrame(leakage_rows)
    leakage.to_parquet(destination / "leakage_report.parquet", index=False)
    if leakage["overlap_count"].sum() != 0:
        raise RuntimeError("molecular identity or scaffold leakage detected in official split")

    align_holdouts = {
        name: set(align_out.loc[align_out["split"].eq(name), "molecule_id"])
        for name in ("validation", "test")
    }
    full_holdouts = {
        name: set(full_out.loc[full_out["split"].eq(name), "molecule_id"])
        for name in ("validation", "test")
    }
    if align_holdouts != full_holdouts:
        raise RuntimeError("full and align validation/test identities differ")

    summary = {
        "split_version": SPLIT_VERSION,
        "algorithm": "strict Bemis-Murcko scaffold groups ordered by SHA-256(seed:scaffold)",
        "seed": seed,
        "identity_key": "full InChIKey",
        "scaffold_key": "manifest Bemis-Murcko scaffold; __ACYCLIC__ is one shared group",
        "full_counts": full_out["split"].value_counts().to_dict(),
        "align_counts": align_out["split"].value_counts().to_dict(),
        "align_train_target": int(requested_train) if requested_train is not None else None,
        "validation_and_test_are_align_only": True,
        "full_and_align_holdouts_identical": True,
        "full_only_molecules_with_holdout_scaffolds_excluded": int(blocked.sum()),
        "full_train_excludes_all_holdout_scaffolds": True,
        "identity_and_scaffold_overlap_total": int(leakage["overlap_count"].sum()),
    }
    atomic_json(destination / "summary.json", summary)
    return summary
