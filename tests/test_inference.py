import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from openmolspec_ui.config import ModelAssets
from openmolspec_ui.inference import OpenMolSpecService
from openmolspec_ui.spectra import SpectralInput


def empty_assets() -> ModelAssets:
    return ModelAssets(
        root=Path("/tmp/missing-openmolspec"),
        hessian_hi_checkpoint=None,
        hessian_hij_checkpoint=None,
        dedipole_checkpoint=None,
        depolar_checkpoint=None,
        nmr_checkpoint=None,
        gap_checkpoint=None,
        retrieval_checkpoint=None,
        generation_checkpoint=None,
        spectrum_lmdb=None,
        generation_predictions=None,
        nmr_normalizer=None,
    )


class ModelPreloadTests(unittest.TestCase):
    def test_default_device_uses_cpu_when_cuda_is_unavailable(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("torch.cuda.is_available", return_value=False),
        ):
            service = OpenMolSpecService(empty_assets())
        self.assertEqual(service.device, "cpu")

    def test_default_device_uses_cuda_when_available(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("torch.cuda.is_available", return_value=True),
        ):
            service = OpenMolSpecService(empty_assets())
        self.assertEqual(service.device, "cuda:0")

    def test_preload_initializes_every_model_on_cuda(self):
        service = OpenMolSpecService(empty_assets(), device="cuda:0")
        with (
            patch("torch.cuda.is_available", return_value=True),
            patch.object(service, "_load_tensor_model") as load_tensor,
            patch.object(service, "_load_nmr") as load_nmr,
            patch.object(service, "_load_gap") as load_gap,
            patch.object(service, "_load_vib2mol") as load_vib2mol,
        ):
            loaded = service.preload()

        self.assertEqual(
            [call.args[0] for call in load_tensor.call_args_list],
            ["Hi", "Hij", "dedipole", "depolar"],
        )
        load_nmr.assert_called_once_with()
        load_gap.assert_called_once_with()
        self.assertEqual(load_vib2mol.call_args_list[0].args, (1,))
        self.assertEqual(load_vib2mol.call_args_list[1].args, (2,))
        self.assertTrue(all(device == "cuda:0" for device in loaded.values()))

    def test_cpu_preload_uses_cached_vib2mol_paths(self):
        service = OpenMolSpecService(empty_assets(), device="cpu")
        with (
            patch.object(service, "_load_theoretical_models"),
            patch.object(service, "_load_nmr"),
            patch.object(service, "_load_gap"),
            patch.object(service, "_load_vib2mol") as load_vib2mol,
        ):
            loaded = service.preload()

        load_vib2mol.assert_not_called()
        self.assertNotIn("vib2mol_retrieval", loaded)
        self.assertNotIn("vib2mol_generation", loaded)


class NMRSimilarityTests(unittest.TestCase):
    def test_identical_unassigned_peak_set_scores_one(self):
        query = np.asarray([1.2, 2.4, 7.1], dtype=np.float32)
        scores = OpenMolSpecService._nmr_scores([query], query, tolerance=0.2)
        self.assertAlmostEqual(float(scores[0]), 1.0, places=6)

    def test_peak_matching_penalizes_missing_and_shifted_peaks(self):
        query = np.asarray([1.2, 2.4, 7.1], dtype=np.float32)
        candidates = [
            np.asarray([1.2, 2.4, 7.1], dtype=np.float32),
            np.asarray([1.2, 2.4], dtype=np.float32),
            np.asarray([4.0, 5.0, 10.0], dtype=np.float32),
        ]
        scores = OpenMolSpecService._nmr_scores(candidates, query, tolerance=0.2)
        self.assertGreater(scores[0], scores[1])
        self.assertGreater(scores[1], scores[2])


class GenerationCandidateTests(unittest.TestCase):
    def test_cached_generation_pools_multiple_nearby_anchors(self):
        service = OpenMolSpecService(empty_assets(), device="cpu")
        dataset = SimpleNamespace(
            records=[
                {"sample_id": "sample-0"},
                {"sample_id": "sample-1"},
            ]
        )
        scores = np.asarray([0.95, 0.90], dtype=np.float32)
        predictions = {
            0: {
                "reranked": ["CCO", "OCC"],
                "positive_probabilities": [0.90, 0.80],
            },
            1: {
                "reranked": ["CCN", "CCC"],
                "positive_probabilities": [0.85, 0.75],
            },
        }
        with (
            patch.object(
                service,
                "nearest_indices",
                return_value=(dataset, np.asarray([0, 1]), scores),
            ),
            patch.object(
                service,
                "_load_generation_predictions",
                return_value=predictions,
            ),
        ):
            result = service.generate(
                SpectralInput(ir=np.ones(1024, dtype=np.float32)), limit=3
            )

        self.assertEqual(len(result["candidates"]), 3)
        self.assertEqual(result["anchors_used"], 2)
        self.assertEqual(
            len({record["smiles"] for record in result["candidates"]}), 3
        )


if __name__ == "__main__":
    unittest.main()
