import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from openmolspec.core.processing import (
    classify_exception,
    record_quality_metadata,
    report_row,
    write_processing_reports,
)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProcessingTest(unittest.TestCase):
    FIXTURE_LOG = Path(__file__).parent / "fixtures" / "NISTIR-11730.log"

    def test_quality_metadata_flags_without_removing_values(self):
        missing, flags = record_quality_metadata(
            {
                "atom": [6],
                "coordinate": [0.0, 0.0, 0.0],
                "freq": [-10.0, float("nan")],
            }
        )
        self.assertIn("ir", missing)
        self.assertIn("raman", missing)
        self.assertIn("IMAGINARY_FREQUENCIES_PRESENT", flags)
        self.assertIn("NONFINITE_FREQ", flags)

    def test_nmr_quality_metadata_uses_nmr_fields(self):
        missing, flags = record_quality_metadata(
            {"atom": [6], "isotropic": [1.0]}, modality="nmr"
        )
        self.assertIn("anisotropy", missing)
        self.assertIn("shielding_tensor", missing)
        self.assertEqual(flags, [])

    def test_error_taxonomy(self):
        self.assertEqual(classify_exception(FileNotFoundError("x")), "FILE_NOT_FOUND")
        self.assertEqual(
            classify_exception(ValueError("invalid frequency value")),
            "FREQUENCY_PARSE_FAILED",
        )

    def test_processing_report_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = [
                report_row("NISTIR-11730", str(self.FIXTURE_LOG), status="success"),
                report_row(
                    "NISTIR-missing",
                    "does-not-exist.log",
                    status="failed",
                    error_type="FILE_NOT_FOUND",
                    error_message="missing fixture",
                ),
            ]
            write_processing_reports(rows, directory)
            self.assertTrue(Path(directory, "processing_report.parquet").exists())
            with open(Path(directory, "processing_summary.json"), encoding="utf-8") as handle:
                summary = json.load(handle)
            self.assertEqual(summary["total"], 2)
            self.assertEqual(summary["status_counts"]["success"], 1)

    def test_gaussian_success_and_failure_are_observable(self):
        module = load_module(
            "extract_spectra_test",
            Path(__file__).parents[1]
            / "src" / "openmolspec" / "legacy" / "extract_spectra.py",
        )
        success = module.LogParser(
            str(self.FIXTURE_LOG), "NISTIR-11730", {"NISTIR-11730": "CCO"}
        )
        self.assertIn("atom", success.properties)
        self.assertIsNone(success.error_type)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".log") as handle:
            handle.write("truncated Gaussian output")
            handle.flush()
            failure = module.LogParser(handle.name, "BROKEN-1", {"BROKEN-1": "CCO"})
        self.assertNotIn("atom", failure.properties)
        self.assertIsNotNone(failure.error_type)
        self.assertTrue(failure.error_message)


if __name__ == "__main__":
    unittest.main()
