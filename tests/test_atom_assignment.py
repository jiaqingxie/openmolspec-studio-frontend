import unittest
import numpy as np
from openmolspec_bench.assignment import atom_sites, assign_peaks


class AssignmentTests(unittest.TestCase):
    def test_permuted_peaks_map_back_to_original_atom_indices(self):
        result = assign_peaks('CCO', 'C', [18., 58.], [58.2, 18.1], 1.)
        self.assertEqual([a['atom_indices'] for a in result['assignments']], [[1], [0]])
        self.assertIsNone(result['assignment_accuracy'])

    def test_symmetry_groups_do_not_invent_separate_methyl_peaks(self):
        sites, mapped = atom_sites('CC(=O)C', 'C', [30., 200., 30.])
        self.assertEqual([s['atom_indices'] for s in sites], [[0, 3], [1]])
        self.assertIn(':4]', mapped)

    def test_missing_and_extra_peaks_remain_visible(self):
        result = assign_peaks('CCO', 'C', [18., 58.], [18., 999.], 1.)
        self.assertEqual(result['unmatched_peak_indices'], [1])
        self.assertEqual(result['unmatched_sites'][0]['atom_indices'], [1])
        self.assertEqual(result['matched_fraction'], .5)

    def test_one_site_cannot_be_assigned_to_two_peaks(self):
        result = assign_peaks('CO', 'C', [50.], [49.9, 50.1], 1.)
        self.assertEqual(len(result['assignments']), 1)
        self.assertEqual(len(result['unmatched_peak_indices']), 1)

    def test_invalid_or_nonfinite_requests_are_rejected(self):
        for predictions, peaks, tolerance in [([np.nan, 58.], [18.], 1.),
                                            ([18., 58.], [np.inf], 1.),
                                            ([18., 58.], [], 1.),
                                            ([18.], [18.], 1.),
                                            ([18., 58.], [18.], 0.)]:
            with self.assertRaises(ValueError):
                assign_peaks('CCO', 'C', predictions, peaks, tolerance)


if __name__ == '__main__':
    unittest.main()
