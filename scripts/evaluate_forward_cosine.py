"""Measure spectrum cosine on the released forward benchmarks without selecting models or widths."""

import argparse
import gzip
import json
from pathlib import Path
import pickle
import sys

# ruff: noqa: E402
# Import project packages from the checkout when this file runs as a standalone script.
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import numpy as np
from rdkit import Chem, RDLogger

from compare_assigned_hc import DATASETS, frozen, reference
from openmolspec.assigned_shifts import PeakSpectrumPredictor
from openmolspec_bench.carbon import group_carbon_shifts
from openmolspec_bench.data import readonly_lmdb, sha256
from openmolspec_bench.metrics import peak_metrics, weighted_r2
from openmolspec_bench.solution_cohort import solution_test_cohort
from openmolspec_bench.nmr_cosine import peak_profile_cosine
from openmolspec_bench.peak_evaluation import matching_errors
from openmolspec_bench.runner import read_prediction_folds

WIDTH_FACTORS = (0.5, 1.0, 2.0)


def read(path):
    return json.loads(Path(path).read_text())


def scores_at_widths(predicted, observed, widths):
    return [
        peak_profile_cosine(predicted, observed, np.asarray(widths) * factor)
        for factor in WIDTH_FACTORS
    ]


def summary(values):
    means = np.mean(values, axis=0).tolist()
    return dict(
        cosine=means[1], half_width_cosine=means[0], double_width_cosine=means[2]
    )


def carbon_predictions(args, name, refs, occupied):
    metadata = args.models / "nmrnetpp/data_ours" / (name + "_C") / "valid.lmdb"
    root = args.models / "nmrnetpp/results" / (name + "_C")
    paths = sorted(root.glob("cv_seed_42_fold_*/*.out.pkl"))
    if len(paths) != 5:
        raise ValueError("Expected all five selected carbon folds")
    folds = read_prediction_folds(paths)
    with readonly_lmdb(metadata) as db, db.begin() as txn:
        records = [pickle.loads(b)["smiles"] for _, b in txn.cursor()]
    for index in sorted(set.intersection(*(set(f) for f in folds))):
        mol = Chem.MolFromSmiles(records[index])
        smi = Chem.MolToSmiles(mol)
        key = Chem.MolToInchiKey(mol).split("-")[0]
        if key in occupied or smi not in refs:
            continue
        occupied.add(key)
        averaged = np.stack([f[index] for f in folds]).mean(axis=0)
        yield [p["shift_ppm"] for p in group_carbon_shifts(mol, averaged)], refs[smi]


def proton_predictions(args, name, refs, occupied, model):
    baselines = frozen(args, name)
    if set(baselines) != {"nmrnet", "nmrnetpp"}:
        raise ValueError(
            "Both frozen baselines are required to identify the published paired cohort"
        )
    for smi in sorted(set(refs).intersection(*baselines.values())):
        key = Chem.MolToInchiKey(Chem.MolFromSmiles(smi)).split("-")[0]
        if key in occupied:
            continue
        values = model.predict(smi)["prediction_ppm"]
        if values:
            occupied.add(key)
            yield values, refs[smi]


def hc_spectrum_sensitivity(predicted, observed, cosine, penalized):
    """Leave each spectrum intact when checking the influence of the largest shift errors."""
    mae = [
        peak_metrics([p], [y])["matched_peak_mae_ppm"]
        for p, y in zip(predicted, observed)
    ]
    drop = int(np.ceil(len(mae) * 0.01))
    keep = np.ones(len(mae), dtype=bool)
    keep[np.argsort(-np.asarray(mae), kind="stable")[:drop]] = False
    return dict(
        selection="Diagnostic: omit ceil(1% of spectra) with largest uncapped within-spectrum matched MAE.",
        excluded_spectra=drop,
        molecules=int(keep.sum()),
        **peak_metrics(
            [v for v, k in zip(predicted, keep) if k],
            [v for v, k in zip(observed, keep) if k],
        ),
        **summary(np.asarray(cosine)[keep]),
        count_penalized_error_ppm=float(np.mean(np.asarray(penalized)[keep])),
    )


