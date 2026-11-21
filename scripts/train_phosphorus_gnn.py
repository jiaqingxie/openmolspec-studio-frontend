"""Train a four-layer bond-conditioned solution-shift GNN on the frozen solution-shift split."""

import argparse
from collections import Counter
from pathlib import Path
import gzip
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import numpy as np
import torch
from rdkit import RDLogger
from openmolspec.phosphorus_gnn import (
    GraphIndex,
    PhosphorusGNN,
    graph_batch,
    index_tensor,
)
from openmolspec.solution_shifts import analyte, root_estimate
from openmolspec_bench.data import sha256

WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)


def prepare(args):
    manifest = json.loads(args.features.with_suffix(".manifest.json").read_text())
    if sha256(args.features) != manifest["output_sha256"]:
        raise ValueError("Feature manifest checksum mismatch")
    cfg = json.loads((args.tree / "model.json").read_text())
    roles_file = args.tree / "identity-splits.tsv.gz"
    if (
        sha256(roles_file) != cfg["identity_splits_sha256"]
        or sha256(args.tree / "environments.json.gz") != cfg["environments_sha256"]
    ):
        raise ValueError("Frozen baseline checksum mismatch")
    with gzip.open(roles_file, "rt") as f:
        roles = dict(s.split() for s in f)
    with gzip.open(args.tree / "environments.json.gz", "rt") as f:
        tables = json.load(f)
    rd = GraphIndex()
    training, validation = {}, []
    with gzip.open(args.features, "rt") as f:
        for line in f:
            key, smiles, scaffold, sites, obs = json.loads(line)
            role = roles[key]
            if role not in ("train", "val") or len(sites) != 1:
                continue
            selected = [
                (src, solvent, peaks[0])
                for src, _, solvent, peaks, _ in obs
                if len(peaks) == 1
            ]
            if not selected:
                continue
            group, codes, _ = sites[0]
            mol, _ = analyte(smiles, cfg["nucleus"])
            ids, g = rd.add(mol, [group[0]])
            if role == "train":
                for _, solvent, peak in selected:
                    signature = (key, solvent, tuple(codes))
                    training.setdefault(signature, (ids[0], g, set()))[2].add(peak)
            else:
                local = root_estimate(tables, codes)
                for src, solvent, peak in dict.fromkeys(selected):
                    validation.append((key, ids[0], g, solvent, peak, local))
    train = [
        (k, idx, g, s, np.median(list(labels)), None)
        for (k, s, _), (idx, g, labels) in training.items()
    ]
    if len(set(r[0] for r in train)) != cfg["training_identities"] or not validation:
        raise ValueError("Graph records differ from the frozen training partition")
    return rd.arrays(), train, validation


