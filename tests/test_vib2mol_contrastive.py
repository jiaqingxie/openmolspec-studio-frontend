import tempfile
import unittest
from pathlib import Path

import torch
import torch.distributed as dist
import torch.multiprocessing as mp
from torch.nn.parallel import DistributedDataParallel

from benchmarks.models.vib2mol.contrastive import contrastive_loss


class ToyModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = torch.nn.Linear(3, 4)
        self.logit_scale = torch.nn.Parameter(torch.tensor(.2))

    def forward(self, x, y):
        return contrastive_loss(self, self.encoder(x), self.encoder(y), True)


def distributed_check(rank, rendezvous):
    torch.set_num_threads(1)
    dist.init_process_group('gloo', init_method=rendezvous, rank=rank, world_size=2)
    try:
        torch.manual_seed(624)
        model = ToyModel()
        reference = ToyModel()
        reference.load_state_dict(model.state_dict())
        x, y = torch.randn(5, 3), torch.randn(5, 3)
        # Eval mode disables collectives, yielding the single-process reference.
        reference.eval()
        expected = reference(x, y)[0]
        expected.backward()
        ddp = DistributedDataParallel(model)
        section = slice(0, 2) if rank == 0 else slice(2, 5)
        loss, local, _ = ddp(x[section], y[section])
        assert local.shape == (len(x[section]), len(x[section]))
        loss.backward()
        average = loss.detach().clone()
        dist.all_reduce(average)
        torch.testing.assert_close(average / 2, expected.detach())
        for actual, target in zip(model.parameters(), reference.parameters()):
            torch.testing.assert_close(actual.grad, target.grad, atol=2e-6, rtol=2e-5)
    finally:
        dist.destroy_process_group()


class GlobalContrastiveTests(unittest.TestCase):
    def test_two_rank_loss_and_gradient_equal_global_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            mp.spawn(distributed_check, args=((Path(directory) / 'rendezvous').as_uri(),),
                     nprocs=2, join=True)


if __name__ == '__main__':
    unittest.main()
