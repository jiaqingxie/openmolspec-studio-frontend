"""Build a frozen, leakage-safe and publication-ready OpenMolSpec release.

Example:
    python -m openmolspec.release.build \
        --config configs/openmolspec_v1_release.yaml --stage all
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict

from .catalog import build_catalog
from .common import load_config
from .export import export_release, index_payload
from .freeze import freeze_release
from .splits import build_splits
from .validation import validate_release


STAGES = ("catalog", "split", "validate", "export", "index", "freeze", "all")


def run(config_path: str, stage: str, *, only: str | None = None, hash_workers: int = 2) -> Dict[str, Any]:
    """Run the release build workflow with the supplied settings."""
    config = load_config(config_path)
    stages = ("catalog", "split", "validate", "export", "freeze") if stage == "all" else (stage,)
    results: Dict[str, Any] = {}
    for current in stages:
        if current == "catalog":
            results[current] = build_catalog(config)
        elif current == "split":
            results[current] = build_splits(config)
        elif current == "validate":
            results[current] = validate_release(config)
        elif current == "export":
            results[current] = export_release(config, only=only)
        elif current == "index":
            results[current] = index_payload(config)
        elif current == "freeze":
            results[current] = freeze_release(config, hash_workers=hash_workers)
    return results


def main() -> None:
    """Run the build command-line workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/openmolspec_v1_release.yaml")
    parser.add_argument("--stage", choices=STAGES, default="all")
    parser.add_argument("--only", choices=("frequency", "nmr", "trajectory"),
                        help="with --stage export, export only one payload family")
    parser.add_argument("--hash-workers", type=int, default=2)
    args = parser.parse_args()
    if args.only and args.stage != "export":
        parser.error("--only is valid only with --stage export")
    print(json.dumps(
        run(args.config, args.stage, only=args.only, hash_workers=args.hash_workers),
        indent=2, ensure_ascii=False, default=str,
    ))


if __name__ == "__main__":
    main()
