import tempfile
import unittest
from pathlib import Path

import torch
from transformers import AutoTokenizer

from benchmarks.models.vib2mol.audit_tokenizer import TOKENIZER, inspect_strings
from benchmarks.models.vib2mol.evaluate_multimodal import (
    canonical, unique_candidates, rerank_candidates, spectrum_row,
    spectral_fields,
)
from benchmarks.models.vib2mol.workflow import evaluation_command


class MatchingStub:
    def __init__(self):
        self.encodes = 0

    def encode_spectra(self, batch):
        self.encodes += 1
        assert 'nmr_c_shifts_ppm' in batch and 'nmr_h_mask' in batch
        return dict(hidden_states=torch.ones(1, 4, 2), mask=torch.tensor([[1, 1, 0, 0]]))

    def molecular_encoding(self, ids, use_cls_token):
        return ids

    def molecular_encoder(self, ids, memory, src_mask, tgt_mask, multimodal):
        assert memory.shape[0] == len(ids) and tgt_mask.shape[1] == ids.shape[1]+1
        assert not src_mask[:, -1].any()
        lengths = (ids != 1).sum(1).float()
        # Raw positive logits and positive probabilities have different rankings.
        return dict(proj_output=torch.stack((lengths*2, lengths), 1))


class Vib2MolEvaluationTest(unittest.TestCase):
    def test_tokenizer_ring_numbers_and_known_stereo_loss(self):
        tokenizer = AutoTokenizer.from_pretrained(TOKENIZER, local_files_only=True)
        rows = inspect_strings(tokenizer, ['C13', '[13CH4]', 'C%13CCCCC%13', 'N[C@@H](C)O', 'C/C=C\\C'])
        self.assertTrue(all(x['roundtrip'] and not x['unknown'] for x in rows[:3]))
        self.assertTrue(all(not x['roundtrip'] for x in rows[3:]))
        self.assertEqual(len(tokenizer), 181)

    def test_invalid_and_duplicate_candidates(self):
        self.assertIsNone(canonical(''))
        self.assertIsNone(canonical('*'))
        self.assertEqual(unique_candidates(['CCO', 'OCC', '*', 'N']), ['CCO', 'N'])
        self.assertEqual(canonical('c1ccccc1'), 'C1=CC=CC=C1')

    def test_chunked_positive_probability_and_nmr_masks(self):
        tokenizer = AutoTokenizer.from_pretrained(TOKENIZER, local_files_only=True)
        model = MatchingStub()
        batch = dict(ir=torch.zeros(2,1,1024), raman=torch.zeros(2,1,1024),
                     nmr_c_shifts_ppm=torch.zeros(2,2), nmr_h_mask=torch.ones(2,3))
        row = spectrum_row(batch, 1)
        order, scores = rerank_candidates(model, tokenizer, row, ['CCC', 'C', 'CC'], 2)
        self.assertEqual(order, [1,2,0])
        self.assertEqual(model.encodes, 1)
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(rerank_candidates(model, tokenizer, row, []), ([], []))

    def test_multimodal_rerank_command(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory)/'model.pth'
            checkpoint.touch()
            for action in ('retrieval-eval', 'generation-eval'):
                command = evaluation_command(action, modality='ir-raman-nmr',
                    checkpoint=checkpoint, rank_checkpoint=checkpoint, device='cpu',
                    rerank=True, topk=50, batch_size=8)
                self.assertIn('--rank_model_path', command)
                self.assertEqual(command[command.index('--topk')+1], '50')
                self.assertEqual(command[command.index('--batch-size')+1], '8')
                self.assertEqual(command[command.index('--modality')+1],
                                 'ir-raman-nmr')

    def test_hnmr_evaluation_uses_multimodal_evaluator(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory)/'model.pth'
            checkpoint.touch()
            command = evaluation_command(
                'generation-eval', modality='ir-raman-hnmr',
                checkpoint=checkpoint, device='cpu')
            self.assertTrue(any('evaluate_multimodal.py' in item
                                for item in command))
            self.assertEqual(command[command.index('--modality')+1],
                             'ir-raman-hnmr')

    def test_plain_generation_uses_maintained_formula_optional_evaluator(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory)/'model.pth'
            checkpoint.touch()
            for modality, fields in (('ir', ['ir']),
                                     ('ir-raman', ['ir', 'raman'])):
                command = evaluation_command(
                    'generation-eval', modality=modality,
                    checkpoint=checkpoint, device='cpu')
                self.assertTrue(any('evaluate_multimodal.py' in item
                                    for item in command))
                self.assertNotIn('--use_formula', command)
                self.assertEqual(spectral_fields(modality), fields)
