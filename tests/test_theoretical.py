import unittest

import numpy as np

from openmolspec_ui.theoretical import harmonic_modes, mode_activities


class TheoreticalSpectrumTests(unittest.TestCase):
    def test_harmonic_modes_remove_six_rigid_modes_for_nonlinear_geometry(self):
        positions = np.asarray(
            [[0.0, 0.0, 0.0], [0.95, 0.0, 0.0], [-0.2, 0.9, 0.0]],
            dtype=np.float64,
        )
        masses = np.asarray([16.0, 1.0, 1.0])
        hessian = np.eye(9, dtype=np.float64)
        modes = harmonic_modes(hessian, positions, masses)
        self.assertEqual(modes.rigid_rank, 6)
        self.assertEqual(modes.frequencies_cm1.shape, (3,))
        self.assertEqual(modes.cartesian_modes.shape, (9, 3))
        self.assertTrue(np.all(modes.frequencies_cm1 > 0))

    def test_response_projection_produces_nonnegative_mode_activities(self):
        modes = np.eye(6, 2, dtype=np.float64)
        dedipole = np.arange(18, dtype=np.float64).reshape(2, 3, 3) / 10
        depolar = np.zeros((2, 3, 3, 3), dtype=np.float64)
        depolar[:, :, 0, 0] = 1.0
        depolar[:, :, 1, 1] = 0.5
        depolar[:, :, 2, 2] = 0.25
        ir, raman = mode_activities(modes, dedipole, depolar)
        self.assertEqual(ir.shape, (2,))
        self.assertEqual(raman.shape, (2,))
        self.assertTrue(np.all(ir >= 0))
        self.assertTrue(np.all(raman >= 0))
        self.assertGreater(float(ir.sum()), 0.0)
        self.assertGreater(float(raman.sum()), 0.0)
