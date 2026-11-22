"""Replay the released NMRGym v2 optimization budget on a specified training cache."""

import argparse
from pathlib import Path
import json
import shutil
import tempfile

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from scipy.optimize import linear_sum_assignment

from openmolspec.nmrgym_proton import FP_SIZE, GRID, adapter_outputs, decode, resample
from openmolspec_bench.data import sha256
from openmolspec_bench.peak_evaluation import matching_errors
from refine_nmrgym_proton_cosine import profile_loss
from train_nmrgym_proton import export, load

N = len(GRID)


def network(dim, checkpoint=None):
    net = nn.Sequential(
        nn.Linear(dim, 192),
        nn.ReLU(),
        nn.Linear(192, 128),
        nn.ReLU(),
        nn.Linear(128, N + 1),
    )
    if checkpoint:
        with np.load(checkpoint) as weights, torch.no_grad():
            names = ("w1", "b1", "w2", "b2", "out", "bias")
            for param, name in zip(net.parameters(), names, strict=True):
                param.copy_(torch.from_numpy(weights[name]))
    return net


def update(net, optimizer, loss, clip):
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    nn.utils.clip_grad_norm_(net.parameters(), clip)
    optimizer.step()


def lower_lr(optimizer):
    for group in optimizer.param_groups:
        group["lr"] *= 0.5


def initial_fit(data, parent, cfg, stage):
    torch.manual_seed(parent["seed"])
    x, ref, counts = load(data, "train", cfg["released_model_sha256"])
    vx, _, vc = load(data, "val", cfg["released_model_sha256"])
    val_by_key = {
        k: y
        for k, _, y in map(json.loads, (data / "val.jsonl").read_text().splitlines())
    }
    ys = [val_by_key[k] for k in np.load(data / "val-keys.npy").astype(str)]
    net = network(x.shape[1])
    nn.init.zeros_(net[-1].weight)
    nn.init.zeros_(net[-1].bias)
    optimizer = torch.optim.AdamW(net.parameters(), lr=0.0015, weight_decay=0.001)
    target_count = torch.log(counts[:, 1] / counts[:, 0])
    residual = ref - x[:, -3 * N : -2 * N]
    history = []
    best_parent = float("inf")
    for original in parent["history"][: parent["best_epoch"]]:
        epoch = original["epoch"]
        total = 0.0
        for ix in torch.randperm(len(x)).split(512):
            output = net(x[ix])
            loss = F.smooth_l1_loss(
                output[:, :-1], residual[ix], beta=0.25
            ) + 1.5 * F.smooth_l1_loss(output[:, -1], target_count[ix], beta=0.15)
            update(net, optimizer, loss, 3.0)
            total += loss.detach().item() * len(ix)
        curves, n = adapter_outputs(vx.numpy(), vc[:, 0].numpy(), export(net))
        error = matching_errors(
            [decode(c, k, [], 0.0) for c, k in zip(curves, n)], ys, 1.0
        ).mean()
        history.append(
            dict(
                epoch=epoch,
                lr=optimizer.param_groups[0]["lr"],
                loss=total / len(x),
                validation_error_ppm=float(error),
            )
        )
        print("initial", history[-1], flush=True)
        # Match the learning rates actually used to fit the v2 checkpoint.
        if original["validation_error_ppm"] < best_parent:
            best_parent = original["validation_error_ppm"]
            best_epoch = epoch
        if epoch - best_epoch in (3, 6):
            lower_lr(optimizer)
    np.savez_compressed(stage / "initial.npz", **export(net))
    return history


def sorted_labels(data, keys, cap=None):
    by_key = {k: i for i, k in enumerate(keys)}
    arrays = [None] * len(keys)
    with (data / "train.jsonl").open() as stream:
        for line in stream:
            key, _, peaks = json.loads(line)
            if key in by_key:
                values = (
                    resample(peaks, cap) if cap and len(peaks) > cap else np.sort(peaks)
                )
                arrays[by_key[key]] = np.asarray(values, dtype="f4")
    return [torch.from_numpy(v) for v in arrays]


