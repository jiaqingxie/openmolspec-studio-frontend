"""NMRGym-specific transfer model for unassigned 1H peak lists."""

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator

from .peak_learning import PeakLearningPredictor, environments, estimate

GRID = np.linspace(0, 1, 64)
FP_SIZE = 512


@lru_cache(maxsize=1)
def fingerprint_generator():
    return rdFingerprintGenerator.GetMorganGenerator(
        radius=3, fpSize=FP_SIZE, includeChirality=True
    )


def resample(values, size):
    """Interpolate an ordered spectrum at evenly spaced ranks, including both ends."""
    values = np.sort(values)
    if size == 1:
        return np.array([np.median(values)])
    return np.interp(np.linspace(0, 1, size), np.linspace(0, 1, len(values)), values)


def proton_features(mol, weak):
    """Use the released proton environment model as the frozen shift backbone."""
    groups, codes, has_h, _ = environments(mol)
    selected = np.flatnonzero(has_h)
    if not len(selected):
        return None
    codes = codes[selected]
    cfg = weak.config
    seed = estimate(codes, cfg["seed_tables"], cfg["center"])
    fitted = estimate(codes, cfg["tables"], cfg["center"], minimum=cfg["min_support"])
    shifts = seed * (1 - cfg["weight"]) + fitted * cfg["weight"]
    equivalents = np.array([len(groups[i]) for i in selected])
    hydrogens = np.array(
        [
            mol.GetAtomWithIdx(groups[i][0]).GetTotalNumHs(includeNeighbors=True)
            for i in selected
        ]
    )
    per_atom = np.repeat(shifts, equivalents)
    per_hydrogen = np.repeat(shifts, equivalents * hydrogens)
    fp = fingerprint_generator().GetCountFingerprintAsNumPy(mol)
    counts = [
        mol.GetNumHeavyAtoms(),
        mol.GetRingInfo().NumRings(),
        sum(a.GetIsAromatic() for a in mol.GetAtoms()),
        len(shifts),
        len(per_atom),
        len(per_hydrogen),
    ]
    curves = [resample(v, len(GRID)) for v in (shifts, per_atom, per_hydrogen)]
    return np.concatenate(
        [np.log1p(fp.astype(float)), np.log1p(counts), *curves]
    ).astype(np.float32), len(shifts)


class NMRGymProtonPredictor:
    """Predict unassigned proton peak positions from a SMILES string."""

    def __init__(self, directory):
        from openmolspec_bench.data import sha256

        root = Path(directory)
        self.config = json.loads((root / "model.json").read_text())
        self.weak = PeakLearningPredictor(
            root, sha256=self.config["environment_sha256"]
        )
        if (
            self.weak.nucleus != "1H"
            or sha256(root / "adapter.npz") != self.config["adapter_sha256"]
        ):
            raise ValueError("NMRGym proton model components do not match the profile")
        with np.load(root / "adapter.npz", allow_pickle=False) as weights:
            self.weights = dict(weights)
        self.base = None
        if self.config["released_peak_weight"] or self.config["snap_radius_ppm"]:
            from .assigned_shifts import PeakSpectrumPredictor

            if (
                sha256(root / "released/model.json")
                != self.config["released_model_sha256"]
            ):
                raise ValueError("Released proton model checksum mismatch")
            self.base = PeakSpectrumPredictor(root / "released")

    def predict(self, smiles, solvent=None):
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError("Invalid SMILES")
        features = proton_features(mol, self.weak)
        peaks = []
        if features is not None:
            x, site_count = features
            curve, count = adapter_outputs(x[None, :], [site_count], self.weights)
            base = (
                self.base.predict(smiles, solvent)["prediction_ppm"]
                if self.base
                else []
            )
            peaks = decode(
                curve[0],
                count[0],
                base,
                self.config["released_peak_weight"],
                self.config["snap_radius_ppm"],
            ).tolist()
        return dict(smiles=smiles, nucleus="1H", unit="ppm", prediction_ppm=peaks)


def adapter_outputs(features, site_counts, weights):
    hidden = np.maximum(features @ weights["w1"].T + weights["b1"], 0)
    hidden = np.maximum(hidden @ weights["w2"].T + weights["b2"], 0)
    outputs = hidden @ weights["out"].T + weights["bias"]
    curves = features[:, -3 * len(GRID) : -2 * len(GRID)] + outputs[:, :-1]
    counts = np.asarray(site_counts) * np.exp(np.clip(outputs[:, -1], -4, 4))
    return np.sort(curves, axis=1), np.maximum(1, np.rint(counts)).astype(int)


def decode(curve, count, released, released_weight, snap_radius=0.0):
    predicted = resample(curve, count)
    if released_weight and released:
        predicted = (1 - released_weight) * predicted + released_weight * resample(
            released, count
        )
    if snap_radius and released:
        base = np.asarray(released)
        nearest = base[np.argmin(np.abs(predicted[:, None] - base), axis=1)]
        predicted = np.where(
            np.abs(predicted - nearest) <= snap_radius, nearest, predicted
        )
    return predicted
