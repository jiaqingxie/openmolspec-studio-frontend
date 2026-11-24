"""Scientific contracts for the numeric comparison examples published by Pages."""
import json
from pathlib import Path
import unittest

ASSETS = Path(__file__).resolve().parents[1] / 'website/assets'


class RecordedComparisonTest(unittest.TestCase):
    def test_labelled_scores_use_fixed_atom_pairs_even_when_matching_would_raise_r2(self):
        data = json.loads((ASSETS/'explore-comparisons.json').read_text())['comparisons']
        spectra = [r for r in data if r['kind']=='nmr']
        self.assertEqual({r['modality'] for r in spectra}, {'1H','13C'})
        for r in spectra:
            pairs = r['reference']['pairs']
            observed = [p['observed'] for p in pairs]
            residuals = [p['observed'] - p['predicted'] for p in pairs]
            mean = sum(observed) / len(observed)
            sd = sum((v-mean)**2 for v in observed)
            self.assertGreaterEqual(len(pairs), 3)
            self.assertAlmostEqual(r['reference']['r2'], 1-sum(v*v for v in residuals)/sd)
            self.assertAlmostEqual(r['reference']['mae'], sum(map(abs,residuals))/len(pairs))
            self.assertEqual(r['reference']['sites'],len(pairs))
            self.assertTrue(all(abs(m['obs']-m['pred']) <= r['tolerance'] for m in r['matched']))
            self.assertEqual(len({tuple(p['atoms']) for p in r['matched']}),len(r['matched']))
            self.assertTrue(set(p['obs'] for p in r['matched']).issubset(r['observed']))

    def test_qm9s_ir_comparisons_retain_source_and_the_reported_positions(self):
        data = json.loads((ASSETS/'explore-comparisons.json').read_text())['comparisons']
        references = {r['model_id']:r for r in data if r['kind']=='ir'}
        record = references['000128']
        self.assertEqual(record['smiles'],'C#CC1CC1')
        self.assertEqual(record['source_id'],'2020/US10689353-20200623')
        self.assertEqual(record['observed'],[1157.,2120.,2873.,3302.,3374.])
        for r in references.values():
            lo,hi,step = r['grid']
            self.assertEqual(len(r['calculated']),(hi-lo)//step+1)
            self.assertEqual(max(r['calculated']),1)
            self.assertEqual(len(r['model_file_sha256']),64)
            self.assertNotIn('r2',r)


if __name__ == '__main__':
    unittest.main()
