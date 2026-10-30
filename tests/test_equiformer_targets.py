import unittest

from benchmarks.models.equiformer_v3.train import resolve_progress_mode, resolve_targets


class EquiformerTargetsTest(unittest.TestCase):
    def test_joint_observable_targets_are_split_into_head_groups(self):
        properties, spectra = resolve_targets(
            "structure2observables", ["energy", "gap", "ir_spectrum"]
        )
        self.assertEqual(properties, ["energy", "gap"])
        self.assertEqual(spectra, ["ir_spectrum"])

    def test_incompatible_target_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "incompatible"):
            resolve_targets("structure2property", ["raman_spectrum"])

    def test_auto_progress_uses_log_for_pipes(self):
        self.assertEqual(resolve_progress_mode("auto", is_tty=False), "log")
        self.assertEqual(resolve_progress_mode("auto", is_tty=True), "tqdm")
        self.assertEqual(resolve_progress_mode("log", is_tty=True), "log")


if __name__ == "__main__":
    unittest.main()
