import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from benchmarks.trainers import experiment


class BenchmarkExperimentTest(unittest.TestCase):
    def _write_config(self, directory: str, family: str = "structure2property") -> Path:
        config = {
            "experiment": {"release": "demo", "seed": 7},
            "task": {"family": family, "targets": ["energy", "gap"]},
            "model": {"name": "equiformer_v3"},
            "data": {"root": "benchmark_data/demo_10k"},
            "training": {"epochs": 2, "batch_size": 8, "device": "cpu"},
            "output": {"root": str(Path(directory) / "runs")},
        }
        path = Path(directory) / "experiment.yaml"
        with open(path, "w", encoding="utf-8") as handle:
            yaml.safe_dump(config, handle)
        return path

    def test_load_and_build_equiformer_command(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(directory)
            config = experiment.load_config(path)
            run_dir = experiment.default_run_dir(config, run_id="trial")
            command = experiment.build_command(config, run_dir)
        self.assertIn("benchmarks.models.equiformer_v3.train", command)
        self.assertIn("--targets", command)
        self.assertIn("energy", command)
        self.assertIn("gap", command)
        self.assertIn("--progress", command)
        self.assertIn("--progress-interval-seconds", command)
        self.assertIn("auto", command)
        self.assertIn("trial", str(run_dir))

    def test_vib2conf_command_uses_shared_progress_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(directory, family="spectrum2property")
            config = yaml.safe_load(path.read_text())
            config["task"]["targets"] = ["dipole_total"]
            config["model"]["name"] = "vib2conf"
            path.write_text(yaml.safe_dump(config))
            normalized = experiment.load_config(path)
            command = experiment.build_command(
                normalized,
                experiment.default_run_dir(normalized, run_id="progress"),
            )
        self.assertIn("benchmarks.models.vib2conf.props_head", command)
        self.assertIn("--progress", command)
        self.assertIn("--progress-interval-seconds", command)

    def test_vib2mol_yaml_uses_internal_model_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(directory)
            config = yaml.safe_load(path.read_text())
            config["task"] = {
                "family": "spectrum2structure",
                "targets": ["kekule_smiles"],
                "modality": "ir-raman",
            }
            config["model"] = {"name": "vib2mol", "stage": "pipeline"}
            config["training"]["gpus"] = 1
            path.write_text(yaml.safe_dump(config))
            normalized = experiment.load_config(path)
            command = experiment.build_command(
                normalized,
                experiment.default_run_dir(normalized, run_id="vib2mol"),
            )
        self.assertIn("benchmarks.models.vib2mol.workflow", command)
        self.assertNotIn("benchmarks", command[3:4])

    def test_invalid_progress_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(directory)
            config = yaml.safe_load(path.read_text())
            config["training"]["progress"] = "animated"
            path.write_text(yaml.safe_dump(config))
            with self.assertRaisesRegex(ValueError, "training.progress"):
                experiment.load_config(path)

    def test_non_positive_progress_interval_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(directory)
            config = yaml.safe_load(path.read_text())
            config["training"]["progress_interval_seconds"] = 0
            path.write_text(yaml.safe_dump(config))
            with self.assertRaisesRegex(ValueError, "progress_interval_seconds"):
                experiment.load_config(path)

    def test_pty_progress_follows_terminal_and_explicit_mode(self):
        self.assertTrue(experiment._use_pty_progress("auto", terminal_is_tty=True))
        self.assertFalse(experiment._use_pty_progress("auto", terminal_is_tty=False))
        self.assertTrue(experiment._use_pty_progress("tqdm", terminal_is_tty=False))
        self.assertFalse(experiment._use_pty_progress("log", terminal_is_tty=True))

    def test_pty_receives_parent_terminal_dimensions(self):
        with mock.patch.object(
            experiment.shutil,
            "get_terminal_size",
            return_value=os.terminal_size((160, 48)),
        ), mock.patch.object(experiment.fcntl, "ioctl") as ioctl:
            size = experiment._set_pty_window_size(17)
        self.assertEqual(size, os.terminal_size((160, 48)))
        ioctl.assert_called_once()
        self.assertEqual(ioctl.call_args.args[:2], (17, experiment.termios.TIOCSWINSZ))

    def test_dry_run_does_not_create_run_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(directory)
            summary = experiment.run_experiment(path, dry_run=True, run_id="dry")
            self.assertFalse(Path(summary["run_dir"]).exists())
            self.assertTrue(summary["artifacts_persisted"])

    def test_debug_mode_overrides_runtime_without_persistent_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(directory)
            summary = experiment.run_experiment(
                path, dry_run=True, run_id="smoke", debug=True
            )
            command = summary["command"]
            self.assertTrue(summary["debug"])
            self.assertIn("--debug", command)
            self.assertEqual(command[command.index("--epochs") + 1], "1")
            self.assertEqual(command[command.index("--workers") + 1], "0")
            self.assertIsNone(summary["run_dir"])
            self.assertFalse(summary["artifacts_persisted"])
            self.assertFalse((Path(directory) / "runs").exists())

    def test_completed_debug_run_removes_temporary_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(directory)
            config = yaml.safe_load(path.read_text())
            config["training"]["progress"] = "tqdm"
            path.write_text(yaml.safe_dump(config))
            process = mock.Mock()
            with mock.patch.object(
                experiment, "_run_with_pty", return_value=(process, 0)
            ) as runner:
                summary = experiment.run_experiment(path, debug=True)
            temporary_run_dir = Path(runner.call_args.args[2]).parent
            self.assertFalse(temporary_run_dir.exists())
            self.assertIsNone(summary["run_dir"])
            self.assertFalse(summary["artifacts_persisted"])
            self.assertFalse((Path(directory) / "runs").exists())

    def test_debug_vib2mol_forwards_subset_and_epochs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(directory)
            config = yaml.safe_load(path.read_text())
            config["task"] = {
                "family": "spectrum2structure",
                "targets": ["kekule_smiles"],
            }
            config["model"] = {"name": "vib2mol"}
            path.write_text(yaml.safe_dump(config))
            summary = experiment.run_experiment(path, dry_run=True, debug=True)
            self.assertIn('--debug', summary['command'])
            self.assertIn('--debug-train-samples', summary['command'])
            self.assertFalse(summary['artifacts_persisted'])

    def test_invalid_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(directory)
            config = yaml.safe_load(path.read_text())
            config["task"]["targets"] = ["raman_spectrum"]
            path.write_text(yaml.safe_dump(config))
            with self.assertRaisesRegex(ValueError, "Unsupported targets"):
                experiment.load_config(path)


if __name__ == "__main__":
    unittest.main()
