import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from online_api.spectrum_library import (build_index, canonical, LibraryUnavailable,
                                         lookup, resolve, source_files)


class SpectrumLibraryTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.index = self.root / 'index.sqlite'
        for family, split, path in source_files(self.root):
            path.parent.mkdir(exist_ok=True)
            path.touch()
            if split == 'test' and family == 'H+C':
                smile = 'CC(O)C(=O)O'
                row = {'smiles':smile, 'standard_inchikey':canonical(smile)[1],
                       'h_peaks_ppm':[1.1, 4.3], 'h_nmr':[{'solvent':'D2O'}],
                       'h_provenance':{'patent_id':'source-h'}, 'c_peaks_ppm':[]}
                path.write_text(json.dumps(row)+'\n')
        self.assertEqual(build_index(self.root, self.index),1)
        self.service = SimpleNamespace(args=SimpleNamespace(spectra_data=self.root,spectra_index=self.index),
                                       enabled_tasks={'nmr.forward.13C'},submit=Mock(return_value={'id':'job-id'}))

    def test_equivalent_smiles_same_experiment_and_missing_nucleus_predicts(self):
        hit, code = resolve(self.service, {'smiles':'OC(=O)C(O)C','modality':'1H'},'browser')
        self.assertEqual(code,200)
        self.assertEqual(hit['records'][0]['source_id'],'source-h')
        self.assertEqual(hit['records'][0]['conditions'],[{'solvent':'D2O'}])
        self.service.submit.assert_not_called()
        miss, code = resolve(self.service,{'smiles':'CC(O)C(=O)O','modality':'13C'},'browser')
        self.assertEqual((code,miss['origin']),(202,'prediction'))
        self.service.submit.assert_called_once_with({'kind':'tool','task':'nmr.forward.13C',
            'inputs':{'smiles':'CC(O)C(=O)O'}},'browser')

    def test_stereochemistry_and_mass_spectrum_conditions(self):
        self.assertEqual(lookup(self.root,self.index,'C[C@H](O)C(=O)O','1H')['match_count'],0)
        miss, code = resolve(self.service,{'smiles':'CC','modality':'MS'},'browser')
        self.assertEqual((code,miss['origin']),(200,'missing'))
        self.service.submit.assert_not_called()

    def test_stale_or_missing_index_never_starts_inference(self):
        (self.root/'opendatalab_nmr/test.jsonl').write_text('')
        with self.assertRaises(LibraryUnavailable):
            resolve(self.service,{'smiles':'CC','modality':'13C'},'browser')
        self.index.unlink()
        with self.assertRaises(LibraryUnavailable):
            resolve(self.service,{'smiles':'CC','modality':'MS'},'browser')
        self.service.submit.assert_not_called()

    def test_validation_rejects_bad_structure_or_unsupported_measurement(self):
        for query in ({'smiles':'CC name','modality':'1H'},{'smiles':'C1','modality':'IR'},
                      {'smiles':'CC','modality':'unsupported'}):
            with self.assertRaises(ValueError):
                resolve(self.service,query,'browser')


if __name__ == '__main__':
    unittest.main()