def cosine_fit(data, parent, cfg, stage):
    fit = parent["cosine_refinement"]
    torch.manual_seed(fit["seed"])
    x, ref, counts = load(data, "train", cfg["released_model_sha256"])
    selected = torch.randperm(len(x))[: fit["train_molecules"]]
    keys = np.load(data / "train-keys.npy")[selected.numpy()].astype(str)
    labels = sorted_labels(data, keys, cap=64)
    ny = torch.tensor([len(v) for v in labels], dtype=torch.long)
    raw = torch.nn.utils.rnn.pad_sequence(labels, batch_first=True)
    x, ref, counts = x[selected], ref[selected], counts[selected]
    net = network(x.shape[1], stage / "initial.npz")
    opt = torch.optim.AdamW(net.parameters(), lr=0.00025, weight_decay=0.001)
    target_count = torch.log(counts[:, 1] / counts[:, 0])
    base = x[:, -3 * N : -2 * N]
    history = []
    for epoch in range(1, fit["chosen"]["epoch"] + 1):
        width = 0.10 if epoch <= 2 else 0.05
        if epoch == 7:
            lower_lr(opt)
        total = 0.0
        for block in torch.randperm(len(x)).split(1024):
            for ix in block[torch.argsort(ny[block])].split(128):
                output = net(x[ix])
                curves = base[ix] + output[:, :-1]
                n = torch.round(
                    counts[ix, 0] * output[:, -1].detach().clamp(-4, 4).exp()
                ).long()
                loss = (
                    profile_loss(curves, n, raw[ix], ny[ix], width)
                    + 0.30 * F.smooth_l1_loss(curves, ref[ix], beta=0.25)
                    + 0.8 * F.smooth_l1_loss(output[:, -1], target_count[ix], beta=0.15)
                )
                update(net, opt, loss, 1.0)
                total += loss.detach().item() * len(ix)
        history.append(dict(epoch=epoch, loss=total / len(x)))
        print("cosine", history[-1], flush=True)
    np.savez_compressed(stage / "adapter.npz", **export(net))
    return history


def overlap(a, b, ma, mb):
    kernel = (1 + ((a[:, :, None] - b[:, None, :]) / 0.05).square()).reciprocal()
    return (kernel * ma[:, :, None] * mb[:, None, :]).sum((1, 2))


def position_loss(curves, n, obs, ny):
    rank = torch.arange(int(n.max()))[None, :]
    q = (rank * (N - 1) / (n[:, None] - 1).clamp(min=1)).clamp(0, N - 1)
    q = torch.where(n[:, None] == 1, (N - 1) / 2, q)
    lo = q.long()
    p = torch.lerp(
        curves.gather(1, lo), curves.gather(1, (lo + 1).clamp(max=N - 1)), q - lo
    )
    pm = rank < n[:, None]
    om = torch.arange(obs.shape[1])[None, :] < ny[:, None]
    cos = (
        overlap(p, obs, pm, om)
        / (overlap(p, p, pm, pm) * overlap(obs, obs, om, om)).sqrt()
    )
    dist = (p[:, :, None] - obs[:, None, :]).abs()
    costs = dist.detach().numpy()
    bi, pi, oi = [], [], []
    for j, (npred, nref) in enumerate(zip(n.tolist(), ny.tolist())):
        i, k = linear_sum_assignment(costs[j, :npred, :nref])
        bi.extend([j] * len(i))
        pi.extend(i)
        oi.extend(k)
    jj = torch.as_tensor(bi)
    matched = (
        dist[jj, np.asarray(pi), np.asarray(oi)] / torch.minimum(n, ny)[jj]
    ).sum() / len(n)
    return (1 - cos).mean() + 0.9 * matched


