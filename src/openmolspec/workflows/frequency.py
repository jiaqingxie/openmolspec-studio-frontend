"""Batch Gaussian extraction stage for the OpenSpec pipeline."""

import multiprocessing as mp
from typing import Any, Dict, Optional

import pandas as pd

from openmolspec.parsing.gaussian import GaussianLogParser
from openmolspec.io.tasks import load_tasks
from openmolspec.core.processing import record_quality_metadata, report_row, write_processing_reports
from openmolspec.core.progress import track


def _init_worker(smiles_map, frequency_scaling_factor, ir_sigma, raman_sigma):
    global _worker_smiles, _worker_scaling, _worker_ir_sigma, _worker_raman_sigma
    _worker_smiles = smiles_map
    _worker_scaling = frequency_scaling_factor
    _worker_ir_sigma = ir_sigma
    _worker_raman_sigma = raman_sigma


def _process_task(task):
    sample_id, path = task
    parser = GaussianLogParser(
        path,
        sample_id,
        _worker_smiles,
        frequency_scaling_factor=_worker_scaling,
        ir_broadening_sigma=_worker_ir_sigma,
        raman_broadening_sigma=_worker_raman_sigma,
    )
    parser.properties["sample_id"] = sample_id
    if "atom" not in parser.properties:
        return None, report_row(
            sample_id,
            path,
            status="failed",
            error_type=parser.error_type or "UNKNOWN_ERROR",
            error_message=parser.error_message or "Parser produced no atom field",
        )
    missing, flags = record_quality_metadata(parser.properties)
    if parser.properties.get("smiles") is None:
        missing.append("smiles")
    return parser.properties, report_row(
        sample_id, path, status="success", missing_fields=missing, quality_flags=flags
    )


def extract_frequency(
    *,
    file_dict: Optional[str] = None,
    smiles_dict: Optional[str] = None,
    manifest_path: Optional[str] = None,
    output: str,
    report_dir: str,
    workers: int,
    frequency_scaling_factor: float,
    ir_broadening_sigma: float,
    raman_broadening_sigma: float,
) -> Dict[str, Any]:
    tasks, smiles = load_tasks(
        manifest_path=manifest_path,
        file_dict=file_dict,
        smiles_dict=smiles_dict,
        path_field="frequency_log_path",
    )
    records = []
    reports = []
    with mp.Pool(
        processes=workers,
        initializer=_init_worker,
        initargs=(smiles, frequency_scaling_factor, ir_broadening_sigma, raman_broadening_sigma),
    ) as pool:
        for record, report in track(
            pool.imap_unordered(_process_task, tasks),
            total=len(tasks),
            desc="Frequency extraction",
            unit="record",
        ):
            reports.append(report)
            if record is not None:
                records.append(record)
    pd.DataFrame(records).to_pickle(output)
    write_processing_reports(reports, report_dir)
    return {"input_records": len(tasks), "parsed_records": len(records), "output": output}