def pack(rows, arrays, batch_size, rng=None):
    n = len(rows)
    idx = np.arange(n) if rng is None else rng.permutation(n)
    counts = Counter(r[0] for r in rows)
    weights = np.array([1 / counts[r[0]] for r in rows])
    weights /= weights.mean()
    y, local = (
        np.array([r[4] for r in rows]),
        np.array([float("nan") if r[5] is None else r[5] for r in rows]),
    )
    root = np.array([r[1] for r in rows])
    cond = torch.from_numpy(np.array([r[2] for r in rows], dtype=np.float32))
    solvent = index_tensor([r[3] for r in rows])
    groups = []
    for start in range(0, n, batch_size):
        ids = idx[start : start + batch_size]
        groups.append(
            (
                graph_batch(arrays, root[ids]),
                cond[ids],
                solvent[ids],
                torch.from_numpy(y[ids].astype("f")),
                torch.from_numpy(weights[ids].astype("f")),
            )
        )
    return groups, y[idx], local[idx], weights[idx]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("features", "tree", "output"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--epochs", type=int, default=140)
    p.add_argument("--seed", type=int, default=4327)
    p.add_argument("--warm-start", type=Path, help="Initial weights for a second training phase")
    p.add_argument("--learning-rate", type=float, default=.0015)
    p.add_argument("--scale", type=float, default=40.0)
    p.add_argument("--threads", type=int, default=2)
    args = p.parse_args()
    RDLogger.DisableLog("rdApp.*")
    args.output.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    # Rebuild graphs for a new experiment so the supplied data and roles are always verified.
    arrays, train, valid = prepare(args)
    print(
        "rows",
        len(train),
        len(valid),
        "graph classes",
        [len(a) if i == 0 else len(a[0]) for i, a in enumerate(arrays)],
        flush=True,
    )
    batches, train_y, _, _ = pack(train, arrays, 256, rng)
    val_batches, y, local, w = pack(valid, arrays, 512)
    mean = float(np.median(train_y))
    scale = args.scale
    net = PhosphorusGNN()
    if args.warm_start is not None:
        initial = torch.load(args.warm_start, weights_only=True, map_location="cpu")
        if initial["center"] != mean or initial["scale"] != scale:
            raise ValueError("Warm-start target normalization differs")
        net.load_state_dict(initial["state"])
    optimizer = torch.optim.AdamW(net.parameters(), lr=args.learning_rate, weight_decay=0.0002)
    schedule = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer,
        mode="min",
        factor=0.45,
        patience=5,
        threshold=0.005,
        threshold_mode="abs",
        min_lr=2e-5,
    )
    start = time.monotonic()
    best = float("inf")
    history = []
    for epoch in range(1, args.epochs + 1):
        net.train()
        for j in rng.permutation(len(batches)):
            graph, cond, solvent, target, weight = batches[j]
            raw = net(graph, cond, solvent)
            loss = (
                weight
                * torch.nn.functional.smooth_l1_loss(
                    raw, (target - mean) / scale, beta=0.04, reduction="none"
                )
            ).mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 5.0)
            optimizer.step()
        net.eval()
        with torch.inference_mode():
            pred = np.concatenate(
                [net(g, c, s).numpy() * scale + mean for g, c, s, _, _ in val_batches]
            )
        estimates = np.where(np.isfinite(local), local, pred)
        scores = [
            float(np.average(np.abs((1 - a) * pred + a * estimates - y), weights=w))
            for a in WEIGHTS
        ]
        k = int(np.argmin(scores))
        score = scores[k]
        schedule.step(score)
        history.append(
            dict(
                epoch=epoch,
                seconds=round(time.monotonic() - start, 1),
                pure=scores[0],
                validation=score,
                weight=WEIGHTS[k],
                lr=optimizer.param_groups[0]["lr"],
            )
        )
        print(json.dumps(history[-1]), flush=True)
        if score < best:
            best = score
            best_epoch = epoch
            tmp = args.output / "gnn.partial"
            torch.save(
                dict(width=net.width, state=net.state_dict(), scale=scale, center=mean),
                tmp,
            )
            tmp.replace(args.output / "gnn.pt")
            np.savez_compressed(
                args.output / "validation.npz",
                raw=pred,
                predictions=(1 - WEIGHTS[k]) * pred + WEIGHTS[k] * estimates,
                targets=y,
                weights=w,
                keys=[r[0] for r in valid],
            )
        if epoch - best_epoch >= 18:
            break
    report = dict(
        history=history,
        best=history[best_epoch - 1],
        parameters=sum(p.numel() for p in net.parameters()),
        features_sha256=sha256(args.features),
        split_sha256=sha256(args.tree / "identity-splits.tsv.gz"),
        checkpoint_sha256=sha256(args.output / "gnn.pt"),
        weight_grid=WEIGHTS,
        initial_weights_sha256=sha256(args.warm_start) if args.warm_start else None,
        seed=args.seed,
        train_records=len(train),
        train_identities=len(set(r[0] for r in train)),
        validation_records=len(valid),
        validation_identities=len(set(r[0] for r in valid)),
    )
    (args.output / "training.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
