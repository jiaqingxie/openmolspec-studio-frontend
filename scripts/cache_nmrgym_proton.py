"""Cache frozen site-model features for training the NMRGym proton adapter."""

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import numpy as np
from rdkit import Chem, RDLogger
from openmolspec.nmrgym_proton import GRID, FP_SIZE, proton_features, resample
from openmolspec.peak_learning import PeakLearningPredictor
from openmolspec_bench.data import sha256


def initialize(model):
    global weak
    RDLogger.DisableLog("rdApp.*")
    cfg = json.loads((model / "model.json").read_text())
    weak = PeakLearningPredictor(
        model / "peak-learning", sha256=cfg["peak_learning_sha256"]
    )


def process(batch):
    values = []
    for key, smiles, reference in batch:
        mol = Chem.MolFromSmiles(smiles)
        if not mol or Chem.MolToInchiKey(mol).split("-")[0] != key:
            continue
        inputs = proton_features(mol, weak)
        if inputs is not None:
            features, count = inputs
            values.append(
                (features, count, resample(reference, len(GRID)), len(reference), key)
            )
    return values


def batches(path):
    with path.open() as stream:
        batch = []
        for line in stream:
            batch.append(json.loads(line))
            if len(batch) == 256:
                yield batch
                batch = []
        if batch:
            yield batch


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument(
        "--base", type=Path, default=ROOT / "../runs/peak-models-selected/1H"
    )
    p.add_argument("--workers", type=int, default=2)
    a = p.parse_args()
    split = json.loads((a.data / "split.json").read_text())
    with ProcessPoolExecutor(
        max_workers=a.workers, initializer=initialize, initargs=(a.base,)
    ) as pool:
        for role, allocation in [
            ("val", split["validation_panel"]),
            ("train", split["eligible_train"]),
        ]:
            path = a.data / (role + ".jsonl")
            assert sha256(path) == split["split_digests"][role]
            size = FP_SIZE + 6 + 3 * len(GRID)
            arrays = {
                name: np.empty(shape, dtype=dtype)
                for name, dtype, shape in [
                    ("x", "f4", (allocation, size)),
                    ("ref", "f4", (allocation, len(GRID))),
                    ("counts", "i4", (allocation, 2)),
                    ("keys", "S14", (allocation,)),
                ]
            }
            n = 0
            # Bounded groups avoid holding the complete decoded training set in the executor.
            from itertools import islice

            source = batches(path)
            while group := list(islice(source, 16)):
                for batch in pool.map(process, group):
                    if not batch:
                        continue
                    x, sites, ref, count, keys = zip(*batch)
                    sl = slice(n, n + len(batch))
                    n = sl.stop
                    arrays["x"][sl], arrays["ref"][sl], arrays["keys"][sl] = (
                        x,
                        ref,
                        keys,
                    )
                    arrays["counts"][sl] = np.column_stack([sites, count])
                if n // 20000 != (n - len(group) * 256) // 20000:
                    print(role, n, flush=True)
            for name, array in arrays.items():
                np.save(a.data / f"{role}-{name}.npy", array[:n], allow_pickle=False)
            (a.data / f"{role}-cache.json").write_text(
                json.dumps(
                    {
                        "usable": n,
                        "input": allocation,
                        "base": sha256(a.base / "model.json"),
                    }
                )
            )
            print(role, n, "ready", flush=True)


if __name__ == "__main__":
    main()
