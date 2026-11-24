"""Evaluate the source-repaired proton specialist on the two frozen NMRGym panels."""

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path

import numpy as np
from rdkit import RDLogger

from evaluate_nmrgym_proton import ROOT, scores
from openmolspec.nmrgym_proton import NMRGymProtonPredictor
from openmolspec_bench.data import sha256


def score_view(rows, reference, expected=None, external=()):
    eligible = [r for r in rows if r[reference] is not None]
    if expected is not None and len(eligible) != expected["molecules"]:
        raise ValueError("The fixed reference cohort changed")
    refs = [r[reference] for r in eligible]
    arrays = {}
    result = dict(molecules=len(refs), reference_peaks=sum(map(len, refs)))
    for model in ("v2", "v3", "v4", *external):
        result[model], arrays[model] = scores([r[model] for r in eligible], refs)
        if expected is not None and model in ("v2", "v3"):
            baseline = expected["v2" if model == "v2" else "clean"]
            for metric, value in baseline.items():
                if isinstance(value, (int, float)):
                    np.testing.assert_allclose(
                        result[model][metric], value, atol=1e-8, rtol=0
                    )

    indices = np.random.default_rng(843).integers(len(refs), size=(3000, len(refs)))
    for baseline in ("v2", "v3", *external):
        delta = {}
        for metric, values in arrays["v4"].items():
            difference = values - arrays[baseline][metric]
            delta[metric] = dict(
                mean=float(difference.mean()),
                ci95=np.percentile(
                    difference[indices].mean(axis=1), [2.5, 97.5]
                ).tolist(),
            )
        result["paired_v4_minus_" + baseline] = delta
    return result


