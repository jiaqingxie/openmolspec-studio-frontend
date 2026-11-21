"""Freeze a single model or two-model blend on validation, then score measured test shifts."""

import argparse
from collections import Counter
import gzip
import itertools
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import numpy as np
from rdkit import RDLogger
import torch
from compare_phosphorus_models import score_partition, SOLVENT_LABELS
from train_solution_shifts import metrics
from openmolspec.solution_shifts import SolutionShiftPredictor
from openmolspec_bench.data import sha256


def materialize_graph(path, tree):
    history = json.loads((path / "training.json").read_text())
    if history["split_sha256"] != tree.config["identity_splits_sha256"]:
        raise ValueError("Training split mismatch")
    if history["checkpoint_sha256"] != sha256(path / "gnn.pt"):
        raise ValueError("GNN checkpoint mismatch")
    cfg = {k: v for k, v in tree.config.items() if k != "booster_sha256"}
    cfg.update(
        engine="solution_gnn",
        gnn_sha256=history["checkpoint_sha256"],
        environment_weight=history["best"]["weight"],
        epoch=history["best"]["epoch"],
    )
    source = args.trees[0]
    for name in (
        "identity-splits.tsv.gz",
        "test-references.jsonl.gz",
        "environments.json.gz",
    ):
        shutil.copyfile(source / name, path / name)
    (path / "model.json").write_text(json.dumps(cfg, indent=2) + "\n")
    return history


def model_predictions(role, trees, graphs, roles):
    candidates = {}
    order = None
    for i in range(max(len(trees), len(graphs))):
        t, g = trees[i % len(trees)], graphs[i % len(graphs)]
        rows, targets, preds = score_partition(
            args.features, roles, role, t, g, set(), detailed=False
        )
        ids = [(r[0], r[1], r[2], r[3], r[4]) for r in rows]
        if order is None:
            order = ids
        elif order != ids:
            raise ValueError("Held-out rows differ between models")
        candidates[args.trees[i % len(trees)].name] = preds["tree"]
        candidates[args.graphs[i % len(graphs)].name] = preds["gnn"]
        if role == "val":
            np.testing.assert_allclose(
                preds["gnn"],
                np.load(args.graphs[i % len(graphs)] / "validation.npz")["predictions"],
                atol=0.001,
                rtol=0,
            )
    return order, targets, candidates


def choose(rows, targets, candidates):
    counts = Counter(r[0] for r in rows)
    weights = np.array([1 / counts[r[0]] for r in rows])
    errors = {}

    def add(names, mix, pred):
        errors[(names, mix)] = float(np.average(abs(pred - targets), weights=weights))

    for name, pred in candidates.items():
        add((name,), (1.0,), pred)
    for a, b in itertools.combinations(candidates, 2):
        for fraction in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
            add(
                (a, b),
                (1 - fraction, fraction),
                (1 - fraction) * candidates[a] + fraction * candidates[b],
            )
    key = min(errors, key=errors.get)
    return dict(zip(*key)), [
        {"models": dict(zip(names, mix)), "macro_mae_ppm": score}
        for (names, mix), score in sorted(errors.items(), key=lambda kv: kv[1])
    ]