def hc(args, nucleus, released):
    args.nucleus = nucleus
    h = nucleus == "1H"
    profile = (
        args.h_model / "model.json"
        if h
        else ROOT / "src/openmolspec/assets/carbon-folds.json"
    )
    if (
        h
        and sha256(profile)
        != read(ROOT / released["evidence"])["selected_config_sha256"]
    ):
        raise ValueError("Wrong proton model configuration")
    model = PeakSpectrumPredictor(args.h_model) if h else None
    width = 0.05 if h else 1.0
    occupied, pooled, splits = set(), [], {}
    all_predictions, all_observations, all_errors = [], [], []
    for name in DATASETS:
        refs = reference(args, name)
        pairs = (
            proton_predictions(args, name, refs, occupied, model)
            if h
            else carbon_predictions(args, name, refs, occupied)
        )
        # Consume development identities first, as in the selection reports.
        predictions, observations = zip(*pairs)
        if name == DATASETS[0]:
            continue
        index = released["benchmark"].index(name)
        errors = matching_errors(predictions, observations, 1.0 if h else 10.0)
        error = float(errors.mean())
        if len(observations) != released["counts"][index]:
            raise ValueError(
                f"{name} paired cohort size differs from the published benchmark"
            )
        np.testing.assert_allclose(
            error, released["selected_scores"][index], rtol=0, atol=1e-6
        )
        scores = [
            scores_at_widths(p, y, width) for p, y in zip(predictions, observations)
        ]
        splits[name] = dict(
            **summary(scores),
            **peak_metrics(predictions, observations),
            molecules=len(scores),
            count_penalized_error_ppm=error,
            reference_sha256=sha256(args.external / name / "test.jsonl"),
        )
        pooled.extend(scores)
        all_predictions.extend(predictions)
        all_observations.extend(observations)
        all_errors.extend(errors)
        print(
            nucleus, name, splits[name]["molecules"], splits[name]["cosine"], flush=True
        )
    return dict(
        **summary(pooled),
        spectrum_sensitivity_99=hc_spectrum_sensitivity(
            all_predictions, all_observations, pooled, all_errors
        ),
        **peak_metrics(all_predictions, all_observations),
        count_penalized_error_ppm=float(np.mean(all_errors)),
        molecules=len(pooled),
        fwhm_ppm=[width],
        model_config_sha256=sha256(profile),
        splits=splits,
    )


def passed_replay(path, task):
    (result,) = [row for row in read(path)["results"] if row["task"] == task]
    if result["status"] != "passed":
        raise ValueError(f"Unsuccessful native replay for {task}")
    return result


def solution_metrics(records):
    _, groups, counts = np.unique(
        [r["connectivity"] for r in records], return_inverse=True, return_counts=True
    )
    observed = np.array([r["reference_ppm"] for r in records])
    predicted = np.array([r["prediction_ppm"] for r in records])
    errors = np.abs(predicted - observed)

    def per_structure(values):
        return np.bincount(groups, weights=values) / counts

    maes = [float(errors.mean()), float(per_structure(errors).mean())]
    # Each record contains exactly one peak. The two self-overlaps are both 1.
    values = 1 / (1 + (errors[:, None] / np.asarray(WIDTH_FACTORS)) ** 2)
    macro = np.column_stack([per_structure(column) for column in values.T])
    return dict(
        **summary(macro),
        molecules=len(counts),
        observations=len(records),
        fwhm_ppm=[1.0],
        per_observation=summary(values),
        observation_mae_ppm=maes[0],
        molecule_macro_mae_ppm=maes[1],
        molecule_weighted_r2=weighted_r2(predicted, observed, 1 / counts[groups]),
    )


