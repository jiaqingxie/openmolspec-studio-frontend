"""Freeze GLACIER/ICEBERG calibration on validation and confirm on additional test structures."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from openmolspec_bench.data import sha256
from openmolspec_bench.ms import spectrum_metrics, calibrated_peaks, calibration_group
from select_ms_calibration import BASE, GRID, paired, cosine_curve



def fit(data, scores, indices, kind, strength):
    global_scores = scores[indices].mean(axis=0)
    fallback = int(np.argmax(global_scores))
    groups = {}
    if kind != "global":
        for i in indices:
            groups.setdefault(calibration_group(data[i][-1], kind), []).append(i)
    choices = {}
    for key, group in groups.items():
        regularized = scores[group].sum(axis=0) + strength * global_scores
        choices[key] = int(np.argmax(regularized))
    return fallback, choices


def freeze(args):
    path = args.cache / (args.model + "-val.jsonl.gz")
    data, counts, manifest = paired(path)
    values = cosine_curve(data, GRID)
    # Splits are determined only by connectivity and cover the whole validation set.
    folds = np.array(
        [int(hashlib.sha256(r[0].encode()).hexdigest()[:8], 16) % 5 for r in data]
    )
    candidates = [("incumbent", 0), ("global", 0)]
    for kind in ("instrument", "energy", "instrument_energy"):
        candidates.extend((kind, strength) for strength in (12, 48, 144))
    rank = []
    for kind, strength in candidates:
        pred = values[:, GRID.index(BASE)].copy()
        if kind != "incumbent":
            for fold in range(5):
                ids = np.flatnonzero(folds != fold)
                fallback, mapping = fit(data, values, ids, kind, strength)
                for i in np.flatnonzero(folds == fold):
                    selected = mapping.get(calibration_group(data[i][-1], kind), fallback)
                    pred[i] = values[i, selected]
        rank.append(
            dict(kind=kind, prior_count=strength, out_of_fold_cosine=float(pred.mean()))
        )
    best = max(rank, key=lambda r: r["out_of_fold_cosine"])
    kind = best["kind"]
    if kind == "incumbent":
        fallback, choices = GRID.index(BASE), {}
    else:
        fallback, choices = fit(
            data, values, np.arange(len(data)), kind, best["prior_count"]
        )
    with (args.cache / (args.model + "-test-sample.csv")).open() as file:
        import csv

        used = sorted(row["spec_id"] for row in csv.DictReader(file))
    if len(set(used)) != 384:
        raise ValueError("Expected the 384 original held-out spectrum IDs")
    plan = dict(
        model=args.model,
        checkpoints=manifest["checkpoints"],
        validation_counts=counts,
        validation_cache_sha256=sha256(path),
        validation_cvs=rank,
        validation_identities=sorted(row[0] for row in data),
        kind=kind,
        prior_count=best["prior_count"],
        fallback=GRID[fallback],
        settings={key: GRID[i] for key, i in choices.items()},
        excluded_original_test=used,
        confirmation_sample_size=1024,
        criterion="Molecule-averaged cosine, promotion requires lower paired 95% interval above zero on new test identities.",
    )
    args.plan.write_text(json.dumps(plan, indent=2, allow_nan=False) + "\n")
    print(
        args.model,
        kind,
        best["out_of_fold_cosine"],
        "fallback",
        GRID[fallback],
        "settings",
        plan["settings"],
        flush=True,
    )


def confirm(args):
    plan = json.loads(args.plan.read_text())
    if plan["model"] != args.model:
        raise ValueError("Model mismatch")
    fresh, counts, meta = paired(args.confirmation / (args.model + "-test.jsonl.gz"))
    if (
        meta["identities_sampled"]
        != len(plan["excluded_original_test"]) + plan["confirmation_sample_size"]
    ):
        raise ValueError("Incomplete expanded test sample")
    if meta["checkpoints"] != plan["checkpoints"]:
        raise ValueError("Checkpoint mismatch")
    old = set(plan["excluded_original_test"])
    fresh = [r for r in fresh if r[-1]["spec_id"] not in old]
    keys = [r[0] for r in fresh]
    if len(set(keys)) != len(keys) or set(keys) & set(plan["validation_identities"]):
        raise ValueError("Overlap or duplicate in independent confirmation set")
    baseline, tuned = [], []
    for r in fresh:
        row = r[-1]
        setting = plan["settings"].get(calibration_group(row, plan["kind"]), plan["fallback"])
        for out, config in ((baseline, BASE), (tuned, setting)):
            peaks = calibrated_peaks(
                row["predicted_peaks"], row["precursor_mz"], *config
            )
            out.append(spectrum_metrics(peaks, row["reference_peaks"]))

    def means(rows):
        return {k: float(np.mean([r[k] for r in rows])) for k in rows[0]}

    delta = np.array(
        [
            t["cosine_similarity"] - b["cosine_similarity"]
            for t, b in zip(tuned, baseline)
        ]
    )
    ci = np.percentile(
        np.random.default_rng(97861).choice(delta, (5000, len(delta))).mean(1),
        [2.5, 97.5],
    ).tolist()
    report = dict(
        model=args.model,
        validation_plan_sha256=sha256(args.plan),
        checkpoints=plan["checkpoints"],
        validation=plan["validation_counts"],
        validation_cvs=plan["validation_cvs"],
        original_test_removed=len(old),
        confirmation_sample_size=plan["confirmation_sample_size"],
        confirmed_identities=len(keys),
        skipped=plan["confirmation_sample_size"] - len(keys),
        audited_ids_sha256=hashlib.sha256("\n".join(sorted(keys)).encode()).hexdigest(),
        source_prediction_sha256=meta["output_sha256"],
        baseline=means(baseline),
        candidate=means(tuned),
        cosine_difference_ci95=ci,
        selected_kind=plan["kind"],
        fallback=plan["fallback"],
        settings=plan["settings"],
        promoted=bool(ci[0] > 0),
    )
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        args.model,
        len(keys),
        report["baseline"]["cosine_similarity"],
        report["candidate"]["cosine_similarity"],
        ci,
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=("freeze", "confirm"))
    p.add_argument("--model", choices=("glacier", "iceberg"), required=True)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--confirmation", type=Path)
    p.add_argument("--report", type=Path)
    args = p.parse_args()
    if args.stage == "confirm" and not (args.confirmation and args.report):
        p.error(
            "Confirmation needs the expanded prediction directory and a report path"
        )
    (freeze if args.stage == "freeze" else confirm)(args)
