import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import torch
import torch.distributed as dist
import torch.multiprocessing as mp

from benchmarks.models.vib2mol.matching import gather_tokens, sample_negatives
from benchmarks.models.vib2mol.matching import install
from benchmarks.models.vib2mol.contrastive import contrastive_loss


def check_exchange(rank, rendezvous):
    dist.init_process_group('gloo', init_method=rendezvous, rank=rank, world_size=2)
    try:
        n, length = ((2, 2), (3, 4))[rank]
        molecule = torch.full((n, length, 3), float(rank + 1), requires_grad=True)
        spectrum = torch.full((n, 5, 3), float(rank + 3), requires_grad=True)
        mask = torch.ones(n, length, dtype=torch.long)
        mol, masks, spec, counts, offset = gather_tokens(molecule, mask, spectrum, True)
        assert counts == [2, 3] and offset == (0 if rank == 0 else 2)
        assert mol.shape == (5, 4, 3)
        assert masks[:2, 2:].sum() == 0
        assert mol[:2, 2:].abs().sum() == 0
        # Every rank consumes only remote features; gradients must return home.
        remote = slice(2, 5) if rank == 0 else slice(0, 2)
        (mol[remote].sum() + spec[remote].sum()).backward()
        torch.testing.assert_close(molecule.grad, torch.ones_like(molecule))
        torch.testing.assert_close(spectrum.grad, torch.ones_like(spectrum))
        logits = torch.full((n, 5), -1000.)
        target = 2 if rank == 0 else 0
        logits[:, target] = 0
        sampled = sample_negatives(logits, offset)
        assert (sampled == target).all()
        upstream = Path(__file__).resolve().parents[1] / 'benchmarks/models/vib2mol/upstream'
        if (upstream / 'models/vib2mol.py').exists():
            sys.path.insert(0, str(upstream))
            import importlib
            upstream_models = importlib.import_module('models.vib2mol')
            from benchmarks.models.vib2mol.train_entry import install_adapters
            install_adapters()
            Vib2Mol = upstream_models.Vib2Mol
            forward = Vib2Mol.forward
            install_adapters()
            assert Vib2Mol.forward is forward
            torch.manual_seed(624)
            # Exercise the registered factory used by the real launcher while
            # reducing architecture size for this CPU regression test.
            def small_model(**kwargs):
                kwargs.update(d_model=16, d_proj=8, nhead=2, d_ff=32,
                              encoder_nlayer=1, decoder_nlayer=1)
                return Vib2Mol(**kwargs)
            import models
            with patch.object(upstream_models, 'Vib2Mol', side_effect=small_model):
                model = models.build_model('vib2mol', phase=1)
            assert model.compute_cl_loss.__func__ is contrastive_loss
            assert model.forward.__func__ is forward
            ddp = torch.nn.parallel.DistributedDataParallel(model, find_unused_parameters=True)
            for _ in range(2):
                ddp.zero_grad()
                output = ddp({'ir': torch.randn(n, 1, 32), 'smiles': {
                    'input_ids': torch.randint(5, 20, (n, length)),
                    'attention_mask': torch.ones(n, length)}})
                assert torch.isfinite(output['loss'])
                output['loss'].backward()
                assert all(torch.isfinite(p.grad).all() for p in model.parameters()
                           if p.grad is not None)
    finally:
        dist.destroy_process_group()


class MatchingTests(unittest.TestCase):
    def test_remote_tokens_masks_and_gradients(self):
        with tempfile.TemporaryDirectory() as directory:
            mp.spawn(check_exchange, args=((Path(directory) / 'rendezvous').as_uri(),),
                     nprocs=2, join=True)

    def test_dominant_positive_is_excluded_before_softmax(self):
        indices = sample_negatives(torch.tensor([[1e8, 0.], [0., 1e8]]), 0)
        self.assertEqual(indices.tolist(), [1, 0])

    def test_single_candidate_has_explicit_error(self):
        with self.assertRaisesRegex(ValueError, 'at least two'):
            sample_negatives(torch.ones(1, 1), 0)


if __name__ == '__main__':
    unittest.main()
