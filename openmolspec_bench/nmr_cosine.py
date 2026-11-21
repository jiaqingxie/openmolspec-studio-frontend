"""Cosine between unit-area Lorentzian NMR peak profiles over the full ppm axis."""

import numpy as np


def peak_profile_cosine(predicted, observed, fwhm_ppm):
    """Integrate the normalized overlap of a pair of 1D or separable 2D peak lists.

    The autocorrelation of a Lorentzian of FWHM w, divided by its value at
    zero, is 1 / (1 + (delta / w)**2). Common area factors cancel in the
    cosine. Each listed peak contributes once, including extra or missing peaks.
    """
    widths = np.atleast_1d(np.asarray(fwhm_ppm, dtype=float))
    if (
        widths.ndim != 1
        or widths.size not in (1, 2)
        or not np.all(np.isfinite(widths) & (widths > 0))
    ):
        raise ValueError("Expected one or two positive finite FWHMs in ppm")

    def coordinates(peaks):
        values = np.asarray(peaks, dtype=float)
        if values.ndim == 1 and widths.size == 1:
            values = values[:, None]
        if (
            values.ndim != 2
            or values.shape[1] != widths.size
            or not len(values)
            or not np.isfinite(values).all()
        ):
            raise ValueError(
                "Expected a nonempty finite peak list with coordinates for each axis"
            )
        return values

    def overlap(left, right):
        delta = (left[:, None, :] - right[None, :, :]) / widths
        return np.prod(1 / (1 + delta**2), axis=2).sum()

    p, y = coordinates(predicted), coordinates(observed)
    return float(overlap(p, y) / np.sqrt(overlap(p, p) * overlap(y, y)))
