import unittest
import numpy as np
from benchmarks.engines.hessian_physics import assemble, physics


class HessianPhysicsTest(unittest.TestCase):
    def test_diatomic_and_negative_internal_mode(self):
        pos = np.array([[0.,0,0],[1.,0,0]])
        vector = np.array([1.,0,0,-1,0,0])
        h = np.outer(vector, vector)
        metrics, freq = physics(h, pos, np.ones(2))
        self.assertEqual(metrics['rigid_rank'], 5)
        self.assertEqual(len(freq), 1)
        self.assertGreater(freq[0], 700)
        self.assertLess(metrics['translation_relative'], 1e-12)
        self.assertLess(metrics['rotation_relative'], 1e-12)
        negative, fs = physics(-h, pos, np.ones(2))
        self.assertEqual(negative['imaginary_count'], 1)
        self.assertLess(fs[0], 0)

    def test_nonlinear_rigid_rank_and_asymmetry(self):
        pos = np.array([[0.,0,0],[1.,0,0],[0.,1,0]])
        h = np.eye(9)
        h[0,1] = .3
        metrics, freq = physics(h, pos, np.ones(3))
        self.assertEqual(metrics['rigid_rank'], 6)
        self.assertEqual(len(freq), 3)
        self.assertGreater(metrics['symmetry_relative'], 0)

    def test_assembly_preserves_raw_asymmetry(self):
        h = assemble(np.zeros((2,3,3)), np.ones((1,3,3)), np.array([[0],[1]]))
        np.testing.assert_array_equal(h[3:,:3], np.ones((3,3)))
        np.testing.assert_array_equal(h[:3,3:], np.zeros((3,3)))
