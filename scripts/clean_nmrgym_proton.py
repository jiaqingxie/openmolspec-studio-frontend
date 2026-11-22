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


def paired_training_rows(cache, raw, expected, all_rows):
    required = {}
    with (cache / "train.jsonl").open() as stream:
        for line in stream:
            key, smi, h = json.loads(line)
            if key in expected and (all_rows or max(map(abs, h)) > 25):
                if smi in required:
                    raise ValueError("Ambiguous specialist training structure")
                required[smi] = h
    pairs = {}
    with raw.open() as stream:
        for line in stream:
            row = json.loads(line)
            smi = row["smiles"]
            if smi in required and shift_list(row, "h_nmr") == required[smi]:
                pair = required[smi], shift_list(row, "c_nmr")
                if smi in pairs and pair != pairs[smi]:
                    raise ValueError("Ambiguous original H/C pair")
                pairs[smi] = pair
    if required.keys() != pairs.keys():
        raise ValueError("Missing original H/C pair")
    return pairs


def prepare(cache, raw, out, bank=None, sdf=None):
    split = json.loads((cache / "split.json").read_text())
    if (
        sha256(raw) != split["sources"]["train"]
        or sha256(cache / "train.jsonl") != split["split_digests"]["train"]
    ):
        raise ValueError("Training inputs differ from the v2 split")
    keys = np.load(cache / "train-keys.npy").astype(str)
    expected = set(keys)
    if bool(bank) != bool(sdf):
        raise ValueError(
            "Supply both --nmrbank and --shiftdb to reconcile source spectra"
        )
    pairs = paired_training_rows(cache, raw, expected, bool(bank))
    decisions = {}
    if bank:
        from openmolspec_bench.nmrgym_source_labels import source_decisions

        decisions = source_decisions(pairs, bank, sdf)
    repaired, repair_counts = {}, Counter()
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
            decision = decisions.get(smiles)
            if decision or max(map(abs, h)) > 25:
                carbon = pairs[smiles][1]
                new = decision["replacement"] if decision else None
                if decision and not new:
                    flags = [decision["reason"]]
                else:
                    flags = reasons(smiles, new or h, carbon)
                action = (
                    "quarantine"
                    if flags
                    else ("repair" if new else "retain_for_review")
                )
                audit.write(
                    json.dumps(
                        dict(
                            connectivity=key,
                            smiles=smiles,
                            h_shift=h,
                            c_shift=carbon,
                            reasons=flags,
                            action=action,
                            **({"source_decision": decision} if decision else {}),
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
                if new:
                    h = repaired[key] = new
                    repair_counts[decision["reason"]] += 1
                    line = json.dumps([key, smiles, h]) + "\n"
                else:
                    review += 1
            retained.write(line)
            written_peaks += len(h)
            repeated_retained += len(h) != len(set(h))
    if seen != expected:
        raise ValueError("Training records missing for cached features")
    keep = np.array([k not in removed for k in keys])
    if repaired:
        from openmolspec.nmrgym_proton import GRID, resample

        repaired_ix = [(i, repaired[k]) for i, k in enumerate(keys) if k in repaired]
    for name in ("x", "ref", "counts", "keys"):
        arr = np.load(cache / f"train-{name}.npy")
        if len(arr) != len(keep):
            raise ValueError(f"Wrong length in cached {name}")
        if repaired and name in ("ref", "counts"):
            for i, shifts in repaired_ix:
                if name == "ref":
                    arr[i] = resample(shifts, len(GRID))
                else:
                    arr[i, 1] = len(shifts)
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
    if bank:
        qc["policy"] = {
            **POLICY,
            "action": "Correct labels corroborated by identified source records. Quarantine carbon-only records, conflicting proposals, and unresolved spectra meeting the original exclusion rules. Other retained training labels are copied verbatim.",
        }
        qc.update(
            source_repaired=len(repaired),
            repairs_by_reason=dict(repair_counts),
            sources_sha256={"NMRBank": sha256(bank), "nmrshiftdb2": sha256(sdf)},
            source_policy="Only cached training identities. Match nucleus-labelled spectra to the original H and C lists. Report one center per multiplet, preserve repeated signals, and quarantine conflicting or carbon-only matches.",
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
    p.add_argument(
        "--nmrbank",
        type=Path,
        help="NMRBank CSV ZIP for source-based repairs (use with --shiftdb)",
    )
    p.add_argument(
        "--shiftdb", type=Path, help="Assigned nmrshiftdb2 SDF for source-based repairs"
    )
    args = p.parse_args()
    RDLogger.DisableLog("rdApp.*")
    if args.out.exists():
        raise FileExistsError(args.out)
    args.out.parent.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as tmp:
        stage = Path(tmp) / "data"
        stage.mkdir()
        prepare(args.cache, args.raw, stage, args.nmrbank, args.shiftdb)
        stage.rename(args.out)
