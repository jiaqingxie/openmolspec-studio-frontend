"""Prepare rooted atom environments and measured peak sets for training without atom assignments."""

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import pickle
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import numpy as np
from rdkit import Chem, RDLogger
from openmolspec.peak_learning import environments
from openmolspec_bench.data import sha256
from prepare_assigned_hc import EXTERNAL


def read_compounds(path):
    with path.open() as f:
        for line in f:
            yield json.loads(line)


def identity(row):
    if row.get("inchi"):
        key = Chem.InchiToInchiKey(row["inchi"])
        if key:
            return key.split("-")[0]
    mol = Chem.MolFromSmiles(row["smiles"])
    return Chem.MolToInchiKey(mol).split("-")[0] if mol is not None else None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("gym", "external", "assigned", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(exist_ok=True, parents=True)
    RDLogger.DisableLog("rdApp.*")
    val_keys = {identity(r) for r in read_compounds(a.gym / "val.jsonl")}
    ext = {
        identity(r)
        for name in EXTERNAL
        for r in read_compounds(a.external / name / "test.jsonl")
    }
    heldout = set()
    with gzip.open(a.assigned, "rt") as f:
        for line in f:
            key, role, *_ = json.loads(line)
            if role != "train":
                heldout.add(key)
    counts = Counter()
    for role in ("val", "train"):
        dest = a.output / (role + ".pkl.gz")
        seen = set()
        reserved = ext | heldout | (val_keys if role == "train" else set())
        temp = dest.with_suffix(".partial")
        with gzip.open(temp, "wb", compresslevel=2) as out:
            for row in read_compounds(a.gym / (role + ".jsonl")):
                counts[role + "_input"] += 1
                key = identity(row)
                if not key or key in reserved or key in seen:
                    continue
                m = Chem.MolFromSmiles(row["smiles"])
                if m is None or len(Chem.GetMolFrags(m)) != 1:
                    continue
                if Chem.MolToInchiKey(m).split("-")[0] != key:
                    counts[role + "_smiles_inchi_mismatch"] += 1
                    continue
                # NMRGym's converted rows contain comma-separated numerical peak centers.
                peaks = []
                for sym in ("h", "c"):
                    values = {
                        float(v)
                        for r in row[sym + "_nmr"]
                        for v in r["chemical_shift"].split(",")
                        if v.strip()
                    }
                    peaks.append(np.array(sorted(values), dtype="f"))
                if not all(np.isfinite(q).all() and len(q) for q in peaks):
                    continue
                groups, codes, h, c = environments(m)
                if not h.any() or not c.any():
                    continue
                pickle.dump((key, row["smiles"], codes, h, c, *peaks), out, protocol=5)
                seen.add(key)
                if len(seen) % 25000 == 0:
                    print(role, len(seen), flush=True)
        temp.replace(dest)
        counts[role + "_retained"] = len(seen)
    metadata = dict(
        counts=counts,
        external_keys=len(ext),
        assigned_holdout_keys=len(heldout),
        excluded_validation_keys=len(val_keys),
        inputs={
            str(path): sha256(path)
            for path in [a.assigned, a.gym / "val.jsonl", a.gym / "train.jsonl"]
        },
        files={n: sha256(a.output / (n + ".pkl.gz")) for n in ("train", "val")},
    )
    (a.output / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(counts, flush=True)


if __name__ == "__main__":
    main()
