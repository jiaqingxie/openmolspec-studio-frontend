import unittest
import numpy as np
from openmolspec.inversion import kernel, invert


class InversionTests(unittest.TestCase):
    def test_known_two_component_decay_reconstructs_signal_and_locations(self):
        times=np.linspace(0,1.5,90);grid=np.geomspace(.01,2,80)
        weights=np.zeros(80);weights[25]=.35;weights[58]=.65
        signal=kernel(times,grid)@weights
        result=invert(times,signal,grid,alpha=1e-6,penalty='identity')
        self.assertTrue(np.all(result.weights>=0))
        self.assertLess(result.diagnostics['residual_rmse'],2e-4)
        self.assertLess(abs(result.weights[:40].sum()-.35),.025)
        self.assertLess(abs(result.weights[40:].sum()-.65),.025)
        self.assertAlmostEqual(grid[np.argmax(result.weights[:40])],grid[25],delta=.01)
        self.assertAlmostEqual(grid[np.argmax(result.weights[40:])+40],grid[58],delta=.04)

    def test_kernel_limits_and_input_units(self):
        t=np.array([0,.1,.2]);grid=np.geomspace(.01,1,5)
        np.testing.assert_allclose(kernel(t,grid,experiment='T1_inversion')[0],-1)
        np.testing.assert_allclose(kernel(t,grid,experiment='T1_saturation')[0],0)
        np.testing.assert_allclose(kernel(t,grid,experiment='diffusion')[0],1)
        with self.assertRaises(ValueError):invert(t,[1,.8,.6],grid,alpha=-1)
        with self.assertRaises(ValueError):kernel([0,.1,.1],grid)


if __name__=='__main__':unittest.main()
