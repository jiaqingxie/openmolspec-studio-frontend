"""Select the 31P checkpoint on validation, then audit paired test predictions."""

import argparse
from collections import defaultdict
import gzip
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import numpy as np
import torch
from rdkit import RDLogger
from audit_solution_phosphorus import phosphorus_group
from train_solution_shifts import metrics, records
from openmolspec_bench.data import sha256
from openmolspec.phosphorus_gnn import GraphIndex, graph_batch, index_tensor
from openmolspec.solution_shifts import (
    SolutionShiftPredictor,
    analyte,
    root_estimate,
    feature_matrix,
)

SOLVENT_LABELS = (
    None,
    "CDCl3",
    "DMSO-d6",
    "D2O",
    "CD3OD",
    "C6D6",
    "acetone-d6",
    "CD3CN",
    "THF-d8",
    "CD2Cl2",
    "toluene-d8",
    "other",
)


def training_scaffolds(features, roles):
    candidates = defaultdict(set)
    fitted = set()
    for key, _, scaffold, sites, obs in records(features):
        if roles[key] == "train":
            candidates[key].add(scaffold)
            if len(sites) == 1 and any(len(o[3]) == 1 for o in obs):
                fitted.add(key)
    return {s for k in fitted for s in candidates[k] if s}


def score_partition(features, roles, role, tree, gnn, scaffolds):
    rows = []
    index = GraphIndex()
    observed_scaffolds = defaultdict(set)
    for key, smiles, scaffold, sites, obs in records(features):
        if roles[key] != role:
            continue
        observed_scaffolds[key].add(scaffold)
        if len(sites) != 1:
            continue
        unique = dict.fromkeys(
            (source, solvent, peaks[0])
            for source, _, solvent, peaks, _ in obs
            if len(peaks) == 1
        )
        if not unique:
            continue
        members, codes, descriptors = sites[0]
        mol, _ = analyte(smiles, "31P")
        root, g = index.add(mol, [members[0]])
        local = root_estimate(tree.tables, codes)
        group = phosphorus_group(smiles)
        for source, solvent, target in unique:
            rows.append(
                (
                    key,
                    smiles,
                    source,
                    solvent,
                    target,
                    group,
                    root[0],
                    g,
                    local,
                    descriptors,
                )
            )
    graph_arrays = index.arrays()
    matrix = feature_matrix((r[9], r[3]) for r in rows)
    tree_raw = tree.booster.predict(matrix, num_threads=2)
    net = gnn._graph_model
    outputs = []
    with torch.inference_mode():
        for start in range(0, len(rows), 512):
            block = rows[start : start + 512]
            batch = graph_batch(graph_arrays, [r[6] for r in block])
            raw = net.model(
                batch,
                torch.tensor([r[7] for r in block], dtype=torch.float32),
                index_tensor([r[3] for r in block]),
            )
            outputs.extend((raw.numpy() * net.scale + net.center).tolist())

    def blended(raw, alpha):
        return np.array(
            [
                (1 - alpha) * v + alpha * r[8] if r[8] is not None else v
                for v, r in zip(raw, rows)
            ]
        )

    preds = {
        "tree": blended(tree_raw, tree.config["environment_weight"]),
        "gnn_raw": np.array(outputs),
        "gnn": blended(outputs, gnn.config["environment_weight"]),
    }
    truth = np.array([r[4] for r in rows])
    keys = np.array([r[0] for r in rows])
    groups = np.array([r[5] for r in rows])
    new = np.array(
        [
            bool(s) and "" not in s and s.isdisjoint(scaffolds)
            for s in (observed_scaffolds[k] for k in keys)
        ]
    )
    masks = {
        "all": np.ones(len(rows), bool),
        "unseen_scaffold": new,
        **{g: groups == g for g in sorted(set(groups))},
    }
    info = {}
    rng = np.random.default_rng(20261121)
    for group, mask in masks.items():
        truth_part = truth[mask]
        part_keys = keys[mask]
        info[group] = {
            name: metrics(values[mask] - truth_part, part_keys)
            for name, values in preds.items()
        }
        deltas = defaultdict(list)
        for k, d in zip(
            part_keys,
            np.abs(preds["gnn"][mask] - truth_part)
            - np.abs(preds["tree"][mask] - truth_part),
        ):
            deltas[k].append(d)
        paired = np.asarray([np.mean(v) for v in deltas.values()])
        means = np.concatenate(
            [
                rng.choice(paired, (100, len(paired)), replace=True).mean(axis=1)
                for _ in range(20)
            ]
        )
        info[group]["gnn_minus_tree_macro_ppm"] = {
            "difference": float(paired.mean()),
            "paired_molecule_bootstrap_95": np.percentile(means, [2.5, 97.5]).tolist(),
        }
    for i in np.linspace(0, len(rows) - 1, 12, dtype=int):
        for name, model in [("tree", tree), ("gnn", gnn)]:
            obs = model.predict(rows[i][1], SOLVENT_LABELS[rows[i][3]])["environments"][
                0
            ]["prediction_ppm"]
            if abs(obs - preds[name][i]) > 0.001:
                raise ValueError(f"{role} SDK inference mismatch at row {i}")
    return info, rows, truth, preds


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("features", "tree", "gnn", "output", "predictions"):
        p.add_argument("--" + arg, type=Path, required=True)
    args = p.parse_args()
    torch.set_num_threads(2)
    RDLogger.DisableLog("rdApp.*")
    hist = json.loads((args.gnn / "training.json").read_text())
    if hist["features_sha256"] != sha256(args.features):
        raise ValueError("Feature checksum mismatch")
    tree = SolutionShiftPredictor(args.tree)
    cfg = {k: v for k, v in tree.config.items() if k != "booster_sha256"}
    if hist["split_sha256"] != cfg["identity_splits_sha256"]:
        raise ValueError("Training split mismatch")
    cfg.update(
        engine="phosphorus_gnn",
        gnn_sha256=hist["checkpoint_sha256"],
        environment_weight=hist["best"]["weight"],
        epoch=hist["best"]["epoch"],
    )
    for name in (
        "identity-splits.tsv.gz",
        "environments.json.gz",
        "test-references.jsonl.gz",
    ):
        shutil.copyfile(args.tree / name, args.gnn / name)
    (args.gnn / "model.json").write_text(json.dumps(cfg, indent=2) + "\n")
    gnn = SolutionShiftPredictor(args.gnn)
    with gzip.open(args.tree / "identity-splits.tsv.gz", "rt") as f:
        roles = dict(line.split() for line in f)
    if sha256(args.tree / "identity-splits.tsv.gz") != cfg["identity_splits_sha256"]:
        raise ValueError("Split file mismatch")
    scaffolds = training_scaffolds(args.features, roles)
    valid, _, val_y, val_pred = score_partition(
        args.features, roles, "val", tree, gnn, scaffolds
    )
    saved = np.load(args.gnn / "validation.npz")
    np.testing.assert_allclose(val_y, saved["targets"], rtol=0, atol=1e-9)
    np.testing.assert_allclose(
        val_pred["gnn"], saved["predictions"], rtol=0, atol=0.001
    )
    scores = {n: valid["all"][n]["molecule_macro_mae_ppm"] for n in ("gnn", "tree")}
    assert abs(scores["tree"] - 7.170915632739434) < 1e-6
    winner = min(scores, key=scores.get)
    selected = {
        "selection_metric": "validation molecule-macro MAE (ppm)",
        "winner": winner,
        "validation_scores": scores,
        "tree_rounds": 5960,
        "gnn_best_epoch": hist["best"]["epoch"],
        "gnn_epochs_run": len(hist["history"]),
        "gnn_parameters": hist["parameters"],
        "gnn_environment_weight": cfg["environment_weight"],
        "gnn_validation_history": hist["history"],
        "train_identities": hist["train_identities"],
        "validation": valid,
        "split_sha256": cfg["identity_splits_sha256"],
        "gnn_sha256": cfg["gnn_sha256"],
        "tree_sha256": tree.config["booster_sha256"],
        "feature_sha256": hist["features_sha256"],
    }
    args.output.write_text(json.dumps(selected, indent=2) + "\n")
    print("Selection frozen", winner, scores, flush=True)
    test, rows, truth, preds = score_partition(
        args.features, roles, "test", tree, gnn, scaffolds
    )
    assert len(rows) == 6693 and len({r[0] for r in rows}) == 4248
    with gzip.open(args.predictions, "wt") as f:
        for i, row in enumerate(rows):
            f.write(
                json.dumps(
                    dict(
                        connectivity=row[0],
                        smiles=row[1],
                        source=row[2],
                        solvent=SOLVENT_LABELS[row[3]],
                        reference_ppm=truth[i],
                        **{n: float(v[i]) for n, v in preds.items()},
                    )
                )
                + "\n"
            )
    selected.update(test=test, test_predictions_sha256=sha256(args.predictions))
    args.output.write_text(json.dumps(selected, indent=2, allow_nan=False) + "\n")
    print(
        "Test macro",
        {n: test["all"][n]["molecule_macro_mae_ppm"] for n in preds},
        flush=True,
    )


if __name__ == "__main__":
    main()
