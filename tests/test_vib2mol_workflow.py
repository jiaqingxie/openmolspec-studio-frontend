import os
import tempfile
import time
import unittest
import pickle
import lmdb
import numpy as np
from pathlib import Path
from unittest import mock

from benchmarks.models.vib2mol import workflow


class Vib2MolWorkflowTest(unittest.TestCase):
    def test_validation_checkpoint_ignores_final_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'checkpoints/openspec/task/vib2mol/run'
            folder.mkdir(parents=True)
            best = folder / 'epoch0_recall20.pth'
            last = folder / 'epoch1.pth'
            best.touch()
            last.touch()
            self.assertEqual(workflow.newest_checkpoint('task', work_dir=root, metric='recall'), best.resolve())

    def test_workspace_subsets_do_not_modify_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'data/vib2mol'
            source.mkdir(parents=True)
            for mode in ('train', 'eval', 'test'):
                env = lmdb.open(str(source / f'openspec_{mode}.lmdb'), subdir=False)
                with env.begin(write=True) as txn:
                    for i in range(4):
                        txn.put(str(i).encode(), pickle.dumps(dict(ir=np.ones(1024), raman=np.ones(1024), kekule_smiles='CC')))
                env.close()
            destination = workflow.prepare_workspace(root / 'work', source, (2, 2, 2))
            for mode in ('train', 'eval', 'test'):
                env = lmdb.open(str(destination / f'openspec_{mode}.lmdb'), subdir=False, readonly=True, lock=False)
                self.assertEqual(env.stat()['entries'], 2)
                env.close()
            self.assertEqual(workflow.inspect_data(source)['splits']['train']['records'], 4)

    def test_task_names(self):
        self.assertEqual(workflow.task_name("ir-raman"), "ir-raman-kekule_smiles")
        self.assertEqual(
            workflow.task_name("raman", use_formula=True),
            "raman-kekule_smiles-formula",
        )

    def test_single_gpu_matching_command_uses_upstream_argument_names(self):
        command = workflow.training_command(
            "matching", modality="ir-raman", epochs=3, batch_size=64,
            learning_rate=2e-4, device="cuda:0",
        )
        self.assertEqual(command[0], os.sys.executable)
        self.assertIn("--batch_size", command)
        self.assertIn("--epoch", command)
        self.assertNotIn("--batch-size", command)
        self.assertNotIn("--ddp", command)
        self.assertEqual(
            command[command.index("--spectroscopy-modality") + 1],
            "ir-raman",
        )

    @mock.patch("benchmarks.models.vib2mol.workflow.shutil.which", return_value="/usr/bin/torchrun")
    def test_multi_gpu_generation_command_uses_torchrun(self, _which):
        with tempfile.NamedTemporaryFile() as checkpoint:
            command = workflow.training_command(
                "spt", modality="raman", epochs=2, batch_size=8,
                learning_rate=1e-4, device="cuda", gpus=4,
                base_checkpoint=checkpoint.name, frozen_encoder=True,
            )
        self.assertEqual(command[:4], ["/usr/bin/torchrun", "--standalone", "--nproc_per_node", "4"])
        self.assertIn("--ddp", command)
        self.assertIn("--base_model_path", command)
        self.assertIn("--frozen_encoder", command)

    def test_checkpoint_resolution_is_exact_and_newest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a" / "epoch1.pth"
            second = root / "b" / "epoch2.pth"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.touch()
            second.touch()
            now = time.time()
            os.utime(first, (now - 2, now - 2))
            os.utime(second, (now, now))
            with mock.patch.object(workflow, "_checkpoint_files", return_value=[first, second]):
                self.assertEqual(workflow.newest_checkpoint("task"), second.resolve())
                self.assertEqual(
                    workflow.newest_checkpoint("task", exclude=[second]),
                    first.resolve(),
                )


if __name__ == "__main__":
    unittest.main()
