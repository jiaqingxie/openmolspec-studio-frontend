"""Orchestrate source scanning and assembly of the unified manifest."""

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

from .manifest_scan import (
    collect_collection,
    configure_rdkit_logging,
    merge_records,
    write_outputs,
)
from openmolspec.core.progress import status


def build_manifest(
    *,
    frequency_root: str,
    nmr_root: str,
    output_dir: str,
    datasets: Iterable[str],
    nmr_datasets: Iterable[str],
    include_nmr: bool = True,
    hash_files: bool = True,
    workers: int = 1,
    show_rdkit_warnings: bool = False,
    cache_dir: str | None = None,
    incremental: bool = True,
    min_file_age_seconds: float = 0.0,
    audit_all_records: bool = False,
    write_compatibility_json: bool = True,
) -> Dict[str, Any]:
    """Build the input-file manifest for molecular data processing."""
    configure_rdkit_logging(show_rdkit_warnings)
    datasets = list(datasets)
    nmr_datasets = list(nmr_datasets)
    records: List[Dict[str, Any]] = []
    audit: List[Dict[str, Any]] = []
    output_path = Path(output_dir)
    cache_root = (
        Path(cache_dir)
        if cache_dir
        else output_path.parent / "cache" / "manifest"
    )
    status(
        f"Manifest build started: {len(datasets)} frequency datasets, "
        f"{len(nmr_datasets) if include_nmr else 0} NMR datasets, "
        f"workers={workers}, hashes={'on' if hash_files else 'off'}"
    )
    for dataset in datasets:
        rows, report = collect_collection(
            Path(frequency_root), dataset, hash_files=hash_files, workers=workers,
            cache_path=cache_root / "frequency" / f"{dataset}.parquet",
            incremental=incremental,
            min_file_age_seconds=min_file_age_seconds,
            audit_all_records=audit_all_records,
        )
        records.extend(rows)
        audit.extend(report)
    identity_lookup = {
        row["sample_id"]: row
        for row in records
        if row.get("canonical_smiles")
    }
    if include_nmr:
        for dataset in nmr_datasets:
            rows, report = collect_collection(
                Path(nmr_root), dataset, nmr=True, hash_files=hash_files,
                label_fallback_dirs=(Path(frequency_root) / dataset,),
                workers=workers,
                cache_path=cache_root / "nmr" / f"{dataset}.parquet",
                incremental=incremental,
                min_file_age_seconds=min_file_age_seconds,
                identity_lookup=identity_lookup,
                audit_all_records=audit_all_records,
            )
            records.extend(rows)
            audit.extend(report)

    manifest, merge_audit = merge_records(records)
    audit_frame = pd.DataFrame(audit + merge_audit)
    summary = write_outputs(
        manifest,
        audit_frame,
        output_path,
        write_compatibility_json=write_compatibility_json,
    )
    status(
        f"Manifest build completed: {summary['records']:,} records, "
        f"{summary['both_frequency_and_nmr']:,} paired frequency/NMR records"
    )
    summary.update({
        "frequency_root": frequency_root,
        "nmr_root": nmr_root if include_nmr else None,
        "datasets": list(datasets),
        "nmr_datasets": list(nmr_datasets) if include_nmr else [],
        "hash_files": hash_files,
        "incremental": incremental,
        "manifest_cache_dir": str(cache_root),
        "min_file_age_seconds": min_file_age_seconds,
        "audit_all_records": audit_all_records,
    })
    with (output_path / "label_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
    return summary
