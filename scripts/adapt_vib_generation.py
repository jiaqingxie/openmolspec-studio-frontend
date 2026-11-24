"""Fit a vibrational-to-shift adapter for the frozen four-channel structure decoder."""

import argparse
import hashlib
import json
from pathlib import Path
import pickle
import numpy as np
from rdkit import Chem
from scipy.linalg import solve
from openmolspec_ui.gap_partial import design, spectral_features
from openmolspec_bench.data import readonly_lmdb, sha256

QUANTILES = (np.arange(32) + 0.5) / 32


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("lmdb", "previous", "weights", "report"):
        parser.add_argument("--" + k, type=Path, required=True)
    parser.add_argument("--fit-index", type=Path, help="Save the train/validation connectivity keys for benchmark exclusion")
    a = parser.parse_args()
    legacy = json.loads(a.previous.read_text())["results"]
    historical = {s for r in legacy for s in r.get("sample_ids", [])}
    env = readonly_lmdb(a.lmdb)
    pool = {}
    with env.begin() as tx:
        for key, raw in tx.cursor():
            r = pickle.loads(raw)
            m = Chem.MolFromSmiles(r["kekule_smiles"])
            s = Chem.MolToSmiles(m, isomericSmiles=False)
            h = np.asarray(r["nmr_h_shifts_ppm"])
            c = np.asarray(r["nmr_c_shifts_ppm"])
            if not len(h) or not len(c) or s in pool:
                continue
            y = np.r_[
                np.log1p(len(h)),
                np.quantile(h, QUANTILES),
                np.log1p(len(c)),
                np.quantile(c, QUANTILES),
            ]
            pool[s] = (Chem.MolToInchiKey(m).split("-")[0], r["ir"], r["raman"], y)
    env.close()
    historical = {
        Chem.MolToSmiles(Chem.MolFromSmiles(s), isomericSmiles=False)
        for s in historical
    }
    ordered = sorted(
        set(pool) - historical,
        key=lambda s: hashlib.sha256(("vib-gen-check-v1:" + s).encode()).digest(),
    )
    # Reserve a larger prefix than the generation benchmark, including any duplicate connectivity.
    protected = {pool[s][0] for s in set(ordered[:150]) | historical if s in pool}
    keys = sorted(pool)
    used = set()
    samples = []
    roles = []
    for s in keys:
        r = pool[s]
        if r[0] in protected or r[0] in used:
            continue
        used.add(r[0])
        bucket = (
            int.from_bytes(
                hashlib.sha256(("vib-adapter-v1:" + r[0]).encode()).digest()[:4], "big"
            )
            % 10
        )
        samples.append(r)
        roles.append("test" if bucket < 2 else "val" if bucket == 2 else "train")
    x = np.concatenate(
        [spectral_features([r[i] for r in samples]) for i in (1, 2)], axis=1
    ) / np.sqrt(np.float32(2))
    y = np.stack([r[3] for r in samples])
    roles = np.array(roles)
    tr = roles == "train"
    va = roles == "val"
    te = roles == "test"
    anchors = x[np.random.default_rng(42).choice(np.where(tr)[0], 768, replace=False)]
    f = design(x, anchors).astype("d")
    mu = f[tr].mean(axis=0)
    ym = y[tr].mean(axis=0)
    sd = np.maximum(y[tr].std(axis=0), 1e-8)
    a0 = (f[tr] - mu).T @ (f[tr] - mu)
    b = (f[tr] - mu).T @ (y[tr] - ym)
    candidates = []
    for lam in (0.03, 0.3, 3.0):
        m = a0.copy()
        m.flat[:: 1 + len(m)] += lam
        coef = solve(m, b, assume_a="pos")
        bias = ym - mu @ coef
        candidates.append(
            (np.mean(abs((f[va] @ coef + bias - y[va]) / sd)), lam, coef, bias)
        )
    validation, lam, coef, bias = min(candidates, key=lambda r: r[0])
    yhat = f[te] @ coef + bias
    np.savez_compressed(
        a.weights,
        anchors=anchors,
        coef=coef.astype("f"),
        bias=bias.astype("f"),
        grid=QUANTILES,
    )
    report = dict(
        adapter="Kernel ridge predicts sorted H/C shift quantiles and counts from the two measured vibrational channels; decoder is frozen. No formula or measured H/C at inference.",
        split="Separate connectivity-grouped adaptation split of the packaged release LMDB",
        lmdb_sha256=sha256(a.lmdb),
        weights_sha256=sha256(a.weights),
        protected_connectivities=sorted(protected),
        validation_standardized_mae=float(validation),
        ridge=lam,
        counts={r: int((roles == r).sum()) for r in ("train", "val", "test")},
        test_shift_quantile_mae_ppm={
            "1H": float(np.mean(abs(yhat[:, 1:33] - y[te, 1:33]))),
            "13C": float(np.mean(abs(yhat[:, 34:] - y[te, 34:]))),
        },
    )
    a.report.write_text(json.dumps(report, indent=2) + "\n")
    if a.fit_index:
        index = {role: sorted(s[0] for s, r in zip(samples, roles) if r == role)
                 for role in ("train", "val")}
        index["weights_sha256"] = report["weights_sha256"]
        a.fit_index.write_text(json.dumps(index, separators=(",", ":")) + "\n")
    print(
        {k: v for k, v in report.items() if k not in ["protected_connectivities"]},
        flush=True,
    )


if __name__ == "__main__":
    main()
