"""Protect the atom order and symmetry averaging used by the 13C release."""
import unittest

from rdkit import Chem

from openmolspec_bench.carbon import group_carbon_shifts


class CarbonPeakTests(unittest.TestCase):
    def test_group_original_indices_and_keep_coincident_environments(self):
        molecule = Chem.MolFromSmiles("OC(C)C")
        peaks = group_carbon_shifts(molecule, [17., 16., 18.])
        self.assertEqual(peaks, [
            {"atom_indices": [1], "shift_ppm": 17.},
            {"atom_indices": [2, 3], "shift_ppm": 17.},
        ])

    def test_isotope_and_input_shape(self):
        molecule = Chem.MolFromSmiles("[13CH3]C(C)O")
        self.assertEqual(len(group_carbon_shifts(molecule, [17., 60., 17.])), 3)
        with self.assertRaises(ValueError):
            group_carbon_shifts(molecule, [17., 60.])
