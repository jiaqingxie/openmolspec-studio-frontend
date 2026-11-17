"""Extract structures and quantum-chemical properties from Gaussian logs."""

import argparse
import json
import multiprocessing as mp
from pathlib import Path
import sys

import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from openmolspec.parsing.gaussian import GaussianLogParser, lorentzian_broadening, raman_intensity
from openmolspec.core.processing import (
    record_quality_metadata,
    report_row,
    write_processing_reports,
)

Lorenz_broadening = lorentzian_broadening
get_raman_intensity = raman_intensity


def get_raman_spectrum(freq, raman_activity, x_axis=None):
    """Construct a Raman spectrum from vibrational frequencies and activities."""
    import numpy as np
    grid = x_axis if x_axis is not None else np.linspace(400, 4000, 1024)
    return raman_intensity(grid, lorentzian_broadening(freq, raman_activity, grid, sigma=12))


def get_ir_spectrum(freq, ir_intensity, x_axis=None):
    """Construct an infrared spectrum from vibrational frequencies and intensities."""
    import numpy as np
    grid = x_axis if x_axis is not None else np.linspace(400, 4000, 1024)
    return lorentzian_broadening(freq, ir_intensity, grid, sigma=20)


class LogParser(GaussianLogParser):
    """Compatibility wrapper preserving the historical no-scaling path."""

    def __init__(self, file_path, unique_id, smiles_map=None):
        super().__init__(file_path, unique_id, smiles_map, frequency_scaling_factor=1.0)


def init_worker(smiles_dict):
    """Initialize shared inputs used by the parallel extraction workers."""
    global global_smiles_dict
    global_smiles_dict = smiles_dict


def process_log(task):
    """Extract molecular properties and spectra from one source log."""
    sample_id, path = task
    parser = LogParser(path, sample_id, global_smiles_dict)
    return parser.properties if "atom" in parser.properties else None


def process_log_with_report(task):
    """Extract one source log and attach structured processing metadata."""
    sample_id, path = task
    parser = LogParser(path, sample_id, global_smiles_dict)
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
    """Run the extract properties command-line workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file-dict", default="datasets/openspec_freq_files.json")
    parser.add_argument("--smiles-dict", default="datasets/openspec_smiles.json")
    parser.add_argument(
        "--save-path", default="artifacts/processed/openspec_properties.pickle"
    )
    parser.add_argument("--report-path", default=None)
    args = parser.parse_args()

    with open(args.file_dict, encoding="utf-8") as handle:
        file_dict = json.load(handle)
    with open(args.smiles_dict, encoding="utf-8") as handle:
        smiles_dict = json.load(handle)

    tasks = list(file_dict.items())
    results = []
    reports = []
    with mp.Pool(mp.cpu_count(), initializer=init_worker, initargs=(smiles_dict,)) as pool:
        for result, report in tqdm(
            pool.imap_unordered(process_log_with_report, tasks), total=len(tasks)
        ):
            reports.append(report)
            if result is not None:
                results.append(result)

    pd.DataFrame(results).to_pickle(args.save_path)
    write_processing_reports(reports, args.report_path or f"{args.save_path}.report")
    print(f"Number of processed files:\t{len(tasks)}")
    print(f"Number of valid files:\t{len(results)}")
    print(f"Saving files in {args.save_path}")


if __name__ == "__main__":
    main()
