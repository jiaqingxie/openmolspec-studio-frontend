import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch
from benchmarks.engines.vib2conf import Vib2ConfPropertyEngine
from benchmarks.engines.normalization import TargetNormalizer

from benchmarks.data.scalar_properties import (
    ACTIVE_PROPERTY_TARGETS,
    convert_benchmark_units,
    polar_invariants,
)
from benchmarks.data.prepare_spectrum_properties import make_record
from benchmarks.data.prepare import _write_lmdb
from benchmarks.models.vib2conf.dataset import LmdbPropsDataset, collate_properties
from benchmarks.trainers.experiment import load_config, build_command
from openmolspec.core.constants import BOHR_TO_ANGSTROM, HARTREE_TO_EV


class SpectrumPropertiesTests(unittest.TestCase):
    def test_smooth_loss_and_gradient(self):
        class Model(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.pred = torch.nn.Parameter(torch.tensor([.5, 2.]))

            def forward(self, batch):
                return {'gap': self.pred}

        model = Model()
        engine = Vib2ConfPropertyEngine(model=model, train_loader=[], eval_loader=[],
            test_loader=[], normalizer=TargetNormalizer({'gap': 10.}, {'gap': 2.}),
            optimizer=None, device='cpu', progress_mode='log', targets=['gap'])
        loss = engine.compute_loss({'props': {'gap': torch.tensor([10., 10.])}})
        self.assertAlmostEqual(float(loss.detach()), (.125 + 1.5) / 2)
        loss.backward()
        torch.testing.assert_close(model.pred.grad, torch.tensor([.25, .5]))

    def test_invariants(self):
        np.testing.assert_allclose(polar_invariants([1, 0, 2, 0, 0, 3]), [2, np.sqrt(3)])
        np.testing.assert_allclose(polar_invariants(np.eye(3) * 5), [5, 0])
        q, _ = np.linalg.qr(np.random.default_rng(624).normal(size=(3, 3)))
        a = np.array([[1., .3, .2], [.3, 2, .1], [.2, .1, 3]])
        np.testing.assert_allclose(polar_invariants(a), polar_invariants(q @ a @ q.T))
        self.assertTrue(np.isnan(polar_invariants(None)).all())

    def test_record_and_single_target(self):
        record = make_record(dict(ir_spectrum=np.ones(1024), raman_spectrum=np.ones(1024),
                                  dipole_total=2., gap=.1, polar=np.eye(3)))
        self.assertEqual(record['polar_anisotropy'], 0.)
        self.assertAlmostEqual(record['polar_iso'], BOHR_TO_ANGSTROM ** 3)
        self.assertAlmostEqual(record['gap'], .1 * HARTREE_TO_EV)
        self.assertEqual(record['dipole_total'], 2.)
        self.assertEqual(record['units']['gap'], 'eV')
        with self.assertRaises(ValueError):
            convert_benchmark_units(record)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data.lmdb'
            _write_lmdb(path, [('a', record)])
            dataset = LmdbPropsDataset(path, targets=['gap'])
            batch = collate_properties([dataset[0]])
            self.assertEqual(list(batch['props']), ['gap'])
            del dataset
            _write_lmdb(Path(directory) / 'old.lmdb', [('a', {'gap': .1})])
            old = LmdbPropsDataset(Path(directory) / 'old.lmdb', targets=['gap'])
            with self.assertRaisesRegex(ValueError, 'units'):
                old[0]
            del old
        with self.assertRaises(ValueError):
            make_record(dict(ir_spectrum=np.ones(1024), raman_spectrum=np.ones(1024),
                             dipole_total=2., gap=.1, polar=None))

    def test_configs(self):
        for target in ACTIVE_PROPERTY_TARGETS:
            config = load_config(f'benchmarks/configs/spectrum2property/{target}_ks200k.yaml')
            hessian = load_config('benchmarks/configs/structure2hessian/Hi_ks200k_r5.yaml')
            for key in ('max_steps', 'eval_every_steps'):
                self.assertEqual(config['training'][key], hessian['training'][key])
            self.assertEqual(config['training']['batch_size'] * config['training']['gpus'],
                             hessian['training']['batch_size'] * hessian['training']['gpus'])
            for modality in ('ir', 'raman', 'ir-raman'):
                config['task']['modality'] = modality
                command = build_command(config, Path('unused'))
                self.assertIn(target, command)
                self.assertIn('--max-steps', command)
                self.assertEqual(command[command.index('--modality') + 1], modality)


if __name__ == '__main__':
    unittest.main()
