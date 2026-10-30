"""Batch NMR extraction for the OpenSpec staged pipeline."""

import multiprocessing as mp
from typing import Any, Dict, Optional

import pandas as pd

from openmolspec.core.constants import SPECTRUM_PARAMETERS
from openmolspec.parsing.gaussian import GaussianNMRParser
from openmolspec.io.tasks import load_tasks
from openmolspec.core.processing import record_quality_metadata, report_row, write_processing_reports
from openmolspec.core.progress import track


def _init_worker(smiles_map, broadening_sigma):
    global _worker_smiles, _worker_sigma
    _worker_smiles = smiles_map
    _worker_sigma = broadening_sigma


def _process_task(task):
    sample_id, path = task
    parser = GaussianNMRParser(
        path,
        sample_id,
        _worker_smiles,
        broadening_sigma=_worker_sigma,
    )
    if parser.error_type is None and "atom" in parser.properties:
        missing, flags = record_quality_metadata(parser.properties, modality="nmr")
        if parser.properties.get("smiles") is None:
            missing.append("smiles")
        return parser.properties, report_row(
            sample_id, path, status="success", missing_fields=missing, quality_flags=flags
        )
    return None, report_row(
        sample_id,
        path,
        status="failed",
        error_type=parser.error_type or "NMR_PARSE_FAILED",
        error_message=parser.error_message or "Parser produced no NMR fields",
    )


def extract_nmr(
    *,
    file_dict: Optional[str] = None,
    smiles_dict: Optional[str] = None,
    manifest_path: Optional[str] = None,
    output: str,
    report_dir: str,
    workers: int,
    broadening_sigma: float = SPECTRUM_PARAMETERS["nmr_broadening_sigma"],
) -> Dict[str, Any]:
    """Parse all NMR files listed by the manifest-generated ID map."""

    tasks, smiles = load_tasks(
        manifest_path=manifest_path,
        file_dict=file_dict,
        smiles_dict=smiles_dict,
        path_field="nmr_log_path",
    )
    records = []
    reports = []
    with mp.Pool(
        processes=workers,
        initializer=_init_worker,
        initargs=(smiles, broadening_sigma),
    ) as pool:
        for record, report in track(
            pool.imap_unordered(_process_task, tasks),
            total=len(tasks),
            desc="NMR extraction",
            unit="record",
        ):
            reports.append(report)
            if record is not None:
                records.append(record)
    pd.DataFrame(records).to_pickle(output)
    write_processing_reports(reports, report_dir)
    return {
        "input_records": len(tasks),
        "parsed_records": len(records),
        "output": output,
    }
