"""Atom-level shift supervision and YAML integration."""
import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path

import torch
from torch_geometric.data import Batch, Data

from benchmarks.engines.nmr_shifts import NMRShiftEngine
from benchmarks.engines.normalization import TargetNormalizer
from benchmarks.models.equiformer_v3.nmr import AtomNMRModel
from benchmarks.trainers.experiment import load_config, build_command, default_run_dir
from benchmarks.trainers.hessian import NMRShiftTrainer


SMALL_BACKBONE = dict(num_layers=1, num_channels=16, lmax=2, mmax=2,
                      num_heads=2, attn_hidden_channels=8, attn_alpha_channels=8,
                      attn_value_channels=8, ffn_hidden_channels=16, edge_channels=16)


def graph(z=(1, 6, 8)):
    z = torch.tensor(z)
    n = len(z)
    pairs = [(i, j) for i in range(n) for j in range(n) if i != j]
    return Batch.from_data_list([Data(
        pos=torch.tensor([[0., 0., 0.], [1., .2, 0.], [.1, 1., .3]])[:n],
        atomic_numbers=z, edge_index=torch.tensor(pairs, dtype=torch.long).reshape(-1, 2).T,
        nmr_shift=torch.zeros(n, 1), nmr_h_mask=z == 1, nmr_c_mask=z == 6)])


def engine(model):
    return NMRShiftEngine(model=model, targets=['H', 'C'], train_loader=[],
                          eval_loader=[], test_loader=[],
                          normalizer=TargetNormalizer({'H': 0., 'C': 0.}, {'H': 2., 'C': 10.}),
                          optimizer=None, device='cpu', progress_mode='log')


class NMRTrainingTest(unittest.TestCase):
    def test_config(self):
        cfg = load_config('benchmarks/configs/structure2nmr/hc_ks200k_r5.yaml')
        cmd = build_command(cfg, default_run_dir(cfg))
        self.assertIn('structure2nmr', cmd)
        self.assertIn('--nproc_per_node=2', cmd)
        self.assertEqual(cmd[cmd.index('--batch-size') + 1], '64')
        self.assertIn('312500', cmd)
        self.assertIn('H', cmd)
        self.assertIn('C', cmd)
        full = load_config('benchmarks/configs/structure2nmr/hc_ks1000k_r5.yaml')
        self.assertEqual(cfg['model'], full['model'])
        self.assertEqual(cfg['training'], full['training'])

    def test_ppm_metrics_and_balanced_loss(self):
        parameter = torch.tensor(1., requires_grad=True)
        eng = engine(lambda batch: {t: parameter.expand(3, 1) for t in ('H', 'C')})
        batch = graph()
        loss = eng.compute_loss(batch)
        self.assertAlmostEqual(loss.detach().item(), .5)
        loss.backward()
        self.assertAlmostEqual(parameter.grad.item(), 1.)
        col = eng.new_collection()
        eng.collect_batch(col, batch, eng.model(batch))
        metrics = eng.compute_metrics(col)
        self.assertEqual(metrics['MAE_H'], 2.)
        self.assertEqual(metrics['MAE_C'], 10.)
        self.assertEqual(metrics['count_H'], 1)

    def test_global_nucleus_counts(self):
        parameter = torch.tensor(2., requires_grad=True)
        eng = engine(lambda batch: {t: parameter.expand(3, 1) for t in ('H', 'C')})
        # Four global atoms per nucleus, one local: scale by world/count.
        with patch('torch.distributed.is_initialized', return_value=True), \
             patch('torch.distributed.get_world_size', return_value=2), \
             patch('torch.distributed.all_reduce', side_effect=lambda count: count.fill_(4)):
            loss = eng.compute_loss(graph())
        self.assertAlmostEqual(loss.detach().item(), .75)
        loss.backward()
        self.assertAlmostEqual(parameter.grad.item(), .5)

    def test_checkpoint_reference_guard(self):
        model = torch.nn.Linear(1, 1)
        model.checkpoint_metadata = {'reference': 'test', 'unit': 'ppm'}
        eng = engine(model)
        with tempfile.TemporaryDirectory() as directory:
            trainer = NMRShiftTrainer(model=model, engine=eng, scheduler=None,
                                      checkpoint_path=Path(directory) / 'best.pt',
                                      epochs=1, device='cpu')
            self.assertEqual(trainer.validation_score({'MAE_H': 2., 'MAE_C': 10.}), 1.)
            trainer._save_checkpoint()
            trainer._load_model_and_normalizer()
            model.checkpoint_metadata['reference'] = 'wrong'
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                trainer._load_model_and_normalizer()

    def test_invariant_atomic_heads_and_empty_supervision(self):
        torch.manual_seed(4)
        model = AtomNMRModel(backbone=SMALL_BACKBONE).eval()
        batch = graph()
        outputs = model(batch)
        rotated = batch.clone()
        rotated.pos = batch.pos @ torch.tensor([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]]) + 2
        with torch.no_grad():
            transformed = model(rotated)
        for t in outputs:
            self.assertEqual(outputs[t].shape, (3, 1))
            torch.testing.assert_close(outputs[t], transformed[t], atol=3e-4, rtol=3e-3)
        permutation = torch.tensor([2, 0, 1])
        permuted = batch.clone()
        permuted.pos = batch.pos[permutation]
        permuted.atomic_numbers = batch.atomic_numbers[permutation]
        permuted.edge_index = permutation.argsort()[batch.edge_index]
        with torch.no_grad():
            reordered = model(permuted)
        for t in outputs:
            torch.testing.assert_close(reordered[t], outputs[t][permutation], atol=3e-4, rtol=3e-3)
        loss = engine(model).compute_loss(batch)
        loss.backward()
        for head in model.heads.values():
            self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in head.parameters()))
        model.zero_grad(set_to_none=True)
        empty = graph((8,))  # no edges, no H/C: must not drop the graph or skip backward
        loss = engine(model).compute_loss(empty)
        self.assertEqual(loss.detach().item(), 0.)
        loss.backward()
        for head in model.heads.values():
            self.assertTrue(all(p.grad is not None for p in head.parameters()))
        # Isolated atom prediction must not depend on whether other graphs
        # happen to supply edges to this batch.
        single = graph((1,))
        combined = Batch.from_data_list([single.to_data_list()[0], batch.to_data_list()[0]])
        with torch.no_grad():
            isolated_output, mixed_output = model(single), model(combined)
        for t in isolated_output:
            torch.testing.assert_close(isolated_output[t], mixed_output[t][:1], atol=3e-4, rtol=3e-3)


if __name__ == '__main__':
    unittest.main()
