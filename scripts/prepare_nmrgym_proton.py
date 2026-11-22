"""Prepare disjoint NMRGym proton spectra and frozen model features."""

import argparse
from collections import Counter
import hashlib
import json
import pickle
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from rdkit import Chem, RDLogger
from openmolspec_bench.data import sha256


def connectivity(row):
    inchi = row.get("inchi", "")
    if inchi.startswith("InChI="):
        return Chem.InchiToInchiKey(inchi).split("-")[0]
    mol = Chem.MolFromSmiles(row["smiles"])
    return Chem.MolToInchiKey(mol).split("-")[0] if mol else ""


def spectra(path, reserved, seen):
    stats = Counter()
    with path.open() as stream:
        for line in stream:
            row = json.loads(line)
            key = connectivity(row)
            stats["input"] += 1
            if len(key) != 14 or key in reserved or key in seen:
                stats["reserved_or_duplicate"] += 1
                continue
            peaks = [
                float(v)
                for record in row["h_nmr"]
                for v in record["chemical_shift"].split(",")
                if v.strip()
            ]
            if not peaks or not all(abs(v) < float("inf") for v in peaks):
                stats["missing_or_nonfinite"] += 1
                continue
            seen.add(key)
            yield key, row["smiles"], peaks
    print(path.name, dict(stats), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=ROOT / "../data/nmrgym_only")
    p.add_argument("--external", type=Path, default=ROOT / "../data/align_eval")
    p.add_argument(
        "--official-test",
        type=Path,
        default=ROOT / "../../data/benchmarks/NMRGym_test_balanced_dedup.pkl",
    )
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    RDLogger.DisableLog("rdApp.*")
    a.output.mkdir(parents=True, exist_ok=True)
    with a.official_test.open("rb") as stream:
        official = pickle.load(stream)
    reserved = {connectivity(row) for row in official}
    sources = {"official_test": sha256(a.official_test)}
    for corpus in ("patent_test_10k", "nmrspec_test", "nmrexp_exp_10k", "nmrgym_test"):
        path = a.external / corpus / "test.jsonl"
        with path.open() as stream:
            reserved.update(connectivity(json.loads(line)) for line in stream)
        sources[corpus] = sha256(path)
    print("Reserved official test and benchmark keys", len(reserved), flush=True)
    val_keys, train_keys = set(), set()
    val = sorted(
        spectra(a.data / "val.jsonl", reserved, val_keys),
        key=lambda r: hashlib.sha256(("nmrgym-v1:" + r[0]).encode()).digest(),
    )
    # Reserve the entire validation view; take a reproducible development panel.
    selected = val[:3072]
    with (a.output / "val.jsonl").open("w") as stream:
        for row in selected:
            stream.write(json.dumps(row) + "\n")
    with (a.output / "train.jsonl").open("w") as stream:
        for row in spectra(a.data / "train.jsonl", reserved | val_keys, train_keys):
            stream.write(json.dumps(row) + "\n")
    assert not (train_keys & val_keys or train_keys & reserved or val_keys & reserved)
    for split in ("train", "val"):
        sources[split] = sha256(a.data / (split + ".jsonl"))
    info = dict(
        sources=sources,
        official_test_rows=len(official),
        reserved_connectivities=len(reserved),
        eligible_train=len(train_keys),
        eligible_validation=len(val_keys),
        validation_panel=len(selected),
        train_validation_overlap=0,
        train_reserved_overlap=0,
        validation_reserved_overlap=0,
        split_digests={s: sha256(a.output / (s + ".jsonl")) for s in ("train", "val")},
    )
    (a.output / "split.json").write_text(json.dumps(info, indent=2) + "\n")
    print(info, flush=True)


if __name__ == "__main__":
    main()
