"""Frozen GLACIER/ICEBERG inference on our real held-out MS/MS records."""

import argparse
import ast
from collections import Counter
import csv
import json
from pathlib import Path
import sys
import time

import numpy as np

from .data import sha256


class UnsupportedCondition(ValueError):
    """A required acquisition condition is unavailable; never invent its value."""


def select_ms_records(csv_path, metadata_path, limit, max_heavy_atoms=40, unique_molecules=True):
    """Join our existing split to acquisition metadata by ID, molecule, and adduct."""
    from rdkit import Chem

    selected, counts, seen = {}, Counter(), set()
    with open(csv_path, newline="") as stream:
        for row in csv.DictReader(stream):
            counts["split_rows_examined"] += 1
            molecule = Chem.MolFromSmiles(row["smiles"])
            if molecule is None:
                counts["invalid_smiles"] += 1
                continue
            if molecule.GetNumHeavyAtoms() > max_heavy_atoms:
                counts["exceeds_heavy_atom_limit"] += 1
                continue
            identity = Chem.MolToSmiles(molecule, isomericSmiles=True)
            if unique_molecules and identity in seen:
                counts["duplicate_molecule"] += 1
                continue
            peaks = np.asarray(ast.literal_eval(row["peaks"]), dtype=float)
            if peaks.ndim != 2 or peaks.shape[1] != 2 or not np.isfinite(peaks).all() or np.any(peaks < 0):
                raise ValueError(f"Invalid real peaks at {row['spec_id']}")
            if not len(peaks) or not np.any(peaks[:, 1] > 0):
                counts["empty_spectrum"] += 1
                continue
            selected[row["spec_id"]] = {"spec_id": row["spec_id"], "smiles": Chem.MolToSmiles(molecule, isomericSmiles=True),
                                         "adduct": row["prec_type"], "reference_peaks": peaks.tolist(),
                                         "heavy_atoms": molecule.GetNumHeavyAtoms()}
            seen.add(identity)
            if len(selected) >= limit:
                break
    found = []
    with open(metadata_path, newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            sid = row["identifier"]
            if sid not in selected:
                continue
            record = selected.pop(sid)
            molecule = Chem.MolFromSmiles(row["smiles"])
            if molecule is None or Chem.MolToSmiles(molecule, isomericSmiles=True) != record["smiles"] or row["adduct"] != record["adduct"]:
                raise ValueError(f"Acquisition metadata identity/adduct mismatch for {sid}")
            record.update(collision_energy=row.get("collision_energy", ""), instrument=row.get("instrument_type", ""),
                          precursor_mz=float(row["precursor_mz"]))
            found.append(record)
            if not selected:
                break
    counts["missing_acquisition_metadata"] = len(selected)
    if not found:
        raise ValueError("No paired real MS records with acquisition metadata")
    return found, dict(counts)


def spectrum_metrics(predicted, reference, num_bins=150000, upper_limit=1500., max_peaks=100):
    """Authors' max-pool mass binning and prediction top-k, using full observed peaks."""
    def binned(peaks):
        peaks = np.asarray(peaks, dtype=float).reshape(-1, 2)
        if not np.isfinite(peaks).all() or np.any(peaks < 0):
            raise ValueError("Nonfinite or negative predicted/observed peaks")
        result = np.zeros(num_bins)
        index = np.floor(peaks[:, 0] * (num_bins - 1) / upper_limit).astype(np.int64) + 1
        valid = (index >= 0) & (index < num_bins)
        np.maximum.at(result, index[valid], peaks[valid, 1])
        return result

    prediction, target = binned(predicted), binned(reference)
    keep = np.argsort(-prediction, kind="stable")[:max_peaks]
    filtered = np.zeros_like(prediction)
    filtered[keep] = prediction[keep]
    norm = np.linalg.norm(filtered) * np.linalg.norm(target)
    cosine = float(filtered @ target / norm) if norm else 0.
    if filtered.sum() <= 0 or target.sum() <= 0:
        entropy = 0.
    else:
        def ent(values):
            values = values[values > 0]
            return -float(np.sum(values * np.log(values)))
        a, b = filtered / filtered.sum(), target / target.sum()
        entropy = 1 - (2 * ent((a + b) / 2) - ent(a) - ent(b)) / np.log(4)
    return {"cosine_similarity": cosine, "entropy_similarity": float(entropy),
            "predicted_nonzero_bins": int(np.count_nonzero(filtered)), "reference_nonzero_bins": int(np.count_nonzero(target))}


def load_frozen_model(args):
    import torch
    torch.set_num_threads(args.threads)
    sys.path.insert(0, str(args.source / "src"))
    paths = ([args.weights / "weights_glacier/best.ckpt"] if args.model == "glacier" else
             [args.weights / "weights_iceberg/gen/best.ckpt", args.weights / "weights_iceberg/inten_contr/best.ckpt"])
    if args.model == "glacier":
        from ms_pred.glacier.joint_model import JointModel
        model = JointModel.load_from_checkpoint(str(paths[0]), map_location="cpu", weights_only=False)
    else:
        from ms_pred.iceberg import gen_model, inten_model, joint_model
        generation = gen_model.FragGNN.load_from_checkpoint(str(paths[0]), map_location="cpu", weights_only=False)
        intensity = inten_model.IntenGNN.load_from_checkpoint(str(paths[1]), map_location="cpu", weights_only=False)
        model = joint_model.JointModel(generation, intensity)
    return model.to(args.device).eval().requires_grad_(False), paths


def predict_request(args):
    """Direct online molecule prediction; no observed spectrum or cached answer required."""
    import torch
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors
    model, paths = load_frozen_model(args)
    import ms_pred.common as common

    row = json.loads(args.predict_request.read_text())
    molecule = Chem.MolFromSmiles(row["smiles"])
    if molecule is None or not molecule.GetNumAtoms() or molecule.GetNumHeavyAtoms() > 100:
        raise ValueError("Require a valid molecule with at most 100 heavy atoms")
    instrument, adduct = row["instrument"], row["adduct"]
    if instrument not in common.instrument2onehot_pos or adduct not in common.ion2mass:
        raise ValueError("Unsupported instrument or adduct")
    ce = common.collision_energy_to_float(str(row["collision_energy"]))
    if not np.isfinite(ce):
        raise ValueError("A finite collision energy is required")
    precursor = float(row.get("precursor_mz") or (rdMolDescriptors.CalcExactMolWt(molecule) + common.ion2mass[adduct]))
    with torch.inference_mode():
        if args.model == "glacier":
            prediction = model.predict_mol(row["smiles"], ce, adduct, args.device, instrument=instrument)["spec"]
        else:
            prediction = model.predict_mol([row["smiles"]], [ce], [precursor], [adduct], threshold=0., device=args.device,
                                          max_nodes=100, instrument=[instrument], binned_out=False, canonical_root_smi=True)["spec"][0]
    peaks = prediction.detach().cpu().numpy()
    if peaks.ndim != 2 or peaks.shape[1] != 2 or not np.isfinite(peaks).all():
        raise ValueError("Model produced invalid mass/intensity pairs")
    output = {"model": args.model, "training_performed": False, "inference_mode": "direct_frozen_checkpoint",
              "smiles": Chem.MolToSmiles(molecule, isomericSmiles=True), "adduct": adduct, "instrument": instrument,
              "collision_energy": float(ce), "precursor_mz": precursor, "predicted_peaks": peaks.tolist(),
              "checkpoints": [{"name": path.name, "sha256": sha256(path)} for path in paths]}
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    return 0


def evaluate(args):
    import torch
    torch.set_num_threads(args.threads)
    sys.path.insert(0, str(args.source / "src"))
    import ms_pred.common as common

    rows, selection = select_ms_records(args.input_csv, args.metadata_tsv, args.limit, args.max_heavy_atoms, not args.allow_repeated_molecules)
    paths = ([args.weights / "weights_glacier/best.ckpt"] if args.model == "glacier" else
             [args.weights / "weights_iceberg/gen/best.ckpt", args.weights / "weights_iceberg/inten_contr/best.ckpt"])
    report = {"task": f"ms.forward.{args.model}", "training_performed": False, "inference_mode": "direct_frozen_checkpoint",
              "dataset": {"path": str(args.input_csv), "sha256": sha256(args.input_csv), "split": "test"},
              "metadata": {"path": str(args.metadata_tsv), "sha256": sha256(args.metadata_tsv)},
              "checkpoints": [{"path": str(path), "sha256": sha256(path)} for path in paths],
              "selection": selection, "sampling": f"first_real_test_records_with_at_most_{args.max_heavy_atoms}_heavy_atoms",
              "unique_molecules": len({row['smiles'] for row in rows}),
              "scoring": {"num_bins": 150000, "upper_limit_da": 1500, "pooling": "max", "prediction_top_peaks": 100,
                          "reference": "all_observed_peaks_from_our_test_CSV_without_MAGMa_filtering"},
              "training_overlap_audit": "pretrained_MassSpecGym_weights; our_split_overlap_not_independently_reaudited",
              "device": args.device, "records": []}
    model, _ = load_frozen_model(args)
    started = time.monotonic()
    for row in rows:
        print(json.dumps({"event": "predicting", "model": args.model, "spec_id": row["spec_id"]}), flush=True)
        entry = dict(row)
        try:
            instrument = row["instrument"]
            if not str(row["collision_energy"]).strip() or instrument not in common.instrument2onehot_pos:
                raise UnsupportedCondition("Missing collision energy or unsupported/missing instrument; no imputation performed")
            try:
                ce = common.collision_energy_to_float(row["collision_energy"])
            except (ValueError, IndexError, TypeError) as error:
                raise UnsupportedCondition(f"Unparseable collision energy: {row['collision_energy']}") from error
            if not np.isfinite(ce):
                raise UnsupportedCondition("Nonfinite collision energy; no imputation performed")
            entry["resolved_collision_energy"] = float(ce)
            with torch.inference_mode():
                if args.model == "glacier":
                    predicted = model.predict_mol(row["smiles"], ce, row["adduct"], args.device, instrument=instrument)["spec"]
                else:
                    predicted = model.predict_mol([row["smiles"]], [ce], [row["precursor_mz"]], [row["adduct"]],
                                                  threshold=0., device=args.device, max_nodes=100, instrument=[instrument],
                                                  binned_out=False, canonical_root_smi=True)["spec"][0]
            predicted = predicted.detach().cpu().numpy()
            entry.update(status="passed", predicted_peaks=predicted.tolist(), metrics=spectrum_metrics(predicted, row["reference_peaks"]))
        except UnsupportedCondition as error:
            entry.update(status="skipped", reason=str(error))
        except Exception as error:
            import traceback
            traceback.print_exc()
            entry.update(status="failed", reason=f"{type(error).__name__}: {error}")
        report["records"].append(entry)
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    successful = [row["metrics"] for row in report["records"] if row["status"] == "passed"]
    report["counts"] = dict(Counter(row["status"] for row in report["records"]))
    report["metrics"] = {name: float(np.mean([row[name] for row in successful])) for name in ("cosine_similarity", "entropy_similarity")} if successful else {}
    report["completed"] = True
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps({"counts": report["counts"], "metrics": report["metrics"]}), flush=True)
    return int(bool(report["counts"].get("failed")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parent = Path(__file__).resolve().parents[3]
    parser.add_argument("--model", choices=("glacier", "iceberg"), required=True)
    parser.add_argument("--source", type=Path, default=parent / "ms-pred-repro")
    parser.add_argument("--weights", type=Path, default=parent / "mspred")
    parser.add_argument("--input-csv", type=Path, default=parent / "MassSpecGym-MAGMA-annotation/data/MassSpecGym_test_full.csv")
    parser.add_argument("--metadata-tsv", type=Path, default=parent / "MassSpecGym-MAGMA-annotation/data/MassSpecGym1.5.tsv")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--max-heavy-atoms", type=int, default=40)
    parser.add_argument("--allow-repeated-molecules", action="store_true")
    parser.add_argument("--predict-request", type=Path, help="JSON molecule request for direct online inference")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output file; existing results are preserved")
    if min(args.limit, args.max_heavy_atoms, args.threads) < 1:
        parser.error("Sizes must be positive")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    return predict_request(args) if args.predict_request else evaluate(args)


if __name__ == "__main__":
    sys.exit(main())
