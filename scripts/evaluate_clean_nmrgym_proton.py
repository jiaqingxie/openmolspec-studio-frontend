"""Score the cleaned-data refit on both complete, checksum-pinned v2 test panels."""

import argparse
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import numpy as np
from rdkit import RDLogger
from evaluate_nmrgym_proton import scores
from openmolspec.nmrgym_proton import NMRGymProtonPredictor
from openmolspec_bench.data import sha256


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--control", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    a = p.parse_args()
    RDLogger.DisableLog("rdApp.*")
    known = json.loads((ROOT / "results/nmrgym_proton_precision.json").read_text())
    receipt = json.loads((a.candidate / "training.json").read_text())
    for directory, digest in (
        (a.control, known["model_sha256"]),
        (a.candidate, receipt["model_sha256"]),
    ):
        if sha256(directory / "model.json") != digest:
            raise ValueError("Unexpected model profile")
    if known["model_sha256"] != receipt["control_model_sha256"]:
        raise ValueError("Wrong control model")
    m = NMRGymProtonPredictor(a.candidate)
    reserved = set(np.load(a.data / "train-keys.npy").astype(str)) | set(
        np.load(a.data / "val-keys.npy").astype(str)
    )
    report = dict(
        control_model_sha256=known["model_sha256"],
        candidate_model_sha256=receipt["model_sha256"],
        comparison="All original test molecules and peak entries. Equal weight per molecule. Paired bootstrap (3000 samples) is conditional on this fit.",
        cosine_fwhm_ppm=0.05,
        unmatched_peak_penalty_ppm=1.0,
        train_validation_test_connectivity_check="Both panels are disjoint from the training cache, validation cache and each other.",
        cleaning=receipt["cleaning"],
        optimizer_epochs={
            s: len(receipt[s]) for s in ("initial", "cosine", "positions")
        },
        test={},
    )
    for label, meta in known["test"].items():
        replay = a.control / (label + ".jsonl.gz")
        if sha256(replay) != meta["predictions_sha256"]:
            raise ValueError("Unexpected original test replay")
        with gzip.open(replay, "rt") as source:
            rows = list(map(json.loads, source))
        keys = {r["connectivity"] for r in rows}
        if len(keys) != len(rows) or len(rows) != meta["molecules"] or keys & reserved:
            raise ValueError("Unexpected test identities")
        reserved.update(keys)
        y = [r["reference"] for r in rows]
        base, ba = scores([r["v2"] for r in rows], y)
        for k, val in base.items():
            if isinstance(val, (float, int)):
                np.testing.assert_allclose(
                    val, meta["metrics"]["v2"][k], atol=1e-7, rtol=0
                )
        predictions = [m.predict(r["smiles"])["prediction_ppm"] for r in rows]
        new, na = scores(predictions, y)
        ind = np.random.default_rng(843).integers(0, len(rows), (3000, len(rows)))
        delta = {}
        for metric in (
            "count_penalized_error_ppm",
            "matched_peak_mae_ppm",
            "matched_fraction",
            "cosine",
        ):
            differences = na[metric] - ba[metric]
            delta[metric] = dict(
                mean=float(differences.mean()),
                ci95=np.percentile(differences[ind].mean(axis=1), [2.5, 97.5]).tolist(),
            )
        unusual = np.array([max(map(abs, ref)) > 50 for ref in y])
        influence = {
            "definition": "Whole test spectra containing a reference proton shift with absolute value >50 ppm, irrespective of chemistry. All are included in the reported scores.",
            "molecules": int(unusual.sum()),
        }
        for model_name, arrays in (("v2", ba), ("clean", na)):
            per_molecule = arrays["matched_peak_mae_ppm"]
            influence[model_name] = {
                "fraction_of_total_molecule_weighted_absolute_error": float(
                    per_molecule[unusual].sum() / per_molecule.sum()
                )
                if per_molecule.sum()
                else None,
            }
        sample = a.candidate / (label + ".jsonl.gz")
        with gzip.open(sample, "wt") as g:
            for r, pred in zip(rows, predictions):
                g.write(
                    json.dumps(
                        dict(
                            connectivity=r["connectivity"],
                            smiles=r["smiles"],
                            reference=r["reference"],
                            v2=r["v2"],
                            clean=pred,
                        )
                    )
                    + "\n"
                )
        report["test"][label] = dict(
            molecules=len(rows),
            reference_peaks=sum(map(len, y)),
            source_sha256=sha256(replay),
            replay_sha256=sha256(sample),
            v2=base,
            clean=new,
            paired_clean_minus_v2=delta,
            reference_shift_influence=influence,
        )
        print(label, delta, flush=True)
    tmp = a.report.with_suffix(".partial")
    tmp.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    tmp.replace(a.report)


if __name__ == "__main__":
    main()
