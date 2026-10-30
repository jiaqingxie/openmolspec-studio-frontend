import unittest

import numpy as np

from openmolspec_ui.spectra import SPECTRUM_AXIS, minmax, parse_peaks, parse_spectrum


class SpectrumTests(unittest.TestCase):
    def test_two_column_input_is_sorted_resampled_and_normalized(self):
        spectrum = parse_spectrum("4000,4\n2200,2\n400,0\n")
        self.assertEqual(spectrum.intensity.shape, (1024,))
        self.assertAlmostEqual(float(spectrum.intensity.min()), 0.0)
        self.assertAlmostEqual(float(spectrum.intensity.max()), 1.0)
        self.assertTrue(np.array_equal(spectrum.wavenumber, SPECTRUM_AXIS))

    def test_single_column_input_uses_model_axis(self):
        spectrum = parse_spectrum("0\n1\n2\n3\n")
        self.assertEqual(spectrum.intensity.shape, (1024,))
        self.assertAlmostEqual(float(spectrum.intensity[-1]), 1.0)

    def test_constant_spectrum_maps_to_zeros(self):
        self.assertTrue(np.array_equal(minmax(np.ones(1024)), np.zeros(1024)))

    def test_peak_parser(self):
        values = parse_peaks("7.2, 1.1\n3.4")
        np.testing.assert_allclose(values, [1.1, 3.4, 7.2])

    def test_out_of_range_spectrum_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "400–4000"):
            parse_spectrum("10,1\n20,2\n")


if __name__ == "__main__":
    unittest.main()

