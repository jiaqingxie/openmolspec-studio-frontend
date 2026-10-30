import argparse
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import torch
import torch.distributed as dist
import torch.multiprocessing as mp
from torch.nn.parallel import DistributedDataParallel

from benchmarks.models.vib2mol.steps import train_steps
from benchmarks.models.vib2mol import workflow
from benchmarks.trainers.experiment import load_config, build_command


class TinyModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.tensor(1.0))

    def forward(self, data, **kwargs):
        loss = self.weight.square()
        return dict(loss=loss, mlm_loss=loss / 2, lm_loss=loss / 2)

    def infer_lm(self, data, **kwargs):
        return dict(metrics=torch.tensor(0.5))


def trial(directory, length, generation=False, ddp=False, debug=False):
    model = TinyModel()
    if ddp:
        model = DistributedDataParallel(model)
    batch = dict(data={'smiles': {'input_ids': torch.ones(2, 3, dtype=torch.long)}}, batch_size=2)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.1)
    rates, evaluations = [], []
    optimizer.register_step_pre_hook(lambda opt, a, k: rates.append(opt.param_groups[0]['lr']))
    def evaluate(step):
        evaluations.append(step)
        model.eval()
        return dict(recall=0.5, loss=0.1)
    engine = SimpleNamespace(model=model, optimizer=optimizer, device='cpu',
                             train_loader=[batch] * length, eval_loader=[batch],
                             _put_on_device=lambda data: data, eval_epoch=evaluate,
                             scheduler=Mock())
    trainer = SimpleNamespace(engine=engine, model=model, writer=Mock(), ddp=ddp,
                              train_sampler=Mock(), model_save_path=str(directory),
                              config=dict(max_steps=5, eval_every_steps=2,
                                          debug_step_budget=debug))
    train_steps(trainer, generation=generation)
    engine.scheduler.step.assert_not_called()
    if not ddp or dist.get_rank() == 0:
        summary = json.loads((Path(directory) / 'training_summary.json').read_text())
        assert summary['global_step'] == (min(length, 5) if debug else 5)
        assert summary['final_lr'] == [0.0]
        assert summary['best_step'] == 2
        assert not summary['early_stopping']
        ckpt = Path(directory) / ('best_acc.pth' if generation else 'best_recall.pth')
        assert ckpt.is_file()
        model.load_state_dict(torch.load(ckpt, weights_only=True))
        trainer.writer.close.assert_called_once()
        steps = [call.args[2] for call in trainer.writer.add_scalar.call_args_list
                 if call.args[0] == 'validation/loss']
        assert steps == ([2] if debug else [2, 4, 5])
    if ddp:
        assert trainer.train_sampler.set_epoch.call_count == (1 if debug else 3)
    return rates, evaluations


def rank_trial(rank, rendezvous, directory):
    dist.init_process_group('gloo', init_method=rendezvous, rank=rank, world_size=2)
    try:
        for generation in (False, True):
            trial(Path(directory) / str(generation), 2, generation=generation, ddp=True)
            dist.barrier()
    finally:
        dist.destroy_process_group()


class Vib2MolStepTests(unittest.TestCase):
    def test_schedule_independent_of_dataset_length_and_final_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            small = trial(Path(directory) / 'small', 2)
            large = trial(Path(directory) / 'large', 7)
            self.assertEqual(small, large)
            self.assertEqual(small[1], [2, 4, 5])
            self.assertEqual(len(small[0]), 5)
            self.assertEqual(small[0][0], 0.1)

    def test_generation_evaluates_at_non_multiple_of_five_and_debug_caps(self):
        with tempfile.TemporaryDirectory() as directory:
            trial(Path(directory) / 'generation', 2, generation=True)
            trial(Path(directory) / 'debug', 2, generation=True, debug=True)

    def test_two_rank_both_stages(self):
        with tempfile.TemporaryDirectory() as directory:
            rendezvous = (Path(directory) / 'rendezvous').as_uri()
            mp.spawn(rank_trial, args=(rendezvous, directory), nprocs=2, join=True)

    def test_yaml_to_stage_cli_and_checkpoint_discovery(self):
        config = load_config('benchmarks/configs/spectrum2structure/vib2mol.yaml')
        with tempfile.TemporaryDirectory() as directory:
            command = build_command(config, Path(directory))
            parser = argparse.ArgumentParser()
            workflow.configure_parser(parser)
            args = parser.parse_args(command[3:])
            workflow.validate_args(parser, args)
            self.assertEqual(args.max_steps, 312500)
            self.assertEqual(args.generation_max_steps, 312500)
            self.assertNotIn('--epochs', command)
            stage = workflow.training_command(
                'matching', modality=args.modality, epochs=args.epochs,
                batch_size=args.batch_size, learning_rate=args.lr, device=args.device,
                max_steps=args.max_steps, eval_every_steps=args.eval_every_steps, debug=True)
            self.assertIn('--debug-step-budget', stage)
            self.assertNotIn('--epoch', stage)
            folder = Path(directory) / 'checkpoints/openspec/task/vib2mol/run'
            folder.mkdir(parents=True)
            best = folder / 'best_recall.pth'
            best.touch()
            self.assertEqual(workflow.newest_checkpoint('task', work_dir=Path(directory),
                                                       metric='recall'), best.resolve())

    def test_mixed_budgets_rejected(self):
        parser = argparse.ArgumentParser()
        workflow.configure_parser(parser)
        for extra in (['--epochs', '2', '--max-steps', '5'],
                      ['--generation-max-steps', '5'], ['--max-steps', '0']):
            with self.assertRaises(SystemExit):
                workflow.validate_args(parser, parser.parse_args(['pipeline', *extra]))


if __name__ == '__main__':
    unittest.main()
