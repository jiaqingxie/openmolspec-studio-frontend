"""Select H/C peak predictors on a development corpus and audit three independent corpora."""

import argparse
import json
from pathlib import Path
import shutil
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import numpy as np
from rdkit import Chem, RDLogger
from openmolspec_bench.peak_evaluation import matching_errors as errors
from compare_assigned_hc import DATASETS, frozen, reference
from openmolspec.assigned_shifts import (
    AssignedShiftPredictor,
    PeakSpectrumPredictor,
    combine_sites,
    merge_peaks,
)
from openmolspec.peak_learning import PeakLearningPredictor
from openmolspec_bench.data import sha256
from openmolspec_bench.metrics import peak_metrics


def group_ci(values, rng):
    boot = rng.choice(values, size=(2000, len(values)), replace=True).mean(axis=1)
    return np.percentile(boot, [2.5, 97.5]).tolist()


def fit_record(args, weight, gap):
    config = dict(
        engine="peak_spectrum",
        nucleus=args.nucleus,
        peak_learning_weight=weight,
        merge_gap_ppm=gap,
    )
    if weight < 1:
        config["assigned_sha256"] = sha256(args.assigned / "model.json")
    if weight > 0:
        config["peak_learning_sha256"] = sha256(args.weak / "environments.json.gz")
    return config


def promote(args, config, example, expected):
    versions = args.registry / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=versions) as tmp:
        model = Path(tmp) / "model"
        model.mkdir()
        if "assigned_sha256" in config:
            (model / "assigned").mkdir()
            for n in ("model.json", "booster.txt", "lookup.json.gz"):
                shutil.copyfile(args.assigned / n, model / "assigned" / n)
        if "peak_learning_sha256" in config:
            (model / "peak-learning").mkdir()
            shutil.copyfile(
                args.weak / "environments.json.gz",
                model / "peak-learning/environments.json.gz",
            )
        (model / "model.json").write_text(json.dumps(config, indent=2) + "\n")
        check = PeakSpectrumPredictor(model)
        np.testing.assert_allclose(
            check.predict(example)["prediction_ppm"], expected, atol=1.0e-6, rtol=0
        )
        digest = sha256(model / "model.json")
        dest = versions / digest
        if not dest.exists():
            model.rename(dest)
        link = Path(tmp) / "selected"
        link.symlink_to(Path("versions") / digest)
        link.replace(args.registry / args.nucleus)
        return digest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in (
        "assigned",
        "weak",
        "weak-report",
        "registry",
        "models",
        "external",
        "report",
    ):
        p.add_argument("--" + n, type=Path, required=True)
    p.add_argument("--nucleus", choices=("1H", "13C"), required=True)
    args = p.parse_args()
    RDLogger.DisableLog("rdApp.*")
    base = AssignedShiftPredictor(args.assigned)
    proof = json.loads(args.weak_report.read_text())
    weak = PeakLearningPredictor(args.weak, sha256=proof["model_sha256"])
    if base.nucleus != weak.nucleus or weak.nucleus != args.nucleus:
        raise ValueError("Nucleus differs between candidates")
    hydrogen = args.nucleus == "1H"
    penalty = 1.0 if hydrogen else 10.0
    settings = [
        (w, g)
        for w in (0.0, 0.25, 0.5, 0.75, 1.0)
        for g in ((0.0, 0.03, 0.07, 0.12) if hydrogen else (0.0, 0.15, 0.4, 0.8))
    ]
    report = dict(
        nucleus=args.nucleus,
        selection_corpus=DATASETS[0],
        metric="per-connectivity absolute matching error, with per-missing/extra peak penalty; pairwise cost capped at twice the penalty before matching",
        unmatched_peak_penalty_ppm=penalty,
        promotion_rule="lower mean error on at least two audit corpora and pooled paired 95% upper bound below zero",
        evaluation_corpora=list(DATASETS[1:]),
        datasets={},
    )
    differences = []
    reserved = set()
    rng = np.random.default_rng(21057)
    for name in DATASETS:
        refs = reference(args, name)
        old = frozen(args, name)
        if set(old) != {"nmrnet", "nmrnetpp"}:
            raise ValueError(
                "Both frozen predictors are required for a paired comparison"
            )
        smiles, ys, raw, alternative = [], [], [], []
        for smi in sorted(set(refs).intersection(*(set(v) for v in old.values()))):
            key = Chem.MolToInchiKey(Chem.MolFromSmiles(smi)).split("-")[0]
            if key in reserved:
                continue
            b, w = base.predict(smi), weak.predict(smi)
            if not b or not w:
                continue
            reserved.add(key)
            smiles.append(smi)
            ys.append(refs[smi])
            raw.append(b)
            alternative.append(w)
        if not smiles:
            raise ValueError("No paired predictions for " + name)

        def prediction(setting):
            weight, gap = setting
            return [
                [s["shift_ppm"] for s in merge_peaks(combine_sites(b, w, weight), gap)]
                for b, w in zip(raw, alternative)
            ]

        existing = {n: [v[s] for s in smiles] for n, v in old.items()}
        old_scores = {n: errors(v, ys, penalty) for n, v in existing.items()}
        if name == DATASETS[0]:
            grid = [
                (float(errors(prediction(s), ys, penalty).mean()), s) for s in settings
            ]
            value, setting = min(grid)
            incumbent = min(old_scores, key=lambda n: old_scores[n].mean())
            choice = (
                "peak_spectrum" if value < old_scores[incumbent].mean() else incumbent
            )
            report.update(
                selected_on_development=choice,
                incumbent=incumbent,
                model=fit_record(args, *setting),
                grid=[dict(weight=w, gap=g, error=v) for v, (w, g) in sorted(grid)],
            )
            args.report.write_text(json.dumps(report, indent=2) + "\n")
        fresh = prediction(setting)
        rows = dict(**existing, peak_spectrum=fresh)
        measures = {
            n: dict(
                **peak_metrics(v, ys),
                count_penalized_error_ppm=float(errors(v, ys, penalty).mean()),
            )
            for n, v in rows.items()
        }
        delta = errors(fresh, ys, penalty) - old_scores[incumbent]
        report["datasets"][name] = dict(
            reference_smiles=len(refs),
            distinct_eligible_paired_connectivities=len(smiles),
            models=measures,
            difference_vs_incumbent=float(delta.mean()),
            confidence_interval_95=group_ci(delta, rng),
        )
        if name != DATASETS[0]:
            differences.append(delta)
        print(
            name,
            len(ys),
            {n: round(v["count_penalized_error_ppm"], 4) for n, v in measures.items()},
            flush=True,
        )
    pooled = np.concatenate(differences)
    ci = group_ci(pooled, rng)
    report["heldout_difference_ci95"] = ci
    approved = (
        choice == "peak_spectrum"
        and sum(v.mean() < 0 for v in differences) >= 2
        and ci[1] < 0
    )
    report["deployed_model"] = "peak_spectrum" if approved else incumbent
    if approved:
        report["selected_config_sha256"] = promote(
            args, report["model"], smiles[0], fresh[0]
        )
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
