import unittest
from pathlib import Path

from benchmarks.models.vib2conf.factory import (
    build_ir_property_model,
    build_ir_raman_nmr_property_model,
    build_ir_raman_property_model,
    build_spectrum_property_model,
)
from benchmarks.models.vib2mol.factory import (
    build_ir_raman_hnmr_vib2mol,
    build_ir_raman_nmr_vib2mol,
    build_ir_raman_vib2mol,
    build_ir_vib2mol,
    make_vib2mol_factory,
)
from benchmarks.trainers.experiment import build_command, load_config


NMR_STATS = {
    "c": {"median": 100.0, "scale": 80.0},
    "h": {"median": 4.0, "scale": 3.0},
}
MODEL_KWARGS = {
    "property_targets": ["gap"],
    "d_model": 32,
    "nheads": 4,
    "nlayers": 2,
    "encoder_layers": 1,
    "pooling_layers": 1,
    "pooling_queries": 8,
    "fusion_channels": 4,
    "hidden_channels": 16,
    "dropout": 0.0,
}


class DummyMultimodal:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class SpectroscopyFactoryTests(unittest.TestCase):
    def test_property_factories_are_explicit_and_controlled(self):
        ir = build_ir_property_model(**MODEL_KWARGS)
        ir_raman = build_ir_raman_property_model(**MODEL_KWARGS)
        full = build_ir_raman_nmr_property_model(
            nmr_statistics=NMR_STATS,
            **MODEL_KWARGS,
        )
        self.assertEqual(ir.modality, "ir")
        self.assertEqual(ir_raman.modality, "ir-raman")
        self.assertEqual(full.modality, "ir-raman-nmr")
        self.assertFalse(ir.use_nmr)
        self.assertFalse(ir_raman.use_nmr)
        self.assertTrue(full.use_nmr)
        self.assertTrue(full.nmr_fitted)
        parameter_counts = {
            sum(parameter.numel() for parameter in model.parameters())
            for model in (ir, ir_raman, full)
        }
        self.assertEqual(len(parameter_counts), 1)
        with self.assertRaisesRegex(ValueError, "requires train-split"):
            build_ir_raman_nmr_property_model(**MODEL_KWARGS)
        self.assertEqual(
            build_spectrum_property_model("ir", **MODEL_KWARGS).modality,
            "ir",
        )

    def test_vib2mol_factories_enforce_channel_count_and_nmr_reference(self):
        upstream = lambda **kwargs: kwargs
        self.assertEqual(build_ir_vib2mol(upstream)["spectral_channel"], 1)
        self.assertEqual(
            build_ir_raman_vib2mol(upstream)["spectral_channel"],
            2,
        )
        with self.assertRaisesRegex(ValueError, "requires spectral_channel=1"):
            build_ir_vib2mol(upstream, spectral_channel=2)
        normalizer = {
            "statistics": NMR_STATS,
            "reference_id": "giao-opbe-tms-v1",
        }
        full = build_ir_raman_nmr_vib2mol(
            DummyMultimodal,
            nmr_normalizer=normalizer,
            phase=1,
        )
        self.assertEqual(full.kwargs["spectral_channel"], 2)
        self.assertEqual(full.kwargs["nmr_reference_id"], "giao-opbe-tms-v1")
        self.assertIs(full.kwargs["nmr_statistics"], NMR_STATS)
        h_only = build_ir_raman_hnmr_vib2mol(
            DummyMultimodal,
            nmr_normalizer=normalizer,
            phase=1,
        )
        self.assertEqual(h_only.kwargs["nuclei"], ("h",))
        self.assertEqual(full.kwargs["nuclei"], ("c", "h"))
        factory = make_vib2mol_factory(
            "ir-raman",
            upstream_factory=upstream,
        )
        self.assertEqual(factory(phase=2)["spectral_channel"], 2)

    def test_all_1m_ablation_configs_use_the_same_budget_and_data(self):
        property_roots = set()
        for target in ("dipole_total", "polar_iso", "gap"):
            expected = (
                (f"{target}_ir_ks1000k.yaml", "ir"),
                (f"{target}_ir_raman_ks1000k.yaml", "ir-raman"),
                (f"{target}_ks1000k.yaml", "ir-raman-nmr"),
            )
            for filename, modality in expected:
                config = load_config(
                    Path("benchmarks/configs/spectrum2property") / filename
                )
                self.assertEqual(config["task"]["modality"], modality)
                self.assertEqual(config["training"]["max_steps"], 312500)
                self.assertEqual(config["training"]["batch_size"], 128)
                property_roots.add(config["data"]["root"])
        self.assertEqual(len(property_roots), 1)

        structure_roots = set()
        expected = (
            ("vib2mol_ir_ks1000k.yaml", "ir"),
            ("vib2mol_ir_raman_ks1000k.yaml", "ir-raman"),
            ("vib2mol_ir_raman_hnmr_ks1000k.yaml", "ir-raman-hnmr"),
            ("vib2mol_ks1000k.yaml", "ir-raman-nmr"),
        )
        for filename, modality in expected:
            config = load_config(
                Path("benchmarks/configs/spectrum2structure") / filename
            )
            self.assertEqual(config["task"]["modality"], modality)
            self.assertEqual(config["training"]["max_steps"], 312500)
            self.assertEqual(config["training"]["batch_size"], 64)
            structure_roots.add(config["data"]["root"])
            command = build_command(config, Path("unused"))
            self.assertEqual(command[command.index("--modality") + 1], modality)
        self.assertEqual(len(structure_roots), 1)


if __name__ == "__main__":
    unittest.main()
