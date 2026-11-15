import json
import pickle
from pathlib import Path
import tempfile
import unittest

import numpy as np

from openmolspec_bench.data import load_rows, normalize_record
from openmolspec_bench.metrics import peak_metrics, regression_metrics, retrieval_metrics
from openmolspec_bench.runner import read_prediction_folds


class BenchmarkTests(unittest.TestCase):
    def test_retrieval_both_directions_are_not_interchangeable(self):
        scores = np.array([[0.9, 0.8], [0.95, 1.0]])
        self.assertEqual(retrieval_metrics(scores, ["a", "b"], ["a", "b"])["recall_at_1"], 1.0)
        self.assertEqual(retrieval_metrics(scores.T, ["a", "b"], ["a", "b"])["recall_at_1"], 0.5)

    def test_multiple_positive_candidates_and_ties(self):
        result = retrieval_metrics([[1, 1, 0]], ["a"], ["a", "a", "b"])
        self.assertEqual(result["mrr"], 1)
        self.assertEqual(result["unique_candidates"], 2)
        tied = retrieval_metrics([[0, 0]], ["b"], ["a", "b"])
        self.assertEqual(tied["mrr"], 0.5)

    def test_missing_retrieval_positive_is_an_error(self):
        with self.assertRaises(ValueError):
            retrieval_metrics([[1]], ["b"], ["a"])

    def test_unmatched_peaks_are_visible_in_coverage_and_count_error(self):
        result = peak_metrics([[1, 2, 100]], [[1, 2]])
        self.assertEqual(result["matched_peak_mae_ppm"], 0)
        self.assertEqual(result["peak_count_mae"], 1)
        self.assertAlmostEqual(result["matched_fraction"], 2 / 3)

    def test_empty_prediction_is_in_coverage_denominator(self):
        result = peak_metrics([[], [2]], [[1], [3]])
        self.assertEqual(result["examples"], 2)
        self.assertEqual(result["scored_examples"], 1)
        self.assertEqual(result["matched_fraction"], 0.5)

    def test_nonfinite_regression_rejected(self):
        with self.assertRaises(ValueError):
            regression_metrics([np.nan], [0])

    def test_regression_units_stay_with_caller(self):
        result = regression_metrics([3, 5], [2, 3])
        self.assertEqual(result["mae_ev"], 1.5)
        self.assertAlmostEqual(result["rmse_ev"], np.sqrt(2.5))

    def test_legacy_aliases_do_not_invent_formula(self):
        row = normalize_record({"smiles": "OCC", "h_nmr": "1.2 (t, 3H)"})
        self.assertEqual(row["smiles"], "CCO")
        self.assertEqual(row["modality_mask"], [1, 0])
        self.assertEqual(row["formula"], "")

    def test_visible_empty_modality_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_record({"smiles": "CC", "modality_mask": [1, 0]})

    def test_model_capacity_exclusions_are_counted_and_refilled(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.jsonl"
            rows = [{"smiles": "CCCC", "h_nmr": "1"}, {"smiles": "CC", "h_nmr": "2"}]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            selected, counts = load_rows(path, "h", 1, max_smiles_bytes=2)
            self.assertEqual(selected[0]["smiles"], "CC")
            self.assertEqual(counts["exceeds_model_capacity"], 1)

    def test_padded_atom_masks_recover_packed_predictions_by_molecule(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.pkl"
            path.write_bytes(pickle.dumps([{"matid": np.array([7, 3]),
                                          "select_atom": np.array([[1, 0, 1], [0, 1, 0]]),
                                          "predict": np.array([10., 20., 30.])}]))
            fold = read_prediction_folds([path])[0]
            np.testing.assert_equal(fold[7], [10., 20.])
            np.testing.assert_equal(fold[3], [30.])

    def test_atom_mask_prediction_count_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.pkl"
            path.write_bytes(pickle.dumps([{"matid": np.array([0]), "select_atom": np.array([1, 1]),
                                          "predict": np.array([1.])}]))
            with self.assertRaises(ValueError):
                read_prediction_folds([path])


if __name__ == "__main__":
    unittest.main()
