"""Compatibility backup entry point for the shared Gaussian parser."""

import argparse
import json
import multiprocessing as mp
from pathlib import Path
import sys

import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from openmolspec.parsing.gaussian import GaussianLogParser
from openmolspec.core.processing import (
    record_quality_metadata,
    report_row,
    write_processing_reports,
)


class LogParser(GaussianLogParser):
    """Compatibility wrapper for the historical backup command."""

    def __init__(self, file_path, unique_id, smiles_map=None):
        super().__init__(file_path, unique_id, smiles_map, frequency_scaling_factor=1.0)


def process_log_file_with_report(task):
    """Process a molecular log and return its processing-report entry."""
    sample_id, path, smiles_dict = task
    parser = LogParser(path, sample_id, smiles_dict)
    if "atom" in parser.properties:
        missing, flags = record_quality_metadata(parser.properties)
        if parser.properties.get("smiles") is None:
            missing.append("smiles")
        return parser.properties, report_row(
            sample_id, path, status="success", missing_fields=missing, quality_flags=flags
        )
    return None, report_row(
        sample_id,
        path,
        status="failed",
        error_type=parser.error_type or "UNKNOWN_ERROR",
        error_message=parser.error_message or "Parser produced no atom field",
    )


def main():
    """Run the extract properties backup command-line workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file-dict", required=True)
    parser.add_argument("--smiles-dict", required=True)
    parser.add_argument("--save-path", required=True)
    parser.add_argument("--report-path", default=None)
    args = parser.parse_args()

    with open(args.file_dict, encoding="utf-8") as handle:
        file_dict = json.load(handle)
    with open(args.smiles_dict, encoding="utf-8") as handle:
        smiles_dict = json.load(handle)

    tasks = [(sample_id, path, smiles_dict) for sample_id, path in file_dict.items()]
    results = []
    reports = []
    with mp.Pool(mp.cpu_count()) as pool:
        for result, report in tqdm(
            pool.imap_unordered(process_log_file_with_report, tasks), total=len(tasks)
        ):
            reports.append(report)
            if result is not None:
                results.append(result)

    frame = pd.DataFrame(results)
    if "smiles" in frame:
        frame = frame[frame["smiles"].notna()]
    frame.to_pickle(args.save_path)
    write_processing_reports(reports, args.report_path or f"{args.save_path}.report")
    print(f"Number of processed files:\t{len(tasks)}")
    print(f"Number of valid files:\t{len(frame)}")
    print(f"Saving files in {args.save_path}")


if __name__ == "__main__":
    main()
