"""Score one frozen HSQC model on the WanJuan and official 2DNMRGym panels."""

import argparse
from functools import lru_cache
import gzip
import json
from pathlib import Path
import sys

import numpy as np
from rdkit import Chem

from prepare_hsqc_benchmarks import matched_count, write_rows


def summarize(rows):
    if not rows:
        return {"spectra": 0}
    observed = sum(r["observed"] for r in rows)
    hits = sum(r["in_window"] for r in rows)
    totals = dict(
        spectra=len(rows),
        connectivities=len({r["connectivity"] for r in rows}),
        observed=observed,
        predicted=sum(r["predicted"] for r in rows),
        in_window=hits,
        observed_hit_fraction_micro=hits / observed,
        observed_hit_fraction_macro=float(
            np.mean([r["in_window"] / r["observed"] for r in rows])
        ),
    )
    for key in ("cosine", "partial_list_cosine", "carbon_mae_ppm", "proton_mae_ppm"):
        if key in rows[0]:
            totals[key] = float(np.mean([r[key] for r in rows]))
    if "with_candidate_carbon" in rows[0]:
        totals["with_candidate_carbon"] = sum(r["with_candidate_carbon"] for r in rows)
        totals["candidate_coverage"] = totals["with_candidate_carbon"] / observed
    if "correct_atom" in rows[0]:
        totals["correct_atom"] = sum(r["correct_atom"] for r in rows)
        totals["correct_atom_fraction_of_observed"] = totals["correct_atom"] / observed
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panels", type=Path, required=True)
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="TransPeakNet author checkout with the frozen weights",
    )
    args = parser.parse_args()
    import torch
    import torch_geometric
    from rdkit import rdBase
    import scipy
    from openmolspec_bench.data import sha256
    from openmolspec_bench.hsqc_evaluation import score_web_matches, site_mae
    from openmolspec_bench.nmr_cosine import peak_profile_cosine
    from openmolspec_bench.transpeaknet import (
        assign_peaks,
        calibrated_prediction,
        default_calibration,
        load_model,
        peak_list,
        predict_sites,
    )

    frozen = json.loads((args.panels / "sources.json").read_text())
    config = default_calibration()
    cal = json.loads(config.read_text())
    torch.set_num_threads(1)
    model = load_model(args.source)

    @lru_cache(maxsize=1100)
    def predict(smiles, solvent):
        mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
        pred = calibrated_prediction(
            predict_sites(model, mol, solvent), mol, solvent, cal
        )
        return mol, pred, *peak_list(mol, *pred)

    report = dict(
        runtime=dict(
            python=sys.version.split()[0],
            torch=torch.__version__,
            pyg=torch_geometric.__version__,
            rdkit=rdBase.rdkitVersion,
            numpy=np.__version__,
            scipy=scipy.__version__,
            cpu_threads=1,
        ),
        checkpoint_sha256=sha256(args.source / "ckpt/model_2dnmr.pt"),
        calibration_sha256=sha256(config),
        source_manifest_sha256=sha256(args.panels / "sources.json"),
        hit_rule="Maximum number of one-to-one pairs with absolute errors <=2 ppm (13C) and <=0.2 ppm (1H). All recorded peaks form the recall denominator.",
        cosine="Equal spectrum weights, unit-area 2D Lorentzians with FWHM 1.0 ppm (13C) and 0.05 ppm (1H). partial_list_cosine compares a full prediction to the explicitly reported subset and is not a whole-spectrum metric.",
        atom_metrics="MAE at known C sites, per spectrum then mean. Website atom assignment uses the released 8 ppm/0.65 ppm ellipse and accepts any expert carbon sharing the coordinate.",
        views="All screened references are retained in all_records. Secondary views remove known fitting-pool connectivities. The published 1D inventory includes potential pretraining structures; membership does not prove use in fitting.",
        panels={},
    )
    for panel in ("wanjuan", "2dnmrgym"):
        metadata = frozen["panels"][panel]
        path = args.panels / (panel + ".jsonl.gz")
        if sha256(path) != metadata["reference_sha256"]:
            raise ValueError(f"Panel checksum changed: {panel}")
        history = []
        with gzip.open(path, "rt") as f:
            for row in map(json.loads, f):
                mol, pred, peaks, atom_ids = predict(row["smiles"], row["solvent"])
                obs = np.array(row["peaks_c_h_ppm"])
                if not len(obs) or not np.isfinite(obs).all():
                    raise ValueError(f"Invalid reference {panel}/{row['id']}")
                rec = dict(
                    id=row["id"],
                    connectivity=row["connectivity"],
                    listed_in=row["listed_in"],
                    observed=len(obs),
                    predicted=len(peaks),
                    in_window=matched_count(obs, peaks, [2.0, 0.2]),
                    prediction_c_h_ppm=peaks.tolist(),
                )
                field = (
                    "cosine"
                    if row["scope"] == "source_peak_list"
                    else "partial_list_cosine"
                )
                rec[field] = peak_profile_cosine(peaks, obs, [1.0, 0.05])
                if "assignments" in row:
                    rec.update(site_mae(pred, row["assignments"]))
                    rec["correct_atom"] = score_web_matches(
                        mol, pred, row["assignments"]
                    )["correct"]
                else:
                    candidates, _ = assign_peaks(obs, peaks, atom_ids)
                    rec["with_candidate_carbon"] = len(candidates)
                history.append(rec)
        evaluation = args.panels / (panel + "-predictions.jsonl.gz")
        write_rows(evaluation, history)
        report["panels"][panel] = dict(
            all_records=summarize(history),
            outside_2d_fitting_pools=summarize(
                [
                    r
                    for r in history
                    if all(
                        n == "author_1d_pretraining_inventory" for n in r["listed_in"]
                    )
                ]
            ),
            outside_all_listed_pools=summarize(
                [r for r in history if not r["listed_in"]]
            ),
            predictions_sha256=sha256(evaluation),
        )
        print(panel, report["panels"][panel]["all_records"], flush=True)
    report["publication_overlap"] = frozen["official_views"]
    pending = args.panels / "metrics.partial"
    pending.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    pending.replace(args.panels / "metrics.json")


if __name__ == "__main__":
    main()
