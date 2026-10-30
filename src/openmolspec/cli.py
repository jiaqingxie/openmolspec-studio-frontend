"""OpenMolSpec staged data-production entry point."""

import argparse
import json
from pathlib import Path

import yaml

from openmolspec.workflows.frequency import extract_frequency
from openmolspec.workflows.manifest import build_manifest
from openmolspec.workflows.nmr import extract_nmr
from openmolspec.datasets.splits import run as run_splits
from openmolspec.quality.dedup import run as run_dedup
from openmolspec.quality.validation import run as run_internal_qc


STAGES = ("manifest", "freq", "nmr", "validate", "dedup", "split", "all")


def load_config(path: str):
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _workers(config):
    configured = int(config["runtime"].get("workers", 0))
    return configured if configured > 0 else __import__("multiprocessing").cpu_count()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--stage", choices=STAGES, default="all")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--no-nmr", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    paths = config["paths"]
    reports = Path(paths["report_dir"])
    output_dir = Path(paths["output_dir"])
    workers = args.workers if args.workers is not None else _workers(config)
    if args.stage == "all":
        stages = ("manifest", "freq", "nmr", "validate", "dedup", "split")
    else:
        stages = (args.stage,)
    results = {}

    if "manifest" in stages:
        results["manifest"] = build_manifest(
            frequency_root=paths["frequency_root"],
            nmr_root=paths["nmr_root"],
            output_dir=str(output_dir),
            datasets=config["datasets"]["frequency"],
            nmr_datasets=config["datasets"]["nmr"],
            include_nmr=not args.no_nmr,
            hash_files=bool(config["runtime"].get("hash_files", True)),
            workers=workers,
            show_rdkit_warnings=bool(
                config["runtime"].get("show_rdkit_warnings", False)
            ),
            cache_dir=paths.get("manifest_cache_dir"),
            incremental=bool(config["runtime"].get("manifest_incremental", True)),
            min_file_age_seconds=float(
                config["runtime"].get("manifest_min_file_age_seconds", 0)
            ),
            audit_all_records=bool(
                config["runtime"].get("manifest_audit_all_records", False)
            ),
            write_compatibility_json=bool(
                config["runtime"].get("write_compatibility_json", True)
            ),
        )

    if "freq" in stages:
        results["freq"] = extract_frequency(
            manifest_path=str(output_dir / "openspec_manifest.parquet"),
            output=paths["parsed_output"],
            report_dir=str(reports / "extraction"),
            workers=workers,
            frequency_scaling_factor=float(config["processing"]["frequency_scaling_factor"]),
            ir_broadening_sigma=float(config["processing"]["ir_broadening_sigma_cm-1"]),
            raman_broadening_sigma=float(config["processing"]["raman_broadening_sigma_cm-1"]),
        )

    if "nmr" in stages:
        results["nmr"] = extract_nmr(
            manifest_path=str(output_dir / "openspec_manifest.parquet"),
            output=paths["nmr_output"],
            report_dir=str(reports / "nmr"),
            workers=workers,
            broadening_sigma=float(config["processing"].get("nmr_broadening_sigma", 0.05)),
        )

    if "validate" in stages:
        results["validate"] = run_internal_qc(paths["parsed_output"], str(reports / "internal_qc"), workers=workers)
    if "dedup" in stages:
        results["dedup"] = run_dedup(paths["parsed_output"], str(reports / "dedup"), workers=workers)
    if "split" in stages:
        split = config["splits"]
        results["split"] = run_splits(
            paths["parsed_output"], str(reports / "splits"),
            seed=int(split["seed"]), train=float(split["train"]),
            validation=float(split["validation"]), test=float(split["test"]),
            workers=workers,
        )
    print(json.dumps(results, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
