"""Predict 1H, 31P and HSQC for a single D2O measurement series from WanJuan."""

import argparse
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
RECORD_ID = "EP18744659NWB1:16:2@214791"
# Compound index 16 in the pinned WanJuan document. Spectra 0 and 3 are 1H and 31P.
PROTON_INTERVALS = [
    [8.74, 8.74],
    [8.54, 8.54],
    [8.00, 8.00],
    [7.72, 7.72],
    [7.62, 7.62],
    [7.49, 7.51],
    [7.06, 7.06],
    [5.18, 5.18],
    [3.86, 3.86],
]
PHOSPHORUS_PPM = 13.91


def main():
    from online_api.transpeaknet import evaluate as predict_hsqc
    from openmolspec.model import PeakSpectrumPredictor, SolutionShiftPredictor
    from openmolspec_bench.data import sha256
    from openmolspec_bench.nmr_cosine import peak_profile_cosine

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proton-model", required=True, type=Path)
    parser.add_argument("--phosphorus-model", required=True, type=Path)
    parser.add_argument("--transpeaknet-source", required=True, type=Path)
    args = parser.parse_args()
    panels = ROOT / "results/hsqc_benchmarks"
    manifest = json.loads((panels / "sources.json").read_text())
    reference = panels / "wanjuan.jsonl.gz"
    if sha256(reference) != manifest["panels"]["wanjuan"]["reference_sha256"]:
        raise ValueError("WanJuan reference differs from the pinned benchmark")
    with gzip.open(reference, "rt") as handle:
        (row,) = (r for r in map(json.loads, handle) if r["id"] == RECORD_ID)
    smiles, solvent = row["smiles"], row["solvent"]
    proton = PeakSpectrumPredictor(args.proton_model).predict(smiles, solvent)
    phosphorus = SolutionShiftPredictor(args.phosphorus_model).predict(smiles, solvent)
    if proton["nucleus"] != "1H" or phosphorus["nucleus"] != "31P":
        raise ValueError("Supply the selected 1H and 31P model directories")
    midway = [(low + high) / 2 for low, high in PROTON_INTERVALS]
    hsqc = predict_hsqc(
        dict(
            source=args.transpeaknet_source,
            smiles=smiles,
            solvent=solvent,
            hsqc_peaks=row["peaks_c_h_ppm"],
        )
    )
    output = dict(
        record_id=RECORD_ID,
        smiles=smiles,
        solvent=solvent,
        source_sha256=manifest["sources"]["wanjuan"],
        proton=dict(
            model_config_sha256=sha256(args.proton_model / "model.json"),
            observed_intervals_ppm=PROTON_INTERVALS,
            predicted_ppm=proton["prediction_ppm"],
            peak_cosine_fwhm_0_05_ppm=peak_profile_cosine(
                proton["prediction_ppm"], midway, [0.05]
            ),
        ),
        phosphorus=dict(
            model_config_sha256=sha256(args.phosphorus_model / "model.json"),
            observed_ppm=PHOSPHORUS_PPM,
            predicted_environments=phosphorus["environments"],
            peak_cosine_fwhm_1_ppm=peak_profile_cosine(
                phosphorus["prediction_ppm"], [PHOSPHORUS_PPM], [1.0]
            ),
        ),
        hsqc={
            key: hsqc[key]
            for key in (
                "checkpoint_sha256",
                "calibration_sha256",
                "unit",
                "atom_index_basis",
                "hsqc_measured",
                "hsqc_predicted",
                "hsqc_assignments",
                "unmatched_peak_indices",
            )
        },
    )
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
