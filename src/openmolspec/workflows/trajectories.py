"""Extract optimization trajectories from Gaussian frequency logs."""

import argparse
import json
import multiprocessing as mp
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from openmolspec.parsing.trajectory import parse_gaussian_trajectory


SOURCE_PREFIXES = {
    "nist_ir": "NISTIR",
    "pah": "PAH",
    "pcqm4mv2": "PCQM4MV2",
    "qm9": "QM9",
    "rxn": "RXN",
    "sdbs": "SDBS",
    "wiley_ir": "WILEYIR",
    "wiley_raman": "WILEYRAMAN",
    "peptide": "PEPTIDE",
    "zinc_v1": "ZINCV1",
    "zinc_v2": "ZINCV2",
}


def _process(task: Tuple[str, str]):
    sample_id, path = task
    try:
        trajectory = parse_gaussian_trajectory(path)
        if not trajectory["steps"]:
            return None, {"sample_id": sample_id, "status": "failed", "error": "NO_OPTIMIZATION_STEPS"}
        for step in trajectory["steps"]:
            step["sample_id"] = sample_id
        return trajectory, {
            "sample_id": sample_id,
            "status": "success",
            "trajectory_status": "converged" if trajectory["is_converged"] else "partial",
            "optimization_converged": trajectory["is_converged"],
            "normal_termination": trajectory["normal_termination"],
            "n_steps": trajectory["n_steps"],
            "unlabeled_geometry_frames": trajectory["unlabeled_geometry_frames"],
        }
    except Exception as exc:  # keep one malformed log from stopping a batch
        return None, {"sample_id": sample_id, "status": "failed", "error": type(exc).__name__, "message": str(exc)}


def run_dataset(log_path: str, save_path: str, report_path: str, workers: int, prefix: str = "") -> Dict[str, Any]:
    """Run trajectory extraction for one configured source dataset."""
    tasks = []
    for path in sorted(Path(log_path).glob("*.log")):
        stem = path.stem
        sample_id = stem if not prefix or stem.startswith(f"{prefix}-") else f"{prefix}-{stem}"
        tasks.append((sample_id, str(path)))

    rows = []
    reports = []
    with mp.Pool(processes=workers) as pool:
        iterator = pool.imap_unordered(_process, tasks)
        for trajectory, report in tqdm(
            iterator, total=len(tasks), desc=f"Optimization trajectories: {prefix or Path(log_path).name}"
        ):
            reports.append(report)
            if trajectory is not None:
                rows.extend(trajectory["steps"])

    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_pickle(save_path)
    report_path_obj = Path(report_path)
    report_path_obj.parent.mkdir(parents=True, exist_ok=True)
    summary: Dict[str, Any] = {
        "input_logs": len(tasks),
        # A successful parse does not imply that Gaussian optimization converged.
        "logs_with_trajectory": sum(row.get("status") == "success" for row in reports),
        "converged_logs": sum(row.get("trajectory_status") == "converged" for row in reports),
        "partial_logs": sum(row.get("trajectory_status") == "partial" for row in reports),
        "failed_logs": sum(row.get("status") == "failed" for row in reports),
        "normal_termination_logs": sum(row.get("normal_termination") is True for row in reports),
        "trajectory_frames": len(rows),
        "unlabeled_geometry_frames_removed": sum(
            row.get("unlabeled_geometry_frames", 0) for row in reports
        ),
        "output": save_path,
        "force_convention": "F = -dE/dR",
        "force_unit": "Hartree/Bohr",
        "coordinate_unit": "Angstrom",
        "energy_unit": "Hartree",
        "reports": reports,
    }
    with open(report_path_obj, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False, default=str)
    return summary


def main() -> None:
    """Run the trajectories command-line workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-path", help="Parse one directory containing Gaussian .log files")
    parser.add_argument(
        "--save-path", default="artifacts/processed/openspec_opt_trajectories.pickle"
    )
    parser.add_argument("--report-path", default="reports/opt_trajectories.json")
    parser.add_argument("--freq-root", help="Parse dataset log directories below <freq-root>/<dataset>/<dataset>_log")
    parser.add_argument("--datasets", nargs="+", choices=sorted(SOURCE_PREFIXES),
                        help="Datasets to process with --freq-root; defaults to all known datasets")
    parser.add_argument("--output-dir", default=".", help="Per-dataset output directory for --freq-root")
    parser.add_argument("--report-dir", default="reports/opt_trajectories",
                        help="Per-dataset report directory for --freq-root")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    if bool(args.log_path) == bool(args.freq_root):
        parser.error("provide exactly one of --log-path or --freq-root")

    if args.log_path:
        summary = run_dataset(args.log_path, args.save_path, args.report_path, args.workers)
        print(json.dumps({key: value for key, value in summary.items() if key != "reports"}, indent=2))
        return

    datasets = args.datasets or list(SOURCE_PREFIXES)
    root = Path(args.freq_root)
    all_summaries = {}
    for dataset in datasets:
        log_path = root / dataset / f"{dataset}_log"
        if not log_path.is_dir():
            print(f"SKIP {dataset}: missing {log_path}", file=sys.stderr)
            continue
        prefix = SOURCE_PREFIXES[dataset]
        summary = run_dataset(
            str(log_path),
            str(Path(args.output_dir) / f"openspec_{dataset}_opt_trajectories.pickle"),
            str(Path(args.report_dir) / f"{dataset}.json"),
            args.workers,
            prefix,
        )
        all_summaries[dataset] = {key: value for key, value in summary.items() if key != "reports"}

    aggregate_path = Path(args.report_dir) / "summary.json"
    aggregate_path.parent.mkdir(parents=True, exist_ok=True)
    with open(aggregate_path, "w", encoding="utf-8") as handle:
        json.dump(all_summaries, handle, indent=2, ensure_ascii=False, default=str)
    print(json.dumps(all_summaries, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
