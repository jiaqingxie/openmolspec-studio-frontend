"""Use measured unassigned spectra to refine atom-centred shift estimates on disjoint molecules."""

import argparse
from array import array
from collections import defaultdict
import gzip
import itertools
import json
from pathlib import Path
import pickle
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import numpy as np
from rdkit import Chem, RDLogger
from scipy.optimize import linear_sum_assignment
from openmolspec_bench.data import sha256
from openmolspec.peak_learning import environments, estimate


def read_rows(path):
    with gzip.open(path, "rb") as f:
        while True:
            try:
                yield pickle.load(f)
            except EOFError:
                return


class Measurements:
    def __init__(self):
        self.codes = array("I")
        self.labels = array("f")

    def add(self, codes, labels):
        self.codes.frombytes(np.ascontiguousarray(codes, dtype=np.uint32).tobytes())
        self.labels.frombytes(np.ascontiguousarray(labels, dtype=np.float32).tobytes())

    def summarize(self):
        codes = np.frombuffer(self.codes, np.uint32).reshape(-1, 6)
        y = np.frombuffer(self.labels, np.float32)
        tables = []
        for radius in range(6):
            order = np.argsort(codes[:, radius], kind="stable")
            keys, start, counts = np.unique(
                codes[order, radius], return_index=True, return_counts=True
            )
            sorted_y = y[order]
            table = {}
            # Only a code recurring at several sites is usable for transfer.
            for k, s, n in zip(keys, start, counts):
                if n >= 3 and k != 0:
                    table[int(k)] = (float(np.median(sorted_y[s : s + n])), int(n))
            tables.append(table)
        return tables


def assigned_tables(a):
    train_ids = set()
    acc = Measurements()
    i = 0
    with gzip.open(a.assigned, "rt") as f:
        for line in f:
            key, role, smi, nuc, _, sites = json.loads(line)
            if nuc != a.nucleus or role != "train":
                continue
            m = Chem.MolFromSmiles(smi)
            groups, all_codes, h, c = environments(m)
            shifts = dict(sites)
            idx = []
            val = []
            for j, group in enumerate(groups):
                ys = {float(v) for k in group for v in shifts.get(k, ())}
                if ys:
                    idx.append(j)
                    val.append(np.median(list(ys)))
            if idx:
                acc.add(all_codes[idx], val)
                i += len(idx)
            train_ids.add(key)
    return (
        acc.summarize(),
        float(np.median(np.frombuffer(acc.labels, np.float32))),
        train_ids,
        i,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("data", "assigned", "output", "report"):
        p.add_argument("--" + n, type=Path, required=True)
    p.add_argument("--nucleus", choices=["1H", "13C"], required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    RDLogger.DisableLog("rdApp.*")
    manifest = json.loads((a.data / "manifest.json").read_text())
    for role in ("train", "val"):
        if sha256(a.data / (role + ".pkl.gz")) != manifest["files"][role]:
            raise ValueError("Cached peak split digest mismatch")
    seed, center, used, nsites = assigned_tables(a)
    h_nucleus = a.nucleus == "1H"
    gate = 0.55 if h_nucleus else 6.0
    penalty = 1.0 if h_nucleus else 10.0
    validation = []
    for key, smi, codes, h, c, hp, cp in read_rows(a.data / "val.pkl.gz"):
        if key not in used:
            validation.append(
                (key, smi, codes[h if h_nucleus else c], hp if h_nucleus else cp)
            )
    previous = None
    history = []
    # Re-estimate site assignments once after the initial model has seen the unassigned spectra.
    for epoch in range(2):
        weak = Measurements()
        ntrain = 0
        for key, _, codes, h, c, hp, cp in read_rows(a.data / "train.pkl.gz"):
            if key in used:
                continue
            codes = codes[h if h_nucleus else c]
            ref = hp if h_nucleus else cp
            base = estimate(codes, seed, center)
            guess = (
                base
                if previous is None
                else (base + estimate(codes, previous["tables"], center)) / 2
            )
            cost = np.abs(guess[:, None] - ref)
            row, col = linear_sum_assignment(cost)
            accept = cost[row, col] <= gate
            if accept.any():
                weak.add(codes[row[accept]], ref[col[accept]])
                ntrain += 1
        tables = weak.summarize()
        nlabels = len(weak.labels)
        del weak
        configs = list(itertools.product((0.0, 0.25, 0.5, 0.75, 1.0), (3, 8, 20)))
        scores = np.zeros(len(configs))
        pe = 0
        for key, smi, codes, ref in validation:
            anchor = estimate(codes, seed, center)
            by_min = {n: estimate(codes, tables, center, minimum=n) for n in (3, 8, 20)}
            for j, (mix, n) in enumerate(configs):
                pred = (1 - mix) * anchor + mix * by_min[n]
                cost = abs(pred[:, None] - ref)
                row, col = linear_sum_assignment(cost)
                scores[j] += (
                    np.minimum(cost[row, col], 2 * penalty).sum()
                    + penalty * abs(len(ref) - len(pred))
                ) / max(len(ref), len(pred))
            pe += 1
        scores /= pe
        best = int(np.argmin(scores))
        mix, support = configs[best]
        payload = dict(
            nucleus=a.nucleus,
            center=center,
            seed_tables=seed,
            tables=tables,
            weight=mix,
            min_support=support,
        )
        selected = dict(
            epoch=epoch + 1,
            validation=float(scores[best]),
            baseline=float(scores[0]),
            weight=mix,
            min_support=support,
            weak_train_molecules=ntrain,
            matched_train_sites=nlabels,
        )
        if not history or selected["validation"] < min(
            r["validation"] for r in history
        ):
            temporary = a.output / "environments.partial"
            with gzip.open(temporary, "wt", compresslevel=3) as f:
                json.dump(payload, f, separators=(",", ":"), allow_nan=False)
            temporary.replace(a.output / "environments.json.gz")
        history.append(selected)
        (a.output / "progress.json").write_text(json.dumps(history, indent=2) + "\n")
        previous = payload
        print(selected, flush=True)
    choice = min(history, key=lambda r: r["validation"])
    a.report.write_text(
        json.dumps(
            dict(
                nucleus=a.nucleus,
                training_input_manifest=manifest,
                seed_training_molecules=len(used),
                seed_site_observations=nsites,
                validation_molecules=len(validation),
                history=history,
                selected=choice,
                model_sha256=sha256(a.output / "environments.json.gz"),
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
