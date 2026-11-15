"""Strict inference records for the existing H/C encoder."""

import hashlib
import io
import json
import pickle
import random
from pathlib import Path
import shutil
import tempfile


class CpuUnpickler(pickle.Unpickler):
    """Read trusted PyTorch prediction pickles on CPU, including CUDA storages."""

    def find_class(self, module, name):
        if module == "torch.storage" and name == "_load_from_bytes":
            import torch
            return lambda value: torch.load(io.BytesIO(value), map_location="cpu", weights_only=False)
        return super().find_class(module, name)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def readonly_lmdb(path):
    """Mirror LMDB locally on filesystems that cannot mmap (for example some NFS mounts)."""
    import lmdb

    path = Path(path).resolve()
    options = dict(subdir=False, readonly=True, lock=False, readahead=False, meminit=False)
    try:
        return lmdb.open(str(path), **options)
    except lmdb.Error as error:
        if "No such device" not in str(error):
            raise
        stat = path.stat()
        identity = hashlib.sha256(f"{path}:{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()
        destination = Path(tempfile.gettempdir()) / "openmolspec-bench-lmdb" / identity / path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.is_file():
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
                temporary = Path(stream.name)
            try:
                shutil.copyfile(path, temporary)
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        return lmdb.open(str(destination), **options)


def select_vibrational_rows(environment, limit, sampling="first", seed=42, require_gap=False):
    """Select distinct real structures; optional seeded reservoir spans the entire test pool."""
    from rdkit import Chem
    from collections import Counter

    selected, seen, counts = [], set(), Counter()
    rng = random.Random(seed)
    eligible = 0
    with environment.begin() as transaction:
        for key, value in transaction.cursor():
            row = pickle.loads(value)
            counts["read"] += 1
            if require_gap and row.get("gap") is None:
                counts["missing_gap"] += 1
                continue
            molecule = Chem.MolFromSmiles(row["kekule_smiles"])
            if molecule is None:
                raise ValueError(f"Invalid vibrational reference at {key!r}")
            identity = Chem.MolToSmiles(molecule, isomericSmiles=True)
            if identity in seen:
                counts["duplicate_structure"] += 1
                continue
            seen.add(identity)
            row = {**row, "_lmdb_key": key.decode(), "_canonical_identity": identity}
            eligible += 1
            if len(selected) < limit:
                selected.append(row)
            elif sampling == "reservoir":
                index = rng.randrange(eligible)
                if index < limit:
                    selected[index] = row
            if sampling == "first" and len(selected) >= limit:
                break
    counts["eligible_distinct_structures"] = eligible
    counts["selected"] = len(selected)
    return selected, dict(counts)


def normalize_record(row):
    """Accept legacy field aliases without inventing a missing molecular formula."""
    from rdkit import Chem

    row = dict(row)
    for key, nucleus in (("h_nmr", "1H"), ("c_nmr", "13C")):
        value = row.get(key) or []
        if isinstance(value, str):
            value = [{"type": f"{nucleus} NMR", "chemical_shift": value}]
        if not isinstance(value, list) or any(not isinstance(v, dict) for v in value):
            raise ValueError(f"Invalid {key}: expected record list or prose")
        row[key] = value
    mask = row.get("modality_mask", [int(bool(row["h_nmr"])), int(bool(row["c_nmr"]))])
    if len(mask) != 2 or any(v not in (0, 1) for v in mask):
        raise ValueError("modality_mask must contain two 0/1 flags")
    if any(flag and not row[key] for flag, key in zip(mask, ("h_nmr", "c_nmr"))):
        raise ValueError("Visible modality has no NMR records")
    row["modality_mask"] = list(mask)
    row["formula"] = row.get("formula") or row.get("molecular_formula") or ""
    molecule = Chem.MolFromSmiles(row.get("smiles", ""))
    if molecule is None or not molecule.GetNumAtoms():
        raise ValueError("A nonempty valid reference SMILES is required")
    row["smiles"] = Chem.MolToSmiles(molecule, isomericSmiles=True)
    return row


def load_rows(path, view, limit, max_smiles_bytes=None):
    rows, seen = [], set()
    counts = {"read": 0, "missing_modality": 0, "duplicate_structure": 0, "exceeds_model_capacity": 0}
    with open(path, encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = normalize_record(json.loads(line))
            except (ValueError, TypeError, KeyError) as error:
                raise ValueError(f"{path}:{number}: {error}") from error
            counts["read"] += 1
            if max_smiles_bytes is not None and len(row["smiles"].encode("utf-8")) > max_smiles_bytes:
                counts["exceeds_model_capacity"] += 1
                continue
            mask = row["modality_mask"]
            visible = {"h": [mask[0], 0], "c": [0, mask[1]],
                       "hc": mask if mask == [1, 1] else [0, 0]}[view]
            if not any(visible):
                counts["missing_modality"] += 1
                continue
            if row["smiles"] in seen:
                counts["duplicate_structure"] += 1
                continue
            seen.add(row["smiles"])
            rows.append({**row, "modality_mask": visible})
            if len(rows) >= limit:
                break
    if not rows:
        raise ValueError(f"No {view} examples in {path}")
    return rows, counts
