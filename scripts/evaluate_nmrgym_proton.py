"""Compare a locked NMRGym proton adapter and the released model on the published 980 molecules."""

import argparse
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import numpy as np
from rdkit import Chem, RDLogger
from scipy.optimize import linear_sum_assignment
from compare_assigned_hc import DATASETS, frozen, reference
from openmolspec.assigned_shifts import PeakSpectrumPredictor
from openmolspec.nmrgym_proton import NMRGymProtonPredictor
from openmolspec_bench.data import sha256
from openmolspec_bench.metrics import peak_metrics
from openmolspec_bench.nmr_cosine import peak_profile_cosine
from openmolspec_bench.peak_evaluation import matching_errors


def reference_panel(args, released):
    occupied = set()
    for name in DATASETS:
        refs = reference(args, name)
        old = frozen(args, name)
        if set(old) != {"nmrnet", "nmrnetpp"}:
            raise ValueError("Both released model reference cohorts are required")
        for smiles in sorted(set(refs).intersection(*old.values())):
            mol = Chem.MolFromSmiles(smiles)
            key = Chem.MolToInchiKey(mol).split("-")[0]
            if key in occupied:
                continue
            if not any(
                a.GetAtomicNum() > 1 and a.GetTotalNumHs(includeNeighbors=True)
                for a in mol.GetAtoms()
            ):
                continue
            occupied.add(key)
            if name == "nmrgym_test":
                prediction = released.predict(smiles)["prediction_ppm"]
                yield dict(
                    connectivity=key,
                    smiles=smiles,
                    reference=refs[smiles],
                    released=prediction,
                )


def scores(predicted, obs):
    pooled = peak_metrics(predicted, obs)
    arrays = dict(
        count_penalized_error_ppm=matching_errors(predicted, obs, 1.0),
        cosine=np.array(
            [peak_profile_cosine(p, y, 0.05) for p, y in zip(predicted, obs)]
        ),
    )
    mae, coverage = [], []
    for p, y in zip(predicted, obs):
        costs = np.abs(np.subtract.outer(p, y))
        i, j = linear_sum_assignment(costs)
        mae.append(costs[i, j].mean())
        coverage.append(len(i) / max(len(p), len(y)))
    arrays.update(
        matched_peak_mae_ppm=np.array(mae), matched_fraction=np.array(coverage)
    )
    return {**pooled, **{k: float(v.mean()) for k, v in arrays.items()}}, arrays


def largest_squared_residual(rows):
    """Contribution of the most influential matched specialist peak to the R² numerator."""
    total = 0.0
    largest = 0.0
    record = {}
    for row in rows:
        p, y = np.asarray(row["specialist"]), np.asarray(row["reference"])
        distance = np.abs(p[:, None] - y)
        i, j = linear_sum_assignment(distance)
        contributions = distance[i, j] ** 2 / len(i)
        total += float(contributions.sum())
        pos = int(np.argmax(contributions))
        if contributions[pos] > largest:
            largest = float(contributions[pos])
            record = dict(
                connectivity=row["connectivity"],
                matched_peaks=len(i),
                predicted_ppm=float(p[i[pos]]),
                reference_ppm=float(y[j[pos]]),
            )
    return dict(
        **record, fraction_of_weighted_squared_error=largest / total if total else None
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument(
        "--base", type=Path, default=ROOT / "../runs/peak-models-selected/1H"
    )
    p.add_argument("--models", type=Path, default=ROOT / "../../models")
    p.add_argument("--external", type=Path, default=ROOT / "../data/align_eval")
    p.add_argument("--report", type=Path, required=True)
    a = p.parse_args()
    RDLogger.DisableLog("rdApp.*")
    a.nucleus = "1H"
    model = NMRGymProtonPredictor(a.model)
    training = json.loads((a.model / "training.json").read_text())
    assert training["model_sha256"] == sha256(a.model / "model.json")
    src = ROOT / "results/forward_cosine_similarity.json"
    known = json.loads(src.read_text())["tasks"]["nmr.forward.1H"]
    assert (
        known["model_config_sha256"]
        == model.config["released_model_sha256"]
        == sha256(a.base / "model.json")
    )
    expected = known["splits"]["nmrgym_test"]
    assert expected["reference_sha256"] == sha256(a.external / "nmrgym_test/test.jsonl")
    rows = list(reference_panel(a, PeakSpectrumPredictor(a.base)))
    keys = {r["connectivity"] for r in rows}
    assert len(keys) == len(rows) == expected["molecules"]
    for split in ("train", "val"):
        assert not keys.intersection(np.load(a.data / f"{split}-keys.npy").astype(str))
    for r in rows:
        r["specialist"] = model.predict(r["smiles"])["prediction_ppm"]
    reference_values = [r["reference"] for r in rows]
    baseline, ba = scores([r["released"] for r in rows], reference_values)
    new, na = scores([r["specialist"] for r in rows], reference_values)
    for k in (
        "count_penalized_error_ppm",
        "cosine",
        "matched_fraction",
        "matched_peak_r2",
        "matched_peak_mae_ppm",
    ):
        np.testing.assert_allclose(baseline[k], expected[k], rtol=0, atol=1e-6)
    rng = np.random.default_rng(713)
    index = rng.integers(0, len(rows), (3000, len(rows)))
    changes = {}
    for k in ba:
        delta = na[k] - ba[k]
        changes[k] = {
            "specialist_minus_released": float(delta.mean()),
            "paired_bootstrap_ci95": np.percentile(
                delta[index].mean(axis=1), [2.5, 97.5]
            ).tolist(),
        }
    # The source view has no natural-product provenance label. Describe this structural subset explicitly.
    complex_rows = []
    for row in rows:
        mol = Chem.MolFromSmiles(row["smiles"])
        if (
            mol.GetRingInfo().NumRings() >= 3
            and len(
                Chem.FindMolChiralCenters(
                    mol, includeUnassigned=False, useLegacyImplementation=False
                )
            )
            >= 2
        ):
            complex_rows.append(row)
    structural_subset = {
        "definition": "RDKit ring count >= 3 and at least two assigned chiral centers",
        "molecules": len(complex_rows),
    }
    if complex_rows:
        for label in ("released", "specialist"):
            structural_subset[label], _ = scores(
                [r[label] for r in complex_rows], [r["reference"] for r in complex_rows]
            )
    predictions_path = a.model / "benchmark-predictions.jsonl.gz"
    with gzip.open(predictions_path, "wt") as out:
        for r in rows:
            out.write(json.dumps(r) + "\n")
    report = dict(
        model="NMRGym 1H specialist v1",
        model_sha256=training["model_sha256"],
        adapter_sha256=model.config["adapter_sha256"],
        validation={
            "released": training["validation_baseline"],
            "specialist": (
                training.get("cosine_refinement", {}).get("chosen")
                or training["selected"]
            ),
        },
        evaluated_split="complete nmrgym_test paired benchmark, all reference peaks retained",
        test_molecules=len(rows),
        training_molecules=training["training_molecules"],
        validation_molecules=training["validation_molecules"],
        train_test_connectivity_overlap=0,
        validation_panel_test_connectivity_overlap=0,
        benchmark_reference_sha256=expected["reference_sha256"],
        benchmark_predictions_sha256=sha256(predictions_path),
        bootstrap="3000 paired molecule resamples, seed 713",
        cosine_fwhm_ppm=0.05,
        released=baseline,
        specialist=new,
        change=changes,
        structural_subset=structural_subset,
        largest_specialist_squared_residual=largest_squared_residual(rows),
    )
    a.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