def single_environment(replay, released):
    if replay["checkpoint"]["sha256"] != released["config_sha256"]:
        raise ValueError("Checkpoint differs from the selected ensemble")
    records = replay["predictions"]
    nucleus = replay["task"].split(".")[-1]
    retained, cohort = solution_test_cohort(
        records, nucleus, replay["dataset"]["sha256"]
    )
    result = solution_metrics(retained)
    result.update(
        cohort=cohort,
        excluded_observations=len(records) - len(retained),
        reference_sha256=replay["dataset"]["sha256"],
        model_config_sha256=replay["checkpoint"]["sha256"],
    )
    if len(retained) != len(records):
        result["full_test"] = solution_metrics(records)
    original = result.get("full_test", result)
    evidence = released.get("full_test", released)
    if [original["observations"], original["molecules"]] != evidence["counts"]:
        raise ValueError(
            "Expected the full released holdout replay (--solution-reference full-test)"
        )
    np.testing.assert_allclose(
        [original["observation_mae_ppm"], original["molecule_macro_mae_ppm"]],
        evidence["selected_scores"],
        rtol=0,
        atol=1e-5,
    )
    return result


def hsqc(directory, released, archive=None):
    from openmolspec_bench.transpeaknet import CHECKPOINT_SHA256, default_calibration

    manifest = directory / "sources.json"
    sources = read(manifest)
    metrics = read(directory / "metrics.json")
    if (
        metrics["checkpoint_sha256"] != CHECKPOINT_SHA256
        or metrics["calibration_sha256"] != sha256(default_calibration())
        or metrics["source_manifest_sha256"] != sha256(manifest)
    ):
        raise ValueError("Wrong HSQC checkpoint, calibration or source manifest")
    if archive and sha256(archive) != sources["sources"]["transpeaknet_expert"]:
        raise ValueError("Wrong upstream atom-order archive")
    panel = "2dnmrgym"
    refs = directory / f"{panel}.jsonl.gz"
    replay = directory / f"{panel}-predictions.jsonl.gz"
    if (
        sha256(refs) != sources["panels"][panel]["reference_sha256"]
        or sha256(replay) != metrics["panels"][panel]["predictions_sha256"]
    ):
        raise ValueError("Official reference or predictions changed")
    widths = [1.0, 0.05]
    identifiers = set()
    scores = []
    n_obs = n_pred = 0
    with gzip.open(refs, "rt") as gold, gzip.open(replay, "rt") as predictions:
        for ref, row in zip(
            map(json.loads, gold), map(json.loads, predictions), strict=True
        ):
            if (
                ref["id"] != row["id"]
                or ref["id"] in identifiers
                or ref["connectivity"] != row["connectivity"]
            ):
                raise ValueError("Official reference and prediction identities differ")
            identifiers.add(ref["id"])
            observed = ref["peaks_c_h_ppm"]
            predicted = row["prediction_c_h_ppm"]
            scores.append(scores_at_widths(predicted, observed, widths))
            n_obs += len(observed)
            n_pred += len(predicted)
    official = metrics["panels"][panel]["all_records"]
    if [len(scores), n_obs] != released["counts"] or [len(scores), n_obs, n_pred] != [
        official[k] for k in ("spectra", "observed", "predicted")
    ]:
        raise ValueError("Incomplete 2DNMRGym test set")
    aggregate = summary(scores)
    np.testing.assert_allclose(
        aggregate["cosine"], official["cosine"], atol=1e-10, rtol=0
    )
    return dict(
        **aggregate,
        benchmark="2DNMRGym official eval",
        spectra=len(scores),
        observed_crosspeaks=n_obs,
        predicted_crosspeaks=n_pred,
        axes=["13C", "1H"],
        fwhm_ppm=widths,
        checkpoint_sha256=metrics["checkpoint_sha256"],
        calibration_sha256=metrics["calibration_sha256"],
        reference_sha256=sha256(refs),
        replay_sha256=sha256(replay),
    )


