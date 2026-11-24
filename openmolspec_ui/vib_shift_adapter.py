"""Estimate two lists of chemical shifts from calculated IR and Raman intensities."""

from functools import lru_cache
from importlib.resources import files
import numpy as np

from .gap_partial import design, spectral_features
from .spectra import SpectralInput


def supports(inputs):
    return (
        all(x is not None and len(x) for x in (inputs.ir, inputs.raman))
        and all(x is None or not len(x) for x in (inputs.nmr_h, inputs.nmr_c))
    )


def weights_file():
    return files("openmolspec").joinpath("assets", "vib_shift_adapter.npz")


@lru_cache(maxsize=1)
def weights():
    with weights_file().open("rb") as stream, np.load(stream, allow_pickle=False) as data:
        return dict(data)


def with_estimated_shifts(inputs):
    h, c = estimate_shifts(inputs.ir, inputs.raman, weights())
    return SpectralInput(ir=inputs.ir, raman=inputs.raman, nmr_h=h, nmr_c=c)


def estimate_shifts(ir, raman, parameters):
    """Return estimated ¹H and ¹³C shifts in ppm from the fitted count/quantile model."""
    x = np.concatenate([spectral_features(ir), spectral_features(raman)], axis=1)
    x = x / np.sqrt(np.float32(2))
    summary = (
        design(x, parameters["anchors"]) @ parameters["coef"] + parameters["bias"]
    )[0]
    shifts = []
    for offset in (0, 33):
        count = int(np.clip(np.round(np.expm1(summary[offset])), 1, 128))
        probabilities = (np.arange(count) + 0.5) / count
        quantiles = np.sort(summary[offset + 1 : offset + 33])
        shifts.append(np.interp(probabilities, parameters["grid"], quantiles))
    return shifts[0], shifts[1]
