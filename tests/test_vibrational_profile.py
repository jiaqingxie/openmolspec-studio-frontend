"""Reference-convention and per-channel checks for structure-to-spectrum inference."""

import unittest

import numpy as np
from scipy.constants import Boltzmann, Planck, speed_of_light

from openmolspec_bench.vibrational_profile import apply_profile, mode_spectra


class ReferenceSpectrumTests(unittest.TestCase):
    def test_stokes_conversion_precedes_line_broadening(self):
        grid = np.linspace(500.0, 4000.0, 997)
        f = np.array([950.0, 3050.0])
        result = dict(
            qm9s_mode_frequencies=f,
            qm9s_ir_activities=np.array([2.0, 1.0]),
            qm9s_raman_activities=np.array([1.0, 3.0]),
        )
        curves = mode_spectra(result, grid)
        shape = 1.0 / (1.0 + ((grid[:, None] - f) / 10.0) ** 2)
        weight = (1.0e7 / 532.0 - f) ** 4 / (
            f * (1.0 - np.exp(-Planck * speed_of_light * 100 * f / (Boltzmann * 298.0)))
        )
        for ch, y in (("ir", [2.0, 1.0]), ("raman", [1.0, 3.0] * weight)):
            expected = shape @ y
            np.testing.assert_allclose(
                curves[ch], expected / expected.max(), rtol=1.0e-8
            )
        result.update(wavenumber=grid, ir=np.ones(len(grid)), raman=np.zeros(len(grid)))
        calibrated = apply_profile(
            result,
            {"ir": [1.0, 0.0], "raman": [1.0, 0.0]},
            {"ir": "openspec", "raman": "modes"},
        )
        np.testing.assert_allclose(calibrated["ir"], 1.0)
        np.testing.assert_allclose(calibrated["raman"], curves["raman"])