def existing_scores(released, replay_dir):
    result = {}
    task = "vibrational.forward"
    path = replay_dir / "vibration-default-replay.json"
    vib = passed_replay(path, task)
    observed = [vib["metrics"][ch + "_cosine_similarity"] for ch in ("ir", "raman")]
    np.testing.assert_allclose(
        observed, released[task]["selected_scores"], rtol=0, atol=1e-10
    )
    if (
        len(set(vib["sample_ids"])) != len(vib["sample_ids"])
        or len(vib["sample_ids"]) != released[task]["counts"]
    ):
        raise ValueError("Wrong QM9S cohort")
    result[task] = dict(
        ir_cosine=observed[0],
        raman_cosine=observed[1],
        molecules=len(vib["sample_ids"]),
        reference="QM9S calculated intensity profiles",
        replay_sha256=sha256(path),
    )
    for model in ("glacier", "iceberg"):
        task = "ms.forward." + model
        report = ROOT / released[task]["evidence"]
        ms = read(report)
        mean = ms["candidate" if ms["promoted"] else "baseline"]["cosine_similarity"]
        np.testing.assert_allclose(
            mean, released[task]["selected_scores"], rtol=0, atol=1e-10
        )
        if [ms["confirmed_identities"], ms["confirmation_sample_size"]] != released[
            task
        ]["counts"]:
            raise ValueError("Wrong MassSpecGym cohort")
        result[task] = dict(
            cosine=mean,
            molecules=ms["confirmed_identities"],
            sampled=ms["confirmation_sample_size"],
            reference="MassSpecGym measured tandem MS, all observed peaks",
            evidence_sha256=sha256(report),
        )
    return result


def main():
    from openmolspec_bench.catalog import TASKS

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--models", type=Path, default=ROOT / "../../models")
    p.add_argument("--external", type=Path, default=ROOT / "../data/align_eval")
    p.add_argument(
        "--h-model", type=Path, default=ROOT / "../runs/peak-models-selected/1H"
    )
    p.add_argument("--replays", type=Path, default=ROOT / ".runtime/forward-tuning")
    p.add_argument("--hsqc-panels", type=Path, default=ROOT / "results/hsqc_benchmarks")
    p.add_argument(
        "--hsqc-archive",
        type=Path,
        help="Optional upstream archive for atom-order provenance verification",
    )
    p.add_argument(
        "--output", type=Path, default=ROOT / "results/forward_cosine_similarity.json"
    )
    args = p.parse_args()
    RDLogger.DisableLog("rdApp.*")
    released = read(ROOT / "results/forward_benchmark_summary.json")["tasks"]
    tasks = {}
    for nucleus in ("31P", "19F", "11B", "29Si"):
        task = "nmr.forward." + nucleus
        filename = {
            "31P": "31P-capacity-kit/native.json",
            "19F": "19F-default-replay.json",
        }.get(nucleus, "bsi-replay.json")
        path = args.replays / filename
        tasks[task] = single_environment(passed_replay(path, task), released[task])
        tasks[task]["replay_sha256"] = sha256(path)
    task = "nmr.hsqc.transpeaknet"
    tasks[task] = hsqc(args.hsqc_panels, released[task], args.hsqc_archive)
    tasks.update(existing_scores(released, args.replays))
    for nucleus in ("1H", "13C"):
        task = "nmr.forward." + nucleus
        tasks[task] = hc(args, nucleus, released[task])
    if set(tasks) != {t.id for t in TASKS if t.enabled and t.family == "forward"}:
        raise ValueError("Incomplete or extra forward tasks")
    result = dict(
        nmr_profile="Unit-area Lorentzians on all real ppm coordinates. HSQC uses the product of both axes. "
        "All listed peaks, no alignment, no clipping, no experimental intensities or multiplet simulation.",
        nmr_aggregation="Equal weight per held-out H/C molecule or official 2DNMRGym spectrum. For single-environment "
        "measurements, first average within connectivity, then across connectivities.",
        nmr_width_sensitivity="Half and double both refer to the listed reference FWHM, scaled along every axis.",
        pf_cohort="Default P/F subset fixes the top 1% of absolute errors from the original released models. "
        "The original complete holdout is reported under full_test.",
        hc_r2="Pool within-molecule minimum-absolute-error peak matches with equal total weight per molecule. "
        "Unpaired peaks contribute to the separate count-penalized error.",
        tasks={k: tasks[k] for k in released},
    )
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
