"""Apply a reference-specific frequency scale and instrumental Gaussian width."""

import numpy as np
from scipy.ndimage import gaussian_filter1d


def checkpoint_hashes(assets):
    """Identify the four tensor networks underlying the calibrated spectra."""
    from .data import sha256

    return {
        "Hi": sha256(assets.hessian_hi_checkpoint),
        "Hij": sha256(assets.hessian_hij_checkpoint),
        "dedipole": sha256(assets.dedipole_checkpoint),
        "depolar": sha256(assets.depolar_checkpoint),
    }


def transform(predictions, scale, width_cm1, wavenumber):
    grid = np.asarray(wavenumber)
    values = np.asarray(predictions)
    if values.ndim != 2 or values.shape[1] != len(grid) or scale <= 0 or width_cm1 < 0:
        raise ValueError("Invalid spectrum profile dimensions or frequency parameters")
    step = np.diff(grid)
    if len(step) == 0 or step[0] <= 0 or not np.allclose(step, step[0]):
        raise ValueError("A uniformly spaced increasing wavenumber axis is required")
    corrected = np.stack(
        [np.interp(grid / scale, grid, row, left=0.0, right=0.0) for row in values]
    )
    if width_cm1:
        corrected = gaussian_filter1d(corrected, width_cm1 / step[0], axis=1)
    return corrected / np.maximum(corrected.max(axis=1, keepdims=True), 1e-15)


def mode_spectra(result, grid):
    """Render predicted normal modes with the QM9S Lorentzian and Stokes convention."""
    from scipy.constants import Boltzmann, Planck, speed_of_light
    from openmolspec.parsing.gaussian import lorentzian_broadening

    # reconstruct_spectra already applies the documented 0.965 harmonic frequency scale.
    frequencies = np.asarray(result["qm9s_mode_frequencies"], dtype=float)
    mask = frequencies > 1.0
    nu = frequencies[mask]
    if not len(nu):
        raise ValueError("No positive modes above 1 cm^-1")
    ir = np.asarray(result["qm9s_ir_activities"], dtype=float)[mask]
    raman = np.asarray(result["qm9s_raman_activities"], dtype=float)[mask]
    population = -np.expm1(-Planck * speed_of_light * 100 * nu / (Boltzmann * 298.0))
    stokes = (1.0e7 / 532.0 - nu) ** 4 / (nu * population)
    channels = {}
    for name, strengths in (("ir", ir), ("raman", raman * stokes)):
        # The authoring function takes full width at half maximum.
        values = lorentzian_broadening(nu, strengths, grid, sigma=20.0)
        channels[name] = values / max(values.max(), 1.0e-30)
    return channels


def apply_profile(result, profile, sources=None):
    """Apply each channel's validation-selected convention on the QM9S grid."""
    grid = np.linspace(500.0, 4000.0, 997)
    sources = sources or {}
    modes = mode_spectra(result, grid) if "modes" in sources.values() else {}
    channels = {"wavenumber": grid}
    for name in ("ir", "raman"):
        source = sources.get(name, "openspec")
        if source == "modes":
            raw = modes[name]
        elif source == "openspec":
            raw = np.interp(grid, result["wavenumber"], result[name])
        else:
            raise ValueError(f"Unknown spectrum profile source {source}")
        channels[name] = transform(raw[None, :], *profile[name], grid)[0]
    return channels
