"""python -m openmolspec_bench: list tasks, inspect assets, run evaluations."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import platform
import sys
import time

from .catalog import BY_ID, TASKS, records


def save(path, payload):
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def implementation_sha256():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for directory in ("openmolspec_bench", "spec2struct_fork", "openmolspec_ui"):
        for path in sorted((root / directory).rglob("*.py")):
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="Show all integrated task definitions")
    listing.add_argument("--json", action="store_true")
    run = sub.add_parser("run", help="Evaluate existing weights or predictions; never train")
    run.add_argument("--tasks", nargs="+", default=["all"], choices=["all", *BY_ID])
    run.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[2])
    run.add_argument("--portable-root", type=Path)
    run.add_argument("--models-root", type=Path)
    run.add_argument("--datasets", nargs="+", default=["nmrspec_test", "patent_test_10k", "nmrexp_exp_10k", "nmrgym_test"])
    run.add_argument("--alignment-checkpoint", type=Path)
    run.add_argument("--generation-checkpoint", type=Path)
    run.add_argument("--fp-inference-root", type=Path, help="Exact prepared F.lmdb/P.lmdb and frozen prediction folders")
    run.add_argument("--allow-cross-domain-diagnostic", action="store_true", help="Report unverified solid-to-solution F/P diagnostic errors separately")
    run.add_argument("--gap-lmdb", type=Path)
    run.add_argument("--forward-logs", nargs="+", type=Path, help="Paired Gaussian geometry/spectrum logs for frozen forward evaluation")
    run.add_argument("--gap-unit", choices=("auto", "hartree", "eV"), default="auto")
    run.add_argument("--ms-python", default=sys.executable, help="Interpreter containing authors' MS dependencies")
    run.add_argument("--nmr-python", default=sys.executable, help="Interpreter containing frozen NMRNet dependencies")
    run.add_argument("--assignment-nucleus", choices=("1H", "13C"), default="13C")
    run.add_argument("--solvent-library", type=Path, default=Path(__file__).resolve().parents[1]/".runtime/solvent_reference_library.json")
    run.add_argument("--transpeaknet-source", type=Path, help="Author 2dNMR checkout with HSQC weights and test ZIP")
    run.add_argument("--ms-source", type=Path)
    run.add_argument("--ms-weights", type=Path)
    run.add_argument("--ms-input-csv", type=Path)
    run.add_argument("--ms-metadata-tsv", type=Path)
    run.add_argument("--magma-source", type=Path)
    run.add_argument("--limit", type=int, default=64)
    run.add_argument("--sampling", choices=("first", "reservoir"), default="first")
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--batch-size", type=int, default=16)
    run.add_argument("--beam-size", type=int, default=5)
    run.add_argument("--vib-beam-size", type=int, default=10, help="Xinyu evaluation default for complete-input Vib2Mol generation")
    run.add_argument("--device", default="cpu")
    run.add_argument("--threads", type=int, default=2)
    run.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "list":
        if args.json:
            print(json.dumps(records(), ensure_ascii=False, indent=2))
        else:
            for task in TASKS:
                backend = task.backend if task.enabled else "deferred_by_user"
                print(f"{task.id:36s} {backend:26s} {task.title}")
        return 0
    if min(args.limit, args.batch_size, args.beam_size, args.vib_beam_size, args.threads) < 1:
        parser.error("limit, batch-size, beam-size and threads must be positive")
    if args.output.exists():
        parser.error(f"Output exists: {args.output}; choose a new result file")
    args.workspace = args.workspace.resolve()
    args.portable_root = args.portable_root or args.workspace.parent / "openmolspec-studio-portable"
    args.models_root = args.models_root or args.workspace.parent / "models"
    args.alignment_checkpoint = args.alignment_checkpoint or args.workspace / "runs/f90bd7f743574d18a7f72ae72ce95e59/best.pt"
    args.generation_checkpoint = args.generation_checkpoint or args.workspace / "runs/bebaecf2bca248f1a47eaa01f403002a/best.pt"
    import torch
    torch.set_num_threads(args.threads)
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        parser.error("CUDA unavailable; use --device cpu")
    from .runner import MissingAsset, Runner
    runner = Runner(args)
    selected = [task for task in TASKS if task.enabled] if "all" in args.tasks else [BY_ID[key] for key in args.tasks]
    started = time.monotonic()
    result = {"schema_version": 1, "release": "1.0.0", "started_at": datetime.now(timezone.utc).isoformat(),
              "purpose": ("hsqc_checkpoint_evaluation" if [t.backend for t in selected] == ["transpeaknet"]
                          else "pipeline_smoke_evaluation"), "limit": args.limit,
              "device": args.device, "python": platform.python_version(), "torch": torch.__version__,
              "implementation_sha256": implementation_sha256(),
              "training_performed": False, "results": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the destination before the first model load; checkpoint after every task.
    with args.output.open("x") as stream:
        stream.write(json.dumps(result))
    for task in selected:
        datasets = args.datasets if task.backend in ("spec2struct_alignment", "spec2struct_generation", "nmrnet_predictions", "nmrnet_atom_assignment") else [None]
        for dataset in datasets:
            item = {"task": task.id, "title": task.title, "backend": task.backend,
                    "domain": task.domain, "dataset_name": dataset}
            then = time.monotonic()
            print(json.dumps({"event": "started", "task": task.id, "dataset": dataset}), flush=True)
            try:
                item.update(runner.run(task, dataset))
                item["status"] = "passed"
            except MissingAsset as error:
                item.update(status="skipped", reason=str(error))
            except Exception as error:
                import traceback
                traceback.print_exc()
                item.update(status="failed", reason=f"{type(error).__name__}: {error}")
            item["elapsed_seconds"] = round(time.monotonic() - then, 3)
            result["results"].append(item)
            result["counts"] = dict(Counter(row["status"] for row in result["results"]))
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            save(args.output, result)
            print(json.dumps({"event": "completed", "task": task.id, "dataset": dataset,
                              "status": item["status"], "seconds": item["elapsed_seconds"],
                              "reason": item.get("reason")}), flush=True)
    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    save(args.output, result)
    print(json.dumps({"output": str(args.output), "counts": result["counts"]}), flush=True)
    return int(bool(result["counts"].get("failed")))


if __name__ == "__main__":
    sys.exit(main())
