import unittest
from unittest.mock import patch
import torch
import numpy as np
from torch_geometric.data import Batch
from benchmarks.models.equiformer_v3.hessian import DirectHessianModel
from benchmarks.data.prepare_response import response_record


class ResponseBenchmarkTest(unittest.TestCase):
    def test_rotation_symmetry_and_gradients(self):
        backbone = dict(
            num_layers=1, num_channels=16, lmax=3, mmax=2, num_heads=2,
            attn_hidden_channels=8, attn_alpha_channels=8, attn_value_channels=8,
            ffn_hidden_channels=16, edge_channels=16,
        )
        torch.manual_seed(14)
        model = DirectHessianModel(["dedipole", "depolar"], backbone).eval()
        data = response_record(
            [6, 8, 1], [[0, 0, 0], [1.2, .1, 0], [-.3, 1, .4]],
            np.zeros((3, 3, 3)), np.zeros((3, 3, 3, 3)), "sample",
        )
        batch = Batch.from_data_list([data])
        with patch('benchmarks.models.equiformer_v3.hessian.CartesianTensor',
                   side_effect=AssertionError('Tensor codegen in forward')):
            outputs = model(batch)
            model.train()
            model(batch)
            model.eval()
        rotation, _ = torch.linalg.qr(torch.randn(3, 3))
        if torch.det(rotation) < 0:
            rotation[:, 0] *= -1
        rotated = batch.clone()
        rotated.pos = batch.pos @ rotation.T
        transformed = model(rotated)
        for name, value in outputs.items():
            expected = (
                rotation @ value @ rotation.T if name == "dedipole" else
                torch.einsum("ia,jb,kc,nabc->nijk", rotation, rotation, rotation, value)
            )
            torch.testing.assert_close(transformed[name], expected, atol=3e-4, rtol=3e-3)
        torch.testing.assert_close(outputs["depolar"], outputs["depolar"].transpose(-1, -2))
        sum(value.square().mean() for value in outputs.values()).backward()
        for name, head in model.heads.items():
            gradients = [parameter.grad for parameter in head.parameters()
                         if parameter.grad is not None]
            self.assertTrue(gradients, name)
            self.assertTrue(all(torch.isfinite(gradient).all() for gradient in gradients))

    def test_cached_conversion_matches_legacy_outputs_and_gradients(self):
        from e3nn.io import CartesianTensor
        # Only conversion is needed here; avoid building a second backbone.
        model = DirectHessianModel.__new__(DirectHessianModel)
        torch.nn.Module.__init__(model)
        model.response_layouts = {}
        for name, formula in [('dedipole', 'ij'), ('depolar', 'ijk=ikj')]:
            tensor = CartesianTensor(formula)
            basis = tensor.reduced_tensor_products().change_of_basis
            model.register_buffer(f'basis_{name}', basis)
            model.response_layouts[name] = tuple((mul, ir.l) for mul, ir in tensor)
            spherical = torch.randn(5, 16, 2, requires_grad=True)
            pieces = [spherical[:, ir.l**2:(ir.l+1)**2, :mul]
                      .transpose(1, 2).flatten(1) for mul, ir in tensor]
            expected = (torch.cat(pieces, 1) @ basis.flatten(1)).reshape(-1, *basis.shape[1:])
            actual = model._response_to_cartesian(name, spherical)
            torch.testing.assert_close(actual, expected, rtol=0, atol=0)
            weight = torch.randn_like(expected)
            old_grad = torch.autograd.grad((expected * weight).sum(), spherical)[0]
            new_grad = torch.autograd.grad((actual * weight).sum(), spherical)[0]
            torch.testing.assert_close(new_grad, old_grad, rtol=0, atol=0)
        # Cached layout is not a new checkpoint key; legacy basis keys remain.
        self.assertEqual(set(model.state_dict()), {'basis_dedipole', 'basis_depolar'})
        model.load_state_dict(model.state_dict(), strict=True)

    def test_export_preserves_units_and_axes(self):
        dd = np.arange(27).reshape(3, 3, 3)
        dp = np.arange(81).reshape(3, 3, 3, 3)
        dp = dp + dp.swapaxes(-1, -2)
        d = response_record([6, 8, 1], [[0, 0, 0], [1, 0, 0], [0, 1, 0]], dd, dp, "sample")
        np.testing.assert_array_equal(d.dedipole, dd)
        np.testing.assert_array_equal(d.depolar, dp)
        with self.assertRaisesRegex(ValueError, "asymmetric"):
            response_record([6, 8, 1], d.pos, dd, np.arange(81).reshape(3, 3, 3, 3), "bad")

    def test_configs_and_ddp(self):
        from benchmarks.trainers.experiment import load_config, build_command, default_run_dir
        from benchmarks.models.equiformer_v3.train import build_parser
        for target in ("dedipole", "depolar"):
            cfg = load_config(f"benchmarks/configs/structure2response/{target}_ks200k_r5.yaml")
            command = build_command(cfg, default_run_dir(cfg))
            self.assertIn("--nproc_per_node=2", command)
            self.assertEqual(command[command.index("--task") + 1], "structure2response")
            self.assertEqual(cfg["task"]["targets"], [target])
            adapter_args = command[command.index("--task"):]
            parsed = build_parser().parse_args(adapter_args)
            self.assertEqual(parsed.targets, [target])
