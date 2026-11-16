"""Recorded examples must retain the evaluated ordering, modality and score."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from spec2struct_fork.train import evaluate_generation


class FixedDecoder:
    config = SimpleNamespace(input_representation='byte', max_source=512)

    def beam_search_batch(self, sources, beam_size):
        return [[('CCO', -1.0), ('COC', -2.0)] for _ in sources]


class GenerationRecordingTests(unittest.TestCase):
    def test_recording_preserves_scores_order_and_visible_inputs(self):
        rows = [
            {'smiles': smiles, 'formula': 'C2H6O',
             'h_nmr': [{'chemical_shift': '1.2'}],
             'c_nmr': [{'chemical_shift': 'hidden-carbon-65.0'}],
             'modality_mask': [1, 1]}
            for smiles in ['CCO', 'COC']
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'examples.jsonl'
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            plain = evaluate_generation(FixedDecoder(), path, 2, 2, modality='h', batch_size=2)
            recorded = evaluate_generation(FixedDecoder(), path, 2, 2, modality='h',
                                           batch_size=2, record_predictions=True)
        predictions = recorded.pop('predictions')
        self.assertEqual(recorded, plain)
        self.assertEqual(plain['exact_rate'], 0.5)
        self.assertEqual([p['reference_smiles'] for p in predictions], ['CCO', 'COC'])
        self.assertEqual(sum(p['exact_match'] for p in predictions), plain['exact'])
        for prediction in predictions:
            self.assertEqual(prediction['input']['modality_mask'], [1, 0])
            self.assertEqual(prediction['input']['c_nmr'], [])
            self.assertEqual(prediction['candidates'][0]['canonical_smiles'], 'CCO')
        json.dumps(predictions)  # Public report remains serializable.


if __name__ == '__main__':
    unittest.main()
