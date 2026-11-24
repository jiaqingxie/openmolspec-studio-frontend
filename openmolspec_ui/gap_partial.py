"""Gap regression for calculated vibrational spectra with no NMR channels."""

from functools import lru_cache
from importlib.resources import files
import numpy as np


def spectral_features(values):
    x = np.asarray(values, dtype=np.float32)
    if x.shape[-1] != 1024 or not np.isfinite(x).all():
        raise ValueError("Expected 1024 finite spectral intensities")
    x = x.reshape(-1, 1024)
    x = x - x.min(axis=1, keepdims=True)
    x = np.sqrt(x / np.maximum(x.max(axis=1, keepdims=True), 1e-12))
    x = x.reshape(-1, 256, 4).mean(axis=2)
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


def design(x, anchors):
    sim = x @ anchors.T
    return np.concatenate((x, np.exp(6 * (sim - 1))), axis=1)


@lru_cache(maxsize=1)
def weights():
    with (
        files("openmolspec")
        .joinpath("assets", "gap_vibrational.npz")
        .open("rb") as stream
    ):
        with np.load(stream, allow_pickle=False) as data:
            return dict(data)


def predict(ir, raman):
    views = [
        (name, spectral_features(value))
        for name, value in (("ir", ir), ("raman", raman))
        if value is not None
    ]
    mode = "_".join(name for name, _ in views)
    x = np.concatenate([v for _, v in views], axis=1) / np.sqrt(np.float32(len(views)))
    w = weights()
    result = design(x, w[mode + "_anchors"]) @ w[mode + "_beta"] + w[mode + "_bias"]
    return {
        "gap_ev": float(result.item()),
        "unit": "eV",
        "training_modality": mode,
        "input_modalities": [
            name.upper() if name == "ir" else "Raman" for name, _ in views
        ],
        "model": "vibrational_gap_ridge_v1",
    }
