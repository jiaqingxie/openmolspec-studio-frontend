import unittest
from unittest.mock import patch

import numpy as np
import torch
from torch_geometric.data import Batch

from benchmarks.data.prepare_hessian import hessian_record
from benchmarks.models.equiformer_v3.hessian import DirectHessianModel
from benchmarks.trainers.experiment import load_config, build_command, default_run_dir
from openmolspec.core.constants import HESSIAN_AU_TO_EV_ANGSTROM2
from benchmarks.engines.hessian import HessianEngine


SMALL_BACKBONE = dict(num_layers=1, num_channels=16, lmax=2, mmax=2,
                      num_heads=2, attn_hidden_channels=8, attn_alpha_channels=8,
                      attn_value_channels=8, ffn_hidden_channels=16, edge_channels=16)


class HessianBenchmarkTest(unittest.TestCase):
    def test_ddp_launch_command(self):
        cfg = load_config("benchmarks/configs/structure2hessian/Hi_ks200k.yaml")
        cfg["training"]["gpus"] = 2
        command = build_command(cfg, default_run_dir(cfg))
        self.assertEqual(command[2], "torch.distributed.run")
        self.assertIn("--nproc_per_node=2", command)
        self.assertEqual(command[command.index("--module") + 1],
                         "benchmarks.models.equiformer_v3.train")

    def test_loss_weights_variable_rank_block_counts(self):
        parameter = torch.tensor(2., requires_grad=True)
        engine = HessianEngine(model=lambda batch: {"Hi": parameter.expand(2)},
                               targets=["Hi"], train_loader=[], eval_loader=[],
                               test_loader=[], normalizer=None, optimizer=None,
                               device="cpu", progress_mode="log")
        # Local rank has 2 components, remote rank has 6: mean over all 8.
        with patch("torch.distributed.is_initialized", return_value=True), \
             patch("torch.distributed.get_world_size", return_value=2), \
             patch("torch.distributed.all_reduce", side_effect=lambda count: count.fill_(8)):
            loss = engine.compute_loss({"Hi": torch.zeros(2)})
        loss.backward()
        self.assertAlmostEqual(loss.item(), .75)
        self.assertAlmostEqual(parameter.grad.item(), .5)

    def test_block_order_and_cutoff(self):
        rng = np.random.default_rng(5)
        h = rng.normal(size=(9, 9))
        h = h + h.T
        data, omitted, total = hessian_record(
            [6, 8, 1], [[0, 0, 0], [1, 0, 0], [6, 0, 0]], h, "sample")
        self.assertEqual(data.edge_index.tolist(), [[1, 0], [0, 1]])
        np.testing.assert_allclose(data.Hij[0], h[:3, 3:6]*HESSIAN_AU_TO_EV_ANGSTROM2, rtol=1e-6)
        np.testing.assert_allclose(data.Hij[1], data.Hij[0].T)
        np.testing.assert_allclose(data.Hi[2], h[6:9, 6:9]*HESSIAN_AU_TO_EV_ANGSTROM2, rtol=1e-6)
        self.assertGreater(omitted, 0)
        self.assertLess(omitted, total)

    def test_direct_heads_rotate_and_backpropagate(self):
        torch.manual_seed(14)
        model = DirectHessianModel(backbone=SMALL_BACKBONE).eval()
        data, _, _ = hessian_record(
            [6, 8, 1], [[0, 0, 0], [1.2, .1, 0], [-.3, 1., .4]],
            np.eye(9), "sample")
        batch = Batch.from_data_list([data])
        outputs = model(batch)
        rotation, _ = torch.linalg.qr(torch.randn(3, 3))
        if torch.det(rotation) < 0:
            rotation[:, 0] *= -1
        rotated = batch.clone()
        rotated.pos = batch.pos @ rotation.T
        with torch.no_grad():
            transformed = model(rotated)
        for target in ("Hi", "Hij"):
            expected = rotation @ outputs[target].detach() @ rotation.T
            torch.testing.assert_close(transformed[target], expected, atol=3e-4, rtol=3e-3)
        torch.testing.assert_close(outputs["Hi"], outputs["Hi"].transpose(-1, -2))
        loss = sum((outputs[t] - batch[t]).square().mean() for t in outputs)
        loss.backward()
        for name, head in model.heads.items():
            grads = [p.grad for p in head.parameters() if p.grad is not None]
            self.assertTrue(grads, name)
            self.assertTrue(all(torch.isfinite(g).all() for g in grads))

    def test_yaml_targets_select_direct_hessian_runner(self):
        for target in ("Hi", "Hij"):
            cfg = load_config(f"benchmarks/configs/structure2hessian/{target}_ks200k.yaml")
            command = build_command(cfg, default_run_dir(cfg))
            self.assertIn("structure2hessian", command)
            self.assertIn(target, command)
            self.assertNotIn("--grad-props", command)
