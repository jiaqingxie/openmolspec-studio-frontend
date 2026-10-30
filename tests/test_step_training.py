import unittest
from pathlib import Path
from unittest.mock import Mock

import torch

from benchmarks.engines.hessian import HessianEngine
from benchmarks.engines.normalization import TargetNormalizer
from benchmarks.trainers.base import BaseTrainer


class Model(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.tensor(1.))

    def forward(self, batch):
        return {'Hi': self.weight.expand_as(batch['Hi'])}


class Engine(HessianEngine):
    def move_batch(self, batch):
        return batch


class StepTrainingTest(unittest.TestCase):
    def trial(self, length):
        model = Model()
        optimizer = torch.optim.SGD(model.parameters(), lr=.1)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=5)
        batches = [{'Hi': torch.zeros(2)} for _ in range(length)]
        engine = Engine(model=model, targets=['Hi'], train_loader=batches,
                        eval_loader=batches[:1], test_loader=batches[:1],
                        optimizer=optimizer, normalizer=TargetNormalizer({'Hi':0.}, {'Hi':1.}),
                        device='cpu', progress_mode='log')
        trainer = BaseTrainer(model=model, engine=engine, scheduler=scheduler,
                              checkpoint_path=Path('unused.pt'), epochs=1, device='cpu',
                              debug=True, max_steps=5, eval_every_steps=2)
        lrs, evals = [], []
        optimizer.register_step_pre_hook(lambda opt, a, k: lrs.append(opt.param_groups[0]['lr']))
        original = engine.evaluate_validation
        def evaluate(**kwargs):
            evals.append(trainer.global_step)
            return original(**kwargs)
        engine.evaluate_validation = evaluate
        trainer.run()
        return lrs, evals

    def test_schedule_and_validation_independent_of_dataset_length(self):
        small = self.trial(2)
        large = self.trial(7)
        self.assertEqual(small, large)
        self.assertEqual(small[1], [2,4,5])
        self.assertEqual(len(small[0]), 5)
        self.assertEqual(small[0][0], .1)
        self.assertGreater(small[0][-1], 0)

    def test_test_metrics_are_scalars_at_best_step(self):
        writer = Mock()
        BaseTrainer._write_test_scalars(writer, {'MAE_Hi': .02, 'RMSE_Hi':.03}, 5)
        writer.add_scalar.assert_any_call('test/MAE_Hi', .02, 5)
        writer.add_scalar.assert_any_call('test/RMSE_Hi', .03, 5)
        self.assertEqual(writer.add_scalar.call_count, 2)
        writer.add_figure.assert_not_called()
