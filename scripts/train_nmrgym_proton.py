"""Fit a residual spectrum and peak-count model on NMRGym training identities."""

import argparse
import json
from pathlib import Path
import shutil
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from openmolspec.nmrgym_proton import GRID, adapter_outputs, decode
from openmolspec.assigned_shifts import PeakSpectrumPredictor
from openmolspec_bench.data import sha256
from openmolspec_bench.nmr_cosine import peak_profile_cosine
from openmolspec_bench.peak_evaluation import matching_errors


def load(data, split, base_digest):
    cache = json.loads((data / f"{split}-cache.json").read_text())
    if cache["base"] != base_digest:
        raise ValueError(f"{split} features belong to another proton backbone")
    x, ref, counts = [
        np.load(data / f"{split}-{name}.npy") for name in ("x", "ref", "counts")
    ]
    if not len(x) == len(ref) == len(counts) == cache["usable"]:
        raise ValueError(f"Incomplete {split} feature cache")
    return torch.from_numpy(x), torch.from_numpy(ref), torch.from_numpy(counts)


def export(net):
    return {
        key: tensor.detach().numpy().copy()
        for key, tensor in zip(
            ("w1", "b1", "w2", "b2", "out", "bias"), net.parameters()
        )
    }


def metrics(predictions, refs):
    return dict(
        error=float(matching_errors(predictions, refs, 1.0).mean()),
        cosine=float(
            np.mean(
                [peak_profile_cosine(p, y, 0.05) for p, y in zip(predictions, refs)]
            )
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument(
        "--base", type=Path, default=ROOT / "../runs/peak-models-selected/1H"
    )
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--epochs", type=int, default=45)
    a = p.parse_args()
    destination = a.out
    destination.parent.mkdir(exist_ok=True, parents=True)
    if destination.exists():
        raise FileExistsError(destination)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
        a.out = Path(temp) / "model"
        a.out.mkdir()
        fit(a)
        a.out.rename(destination)


def fit(a):
    seed = 713
    torch.manual_seed(seed)
    torch.set_num_threads(3)
    torch.set_num_interop_threads(1)
    base_digest = sha256(a.base / "model.json")
    x, refs, counts = load(a.data, "train", base_digest)
    vx, _, vc = load(a.data, "val", base_digest)
    keys = np.load(a.data / "val-keys.npy").astype(str)
    panel = {
        k: (s, y)
        for k, s, y in map(json.loads, (a.data / "val.jsonl").read_text().splitlines())
    }
    ys = [panel[k][1] for k in keys]
    net = nn.Sequential(
        nn.Linear(x.shape[1], 192),
        nn.ReLU(),
        nn.Linear(192, 128),
        nn.ReLU(),
        nn.Linear(128, len(GRID) + 1),
    )
    nn.init.zeros_(net[-1].weight)
    nn.init.zeros_(net[-1].bias)
    optimizer = torch.optim.AdamW(net.parameters(), lr=0.0015, weight_decay=0.001)
    target_count = torch.log(counts[:, 1] / counts[:, 0])
    residual = refs - x[:, -3 * len(GRID) : -2 * len(GRID)]
    history, best_error = [], float("inf")
    for epoch in range(1, a.epochs + 1):
        net.train()
        total_loss = 0.0
        for batch in torch.randperm(len(x)).split(512):
            output = net(x[batch])
            loss = F.smooth_l1_loss(output[:, :-1], residual[batch], beta=0.25)
            loss += 1.5 * F.smooth_l1_loss(
                output[:, -1], target_count[batch], beta=0.15
            )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 3.0)
            optimizer.step()
            total_loss += float(loss.detach()) * len(batch)
        weights = export(net)
        curve, n = adapter_outputs(vx.numpy(), vc[:, 0].numpy(), weights)
        dev = float(
            matching_errors(
                [decode(c, k, [], 0.0) for c, k in zip(curve, n)], ys, 1.0
            ).mean()
        )
        history.append(
            dict(epoch=epoch, loss=total_loss / len(x), validation_error_ppm=dev)
        )
        print(history[-1], flush=True)
        if dev < best_error:
            best_error, best_epoch = dev, epoch
            np.savez_compressed(a.out / "adapter.npz", **weights)
        if epoch - best_epoch in (3, 6):
            for group in optimizer.param_groups:
                group["lr"] *= 0.5
        if epoch - best_epoch >= 9:
            break
    with np.load(a.out / "adapter.npz") as w:
        curve, n = adapter_outputs(vx.numpy(), vc[:, 0].numpy(), w)
    # Recompute when no cached predictions are supplied; cache identity is checked below.
    baseline_cache = a.data / "val-baseline.jsonl"
    if baseline_cache.is_file() and (a.data / "val-baseline.sha256").is_file():
        provenance = json.loads((a.data / "val-baseline.sha256").read_text())
        assert provenance == {
            "model": sha256(a.base / "model.json"),
            "rows": sha256(baseline_cache),
        }
        by_key = dict(map(json.loads, baseline_cache.read_text().splitlines()))
        baseline = [by_key[k] for k in keys]
    else:
        model = PeakSpectrumPredictor(a.base)
        baseline = [model.predict(panel[k][0])["prediction_ppm"] for k in keys]
    previous = metrics(baseline, ys)
    grid = []
    for weight in (0.0, 0.25, 0.5, 0.75, 1.0):
        for snap in (0.0, 0.10, 0.25):
            predictions = [
                decode(c, k, b, weight, snap) for c, k, b in zip(curve, n, baseline)
            ]
            grid.append(dict(weight=weight, snap=snap, **metrics(predictions, ys)))
    acceptable = [choice for choice in grid if choice["cosine"] >= previous["cosine"]]
    chosen = min(acceptable or grid, key=lambda r: (r["error"], -r["cosine"]))
    if chosen["weight"] or chosen["snap"]:
        shutil.copytree(a.base, a.out / "released")
    source = a.base / "peak-learning/environments.json.gz"
    shutil.copyfile(source, a.out / source.name)
    config = dict(
        engine="nmrgym_proton_residual_v1",
        nucleus="1H",
        seed=seed,
        released_model_sha256=sha256(a.base / "model.json"),
        environment_sha256=sha256(source),
        adapter_sha256=sha256(a.out / "adapter.npz"),
        released_peak_weight=chosen["weight"],
        snap_radius_ppm=chosen["snap"],
    )
    (a.out / "model.json").write_text(json.dumps(config, indent=2) + "\n")
    report = dict(
        training_molecules=len(x),
        validation_molecules=len(ys),
        split=json.loads((a.data / "split.json").read_text()),
        backbone="Frozen released proton environment estimates & rooted Morgan counts; trained residual shift and peak-count heads.",
        seed=seed,
        epochs=len(history),
        best_epoch=best_epoch,
        history=history,
        selection="Checkpoint with lowest validation count-penalized error. Select decoding on validation by lowest error among candidates reaching released cosine, or lowest error if none qualify.",
        validation_baseline=previous,
        validation_grid=grid,
        selected=chosen,
        model_sha256=sha256(a.out / "model.json"),
    )
    (a.out / "training.json").write_text(json.dumps(report, indent=2) + "\n")
    print("selected", chosen, "baseline", previous, flush=True)


if __name__ == "__main__":
    main()
