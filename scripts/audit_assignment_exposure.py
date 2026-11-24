"""Bound NMRNet liquid-data overlap using heavy-element counts from its public archive."""

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import shutil
import tempfile
from zipfile import ZipFile

import lmdb
from rdkit import Chem


def composition(symbols):
    return tuple(
        sorted(Counter(s for s in symbols if s not in ("H", "D", "T")).items())
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "dataset", "previous", "output", "exclusions"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    with args.archive.open("rb") as f:
        hasher = hashlib.md5()
        for chunk in iter(lambda: f.read(2**20), b""):
            hasher.update(chunk)
        digest = hasher.hexdigest()
    if digest != "75fe82a1c9ef7a6749cbf3a3896f198f":
        raise ValueError("Expected the published NMRNet data.zip checksum")
    formulas = set()
    files = {}
    with ZipFile(args.archive) as archive, tempfile.TemporaryDirectory() as temporary:
        local = Path(temporary) / "split.lmdb"
        for name in sorted(archive.namelist()):
            if not name.startswith("data/nmrshiftdb2_") or not name.endswith(".lmdb"):
                continue
            with archive.open(name) as src, local.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            with (
                lmdb.open(str(local), readonly=True, subdir=False, lock=False) as db,
                db.begin() as txn,
            ):
                count = 0
                for _, value in txn.cursor():
                    atoms = pickle.loads(value)["atoms"]
                    if not atoms or any(
                        not s or not Chem.GetPeriodicTable().GetAtomicNumber(s)
                        for s in atoms
                    ):
                        raise ValueError("Missing or unknown atom in " + name)
                    formulas.add(composition(atoms))
                    count += 1
            files[name] = count
    eligible = defaultdict(set)
    blocked = set()
    with gzip.open(args.dataset, "rt") as stream:
        for key, split, smiles, nucleus, _, _ in map(json.loads, stream):
            if split != "test":
                continue
            mol = Chem.MolFromSmiles(smiles)
            if composition(a.GetSymbol() for a in mol.GetAtoms()) in formulas:
                blocked.add(key)
            else:
                eligible[nucleus].add(key)
    args.exclusions.write_text(json.dumps(sorted(blocked)) + "\n")
    previous = json.loads(args.previous.read_text())
    report = dict(
        archive="https://zenodo.org/records/19142375",
        archive_md5=digest,
        rule="Exclude every test structure with the same heavy-element counts as any public 2018 or 2024 NMRShiftDB liquid train OR validation row. Coordinates lack molecule identifiers. Isomers with matching composition are excluded together.",
        scope="Disjoint from named liquid archives by composition; other pretraining exposure is unknown.",
        archive_rows=files,
        distinct_heavy_compositions=len(formulas),
        eligible={},
        previous_clean={},
    )
    for nucleus, keys in eligible.items():
        eligible_keys = keys - blocked
        report["eligible"][nucleus] = len(eligible_keys)
        records = [
            r
            for r in previous["nuclei"][nucleus]["records"]
            if r["connectivity"] in eligible_keys
        ]
        n = sum(r["peaks"] for r in records)
        c = sum(r["correct"] for r in records)
        report["previous_clean"][nucleus] = dict(
            connectivities=len({r["connectivity"] for r in records}),
            correct=c,
            peaks=n,
            accuracy=c / n if n else None,
        )
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(report["eligible"], report["previous_clean"])


if __name__ == "__main__":
    main()
