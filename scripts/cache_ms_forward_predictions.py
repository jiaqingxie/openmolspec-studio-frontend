"""Cache author model peaks for a reproducible sample of a named MassSpecGym partition."""

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from openmolspec_bench.data import sha256
from openmolspec_bench.ms import load_frozen_model, select_ms_records


def main():
    import numpy as np
    import torch
    from rdkit import Chem

    p = argparse.ArgumentParser(description=__doc__)
    for name in ("data", "source", "weights", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--model", choices=["glacier", "iceberg"], required=True)
    p.add_argument("--split", choices=["val", "test"], required=True)
    p.add_argument("--limit", type=int, default=384)
    p.add_argument("--device", default="cpu")
    p.add_argument("--threads", type=int, default=2)
    args = p.parse_args()
    torch.set_num_threads(args.threads)
    sys.path.insert(0, str(args.source.resolve() / "src"))
    import ms_pred.common as common

    args.output.mkdir(parents=True, exist_ok=True)
    tab = args.data / "MassSpecGym1.5.tsv"
    split_csv = args.data / f"MassSpecGym_{args.split}_full.csv"
    selected = {}
    with split_csv.open() as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        for row in reader:
            smi = row["smiles"]
            mol = Chem.MolFromSmiles(smi)
            if mol is None or mol.GetNumHeavyAtoms() > 40:
                continue
            key = Chem.MolToInchiKey(mol).split("-")[0]
            if not key:
                continue
            order = hashlib.sha256(("oms-ms-v1:" + row["spec_id"]).encode()).digest()
            if key not in selected or order < selected[key][0]:
                selected[key] = order, row
    sample = sorted(selected.items(), key=lambda kv: kv[1][0])[: args.limit]
    subset = args.output / f"{args.model}-{args.split}-sample.csv"
    with subset.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(row for _, (_, row) in sample)
    rows, coverage = select_ms_records(subset, tab, args.limit)
    keys = {row["spec_id"]: key for key, (_, row) in sample}
    model, paths = load_frozen_model(args)
    dest = args.output / f"{args.model}-{args.split}.jsonl.gz"
    completed = set()
    if dest.exists():
        with gzip.open(dest, "rt") as f:
            completed = {json.loads(line)["spec_id"] for line in f}
    for i, row in enumerate(rows):
        if row["spec_id"] in completed:
            continue
        row["key"] = keys[row["spec_id"]]
        instrument = row["instrument"]
        try:
            ce = (
                common.collision_energy_to_float(row["collision_energy"])
                if row["collision_energy"].strip()
                else float("nan")
            )
            if not np.isfinite(ce) or instrument not in common.instrument2onehot_pos:
                raise ValueError("unsupported acquisition conditions")
            with torch.inference_mode():
                if args.model == "glacier":
                    pred = model.predict_mol(
                        row["smiles"],
                        ce,
                        row["adduct"],
                        args.device,
                        instrument=instrument,
                    )["spec"]
                else:
                    pred = model.predict_mol(
                        [row["smiles"]],
                        [ce],
                        [row["precursor_mz"]],
                        [row["adduct"]],
                        threshold=0.0,
                        device=args.device,
                        max_nodes=100,
                        instrument=[instrument],
                        binned_out=False,
                        canonical_root_smi=True,
                    )["spec"][0]
            peaks = pred.detach().cpu().numpy()
            if not np.isfinite(peaks).all() or np.any(peaks < 0):
                raise ValueError("invalid predicted peaks")
            row["predicted_peaks"] = peaks[peaks[:, 1] > 0].tolist()
            row["status"] = "passed"
        except (ValueError, KeyError, RuntimeError, IndexError, TypeError) as e:
            row.update(status="skipped", reason=str(e))
        with gzip.open(dest, "at", compresslevel=2) as f:
            f.write(json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n")
        if i % 20 == 0:
            print(args.split, i, row["status"], flush=True)
    manifest = dict(
        model=args.model,
        split=args.split,
        source_sha256=sha256(split_csv),
        metadata_sha256=sha256(tab),
        checkpoints=[sha256(path) for path in paths],
        identities_sampled=len(sample),
        identities_available=len(selected),
        selection=coverage,
        output_sha256=sha256(dest),
    )
    dest.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