def main():
    torch.set_num_threads(1)
    RDLogger.DisableLog("rdApp.*")
    trees = [SolutionShiftPredictor(path) for path in args.trees]
    cfg = trees[0].config
    for tree in trees:
        if any(
            tree.config[k] != cfg[k]
            for k in ("identity_splits_sha256", "environments_sha256", "nucleus")
        ):
            raise ValueError("Candidate model training datasets differ")
    histories = {p.name: materialize_graph(p, trees[0]) for p in args.graphs}
    if any(h["features_sha256"] != sha256(args.features) for h in histories.values()):
        raise ValueError("Candidate feature dataset differs")
    graphs = [SolutionShiftPredictor(p) for p in args.graphs]
    paths = {p.name: p for p in args.trees + args.graphs}
    if len(paths) != len(args.trees) + len(args.graphs):
        raise ValueError("Models must have distinct directory names")
    with gzip.open(args.trees[0] / "identity-splits.tsv.gz", "rt") as f:
        roles = dict(line.split() for line in f)
    val_rows, val_y, validation = model_predictions("val", trees, graphs, roles)
    winner, scores = choose(val_rows, val_y, validation)
    report = dict(
        nucleus=cfg["nucleus"],
        selection_metric="validation molecule-weighted MAE in ppm",
        validation=scores,
        selected=winner,
        validation_identities=len(set(r[0] for r in val_rows)),
        validation_observations=len(val_rows),
        training_identities=cfg["training_identities"],
        graph_runs={
            n: {k: h[k] for k in ("best", "seed", "parameters", "train_records")}
            for n, h in histories.items()
        },
        split_sha256=cfg["identity_splits_sha256"],
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print("Frozen", cfg["nucleus"], winner, scores[0]["macro_mae_ppm"], flush=True)
    rows, targets, test = model_predictions("test", trees, graphs, roles)
    pred = sum(w * test[n] for n, w in winner.items())
    keys = [r[0] for r in rows]
    report["test"] = {
        n: metrics(v - targets, keys) for n, v in {**test, "selected": pred}.items()
    }
    identities, mapped = np.unique(keys, return_inverse=True)
    counts = np.bincount(mapped)
    rng = np.random.default_rng(1893)
    report["paired_test_differences"] = {}
    for name, values in test.items():
        delta = np.bincount(mapped, weights=abs(pred-targets)-abs(values-targets)) / counts
        draws = np.concatenate([rng.choice(delta, size=(100, len(identities))).mean(axis=1) for _ in range(20)])
        report["paired_test_differences"][name] = dict(
            difference_ppm=float(delta.mean()), molecule_bootstrap_ci95=np.percentile(draws,[2.5,97.5]).tolist()
        )
    args.registry.mkdir(parents=True, exist_ok=True)
    versions = args.registry / "versions"
    versions.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=versions) as temp:
        stage = Path(temp) / "model"
        stage.mkdir()
        for file in ("identity-splits.tsv.gz", "test-references.jsonl.gz"):
            shutil.copyfile(args.trees[0] / file, stage / file)
        manifest = {
            k: v
            for k, v in cfg.items()
            if k not in ("booster_sha256", "environment_weight", "environments_sha256")
        }
        manifest.update(engine="solution_ensemble", components=[])
        for name, weight in winner.items():
            directory = stage / name
            directory.mkdir()
            for file in ("model.json", "environments.json.gz", "gnn.pt", "booster.txt"):
                if (paths[name] / file).is_file():
                    shutil.copyfile(paths[name] / file, directory / file)
            manifest["components"].append(
                dict(name=name, weight=weight, sha256=sha256(directory / "model.json"))
            )
        (stage / "model.json").write_text(json.dumps(manifest, indent=2) + "\n")
        loaded = SolutionShiftPredictor(stage)
        for idx in np.linspace(0, len(rows) - 1, min(36, len(rows)), dtype=int):
            _, smi, _, solvent, _ = rows[idx]
            result = loaded.predict(smi, SOLVENT_LABELS[solvent])
            actual = result["environments"][0]["prediction_ppm"]
            np.testing.assert_allclose(actual, pred[idx], rtol=0, atol=0.001)
        digest = sha256(stage / "model.json")
        destination = versions / digest
        if not destination.exists():
            stage.rename(destination)
        link = Path(temp) / "selected"
        link.symlink_to(Path("versions") / digest)
        link.replace(args.registry / cfg["nucleus"])
    report.update(model_config_sha256=digest, test_predictions_verified_with_sdk=True)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print("Selected test", report["test"]["selected"], flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("features", "registry", "report"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--trees", nargs="+", type=Path, required=True)
    p.add_argument("--graphs", nargs="+", type=Path, required=True)
    args = p.parse_args()
    main()
