"""Select a peak-intensity calibration on MassSpecGym validation, then evaluate on a separate split."""

import argparse
from collections import Counter
import gzip
import itertools
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import numpy as np
from openmolspec_bench.ms import spectrum_metrics
from openmolspec_bench.data import sha256

BASE = (1.0, 1.0, 100)
GRID = list(
    itertools.product(
        (0.4, 0.55, 0.7, 0.85, 1.0, 1.2, 1.45, 1.75, 2.0),
        (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0),
        (20, 50, 100),
    )
)


def binned(peaks):
    peaks = np.array(peaks, dtype=float).reshape(-1, 2)
    idx = np.floor(peaks[:, 0] * (149999 / 1500.0)).astype(int) + 1
    valid = (idx >= 0) & (idx < 150000) & (peaks[:, 1] > 0)
    bins, rev = np.unique(idx[valid], return_inverse=True)
    v = np.zeros(len(bins))
    np.maximum.at(v, rev, peaks[valid, 1])
    return bins, v


def paired(path):
    manifest = json.loads(path.with_suffix(".manifest.json").read_text())
    if sha256(path) != manifest["output_sha256"]:
        raise ValueError("Prediction cache digest mismatch")
    with gzip.open(path, "rt") as f:
        rows = [json.loads(l) for l in f]
    data = []
    for r in rows:
        if r["status"] != "passed":
            continue
        ref, y = binned(r["reference_peaks"])
        bins, v = binned(r["predicted_peaks"])
        _, ix, iy = np.intersect1d(bins, ref, return_indices=True)
        matched = np.zeros(len(bins))
        matched[ix] = y[iy]
        mz = (bins - 0.5) * 1500 / 149999
        is_parent = abs(mz - r["precursor_mz"]) <= 0.02
        data.append((r["key"], v, matched, np.linalg.norm(y), is_parent, r))
    if not data:
        raise ValueError("Empty evaluation partition")
    return data, Counter(r["status"] for r in rows), manifest


def cosine_curve(data, candidates):
    scores = np.empty((len(data), len(candidates)))
    for i, (_, v, matched, norm, prec, _) in enumerate(data):
        for j, (power, parent, k) in enumerate(candidates):
            # Intensity power is monotone, so retaining the largest k per parent class is exact.
            if not len(v) or not norm:
                scores[i, j] = 0
                continue
            a = v**power
            a[prec] *= parent
            ix = np.argsort(-a, kind="stable")[:k] if len(a) > k else slice(None)
            den = np.linalg.norm(a[ix]) * norm
            scores[i, j] = a[ix] @ matched[ix] / den if den else 0.0
    return scores


def full_scores(data, setting):
    from openmolspec_bench.ms import calibrated_peaks

    scored = []
    for _, _, _, _, _, row in data:
        peaks = calibrated_peaks(row["predicted_peaks"], row["precursor_mz"], *setting)
        scored.append(spectrum_metrics(peaks, row["reference_peaks"]))
    return {k: float(np.mean([m[k] for m in scored])) for k in scored[0]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", choices=["glacier", "iceberg"], required=True)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    val, counts, manifest = paired(a.cache / (a.model + "-val.jsonl.gz"))
    matrix = cosine_curve(val, GRID)
    base = GRID.index(BASE)
    best = int(np.argmax(matrix.mean(axis=0)))
    # Three interleaved validation folds estimate generalization of parameter selection.
    split = np.arange(len(matrix)) % 3
    cross = matrix[:, base].copy()
    for i in range(3):
        mask = split == i
        opt = np.argmax(matrix[~mask].mean(axis=0))
        cross[mask] = matrix[mask, opt]
    if cross.mean() <= matrix[:, base].mean():
        best = base
    setting = GRID[best]
    report = dict(
        model=a.model,
        selection_metric="molecule-weighted validation cosine, top 100 predicted bins",
        checkpoints=manifest["checkpoints"],
        grid_size=len(GRID),
        selected=setting,
        validation_counts=counts,
        validation_cosine=float(matrix[:, best].mean()),
        baseline_validation_cosine=float(matrix[:, base].mean()),
        crossvalidated_selection_cosine=float(cross.mean()),
        validation_top=[
            dict(setting=GRID[idx], cosine=float(matrix[:, idx].mean()))
            for idx in np.argsort(-matrix.mean(axis=0))[:8]
        ],
    )
    a.output.write_text(json.dumps(report, indent=2) + "\n")
    print("Selected", setting, report["validation_cosine"], flush=True)
    test, counts, test_manifest = paired(a.cache / (a.model + "-test.jsonl.gz"))
    if {r[0] for r in test} & {r[0] for r in val} or test_manifest[
        "checkpoints"
    ] != manifest["checkpoints"]:
        raise ValueError("Validation/test connectivity or checkpoint mismatch")
    paired_scores = cosine_curve(test, [BASE, setting])
    difference = paired_scores[:, 1] - paired_scores[:, 0]
    rng = np.random.default_rng(4819)
    intervals = np.percentile(
        rng.choice(difference, size=(2000, len(test)), replace=True).mean(axis=1),
        [2.5, 97.5],
    ).tolist()
    baseline = full_scores(test, BASE)
    selected = full_scores(test, setting)
    for actual, expected in zip([baseline, selected], paired_scores.mean(axis=0)):
        np.testing.assert_allclose(
            actual["cosine_similarity"], expected, atol=1e-6, rtol=0
        )
    report.update(
        test_counts=counts,
        baseline_test=baseline,
        selected_test=selected,
        test_cosine_difference_ci95=intervals,
        deployment_setting=setting if intervals[0] > 0 else BASE,
        validation_test_overlap=0,
        validation_cache_sha256=manifest["output_sha256"],
        test_cache_sha256=test_manifest["output_sha256"],
    )
    a.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(selected, intervals, flush=True)


if __name__ == "__main__":
    main()
