import unittest

from benchmarks.models import registry


class BenchmarkRegistryTest(unittest.TestCase):
    def test_task_formats_are_minimal_and_ordered(self):
        formats = registry.formats_for_tasks(
            ["structure2property", "structure2spectrum", "spectrum2property"]
        )
        self.assertEqual(formats, ["vib2conf", "equiformer_v3"])

    def test_dependency_report_has_no_model_import_side_effect(self):
        report = registry.dependency_report()
        self.assertIn("python", report)
        self.assertIn("upstream_models", report)
        self.assertEqual(
            set(report["upstream_models"]),
            {"equiformer_v3", "vib2mol", "vib2conf"},
        )

    def test_registered_tasks_have_export_formats(self):
        self.assertEqual(set(registry.TASKS), set(registry.TASK_FORMAT))
        self.assertTrue(set(registry.TASK_FORMAT.values()) <= set(registry.EXPORT_FORMATS))


if __name__ == "__main__":
    unittest.main()
