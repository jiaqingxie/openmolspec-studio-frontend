import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

from benchmarks.engines.base import BaseEngine
from benchmarks.engines.normalization import (
    TargetNormalizer,
    fit_or_load_normalizer,
)
from benchmarks.trainers.base import BaseTrainer


class _RegressionEngine(BaseEngine):
    name = "TestModel"

    def move_batch(self, batch):
        return tuple(value.to(self.device) for value in batch)

    def compute_loss(self, batch):
        features, target = batch
        prediction = self.forward(batch).squeeze(-1)
        normalized = self.require_normalizer().normalize(target, "target")
        return torch.nn.functional.mse_loss(prediction, normalized)

    def forward(self, batch):
        features, _ = batch
        return self.model(features)

    def new_collection(self):
        return {"pred": [], "target": []}

    def collect_batch(self, collection, batch, outputs):
        _, target = batch
        prediction = self.require_normalizer().denormalize(
            outputs.squeeze(-1), "target"
        )
        collection["pred"].append(prediction.cpu().numpy())
        collection["target"].append(target.cpu().numpy())

    def compute_metrics(self, collection):
        prediction = np.concatenate(collection["pred"])
        target = np.concatenate(collection["target"])
        return {"MAE_target": float(np.mean(np.abs(prediction - target)))}


class BenchmarkTrainingTest(unittest.TestCase):
    def _components(self):
        features = torch.arange(8, dtype=torch.float32).reshape(-1, 1)
        targets = 2.0 * features.squeeze(-1) + 1.0
        loader = DataLoader(TensorDataset(features, targets), batch_size=4)
        model = torch.nn.Linear(1, 1)
        optimizer = torch.optim.AdamW(model.parameters(), lr=0.05)
        normalizer = TargetNormalizer.fit(
            loader, ["target"], lambda batch, _: batch[1]
        )
        engine = _RegressionEngine(
            model=model,
            train_loader=loader,
            eval_loader=loader,
            test_loader=loader,
            normalizer=normalizer,
            optimizer=optimizer,
            device="cpu",
            progress_mode="log",
        )
        return model, optimizer, normalizer, engine

    def test_base_trainer_owns_checkpoint_lifecycle(self):
        model, optimizer, _, engine = self._components()
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=2
        )
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "best.pt"
            trainer = BaseTrainer(
                model=model,
                engine=engine,
                scheduler=scheduler,
                checkpoint_path=checkpoint,
                epochs=2,
                device="cpu",
            )
            outcome = trainer.run()
            self.assertTrue(checkpoint.is_file())
            saved = torch.load(checkpoint, weights_only=True)
            self.assertTrue(saved['optimizer']['state'])
            self.assertIn('last_epoch', saved['scheduler'])
            self.assertIn("MAE_target", outcome.best_validation)
            self.assertIn("MAE_target", outcome.test)
            from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

            events = EventAccumulator(str(checkpoint.parent / "tensorboard"))
            events.Reload()
            self.assertEqual([e.step for e in events.Scalars("train/loss")], [1, 2])
            rates = events.Scalars("train/learning_rate_group_0")
            self.assertAlmostEqual(rates[0].value, 0.05)
            self.assertAlmostEqual(rates[1].value, 0.025)
            self.assertEqual(len(events.Scalars("validation/MAE_target")), 2)
            self.assertAlmostEqual(events.Scalars('test/MAE_target')[0].value,
                                   outcome.test['MAE_target'], places=5)
            self.assertNotIn('test/metrics', events.Tags()['images'])

    def test_tensorboard_disabled_for_debug_evaluation_and_nonzero_rank(self):
        model, _, _, engine = self._components()
        for debug, evaluate_only, rank in [(True, False, 0), (False, True, 0), (False, False, 1)]:
            with self.subTest(debug=debug, evaluate_only=evaluate_only, rank=rank):
                trainer = BaseTrainer(
                    model=model, engine=engine, scheduler=None,
                    checkpoint_path=Path("unused.pt"), epochs=1, device="cpu",
                    debug=debug, evaluate_only=evaluate_only,
                )
                with patch("torch.distributed.is_initialized", return_value=True), \
                     patch("torch.distributed.get_rank", return_value=rank), \
                     patch("torch.utils.tensorboard.SummaryWriter") as writer, \
                     patch.object(trainer, "_run") as run:
                    trainer.run()
                    writer.assert_not_called()
                    run.assert_called_once_with(None)

    def test_tensorboard_closes_after_training_failure(self):
        model, _, _, engine = self._components()
        trainer = BaseTrainer(
            model=model, engine=engine, scheduler=None,
            checkpoint_path=Path("unused.pt"), epochs=1, device="cpu",
        )
        with patch("torch.utils.tensorboard.SummaryWriter") as writer, \
             patch.object(trainer, "_run", side_effect=RuntimeError("training failed")):
            with self.assertRaisesRegex(RuntimeError, "training failed"):
                trainer.run()
            writer.return_value.close.assert_called_once()

    def test_engine_owns_one_training_epoch(self):
        _, _, _, engine = self._components()
        stats = engine.train_epoch(epoch=1, total_epochs=1)
        self.assertEqual(stats.batches, 2)
        self.assertTrue(np.isfinite(stats.loss))

    def test_target_normalizer_cache_is_reused_and_invalidated(self):
        features = torch.arange(8, dtype=torch.float32).reshape(-1, 1)
        targets = 2.0 * features.squeeze(-1) + 1.0
        loader = DataLoader(TensorDataset(features, targets), batch_size=4)
        calls = 0

        def values_from_batch(batch, _):
            nonlocal calls
            calls += 1
            return batch[1]

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "train.lmdb"
            source.write_bytes(b"first prepared dataset")
            first = fit_or_load_normalizer(
                loader,
                ["target"],
                values_from_batch,
                source_path=source,
            )
            self.assertEqual(calls, 2)

            second = fit_or_load_normalizer(
                loader,
                ["target"],
                values_from_batch,
                source_path=source,
            )
            self.assertEqual(calls, 2)
            self.assertEqual(first.state_dict(), second.state_dict())

            source.write_bytes(b"replacement prepared dataset is different")
            fit_or_load_normalizer(
                loader,
                ["target"],
                values_from_batch,
                source_path=source,
            )
            self.assertEqual(calls, 4)


if __name__ == "__main__":
    unittest.main()
