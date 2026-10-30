import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch
import torch.distributed as dist
import torch.multiprocessing as mp

from benchmarks.models.vib2mol.lifecycle import update_stop
from benchmarks.models.vib2mol import train_entry


class Stop:
    def __init__(self):
        self.best_score = None
        self.val_score = -float('inf')
        self.counter = 0
        self.early_stop = False

    def __call__(self, score, model, path):
        if self.best_score is None or score > self.best_score:
            self.best_score = self.val_score = score
            self.counter = 0
        else:
            self.counter += 1
        self.early_stop = self.counter >= 2


def check_ranks(rank, rendezvous):
    dist.init_process_group('gloo', init_method=rendezvous, rank=rank, world_size=2)
    try:
        for generation in (False, True):
            trainer = SimpleNamespace(es=Stop(), model=None, model_save_path='unused')
            for epoch in range(15):
                # Other ranks' replicated validation is deliberately different.
                score = .5 if rank == 0 else .9
                update_stop(trainer, {'recall': score, 'metrics': score}, epoch, generation)
                assert trainer.es.val_score == .5
                if trainer.es.early_stop:
                    break
            assert epoch == (10 if generation else 2), epoch
        trainer = SimpleNamespace(es=Stop(), model=None, model_save_path='unused')
        try:
            update_stop(trainer, {'recall': float('nan')}, 0, False)
        except RuntimeError as exc:
            assert 'Non-finite' in str(exc)
        else:
            raise AssertionError('Non-finite validation was accepted')
    finally:
        dist.destroy_process_group()


class LifecycleTests(unittest.TestCase):
    def test_two_ranks_stop_together_and_skip_unmeasured_accuracy(self):
        with tempfile.TemporaryDirectory() as directory:
            mp.spawn(check_ranks, args=((Path(directory) / 'rendezvous').as_uri(),),
                     nprocs=2, join=True)

    def test_cleanup_on_failure(self):
        with patch.object(train_entry, 'run', side_effect=ValueError('failure')), \
                patch.object(dist, 'is_initialized', return_value=True), \
                patch.object(dist, 'destroy_process_group') as cleanup:
            with self.assertRaisesRegex(ValueError, 'failure'):
                train_entry.main()
            cleanup.assert_called_once()


if __name__ == '__main__':
    unittest.main()
