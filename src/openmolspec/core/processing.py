"""Shared structured processing results for the extraction CLIs."""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

import pandas as pd
import numpy as np

from .constants import PARSER_VERSION, PROCESSING_VERSION


ERROR_TYPES = (
    "FILE_NOT_FOUND",
    "LOG_INCOMPLETE",
    "SCF_FAILED",
    "OPT_NOT_CONVERGED",
    "GEOMETRY_PARSE_FAILED",
    "ENERGY_PARSE_FAILED",
    "FREQUENCY_PARSE_FAILED",
    "IR_PARSE_FAILED",
    "RAMAN_PARSE_FAILED",
    "NMR_PARSE_FAILED",
    "HESSIAN_PARSE_FAILED",
    "SMILES_MISSING",
    "ATOM_COUNT_MISMATCH",
    "INVALID_NUMERIC_VALUE",
    "UNKNOWN_ERROR",
)


def classify_exception(exc: BaseException) -> str:
    """Map a parser exception to the stable v1 error taxonomy."""

    message = str(exc).lower()
    if isinstance(exc, FileNotFoundError):
        return "FILE_NOT_FOUND"
    if isinstance(exc, (ValueError, TypeError)):
        if "coordinate" in message or "atom" in message:
            return "GEOMETRY_PARSE_FAILED"
        if "hessian" in message:
            return "HESSIAN_PARSE_FAILED"
        if "frequency" in message or "freq" in message:
            return "FREQUENCY_PARSE_FAILED"
        if "nmr" in message or "shield" in message:
            return "NMR_PARSE_FAILED"
        return "INVALID_NUMERIC_VALUE"
    if isinstance(exc, (KeyError, IndexError)):
        if "hessian" in message:
            return "HESSIAN_PARSE_FAILED"
        return "LOG_INCOMPLETE"
    return "UNKNOWN_ERROR"


def source_parts(sample_id: str) -> Dict[str, str]:
    """Return a best-effort source dataset and source ID from a sample ID."""

    if not sample_id:
        return {"source_dataset": "unknown", "source_id": ""}
    if "-" not in sample_id:
        return {"source_dataset": "unknown", "source_id": sample_id}
    prefix, source_id = sample_id.split("-", 1)
    return {"source_dataset": prefix, "source_id": source_id}


def file_sha256(path: str) -> Optional[str]:
    """Return a source-file SHA-256, or ``None`` when the file is unavailable."""

    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return None


def report_row(
    sample_id: str,
    source_path: str,
    *,
    status: str,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    missing_fields: Optional[Iterable[str]] = None,
    quality_flags: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Build one machine-readable processing-report row."""

    row = {
        "sample_id": sample_id,
        **source_parts(sample_id),
        "status": status,
        "error_type": error_type,
        "error_message": error_message,
        "missing_fields": sorted(set(missing_fields or [])),
        "quality_flags": sorted(set(quality_flags or [])),
        "source_file_hash": file_sha256(source_path),
        "parser_version": PARSER_VERSION,
        "processing_version": PROCESSING_VERSION,
    }
    return row


def record_quality_metadata(record: Mapping[str, Any], modality: str = "gaussian"):
    """Return non-destructive missing-field and quality flags for a record."""

    expected = (
        ("atom", "isotropic", "anisotropy", "shielding_tensor")
        if modality == "nmr"
        else ("atom", "coordinate", "freq", "ir", "raman")
    )
    missing = [field for field in expected if field not in record]
    flags = []
    for field in expected:
        if field not in record:
            continue
        try:
            values = np.asarray(record[field])
            if not np.all(np.isfinite(values)):
                flags.append(f"NONFINITE_{field.upper()}")
        except (TypeError, ValueError):
            flags.append(f"INVALID_{field.upper()}_ARRAY")
    if "freq" in record:
        try:
            if np.any(np.asarray(record["freq"]) < 0):
                flags.append("IMAGINARY_FREQUENCIES_PRESENT")
        except (TypeError, ValueError):
            flags.append("INVALID_FREQ_ARRAY")
    if "atom" in record and "coordinate" in record:
        try:
            if np.asarray(record["coordinate"]).size != 3 * len(record["atom"]):
                flags.append("ATOM_COORDINATE_COUNT_MISMATCH")
        except (TypeError, ValueError):
            flags.append("INVALID_COORDINATE_SHAPE")
    return missing, flags


def write_processing_reports(rows: Iterable[Mapping[str, Any]], output_dir: str) -> None:
    """Write the required parquet report and JSON summary."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(list(rows))
    report_path = output_path / "processing_report.parquet"
    frame.to_parquet(report_path, index=False)

    summary = {
        "total": int(len(frame)),
        "status_counts": frame["status"].value_counts(dropna=False).to_dict()
        if "status" in frame
        else {},
        "error_type_counts": frame["error_type"].value_counts(dropna=False).to_dict()
        if "error_type" in frame
        else {},
        "parser_version": PARSER_VERSION,
        "processing_version": PROCESSING_VERSION,
        "report_file": str(report_path.name),
    }
    with open(output_path / "processing_summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False, default=str)
