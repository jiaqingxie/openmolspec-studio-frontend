"""Predict experimental 1H and 13C shifts for symmetry-distinct heavy-atom sites."""

import gzip
import json
from pathlib import Path

from .solution_shifts import site_features, solvent_id, feature_matrix, root_estimate


def assigned_sites(molecule, nucleus):
    if nucleus == "1H":
        indices = [
            a.GetIdx()
            for a in molecule.GetAtoms()
            if a.GetAtomicNum() > 1 and a.GetTotalNumHs(includeNeighbors=True) > 0
        ]
    elif nucleus == "13C":
        indices = [a.GetIdx() for a in molecule.GetAtoms() if a.GetAtomicNum() == 6]
    else:
        raise ValueError("Expected 1H or 13C")
    if not indices:
        return []
    return site_features(molecule, nucleus, indices)


class AssignedShiftPredictor:
    def __init__(self, directory):
        import lightgbm as lgb
        from openmolspec_bench.data import sha256

        root = Path(directory)
        self.config = json.loads((root / "model.json").read_text())
        self.nucleus = self.config["nucleus"]
        for name, field in [
            ("booster.txt", "tree_sha256"),
            ("lookup.json.gz", "lookup_sha256"),
        ]:
            if sha256(root / name) != self.config[field]:
                raise ValueError("Assigned model checksum mismatch")
        self.model = lgb.Booster(model_file=str(root / "booster.txt"))
        with gzip.open(root / "lookup.json.gz", "rt") as f:
            self.lookup = json.load(f)

    def predict(self, smiles, solvent=None):
        from rdkit import Chem

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError("Invalid SMILES")
        sites = assigned_sites(mol, self.nucleus)
        if not sites:
            return []
        matrix = feature_matrix((v, solvent_id(solvent)) for _, _, v in sites)
        predictions = self.model.predict(matrix, num_threads=1)
        peaks = []
        for (group, codes, _), v in zip(sites, predictions):
            estimate = root_estimate(self.lookup, codes)
            mix = self.config["lookup_weight"] if estimate is not None else 0
            peaks.append(
                dict(
                    atom_indices=group,
                    shift_ppm=float((1 - mix) * v + mix * (estimate or 0.0)),
                )
            )
        return peaks


    def assignment_predictions(self, smiles, solvent=None):
        """Map heavy-site estimates to the explicit atom order used by the assignment API."""
        from rdkit import Chem

        sites = self.predict(smiles, solvent)
        by_atom = {idx: site["shift_ppm"] for site in sites for idx in site["atom_indices"]}
        molecule = Chem.AddHs(Chem.MolFromSmiles(smiles))
        if self.nucleus == "13C":
            return [by_atom[a.GetIdx()] for a in molecule.GetAtoms() if a.GetAtomicNum() == 6]
        shifts = []
        for atom in molecule.GetAtoms():
            if atom.GetAtomicNum() == 1:
                neighbors = atom.GetNeighbors()
                if len(neighbors) != 1 or neighbors[0].GetIdx() not in by_atom:
                    raise ValueError("A hydrogen lacks a supported attached heavy-atom site")
                shifts.append(by_atom[neighbors[0].GetIdx()])
        return shifts


def merge_peaks(sites, gap):
    """Group unresolved site predictions within the fitted maximum ppm span."""
    groups = []
    for site in sorted(sites, key=lambda s: s["shift_ppm"]):
        if (
            gap == 0
            or not groups
            or site["shift_ppm"] - groups[-1][0]["shift_ppm"] > gap
        ):
            groups.append([])
        groups[-1].append(site)
    return [
        dict(
            atom_indices=sorted(i for s in group for i in s["atom_indices"]),
            shift_ppm=sum(s["shift_ppm"] for s in group) / len(group),
        )
        for group in groups
    ]


def combine_sites(base, weak, weight):
    if weight == 0:
        return base
    if weight == 1:
        return weak
    if [s["atom_indices"] for s in base] != [s["atom_indices"] for s in weak]:
        raise ValueError("Site grouping differs between the fitted H/C models")
    return [
        dict(
            atom_indices=b["atom_indices"],
            shift_ppm=b["shift_ppm"] * (1 - weight) + w["shift_ppm"] * weight,
        )
        for b, w in zip(base, weak)
    ]


class PeakSpectrumPredictor:
    """Predict a 1H or 13C peak list with contributing heavy-atom indices."""

    def __init__(self, directory):
        from openmolspec_bench.data import sha256
        from .peak_learning import PeakLearningPredictor

        root = Path(directory)
        self.config = json.loads((root / "model.json").read_text())
        self.nucleus = self.config["nucleus"]
        weight = self.config["peak_learning_weight"]
        if not 0 <= weight <= 1 or self.config["merge_gap_ppm"] < 0:
            raise ValueError("Invalid peak model settings")
        self.base = None
        self.weak = None
        if weight < 1:
            if sha256(root / "assigned/model.json") != self.config["assigned_sha256"]:
                raise ValueError("Assigned predictor checksum mismatch")
            self.base = AssignedShiftPredictor(root / "assigned")
        if weight > 0:
            self.weak = PeakLearningPredictor(
                root / "peak-learning", sha256=self.config["peak_learning_sha256"]
            )
        if any(m.nucleus != self.nucleus for m in (self.base, self.weak) if m):
            raise ValueError("Peak model nucleus mismatch")

    def predict(self, smiles, solvent=None):
        base = self.base.predict(smiles, solvent) if self.base else []
        weak = self.weak.predict(smiles, solvent) if self.weak else []
        sites = combine_sites(base, weak, self.config["peak_learning_weight"])
        peaks = merge_peaks(sites, self.config["merge_gap_ppm"])
        return dict(
            smiles=smiles,
            nucleus=self.nucleus,
            unit="ppm",
            atom_index_basis="zero-based heavy-atom site indices in input SMILES",
            sites=sites,
            peaks=peaks,
            prediction_ppm=[p["shift_ppm"] for p in peaks],
        )
