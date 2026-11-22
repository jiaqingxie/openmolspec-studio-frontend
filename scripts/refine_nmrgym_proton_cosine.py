"""Refine the validation-selected NMRGym model using differentiable peak-profile cosine."""

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
from openmolspec.nmrgym_proton import GRID, adapter_outputs, decode, resample
from openmolspec_bench.data import sha256
from train_nmrgym_proton import export, load, metrics


def profile_loss(curves, counts, observed, obs_counts, width):
    # Bound quadratic work for long spectra during fitting. Validation uses exact lists.
    cap = observed.shape[1]
    counts = counts.clamp(1, cap)
    positions = torch.arange(int(counts.max()))[None, :]
    where = (
        (len(GRID) - 1)
        * positions.to(curves.dtype)
        / (counts[:, None] - 1).clamp(min=1)
    )
    where = torch.where(counts[:, None] == 1, (len(GRID) - 1) * 0.5, where).clamp(
        0, len(GRID) - 1
    )
    curved = curves.sort(dim=1).values
    low = where.long()
    predicted = torch.lerp(
        curved.gather(1, low),
        curved.gather(1, (low + 1).clamp(max=len(GRID) - 1)),
        where - low,
    )
    pmask = positions < counts[:, None]
    obs = observed[:, : int(obs_counts.max())]
    omask = torch.arange(obs.shape[1])[None, :] < obs_counts[:, None]

    def overlap(a, b, ma, mb):
        k = (1 + ((a[:, :, None] - b[:, None, :]) / width).square()).reciprocal()
        return (k * ma[:, :, None] * mb[:, None, :]).sum((1, 2))

    numerator = overlap(predicted, obs, pmask, omask)
    denominator = (
        overlap(predicted, predicted, pmask, pmask) * overlap(obs, obs, omask, omask)
    ).sqrt()
    return (1 - numerator / denominator).mean()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--first", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    torch.set_num_threads(3)
    torch.set_num_interop_threads(1)
    seed = 714
    torch.manual_seed(seed)
    cfg = json.loads((args.first / "model.json").read_text())
    first = json.loads((args.first / "training.json").read_text())
    if cfg["released_peak_weight"] or cfg["snap_radius_ppm"]:
        raise ValueError(
            "This refinement starts from the neural decoder without released-peak blending"
        )
    x, ref, counts = load(args.data, "train", cfg["released_model_sha256"])
    vx, _, vc = load(args.data, "val", cfg["released_model_sha256"])
    # Fresh uniform sample without replacement from training identities, fixed before validation.
    chosen = torch.randperm(len(x))[:32768]
    keys = np.load(args.data / "train-keys.npy")[chosen.numpy()].astype(str)
    idx = {k: i for i, k in enumerate(keys)}
    raw = torch.zeros(len(keys), 64)
    obs_count = torch.zeros(len(keys), dtype=torch.long)
    with (args.data / "train.jsonl").open() as stream:
        for line in stream:
            key, _, peaks = json.loads(line)
            if key in idx:
                i = idx[key]
                vals = np.sort(peaks) if len(peaks) <= 64 else resample(peaks, 64)
                obs_count[i] = len(vals)
                raw[i, : len(vals)] = torch.from_numpy(vals)
    assert (obs_count > 0).all()
    x, ref, counts = x[chosen], ref[chosen], counts[chosen]
    vkeys = np.load(args.data / "val-keys.npy").astype(str)
    refs = {
        k: y
        for k, s, y in map(
            json.loads, (args.data / "val.jsonl").read_text().splitlines()
        )
    }
    ys = [refs[k] for k in vkeys]
    net = nn.Sequential(
        nn.Linear(x.shape[1], 192),
        nn.ReLU(),
        nn.Linear(192, 128),
        nn.ReLU(),
        nn.Linear(128, len(GRID) + 1),
    )
    with np.load(args.first / "adapter.npz") as initial, torch.no_grad():
        for param, k in zip(net.parameters(), ("w1", "b1", "w2", "b2", "out", "bias")):
            param.copy_(torch.from_numpy(initial[k]))
    opt = torch.optim.AdamW(net.parameters(), lr=0.00025, weight_decay=0.001)
    count_target = torch.log(counts[:, 1] / counts[:, 0])
    base = x[:, -3 * len(GRID) : -2 * len(GRID)]
    error_limit = first["selected"]["error"] + 0.01
    min_cosine = first["validation_baseline"]["cosine"]
    best = None
    history = []
    for epoch in range(1, 11):
        width = 0.10 if epoch <= 2 else 0.05
        if epoch == 7:
            for group in opt.param_groups:
                group["lr"] *= 0.5
        # Group by approximate spectrum size within randomized blocks to limit padding.
        for block in torch.randperm(len(x)).split(1024):
            for ix in block[torch.argsort(obs_count[block])].split(128):
                output = net(x[ix])
                curves = base[ix] + output[:, :-1]
                n = torch.round(
                    counts[ix, 0] * output[:, -1].detach().clamp(-4, 4).exp()
                ).long()
                loss = profile_loss(curves, n, raw[ix], obs_count[ix], width)
                loss = (
                    loss
                    + 0.30 * F.smooth_l1_loss(curves, ref[ix], beta=0.25)
                    + 0.8 * F.smooth_l1_loss(output[:, -1], count_target[ix], beta=0.15)
                )
                opt.zero_grad(set_to_none=True)
                loss.backward()
                nn.utils.clip_grad_norm_(net.parameters(), 1.0)
                opt.step()
        weights = export(net)
        curves, n = adapter_outputs(vx.numpy(), vc[:, 0].numpy(), weights)
        val = metrics([decode(c, k, [], 0) for c, k in zip(curves, n)], ys)
        history.append({"epoch": epoch, "training_width_ppm": width, **val})
        print(history[-1], flush=True)
        if (
            val["cosine"] >= min_cosine
            and val["error"] <= error_limit
            and (best is None or val["error"] < best["error"])
        ):
            best = history[-1]
            best_weights = weights
    # This script reads training and validation data only, including the selection criteria.
    with tempfile.TemporaryDirectory(dir=args.out.parent) as tmp:
        target = Path(tmp) / "model"
        target.mkdir()
        shutil.copyfile(
            args.first / "environments.json.gz", target / "environments.json.gz"
        )
        if best is None:
            shutil.copyfile(args.first / "adapter.npz", target / "adapter.npz")
        else:
            np.savez_compressed(target / "adapter.npz", **best_weights)
        cfg["adapter_sha256"] = sha256(target / "adapter.npz")
        (target / "model.json").write_text(json.dumps(cfg, indent=2) + "\n")
        first["model_sha256"] = sha256(target / "model.json")
        first["cosine_refinement"] = dict(
            seed=seed,
            train_molecules=len(x),
            validation_molecules=len(ys),
            epochs=history,
            source_adapter=sha256(args.first / "adapter.npz"),
            validation_error_limit=error_limit,
            validation_cosine_floor=min_cosine,
            chosen=best,
            selection="Lowest validation count-penalized error meeting both limits; otherwise retain phase one.",
        )
        (target / "training.json").write_text(json.dumps(first, indent=2) + "\n")
        target.rename(args.out)
    print("refinement chosen", best, flush=True)


if __name__ == "__main__":
    main()
