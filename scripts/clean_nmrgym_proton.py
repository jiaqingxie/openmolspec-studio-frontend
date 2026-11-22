"""Quarantine suspicious NMRGym training spectra, retaining their original shifts and audit trail."""

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import tempfile

import numpy as np
from rdkit import Chem, RDLogger

from openmolspec_bench.data import sha256

COMMON_ELEMENTS = {1, 5, 6, 7, 8, 9, 14, 15, 16, 17, 35, 53}
POLICY = {
    "cross_nucleus_copy": "Identical sorted H and C lists including multiplicities, with at least one absolute shift >25 ppm.",
    "extreme_organic": "At least one absolute H shift >50 ppm in a neutral single-fragment structure made of H/B/C/N/O/F/Si/P/S/Cl/Br/I with no RDKit radical electrons.",
    "action": "Quarantine whole training records. Preserve repeated shifts and the original peak count of every retained spectrum. Flag other H shifts outside +/-25 ppm for review.",
}


def reasons(smiles, protons, carbon):
    extreme = max(abs(v) for v in protons)
    if extreme <= 25:
        return []
    found = []
    if sorted(protons) == sorted(carbon):
        found.append("cross_nucleus_copy")
    if extreme > 50:
        mol = Chem.MolFromSmiles(smiles)
        if (
            mol is not None
            and len(Chem.GetMolFrags(mol)) == 1
            and Chem.GetFormalCharge(mol) == 0
            and all(
                a.GetAtomicNum() in COMMON_ELEMENTS and a.GetNumRadicalElectrons() == 0
                for a in mol.GetAtoms()
            )
        ):
            found.append("extreme_organic")
    return found


def shift_list(row, field):
    return [
        float(token)
        for rec in row[field]
        for token in rec["chemical_shift"].split(",")
        if token.strip()
    ]


def prepare(cache, raw, out):
    split = json.loads((cache / "split.json").read_text())
    if (
        sha256(raw) != split["sources"]["train"]
        or sha256(cache / "train.jsonl") != split["split_digests"]["train"]
    ):
        raise ValueError("Training inputs differ from the v2 split")
    keys = np.load(cache / "train-keys.npy").astype(str)
    expected = set(keys)
    # Match the original H/C pair by the exact SMILES and proton list, including token order.
    suspicious = {}
    with raw.open() as stream:
        for line in stream:
            row = json.loads(line)
            h = shift_list(row, "h_nmr")
            if h and max(map(abs, h)) > 25:
                signature = (row["smiles"], tuple(h))
                carbon = shift_list(row, "c_nmr")
                if signature in suspicious and suspicious[signature] != carbon:
                    raise ValueError("Ambiguous carbon list for suspected spectrum")
                suspicious[signature] = carbon
    removed = set()
    seen = set()
    totals, overlap = Counter(), Counter()
    written_peaks = excluded_peaks = repeated_retained = review = 0
    with (
        (cache / "train.jsonl").open() as stream,
        (out / "train.jsonl").open("w") as retained,
        (out / "audit.jsonl").open("w") as audit,
    ):
        for line in stream:
            key, smiles, h = json.loads(line)
            if key not in expected:
                continue
            if key in seen:
                raise ValueError("Duplicate training connectivity")
            seen.add(key)
            if max(map(abs, h)) > 25:
                carbon = suspicious[(smiles, tuple(h))]
                flags = reasons(smiles, h, carbon)
                audit.write(
                    json.dumps(
                        dict(
                            connectivity=key,
                            smiles=smiles,
                            h_shift=h,
                            c_shift=carbon,
                            reasons=flags,
                            action="quarantine" if flags else "retain_for_review",
                        )
                    )
                    + "\n"
                )
                if flags:
                    totals.update(flags)
                    overlap["+".join(flags)] += 1
                    removed.add(key)
                    excluded_peaks += len(h)
                    continue
                review += 1
            retained.write(line)
            written_peaks += len(h)
            repeated_retained += len(h) != len(set(h))
    if seen != expected:
        raise ValueError("Training records missing for cached features")
    keep = np.array([k not in removed for k in keys])
    for name in ("x", "ref", "counts", "keys"):
        arr = np.load(cache / f"train-{name}.npy")
        if len(arr) != len(keep):
            raise ValueError(f"Wrong length in cached {name}")
        np.save(out / f"train-{name}.npy", arr[keep], allow_pickle=False)
    for name in (
        "val.jsonl",
        "val-x.npy",
        "val-ref.npy",
        "val-counts.npy",
        "val-keys.npy",
        "val-cache.json",
        "val-baseline.jsonl",
        "val-baseline.sha256",
    ):
        shutil.copyfile(cache / name, out / name)
    meta = json.loads((cache / "train-cache.json").read_text())
    meta.update(usable=int(keep.sum()), input=len(keys))
    (out / "train-cache.json").write_text(json.dumps(meta) + "\n")
    qc = dict(
        policy=POLICY,
        before=len(keys),
        after=int(keep.sum()),
        quarantined=len(removed),
        rule_counts=dict(totals),
        mutually_exclusive_counts=dict(overlap),
        retained_for_review=review,
        retained_spectra_with_repeats=repeated_retained,
        retained_shift_entries=written_peaks,
        quarantined_shift_entries=excluded_peaks,
        raw_training_sha256=sha256(raw),
        cleaned_train_sha256=sha256(out / "train.jsonl"),
        audit_sha256=sha256(out / "audit.jsonl"),
    )
    (out / "cleaning.json").write_text(json.dumps(qc, indent=2) + "\n")
    split["parent_split_digests"] = dict(split["split_digests"])
    split["split_digests"]["train"] = qc["cleaned_train_sha256"]
    split["eligible_train"] = qc["after"]
    split["cleaning"] = qc
    (out / "split.json").write_text(json.dumps(split, indent=2) + "\n")
    print(json.dumps(qc, indent=2), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--raw", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    RDLogger.DisableLog("rdApp.*")
    if args.out.exists():
        raise FileExistsError(args.out)
    args.out.parent.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as tmp:
        stage = Path(tmp) / "data"
        stage.mkdir()
        prepare(args.cache, args.raw, stage)
        stage.rename(args.out)
