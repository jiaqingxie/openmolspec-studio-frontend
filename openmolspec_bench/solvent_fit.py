"""Fit H/C solvent shift corrections and evaluate them by held-out molecular connectivity."""

import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np

from .solvent_transfer import solvent
from .data import sha256


def design(nucleus, source, target, ppm, solvents):
    # A solvent-specific offset and slope share information between solvent pairs.
    scale = 10.0 if nucleus == "1H" else 200.0
    v = np.zeros(len(solvents))
    v[solvents.index(source)] -= 1
    v[solvents.index(target)] += 1
    return np.concatenate((v, v * (ppm / scale)))


def fit(rows, solvents):
    groups = Counter(r["smiles"] for r in rows)
    x, y, w = [], [], []
    for r in rows:
        for a, b in [("source", "target"), ("target", "source")]:
            ppm = r[a]["shift_ppm"]
            x.append(
                design(
                    r["nucleus"], r[a + "_solvent"], r[b + "_solvent"], ppm, solvents
                )
            )
            y.append(r[b]["shift_ppm"] - ppm)
            w.append(0.5 / groups[r["smiles"]])
    x, y, w = np.asarray(x), np.asarray(y), np.asarray(w)
    return np.linalg.solve((x.T * w) @ x + np.eye(x.shape[1]), (x.T * w) @ y).tolist()


def predict(model, nucleus, source_solvent, target_solvent, source_ppm):
    solvents = model["solvents"][nucleus]
    source, target = solvent(source_solvent), solvent(target_solvent)
    if (
        source == target
        or source not in solvents
        or target not in solvents
        or not np.isfinite(source_ppm)
    ):
        raise ValueError(
            "Supply two distinct fitted solvents and a finite source shift"
        )
    delta = float(
        design(nucleus, source, target, source_ppm, solvents)
        @ model["coefficients"][nucleus]
    )
    return dict(
        nucleus=nucleus,
        predicted_delta_ppm=delta,
        predicted_target_ppm=source_ppm + delta,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("library", "baseline", "report", "weights"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    pairs = json.loads(a.library.read_text())["pairs"]
    baseline = json.loads(a.baseline.read_text())
    if baseline["library"]["sha256"] != sha256(a.library):
        raise ValueError("Reference library differs from the evaluated baseline")
    model = {
        "method": "ridge_solvent_difference_v1",
        "solvents": {},
        "coefficients": {},
        "library_sha256": sha256(a.library),
    }
    report = {
        "protocol": "Leave one molecular connectivity out of all fitted coefficients. Ridge penalty 1, equal total weight per molecule. Score the same oriented peaks as the frozen baseline.",
        "metrics": {},
        "records": [],
    }
    for nucleus in ("1H", "13C"):
        rows = [r for r in pairs if r["nucleus"] == nucleus]
        solvents = sorted(
            {r[k + "_solvent"] for r in rows for k in ("source", "target")}
        )
        model["solvents"][nucleus] = solvents
        references = [r for r in baseline["records"] if r["nucleus"] == nucleus]
        errors = []
        for key in sorted({r["query_connectivity"] for r in references}):
            train = [r for r in rows if r["smiles"] != key]
            model["coefficients"][nucleus] = fit(train, solvents)
            for r in (r for r in references if r["query_connectivity"] == key):
                prediction = predict(
                    model,
                    nucleus,
                    r["source_solvent"],
                    r["target_solvent"],
                    r["source_ppm"],
                )
                truth = r["target_reference_ppm"]
                errors.append(
                    [
                        abs(x - truth)
                        for x in (
                            prediction["predicted_target_ppm"],
                            r["predicted_target_ppm"],
                            r["source_ppm"],
                        )
                    ]
                )
                report["records"].append(
                    dict(connectivity=key, truth_ppm=truth, **prediction)
                )
        mean = np.mean(errors, axis=0)
        report["metrics"][nucleus] = dict(
            atoms=len(errors),
            fit_mae_ppm=mean[0],
            retrieval_mae_ppm=mean[1],
            unchanged_mae_ppm=mean[2],
        )
        model["coefficients"][nucleus] = fit(rows, solvents)
    a.weights.write_text(json.dumps(model, indent=2) + "\n")
    report["full_fit_sha256"] = sha256(a.weights)
    a.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
