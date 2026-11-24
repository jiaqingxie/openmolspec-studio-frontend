"""Replay the released HSQC peak-list and assignment rules on expert spectra."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

import numpy as np
from rdkit import Chem

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    from openmolspec.dataset import molspectra
    from openmolspec_bench.data import sha256
    from openmolspec_bench.nmr_cosine import peak_profile_cosine
    from openmolspec_bench.transpeaknet import assign_peaks, peak_list

    selection = json.loads((ROOT / "results/forward_selection_hsqc.json").read_text())
    evaluation = json.loads(args.replay.read_text())["results"][0]
    if (
        sha256(args.archive) != selection["gold_sha256"]
        or evaluation["calibration"]["sha256"] != selection["config_sha256"]
    ):
        raise ValueError(
            "Inputs differ from the native author-archive calibration audit"
        )
    np.testing.assert_allclose(
        [evaluation["metrics"][k] for k in ("carbon_mae_ppm", "proton_mae_ppm")],
        selection["selected_expert_test"],
    )
    widths = np.array([1.0, 0.05])
    dataset = molspectra("transpeaknet_hsqc_test", root=args.archive)
    references = {r["source_id"]: r for r in dataset["test"]}
    totals = Counter()
    groups = defaultdict(Counter)
    ch2 = Counter()
    resolved_separations = []
    cosines = []
    for row in evaluation["predictions"]:
        reference = references.pop(row["source_id"])
        if reference["smiles"] != row["smiles"]:
            raise ValueError("Expert atom order differs from model input")
        mol = Chem.AddHs(Chem.MolFromSmiles(row["smiles"]))
        positions = row["carbon_atom_index"]
        # Restore the head dtype before averaging H pairs, including tied assignment costs.
        peaks, atom_ids = peak_list(
            mol,
            positions,
            np.asarray(row["carbon_ppm"], dtype="f4"),
            np.asarray(row["proton_ppm"], dtype="f4"),
        )
        multiplicity = Counter(atom_ids)
        gold = defaultdict(set)
        annotations = {r["carbon_atom_index"]: r for r in reference["hsqc_assignments"]}
        if set(annotations) != set(positions):
            raise ValueError("Predicted and expert site identities differ")
        for i, proton in zip(positions, row["proton_ppm"]):
            label = annotations[i]
            for h in label["proton_ppm"]:
                gold[label["carbon_ppm"], h].add(i)
            if mol.GetAtomWithIdx(i).GetTotalNumHs(includeNeighbors=True) == 2:
                nref = len(label["proton_ppm"])
                ch2[f"observed_{nref}_predicted_{multiplicity[i]}"] += 1
                if nref == 2:
                    gap = float(np.ptp(label["proton_ppm"]))
                    resolved_separations.append(
                        (gap, float(np.ptp(proton)), multiplicity[i])
                    )
        measured = sorted(gold)
        matches, unmatched = assign_peaks(np.array(measured), peaks, atom_ids)
        correct = sum(
            m["carbon_atom_index"] in gold[measured[m["peak_index"]]] for m in matches
        )
        count = dict(observed=len(measured), matched=len(matches), correct=correct)
        if count != row["web_matches"]:
            raise ValueError(
                f"Assignment does not reproduce the release for {row['source_id']}"
            )
        count.update(
            spectra=1,
            predicted=len(peaks),
            wrong_atom=len(matches) - correct,
            unassigned_observed=len(unmatched),
            unused_predicted=len(peaks) - len(matches),
            all_correct=int(correct == len(measured)),
        )
        totals.update(count)
        group = (
            "1-10" if len(measured) <= 10 else "11-20" if len(measured) <= 20 else "21+"
        )
        groups[group].update(count)
        cosines.append(
            [
                peak_profile_cosine(peaks, measured, widths * scale)
                for scale in (0.5, 1.0, 2.0)
            ]
        )
    if (
        references
        or totals["observed"] != selection["observed_crosspeaks"]
        or totals["spectra"] != selection["gold_spectra"]
    ):
        raise ValueError("Incomplete native author-archive evaluation")
    half, center, double = np.mean(cosines, axis=0)
    profile = dict(
        cosine=center,
        half_width_cosine=half,
        double_width_cosine=double,
        spectra=totals["spectra"],
        observed_crosspeaks=totals["observed"],
        predicted_crosspeaks=totals["predicted"],
        axes=["13C", "1H"],
        fwhm_ppm=widths.tolist(),
        checkpoint_sha256=evaluation["checkpoint"]["sha256"],
        calibration_sha256=evaluation["calibration"]["sha256"],
        reference_sha256=sha256(args.archive),
        replay_sha256=sha256(args.replay),
    )
    gaps = np.asarray(resolved_separations)
    visible = gaps[gaps[:, 0] >= 0.1]
    report = dict(
        replay_sha256=profile["replay_sha256"],
        reference_sha256=profile["reference_sha256"],
        site_mae_ppm=evaluation["metrics"],
        spectrum_cosine=profile,
        website_assignment=totals,
        by_distinct_observed_crosspeaks=groups,
        methylene_sites=ch2,
        two_annotated_h_same_methylene=dict(
            sites=len(gaps),
            median_expert_separation_ppm=float(np.median(gaps[:, 0])),
            median_predicted_separation_ppm=float(np.median(gaps[:, 1])),
            expert_separation_at_least_0_1_ppm=len(visible),
            predicted_two_for_those=int((visible[:, 2] == 2).sum()),
        ),
        protocol="Website matching on distinct measured coordinates; any carbon sharing the "
        "expert coordinate is accepted. CH2 multiplicity compares the released peak list "
        "for the same carbon to its number of distinct expert proton annotations.",
    )
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
