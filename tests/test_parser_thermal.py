import unittest
from pathlib import Path

import numpy as np

from openmolspec.parsing.gaussian import GaussianLogParser

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class ParserThermalFallbackTest(unittest.TestCase):
    """QM9 logs omit ETot/HTot/GTot from the Gaussian archive section but
    print the thermal corrections in the log body; the parser must fall back
    to the text lines so U/H/G are not silently lost."""

    @classmethod
    def setUpClass(cls):
        cls.log = str(FIXTURES / "QM9-dsgdb9nsd_000001.log")

    @staticmethod
    def _scalar(value) -> float:
        return float(np.asarray(value).reshape(-1)[0])

    def test_parser_extracts_thermal_properties_from_text_lines(self):
        parser = GaussianLogParser(self.log, "QM9-0")
        self.assertIsNone(parser.error_type, parser.error_message)
        self.assertIn("U", parser.properties)
        self.assertIn("H", parser.properties)
        self.assertIn("G", parser.properties)
        # -40.488438 (thermal Energies) is the expected U for this molecule.
        self.assertAlmostEqual(self._scalar(parser.properties["U"]), -40.488438, places=3)
        self.assertAlmostEqual(self._scalar(parser.properties["H"]), -40.487493, places=3)
        self.assertAlmostEqual(self._scalar(parser.properties["G"]), -40.510970, places=3)

    def test_parser_still_prefers_archive_values(self):
        """NISTIR-style logs carry ETot/HTot/GTot in the archive and must be
        unaffected by the text fallback."""
        parser = GaussianLogParser(str(FIXTURES / "NISTIR-11730.log"), "NISTIR-11730")
        self.assertIsNone(parser.error_type, parser.error_message)
        self.assertIn("U", parser.properties)
        self.assertTrue(np.isfinite(parser.properties["U"]).all())

    def test_thermal_values_match_zero_point_relation(self):
        parser = GaussianLogParser(self.log, "QM9-0")
        energy = self._scalar(parser.properties["energy"])
        zpve = self._scalar(parser.properties["zpve"])
        u0 = self._scalar(parser.properties["U0"])
        self.assertAlmostEqual(energy + zpve, u0, places=4)
        # U (thermal Energies) should be slightly above U0 (zero-point energy).
        u = self._scalar(parser.properties["U"])
        self.assertGreater(u, u0)


if __name__ == "__main__":
    unittest.main()