def position_fit(data, parent, cfg, stage):
    fit = parent["matched_position_training"]
    torch.set_num_threads(2)
    torch.manual_seed(fit["seed"])
    x, ref, counts = load(data, "train", cfg["released_model_sha256"])
    del ref
    raw = sorted_labels(data, np.load(data / "train-keys.npy").astype(str))
    ny = torch.tensor([len(v) for v in raw], dtype=torch.long)
    with np.load(stage / "adapter.npz") as f:
        w = dict(f)
    pn = torch.from_numpy(
        np.concatenate(
            [
                adapter_outputs(
                    x[i : i + 1024].numpy(), counts[i : i + 1024, 0].numpy(), w
                )[1]
                for i in range(0, len(x), 1024)
            ]
        )
    )
    net = network(x.shape[1], stage / "adapter.npz")
    opt = torch.optim.AdamW(net.parameters(), lr=0.00018, weight_decay=0.001)
    history = []
    state_path = stage / "position-progress.pt"
    if state_path.is_file():
        state = torch.load(state_path, map_location="cpu", weights_only=True)
        net.load_state_dict(state["network"])
        opt.load_state_dict(state["optimizer"])
        torch.set_rng_state(state["rng"])
        history, chunks = state["history"], state["chunks"]
    for epoch in range(len(history) + 1, fit["best_epoch"] + 1):
        if epoch == 7:
            lower_lr(opt)
        if (epoch - 1) % 3 == 0:
            chunks = torch.randperm(len(x)).tensor_split(3)
        ids = chunks[(epoch - 1) % 3]
        total = 0.0
        for block in ids.split(1024):
            for ix in block[torch.argsort(torch.maximum(ny[block], pn[block]))].split(
                96
            ):
                # Long spectra need quadratic pair matrices. Accumulate all
                # molecule-weighted gradients before the original optimizer step.
                max_peaks = int(torch.maximum(ny[ix], pn[ix]).max())
                step = max(1, 800_000 // max_peaks**2)
                opt.zero_grad(set_to_none=True)
                for part in ix.split(step):
                    xb = x[part]
                    curves = (
                        (xb[:, -3 * N : -2 * N] + net(xb)[:, :N]).sort(dim=1).values
                    )
                    obs = torch.nn.utils.rnn.pad_sequence(
                        [raw[i] for i in part.tolist()], batch_first=True
                    )
                    loss = position_loss(curves, pn[part], obs, ny[part])
                    (loss * (len(part) / len(ix))).backward()
                    total += loss.detach().item() * len(part)
                nn.utils.clip_grad_norm_(net.parameters(), 1.0)
                opt.step()
        history.append(dict(epoch=epoch, loss=total / len(ids)))
        torch.save(
            dict(
                network=net.state_dict(),
                optimizer=opt.state_dict(),
                rng=torch.get_rng_state(),
                history=history,
                chunks=chunks,
            ),
            state_path.with_suffix(".partial"),
        )
        state_path.with_suffix(".partial").replace(state_path)
        print("positions", history[-1], flush=True)
    np.savez_compressed(stage / "positions.npz", **export(net))
    state_path.unlink()
    return history


def build_library(data, stage):
    x = np.load(data / "train-x.npy")
    words = np.ascontiguousarray(np.packbits(x[:, :FP_SIZE] > 0, axis=1)).view(
        np.uint64
    )
    del x
    keys = np.load(data / "train-keys.npy").astype(str)
    idx = {k: i for i, k in enumerate(keys)}
    refs = [None] * len(keys)
    with (data / "train.jsonl").open() as stream:
        for l in stream:
            k, _, y = json.loads(l)
            refs[idx[k]] = np.sort(y).astype("f4")
    ends = np.r_[0, np.cumsum([len(y) for y in refs])].astype("i4")
    np.savez_compressed(
        stage / "library.npz", words=words, ends=ends, ppm=np.concatenate(refs)
    )


def finish(a, parent, cfg, stage, h1, h2):
    h3 = position_fit(a.data, parent, cfg, stage)
    build_library(a.data, stage)
    (stage / "initial.npz").unlink()
    shutil.copyfile(a.v2 / "environments.json.gz", stage / "environments.json.gz")
    cfg["engine"] = "nmrgym_proton_precision_clean_v1"
    cfg["adapter_sha256"] = sha256(stage / "adapter.npz")
    cfg["position_sha256"] = sha256(stage / "positions.npz")
    cfg["training_analogs"]["sha256"] = sha256(stage / "library.npz")
    (stage / "model.json").write_text(json.dumps(cfg, indent=2) + "\n")
    report = dict(
        control_model_sha256=parent["model_sha256"],
        model_sha256=sha256(stage / "model.json"),
        cleaning=json.loads((a.data / "cleaning.json").read_text()),
        seeds=[
            parent["seed"],
            parent["cosine_refinement"]["seed"],
            parent["matched_position_training"]["seed"],
        ],
        initial=h1,
        cosine=h2,
        positions=h3,
        protocol="Fresh specialist weights; same frozen generic environment model, v2 architecture, optimizer settings, parent learning-rate schedule and selected epoch budgets. Analogs rebuilt from the retained training spectra.",
    )
    (stage / "training.json").write_text(json.dumps(report, indent=2) + "\n")
    stage.rename(a.out)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", required=True, type=Path)
    p.add_argument("--v2", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    torch.set_num_threads(3)
    torch.set_num_interop_threads(1)
    cfg = json.loads((a.v2 / "model.json").read_text())
    parent = json.loads((a.v2 / "training.json").read_text())
    if (
        sha256(a.v2 / "model.json") != parent["model_sha256"]
        or sha256(a.v2 / "environments.json.gz") != cfg["environment_sha256"]
    ):
        raise ValueError("Unrecognized v2 model or backbone")
    a.out.parent.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory(dir=a.out.parent) as tmp:
        stage = Path(tmp) / "model"
        stage.mkdir()
        h1 = initial_fit(a.data, parent, cfg, stage)
        h2 = cosine_fit(a.data, parent, cfg, stage)
        finish(a, parent, cfg, stage, h1, h2)


if __name__ == "__main__":
    main()
