"""Online generation must not silently downgrade the advertised ranking protocol."""
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import torch

from openmolspec_ui.inference import OpenMolSpecService
from openmolspec_ui.spectra import SpectralInput


class OnlineGenerationTests(unittest.TestCase):
    def setUp(self):
        self.service = object.__new__(OpenMolSpecService)
        self.encoding = SimpleNamespace(center=torch.tensor([0.]), scale=torch.tensor([1.]))
        self.generation = SimpleNamespace(spectral_encoding=self.encoding,
                                         beam_infer_lm=Mock(return_value={'pred_ids': [['CC', 'CCC']]}))
        self.ranker = SimpleNamespace(spectral_encoding=self.encoding)
        self.tokenizer = SimpleNamespace(decode=lambda value, **kwargs: value)
        self.service._load_vib2mol = lambda phase: (self.generation if phase == 2 else self.ranker, self.tokenizer, 'cpu')
        self.module = ModuleType('benchmarks.models.vib2mol.evaluate_multimodal')
        self.module.unique_candidates = lambda candidates: candidates
        self.module.rerank_candidates = Mock(return_value=([1, 0], [.9, .2]))
        self.inputs = SpectralInput(ir=np.ones(1024), raman=np.ones(1024),
                                    nmr_h=np.array([1.]), nmr_c=np.array([10.]))

    def run_generation(self):
        with patch.dict(sys.modules, {self.module.__name__: self.module}):
            return self.service._generate_vib2mol(self.inputs, 2)

    def test_scores_stay_attached_to_reranked_candidates(self):
        result = self.run_generation()
        self.assertEqual([(row['smiles'], row['score']) for row in result['candidates']], [('CCC', .9), ('CC', .2)])
        self.assertEqual(self.generation.beam_infer_lm.call_args.kwargs['beam_size'], 10)

    def test_reranking_failure_is_visible_to_caller(self):
        self.module.rerank_candidates.side_effect = RuntimeError('ranker unavailable')
        with self.assertRaisesRegex(RuntimeError, 'ranker unavailable'):
            self.run_generation()

    def test_mismatched_normalization_prevents_generation(self):
        self.ranker.spectral_encoding = SimpleNamespace(center=torch.tensor([2.]), scale=torch.tensor([1.]))
        with self.assertRaisesRegex(ValueError, 'normalization differs'):
            self.run_generation()
        self.generation.beam_infer_lm.assert_not_called()


if __name__ == '__main__':
    unittest.main()
