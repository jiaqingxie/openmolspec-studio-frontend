import tempfile
import unittest
from pathlib import Path

from openmolspec_ui.config import APP_ROOT, discover_assets


class ConfigTests(unittest.TestCase):
    def test_default_root_is_the_repository_root(self):
        self.assertEqual(discover_assets().root, APP_ROOT)

    def test_empty_root_reports_missing_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = discover_assets(Path(directory))
            self.assertTrue(assets.root_available)
            self.assertIsNone(assets.gap_checkpoint)
            self.assertFalse(any(value[0] for value in assets.capability_status().values()))


if __name__ == "__main__":
    unittest.main()
