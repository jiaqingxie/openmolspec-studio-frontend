import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from openmolspec.quality.validation import _stats, run, validate_record


class InternalValidationTest(unittest.TestCase):
    def test_record_validation_flags_imaginary_frequency(self):
        result = validate_record(
            {
                "atom": np.array([6, 1], dtype=np.int32),
                "coordinate": np.zeros(6, dtype=np.float32),
                "freq": np.array([-12.0, 100.0]),
                "ir": np.zeros(2),
                "raman": np.zeros(2),
            },
            "sample-1",
        )
        self.assertTrue(result["schema_valid"])
        self.assertIn("IMAGINARY_FREQUENCIES_PRESENT", result["quality_flags"])

    def test_invalid_coordinate_count_fails_qc(self):
        result = validate_record(
            {"atom": np.array([6, 1]), "coordinate": np.zeros(3)}, "sample-2"
        )
        self.assertFalse(result["qc_pass"])
        self.assertIn("ATOM_COORDINATE_COUNT_MISMATCH", result["errors"])

    def test_run_writes_reports(self):
        frame = pd.DataFrame(
            [
                {
                    "sample_id": "sample-1",
                    "atom": np.array([6]),
                    "coordinate": np.zeros(3),
                    "freq": np.array([100.0]),
                    "ir": np.array([1.0]),
                    "raman": np.array([2.0]),
                }
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "data.pickle"
            output = Path(directory) / "qc"
            frame.to_pickle(dataset)
            summary = run(str(dataset), str(output))
            self.assertEqual(summary["records"], 1)
            self.assertTrue((output / "summary.json").exists())
            self.assertTrue((output / "attrition.csv").exists())
            self.assertTrue((output / "record_qc.parquet").exists())

    def test_large_array_statistics_are_bounded_and_exact_for_moments(self):
        frame = pd.DataFrame({"ir": [np.arange(10.0), np.arange(10.0, 20.0)]})
        result = _stats(frame, ["ir"], quantile_sample_limit=4).iloc[0]
        self.assertEqual(result["count"], 20)
        self.assertAlmostEqual(result["mean"], 9.5)
        self.assertEqual(result["min"], 0.0)
        self.assertEqual(result["max"], 19.0)
        self.assertEqual(result["quantile_sample_count"], 4)
        self.assertTrue(result["quantiles_approximate"])


if __name__ == "__main__":
    unittest.main()
