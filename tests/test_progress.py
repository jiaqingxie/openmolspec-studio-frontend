import contextlib
import io
import os
import unittest
from unittest import mock

from openmolspec.core.progress import track


class ProgressTest(unittest.TestCase):
    def test_log_mode_uses_clean_newline_records(self):
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"OPENSPEC_PROGRESS": "log"}):
            with contextlib.redirect_stderr(output):
                values = list(
                    track(
                        range(3),
                        total=3,
                        desc="Manifest test",
                        unit="record",
                        log_interval_seconds=0,
                    )
                )

        text = output.getvalue()
        self.assertEqual(values, [0, 1, 2])
        self.assertNotIn("\r", text)
        self.assertIn("[OpenMolSpec] Manifest test: started", text)
        self.assertIn("3/3 (100.0%)", text)
        self.assertIn("Manifest test: completed", text)


if __name__ == "__main__":
    unittest.main()
