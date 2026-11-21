"""Measure spectrum cosine on the released forward benchmarks without selecting models or widths."""

import argparse
import json
from pathlib import Path
import pickle
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import numpy as np
from rdkit import Chem, RDLogger

from compare_assigned_hc import DATASETS, frozen, reference
from openmolspec.assigned_shifts import PeakSpectrumPredictor
from openmolspec_bench.carbon import group_carbon_shifts
from openmolspec_bench.data import readonly_lmdb, sha256
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
        error = float(
            matching_errors(predictions, observations, 1.0 if h else 10.0).mean()
        )
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
            molecules=len(scores),
            count_penalized_error_ppm=error,
            reference_sha256=sha256(args.external / name / "test.jsonl"),
        )
        pooled.extend(scores)
        print(
            nucleus, name, splits[name]["molecules"], splits[name]["cosine"], flush=True
        )
    return dict(
        **summary(pooled),
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


def single_environment(replay, released):
    records = replay["predictions"]
    if replay["checkpoint"]["sha256"] != released["config_sha256"]:
        raise ValueError("Checkpoint differs from the selected ensemble")
    _, groups, counts = np.unique(
        [r["connectivity"] for r in records], return_inverse=True, return_counts=True
    )
    if [len(records), len(counts)] != released["counts"]:
        raise ValueError("Wrong measurement or connectivity count")
    errors = np.array([abs(r["prediction_ppm"] - r["reference_ppm"]) for r in records])

    def per_structure(values):
        return np.bincount(groups, weights=values) / counts

    maes = [float(errors.mean()), float(per_structure(errors).mean())]
    np.testing.assert_allclose(maes, released["selected_scores"], rtol=0, atol=1e-5)
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
        model_config_sha256=replay["checkpoint"]["sha256"],
        reference_sha256=replay["dataset"]["sha256"],
    )


def hsqc(replay, released, archive):
    from openmolspec.dataset import molspectra
    from openmolspec_bench.transpeaknet import CHECKPOINT_SHA256, peak_list

    evidence = read(ROOT / released["evidence"])
    if (
        replay["calibration"]["sha256"] != evidence["config_sha256"]
        or replay["checkpoint"]["sha256"] != CHECKPOINT_SHA256
    ):
        raise ValueError("Wrong HSQC model or shift calibration")
    if not sha256(archive) == replay["dataset"]["sha256"] == evidence["gold_sha256"]:
        raise ValueError("Wrong expert reference archive")
    refs = {
        record["source_id"]: record
        for record in molspectra("transpeaknet_hsqc_test", root=archive)["test"]
    }
    spectra = replay["predictions"]
    if len(spectra) != len(refs) or {r["source_id"] for r in spectra} != set(refs):
        raise ValueError("Expert spectra differ from replay")
    widths = [1.0, 0.05]
    scores, n_obs, n_pred = [], 0, 0
    for row in spectra:
        ref = refs[row["source_id"]]
        if row["smiles"] != ref["smiles"]:
            raise ValueError(
                "Original atom order or structure differs from expert record"
            )
        mol = Chem.AddHs(Chem.MolFromSmiles(row["smiles"]))
        peaks, _ = peak_list(
            mol, row["carbon_atom_index"], row["carbon_ppm"], row["proton_ppm"]
        )
        observed = ref["hsqc_peaks"]
        if len(observed) != row["web_matches"]["observed"]:
            raise ValueError("Incomplete expert cross-peak list")
        scores.append(scores_at_widths(peaks, observed, widths))
        n_obs += len(observed)
        n_pred += len(peaks)
    if [len(scores), n_obs] != released["counts"]:
        raise ValueError("Wrong expert test set")
    return dict(
        **summary(scores),
        spectra=len(scores),
        observed_crosspeaks=n_obs,
        predicted_crosspeaks=n_pred,
        axes=["13C", "1H"],
        fwhm_ppm=widths,
        checkpoint_sha256=replay["checkpoint"]["sha256"],
        calibration_sha256=replay["calibration"]["sha256"],
        reference_sha256=replay["dataset"]["sha256"],
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
    p.add_argument(
        "--hsqc-archive",
        type=Path,
        default=ROOT
        / ".runtime/transpeaknet-source/data_annotation/HSQC_Annotation_TestData.zip",
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
    path = args.replays / "hsqc-default.json"
    tasks[task] = hsqc(passed_replay(path, task), released[task], args.hsqc_archive)
    tasks[task]["replay_sha256"] = sha256(path)
    tasks.update(existing_scores(released, args.replays))
    for nucleus in ("1H", "13C"):
        task = "nmr.forward." + nucleus
        tasks[task] = hc(args, nucleus, released[task])
    if set(tasks) != {t.id for t in TASKS if t.enabled and t.family == "forward"}:
        raise ValueError("Incomplete or extra forward tasks")
    result = dict(
        nmr_profile="Unit-area Lorentzians on all real ppm coordinates. HSQC uses the product of both axes. "
        "All listed peaks, no alignment, no clipping, no experimental intensities or multiplet simulation.",
        nmr_aggregation="Equal weight per held-out H/C molecule or expert HSQC spectrum. For single-environment "
        "measurements, first average within connectivity, then across connectivities.",
        nmr_width_sensitivity="Half and double both refer to the listed reference FWHM, scaled along every axis.",
        tasks={k: tasks[k] for k in released},
    )
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
