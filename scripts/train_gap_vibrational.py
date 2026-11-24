"""Train vibrational-only gap regressors on a new connectivity-disjoint development split."""

import argparse
import hashlib
import json
from pathlib import Path
import pickle
import numpy as np
from rdkit import Chem
from scipy.linalg import solve
from openmolspec_bench.data import readonly_lmdb, sha256
from openmolspec_ui.gap_partial import design, spectral_features


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("lmdb", "original", "weights", "report"):
        p.add_argument("--" + arg, type=Path, required=True)
    a = p.parse_args()
    previous = json.loads(a.original.read_text())["results"][0]
    old_ids = set(previous["sample_ids"])
    env = readonly_lmdb(a.lmdb)
    cache = {}
    data = {}
    forced_test = set()
    old_rows = []
    with env.begin() as tx:
        for _, blob in tx.cursor():
            r = pickle.loads(blob)
            if r.get("gap") is None:
                continue
            smiles = r["kekule_smiles"]
            if smiles not in cache:
                cache[smiles] = Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)).split(
                    "-"
                )[0]
            key = cache[smiles]
            if not key:
                raise ValueError(smiles)
            row = (
                r["ir"],
                r["raman"],
                float(r["gap"]) * 27.211386245988,
                r["sample_id"],
            )
            if key not in data:
                data[key] = row
            if r["sample_id"] in old_ids:
                forced_test.add(key)
                old_rows.append(row)
    env.close()
    if {r[-1] for r in old_rows} != old_ids:
        raise ValueError("Legacy test mismatch")
    keys = sorted(data)
    roles = []
    for key in keys:
        bucket = (
            int.from_bytes(
                hashlib.sha256(("gap-v1:" + key).encode()).digest()[:4], "big"
            )
            % 10
        )
        roles.append(
            "prior"
            if key in forced_test
            else "test"
            if bucket < 2
            else "val"
            if bucket == 2
            else "train"
        )
    rows = [data[k] for k in keys] + old_rows
    roles = np.array(roles + ["replay"] * len(old_rows))
    target = np.array([r[2] for r in rows])
    features = [spectral_features([r[j] for r in rows]) for j in range(2)]
    train, val = roles == "train", roles == "val"
    rng = np.random.default_rng(913)
    ai = rng.choice(np.where(train)[0], 768, replace=False)
    model = {
        "fit_keys": np.array(
            [k for k, role in zip(keys, roles) if role in ("train", "val")]
        ),
        "training_mean_ev": np.float64(target[train].mean()),
    }
    report = dict(
        split="New adaptation split of the packaged theoretical test LMDB, grouped by InChI connectivity. Historical 128 reserved for replay only.",
        source_sha256=sha256(a.lmdb),
        unit="eV",
        training_mean_ev=float(target[train].mean()),
        counts={r: int(np.sum(roles == r)) for r in np.unique(roles)},
        rows={},
        models={},
    )
    for role in ("train", "val", "test", "replay"):
        report["rows"][role] = [
            r[3] for r, selected in zip(rows, roles == role) if selected
        ]
    for mode, parts in (("ir", [0]), ("raman", [1]), ("ir_raman", [0, 1])):
        x = np.concatenate([features[j] for j in parts], axis=1) / np.sqrt(
            np.float32(len(parts))
        )
        anchors = x[ai]
        f = design(x, anchors).astype(np.float64)
        mu, ym = f[train].mean(axis=0), target[train].mean()
        ft = f[train] - mu
        A = ft.T @ ft
        b = ft.T @ (target[train] - ym)
        candidates = []
        for reg in (0.03, 0.3, 3.0, 30.0):
            M = A.copy()
            M.flat[:: len(M) + 1] += reg
            beta = solve(M, b, assume_a="pos")
            bias = ym - mu @ beta
            candidates.append(
                (np.mean(abs(f[val] @ beta + bias - target[val])), reg, beta, bias)
            )
        loss, reg, beta, bias = min(candidates, key=lambda v: v[0])
        model.update(
            {
                mode + "_anchors": anchors,
                mode + "_beta": beta.astype(np.float32),
                mode + "_bias": np.float32(bias),
            }
        )
        prediction = f @ model[mode + "_beta"] + model[mode + "_bias"]
        summary = dict(ridge=reg, validation_mae_ev=float(loss))
        for role in ("test", "replay"):
            ix = roles == role
            summary[role] = dict(
                mae_ev=float(np.mean(abs(prediction[ix] - target[ix]))),
                mean_baseline_mae_ev=float(np.mean(abs(ym - target[ix]))),
                predictions_ev=prediction[ix].tolist(),
                reference_ev=target[ix].tolist(),
            )
        report["models"][mode] = summary
        print(
            mode,
            reg,
            summary["test"]["mae_ev"],
            summary["replay"]["mae_ev"],
            flush=True,
        )
    np.savez_compressed(a.weights, **model)
    report["weights_sha256"] = sha256(a.weights)
    a.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
