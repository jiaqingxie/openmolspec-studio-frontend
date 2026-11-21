"""Select experimental 1H or 13C site predictors using disjoint molecular connectivities."""

import argparse
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import lightgbm as lgb
import numpy as np
from rdkit import Chem, RDLogger
from openmolspec.assigned_shifts import assigned_sites
from openmolspec.solution_shifts import feature_matrix, root_estimate
from openmolspec_bench.data import sha256
from train_solution_shifts import metrics


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("data", "output", "report"):
        p.add_argument("--" + name, required=True, type=Path)
    p.add_argument("--nucleus", choices=["13C", "1H"], required=True)
    p.add_argument("--threads", type=int, default=2)
    a = p.parse_args()
    RDLogger.DisableLog("rdApp.*")
    a.output.mkdir(exist_ok=True, parents=True)
    integ = json.loads(a.data.with_suffix(".manifest.json").read_text())
    if sha256(a.data) != integ["output_sha256"]:
        raise ValueError("Assignment archive checksum mismatch")
    molecules = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    with gzip.open(a.data, "rt") as f:
        for line in f:
            key, split, smi, nuc, sol, sites = json.loads(line)
            if nuc != a.nucleus:
                continue
            for idx, labels in sites:
                molecules[(key, split, smi)][sol][idx].update(labels)
    keys = []
    roles = []
    targets = []
    roots = []

    def examples():
        while molecules:
            (key, role, smi), spectra = molecules.popitem()
            sites = assigned_sites(Chem.MolFromSmiles(smi), a.nucleus)
            for sol, annotations in spectra.items():
                for members, codes, feats in sites:
                    shifts = {v for i in members for v in annotations.get(i, ())}
                    if not shifts:
                        continue
                    keys.append(key)
                    roles.append(role)
                    roots.append(codes[3:6])
                    targets.append(np.median(list(shifts)))
                    yield feats, sol

    X = feature_matrix(examples())
    keys = np.array(keys)
    roles = np.array(roles)
    y = np.array(targets, dtype=np.float64)
    roots = np.array(roots, dtype=np.uint32)
    del targets
    train = roles == "train"
    val = roles == "val"
    test = roles == "test"
    if set(keys[train]) & (set(keys[val]) | set(keys[test])) or set(keys[val]) & set(
        keys[test]
    ):
        raise ValueError("Connectivity leakage")
    weights = Counter(keys)
    w = np.array([1 / weights[k] for k in keys])
    w /= w.mean()
    local = [{} for _ in range(6)]
    for i in range(3):
        table = defaultdict(list)
        for code, shift in zip(roots[train, i], y[train]):
            table[int(code)].append(shift)
        local[i + 3] = {
            str(k): [float(np.median(v)), len(v)]
            for k, v in table.items()
            if len(v) >= 2
        }
    with gzip.open(a.output / "lookup.json.gz", "wt") as f:
        json.dump(local, f, separators=(",", ":"))

    def lookup(mask):
        return np.array(
            [root_estimate(local, [0, 0, 0, *r]) for r in roots[mask]], dtype=float
        )

    val_local = lookup(val)
    val_x = X[val]
    train_x = X[train]
    grid = []
    for leaves, leaf in [(31, 12), (63, 10), (95, 20)]:
        ds = lgb.Dataset(
            train_x, label=y[train], weight=w[train], categorical_feature=[0]
        )
        vd = ds.create_valid(val_x, label=y[val], weight=w[val])
        tree = lgb.train(
            dict(
                objective="regression_l1",
                metric="l1",
                verbosity=-1,
                deterministic=True,
                force_col_wise=True,
                num_leaves=leaves,
                min_data_in_leaf=leaf,
                max_bin=63,
                feature_fraction=0.9,
                num_threads=a.threads,
                learning_rate=0.065,
                seed=2539,
            ),
            ds,
            num_boost_round=3000,
            valid_sets=[vd],
            callbacks=[lgb.early_stopping(100, verbose=False)],
        )
        raw = tree.predict(val_x, num_threads=a.threads)
        look = np.where(np.isfinite(val_local), val_local, raw)
        for mix in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
            loss = np.average(
                abs(raw * (1 - mix) + look * mix - y[val]), weights=w[val]
            )
            grid.append(
                dict(
                    leaves=leaves,
                    min_leaf=leaf,
                    rounds=tree.best_iteration,
                    weight=mix,
                    mae=float(loss),
                )
            )
        current = min(
            (r for r in grid if r["leaves"] == leaves), key=lambda r: r["mae"]
        )
        if current == min(grid, key=lambda r: r["mae"]):
            tree.save_model(
                str(a.output / "booster.txt"), num_iteration=tree.best_iteration
            )
        print(current, flush=True)
    best = min(grid, key=lambda r: r["mae"])
    config = dict(
        nucleus=a.nucleus,
        lookup_weight=best["weight"],
        tree_sha256=sha256(a.output / "booster.txt"),
        lookup_sha256=sha256(a.output / "lookup.json.gz"),
    )
    (a.output / "model.json").write_text(json.dumps(config, indent=2) + "\n")
    test_local = lookup(test)
    model = lgb.Booster(model_file=str(a.output / "booster.txt"))
    raw = model.predict(X[test], num_threads=a.threads)
    est = (1 - best["weight"]) * raw + best["weight"] * np.where(
        np.isfinite(test_local), test_local, raw
    )
    report = dict(
        nucleus=a.nucleus,
        reference="median assigned shift per symmetry class and solvent; H attached to the same heavy-atom site are pooled",
        split_identity_counts={
            r: len(set(keys[roles == r])) for r in ("train", "val", "test")
        },
        training_site_records=int(train.sum()),
        source=integ,
        grid=grid,
        selected=best,
        test=metrics(est - y[test], keys[test]),
        tree_only_test=metrics(raw - y[test], keys[test]),
        train_median_test=metrics(np.median(y[train]) - y[test], keys[test]),
        config=config,
    )
    a.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(report["test"], flush=True)


if __name__ == "__main__":
    main()
