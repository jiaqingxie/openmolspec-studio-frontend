"""Parse only the ZINCV2 NMR Gaussian logs.

This entry point is intended for re-running validation after a new ZINCV2
NMR batch.  It scans the current log directory instead of processing the
full OpenSpec NMR manifest.
"""

import argparse
import json
import multiprocessing as mp
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd
from tqdm import tqdm

# Make direct execution from the repository root resolve the ``openmolspec`` package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from openmolspec.core.constants import SPECTRUM_PARAMETERS
from openmolspec.parsing.gaussian import GaussianNMRParser
from openmolspec.core.processing import (
    record_quality_metadata,
    report_row,
    write_processing_reports,
)


_smiles: Dict[str, str] = {}
_sigma: float = SPECTRUM_PARAMETERS["nmr_broadening_sigma"]
_require_normal_termination = True


def _init_worker(smiles: Dict[str, str], sigma: float, require_normal: bool) -> None:
    global _smiles, _sigma, _require_normal_termination
    _smiles = smiles
    _sigma = sigma
    _require_normal_termination = require_normal


def _smiles_for(sample_id: str, source_id: str) -> Optional[str]:
    return _smiles.get(sample_id) or _smiles.get(source_id)


def _process(task: Tuple[str, str]):
    sample_id, path = task
    source_id = sample_id.split("-", 1)[-1]
    parser = GaussianNMRParser(
        path,
        sample_id,
        {sample_id: _smiles_for(sample_id, source_id)},
        broadening_sigma=_sigma,
    )

    if parser.error_type is not None:
        return None, report_row(
            sample_id,
            path,
            status="failed",
            error_type=parser.error_type,
            error_message=parser.error_message,
        )

    if _require_normal_termination and "normal termination" not in parser.text.lower():
        return None, report_row(
            sample_id,
            path,
            status="failed",
            error_type="LOG_INCOMPLETE",
            error_message="Gaussian log has no Normal termination marker",
        )

    if "atom" not in parser.properties:
        return None, report_row(
            sample_id,
            path,
            status="failed",
            error_type="NMR_PARSE_FAILED",
            error_message="Parser produced no NMR atom field",
        )

    missing, flags = record_quality_metadata(parser.properties, modality="nmr")
    if parser.properties.get("smiles") is None:
        missing.append("smiles")
    return parser.properties, report_row(
        sample_id,
        path,
        status="success",
        missing_fields=missing,
        quality_flags=flags,
    )


def parse_zinc_v2_nmr(
    *,
    log_path: str,
    smiles_dict: str,
    save_path: str,
    report_dir: str,
    workers: int,
    broadening_sigma: float,
    require_normal_termination: bool,
) -> Dict[str, Any]:
    """Parse the ZINC v2 NMR records into the maintained output representation."""
    with open(smiles_dict, encoding="utf-8") as handle:
        smiles = json.load(handle)

    tasks = []
    for path in sorted(Path(log_path).glob("*.log")):
        stem = path.stem
        sample_id = stem if stem.startswith("ZINCV2-") else f"ZINCV2-{stem}"
        tasks.append((sample_id, str(path)))

    records = []
    reports = []
    with mp.Pool(
        processes=workers,
        initializer=_init_worker,
        initargs=(smiles, broadening_sigma, require_normal_termination),
    ) as pool:
        for record, report in tqdm(
            pool.imap_unordered(_process, tasks),
            total=len(tasks),
            desc="ZINCV2 NMR",
        ):
            reports.append(report)
            if record is not None:
                records.append(record)

    pd.DataFrame(records).to_pickle(save_path)
    write_processing_reports(reports, report_dir)
    return {
        "input_records": len(tasks),
        "parsed_records": len(records),
        "output": save_path,
        "report_dir": report_dir,
    }


def main() -> None:
    """Run the parse zinc v2 nmr command-line workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log-path",
        default="/inspire/hdd/project/chemicalreaction/luxinyu-240207020178/hpc/mols/nmr/zinc_v2_nmr/zinc_v2_nmr_log",
    )
    parser.add_argument("--smiles-dict", default="datasets/openspec_smiles.json")
    parser.add_argument(
        "--save-path", default="artifacts/processed/openspec_zinc_v2_nmr.pickle"
    )
    parser.add_argument("--report-dir", default="reports/nmr_zinc_v2")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--broadening-sigma",
        type=float,
        default=SPECTRUM_PARAMETERS["nmr_broadening_sigma"],
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Allow logs without a Normal termination marker (not recommended).",
    )
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    if args.broadening_sigma <= 0:
        parser.error("--broadening-sigma must be positive")

    result = parse_zinc_v2_nmr(
        log_path=args.log_path,
        smiles_dict=args.smiles_dict,
        save_path=args.save_path,
        report_dir=args.report_dir,
        workers=args.workers,
        broadening_sigma=args.broadening_sigma,
        require_normal_termination=not args.allow_incomplete,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
