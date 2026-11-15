import csv
from pathlib import Path
import tempfile
import unittest

from openmolspec_bench.ms import select_ms_records, spectrum_metrics


class MassSpectrumTests(unittest.TestCase):
    def test_identical_mass_spectra_score_one(self):
        peaks = [[31.0178, 1.], [47.0491, .4]]
        result = spectrum_metrics(peaks, peaks)
        self.assertAlmostEqual(result["cosine_similarity"], 1.)
        self.assertAlmostEqual(result["entropy_similarity"], 1.)

    def test_distinct_mass_bins_do_not_match(self):
        result = spectrum_metrics([[100., 1.]], [[100.1, 1.]])
        self.assertEqual(result["cosine_similarity"], 0.)

    def test_duplicate_peak_bin_uses_max_not_sum(self):
        result = spectrum_metrics([[100., .25], [100., .75], [200., 1.]], [[100., .75], [200., 1.]])
        self.assertAlmostEqual(result["cosine_similarity"], 1.)
        self.assertAlmostEqual(result["entropy_similarity"], 1.)

    def test_only_prediction_is_peak_limited(self):
        result = spectrum_metrics([[100., 1.], [200., .1]], [[100., 1.], [200., .1]], max_peaks=1)
        self.assertEqual(result["predicted_nonzero_bins"], 1)
        self.assertEqual(result["reference_nonzero_bins"], 2)
        self.assertLess(result["cosine_similarity"], 1.)

    def test_negative_or_nonfinite_peaks_are_rejected(self):
        with self.assertRaises(ValueError):
            spectrum_metrics([[100., -1.]], [[100., 1.]])

    def test_metadata_identity_mismatch_is_not_silently_joined(self):
        with tempfile.TemporaryDirectory() as directory:
            split, metadata = Path(directory) / "test.csv", Path(directory) / "metadata.tsv"
            with split.open("w") as stream:
                writer = csv.DictWriter(stream, fieldnames=["spec_id", "smiles", "prec_type", "peaks"])
                writer.writeheader()
                writer.writerow({"spec_id": "one", "smiles": "CCO", "prec_type": "[M+H]+", "peaks": "[(31., 1.)]"})
            with metadata.open("w") as stream:
                writer = csv.DictWriter(stream, fieldnames=["identifier", "smiles", "adduct", "precursor_mz"], delimiter="\t")
                writer.writeheader()
                writer.writerow({"identifier": "one", "smiles": "CCN", "adduct": "[M+H]+", "precursor_mz": "46.1"})
            with self.assertRaisesRegex(ValueError, "identity/adduct mismatch"):
                select_ms_records(split, metadata, 1)


if __name__ == "__main__":
    unittest.main()