def same_eligible_original(rows, expected, external=()):
    """Isolate label changes by keeping exactly the molecules with reviewed references."""
    eligible = [row for row in rows if row["reviewed_reference"] is not None]
    return score_view(eligible, "reference", expected, external)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--v2", type=Path, required=True)
    parser.add_argument("--v3", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    RDLogger.DisableLog("rdApp.*")
    baseline_path = ROOT / "results/nmrgym_proton_clean.json"
    audit_path = ROOT / "results/nmrgym_proton_reference_audit.json"
    baseline = json.loads(baseline_path.read_text())
    audit = json.loads(audit_path.read_text())
    training = json.loads((args.candidate / "training.json").read_text())
    split = json.loads((args.data / "split.json").read_text())
    val_digest = sha256(args.data / "val.jsonl")
    if (
        sha256(args.v2 / "model.json") != baseline["control_model_sha256"]
        or sha256(args.v3 / "model.json") != baseline["candidate_model_sha256"]
        or sha256(args.candidate / "model.json") != training["model_sha256"]
        or training["control_model_sha256"] != baseline["control_model_sha256"]
        or training["cleaning"] != json.loads((args.data / "cleaning.json").read_text())
        or sha256(args.data / "train.jsonl")
        != training["cleaning"]["cleaned_train_sha256"]
        or val_digest != split["parent_split_digests"]["val"]
    ):
        raise ValueError("Model or training data differs from its receipt")
    predictor = NMRGymProtonPredictor(args.candidate)
    train = set(np.load(args.data / "train-keys.npy").astype(str))
    val = set(np.load(args.data / "val-keys.npy").astype(str))
    if train & val or len(train) != training["cleaning"]["after"]:
        raise ValueError("Unexpected training or validation split")
    reserved = train | val
    report = dict(
        models_sha256=dict(
            v2=training["control_model_sha256"],
            v3=baseline["candidate_model_sha256"],
            v4=training["model_sha256"],
        ),
        training_receipt_sha256=sha256(args.candidate / "training.json"),
        split_sha256=sha256(args.data / "split.json"),
        validation_sha256=val_digest,
        baseline_report_sha256=sha256(baseline_path),
        label_audit_sha256=sha256(audit_path),
        training_molecules=len(train),
        validation_molecules=len(val),
        cleaning=training["cleaning"],
        seeds=training["seeds"],
        optimizer_epochs={
            k: len(training[k]) for k in ("initial", "cosine", "positions")
        },
        test_policy="Official includes every original test entry. Reviewed uses the earlier source audit: "
        "replace verified proton lists and omit only entries without proton references. "
        "The views reuse the same predictions. Both panels are connectivity-disjoint "
        "from each other, training and validation.",
        comparison="Equal molecule weights. Confidence intervals use 3000 paired molecule bootstrap "
        "resamples per panel and reference view, conditional on the fitted models.",
        cosine_fwhm_ppm=0.05,
        unmatched_peak_penalty_ppm=1.0,
        test={},
    )
    reviews = {r["connectivity"]: r for r in audit["audit"]}
    seen = set()
    for label, control in baseline["test"].items():
        path = args.v3 / (label + ".jsonl.gz")
        if sha256(path) != control["replay_sha256"]:
            raise ValueError(f"Frozen predictions changed for {label}")
        rows = []
        with gzip.open(path, "rt") as source:
            for row in map(json.loads, source):
                key = row["connectivity"]
                if key in reserved:
                    raise ValueError(f"Repeated molecular connectivity: {key}")
                reserved.add(key)
                review = reviews.get(key)
                reviewed = row["reference"]
                if review is not None:
                    if review["panel"] != label or Counter(
                        review["official_h_ppm"]
                    ) != Counter(reviewed):
                        raise ValueError(
                            f"Review does not match the frozen reference: {key}"
                        )
                    reviewed = review["sensitivity_reference_ppm"]
                    seen.add(key)
                rows.append(
                    dict(
                        connectivity=key,
                        smiles=row["smiles"],
                        reference=row["reference"],
                        reviewed_reference=reviewed,
                        v2=row["v2"],
                        v3=row["clean"],
                        v4=predictor.predict(row["smiles"])["prediction_ppm"],
                    )
                )
        external = ()
        if label == "published_980":
            external = ("nmrnet", "nmrnetpp")
            public = args.v2 / path.name
            if sha256(public) != control["source_sha256"]:
                raise ValueError("Unexpected external baseline replay")
            with gzip.open(public, "rt") as source:
                for row, released in zip(rows, map(json.loads, source), strict=True):
                    if (row["connectivity"], row["reference"]) != (
                        released["connectivity"],
                        released["reference"],
                    ):
                        raise ValueError(
                            "Mismatched external baseline identities or labels"
                        )
                    row.update({m: released[m] for m in external})
        official = score_view(rows, "reference", control, external)
        reviewed = score_view(
            rows,
            "reviewed_reference",
            audit["panels"][label]["same_eligible_reviewed_labels"],
            external,
        )
        replay = args.candidate / (label + ".jsonl.gz")
        pending = replay.with_suffix(".partial")
        with gzip.open(pending, "wt") as output:
            for row in rows:
                output.write(json.dumps(row, allow_nan=False) + "\n")
        pending.replace(replay)
        report["test"][label] = dict(
            official=official,
            same_eligible_original=same_eligible_original(
                rows, audit["panels"][label]["same_eligible_original_labels"], external
            ),
            reviewed=reviewed,
            source_sha256=control["replay_sha256"],
            replay_sha256=sha256(replay),
        )
        for view, metrics in (("official", official), ("reviewed", reviewed)):
            print(
                label,
                view,
                {k: metrics["v4"][k] for k in ("matched_peak_mae_ppm", "cosine")},
                flush=True,
            )
    if seen != set(reviews):
        raise ValueError("Unmatched entries in the frozen label audit")
    validation_rows = []
    predictors = dict(
        v2=NMRGymProtonPredictor(args.v2),
        v3=NMRGymProtonPredictor(args.v3),
        v4=predictor,
    )
    with (args.data / "val.jsonl").open() as source:
        for key, smiles, reference in map(json.loads, source):
            val.remove(key)
            predictions = {
                name: model.predict(smiles)["prediction_ppm"]
                for name, model in predictors.items()
            }
            validation_rows.append(dict(reference=reference, **predictions))
            if len(validation_rows) % 1024 == 0:
                print("Scored validation molecules:", len(validation_rows), flush=True)
    if val:
        raise ValueError("Validation predictions are incomplete")
    report["validation"] = score_view(validation_rows, "reference")
    pending = args.report.with_suffix(".partial")
    pending.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    pending.replace(args.report)


if __name__ == "__main__":
    main()
