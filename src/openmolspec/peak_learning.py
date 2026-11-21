"""Estimate H/C site shifts using observed spectra matched to atom environments."""

import gzip
import json
from pathlib import Path

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator
from .solution_shifts import _generator


def environments(mol):
    ranks = Chem.CanonicalRankAtoms(mol, breakTies=False, includeChirality=True)
    groups = {}
    for atom, rank in zip(mol.GetAtoms(), ranks):
        groups.setdefault(rank, []).append(atom.GetIdx())
    info = rdFingerprintGenerator.AdditionalOutput()
    info.AllocateBitInfoMap()
    _generator().GetSparseCountFingerprint(mol, additionalOutput=info)
    codes = np.zeros((mol.GetNumAtoms(), 6), dtype=np.uint32)
    for code, spots in info.GetBitInfoMap().items():
        for idx, radius in spots:
            codes[idx, radius] = code
    groups = list(groups.values())
    roots = [g[0] for g in groups]
    h = np.array(
        [
            mol.GetAtomWithIdx(i).GetTotalNumHs(includeNeighbors=True) > 0
            and mol.GetAtomWithIdx(i).GetAtomicNum() > 1
            for i in roots
        ],
        dtype=bool,
    )
    c = np.array([mol.GetAtomWithIdx(i).GetAtomicNum() == 6 for i in roots], dtype=bool)
    return groups, codes[roots], h, c


def estimate(codes, tables, prior, minimum=3, shrink=3.0):
    values = np.full(len(codes), prior, dtype=float)
    supported = np.zeros(len(codes), dtype=bool)
    for j, c in enumerate(codes):
        for radius, token in enumerate(c):
            entry = tables[radius].get(int(token))
            if entry is None or entry[1] < minimum:
                continue
            median, n = entry
            weight = n / (n + shrink) if supported[j] else 1.0
            values[j] = values[j] * (1 - weight) + median * weight
            supported[j] = True
    return values


class PeakLearningPredictor:
    """Load a fitted hierarchy of rooted Morgan environments for hydrogen or carbon."""

    def __init__(self, directory, *, sha256=None):
        from openmolspec_bench.data import sha256 as file_digest

        path = Path(directory) / "environments.json.gz"
        if sha256 and file_digest(path) != sha256:
            raise ValueError("Peak environment checksum mismatch")
        with gzip.open(path, "rt") as stream:
            self.config = json.load(stream)
        for key in ("seed_tables", "tables"):
            self.config[key] = [
                {int(k): v for k, v in table.items()} for table in self.config[key]
            ]
        self.nucleus = self.config["nucleus"]
        if self.nucleus not in ("1H", "13C"):
            raise ValueError("Expected 1H or 13C")

    def predict(self, smiles, solvent=None):
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError("Invalid SMILES")
        groups, codes, h, c = environments(mol)
        use = np.flatnonzero(h if self.nucleus == "1H" else c)
        cfg = self.config
        base = estimate(codes[use], cfg["seed_tables"], cfg["center"])
        matched = estimate(
            codes[use], cfg["tables"], cfg["center"], minimum=cfg["min_support"]
        )
        values = (1 - cfg["weight"]) * base + cfg["weight"] * matched
        return [
            dict(atom_indices=groups[i], shift_ppm=float(v))
            for i, v in zip(use, values)
        ]
