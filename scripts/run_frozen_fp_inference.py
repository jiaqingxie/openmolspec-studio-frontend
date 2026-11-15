"""Run the authors' inference entry point on exact current F/P inputs; no training."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from openmolspec_bench.data import sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-root", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--symbol", choices=("F", "P"), required=True)
    parser.add_argument("--folds", type=int, default=1)
    args = parser.parse_args()
    prepared = args.prepared.resolve()
    models = args.models_root.resolve()
    source = models / "nmrnet/nmrnet-orig"
    run = next((models / "nmrnet/solid_oc").glob(args.symbol + "_*"))
    checkpoints = sorted(run.glob("*/checkpoint_best.pt"))[:args.folds]
    if not checkpoints:
        raise FileNotFoundError("No existing NMRNet checkpoint")
    env = dict(os.environ, OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="1", TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD="1")
    with tempfile.TemporaryDirectory(prefix=f"openmolspec-{args.symbol}-frozen-") as temporary:
        shutil.copyfile(prepared / f"{args.symbol}.lmdb", Path(temporary) / "valid.lmdb")
        for checkpoint in checkpoints:
            output = prepared / args.symbol / checkpoint.parent.name
            output.mkdir(exist_ok=False)
            command = [sys.executable, str(source / "uninmr/infer.py"), "--user-dir", str(source / "uninmr"), temporary,
                       "--valid-subset", "valid", "--results-path", str(output), "--saved-dir", str(run),
                       "--num-workers", "0", "--batch-size", "8", "--task", "uninmr", "--loss", "atom_regloss_mae",
                       "--arch", "unimol_large", "--dict-name", str(run.parent / "oc_limit_dict.txt"),
                       "--path", str(checkpoint), "--selected-atom", args.symbol, "--gaussian-kernel", "--atom-descriptor", "0",
                       "--split-mode", "infer", "--cpu", "--required-batch-size-multiple", "1", "--no-progress-bar"]
            manifest = {"training_performed": False, "command": command, "checkpoint": str(checkpoint),
                        "checkpoint_sha256": sha256(checkpoint), "scaler_sha256": sha256(run / "target_scaler.ss"),
                        "input_sha256": sha256(prepared / f"{args.symbol}.lmdb")}
            with (output / "inference.log").open("w") as stream:
                result = subprocess.run(command, cwd=source, env=env, stdout=stream, stderr=subprocess.STDOUT)
            manifest["exit_code"] = result.returncode
            (output / "inference_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            print(json.dumps({"symbol": args.symbol, "fold": checkpoint.parent.name, "exit_code": result.returncode}), flush=True)
            if result.returncode:
                raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
