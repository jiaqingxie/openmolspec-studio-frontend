import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openmolspec.dataset import MolecularSpectra, SpectraSplit, audit_splits, dataset_info, sha256
from openmolspec.model import NMRNet, NMRTransformer
from openmolspec.training import TrainingPlan, prepare_nmr_training


def example(smiles, formula):
    return {'smiles': smiles, 'formula': formula, 'h_nmr': '1.2 (s, 1H)', 'c_nmr': []}


class PublicSDKTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.train = self.write('train', [example('CCO', 'C2H6O'), example('CCC', 'C3H8')])
        self.val = self.write('val', [example('COC', 'C2H6O'), example('CC', 'C2H6')])

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, role, rows):
        path = self.root / f'{role}.jsonl'
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        return SpectraSplit(path, role, 'test-fixture', 'experimental')

    def test_reader_is_lazy_and_preserves_split_and_source(self):
        with self.train.path.open('a') as stream:
            stream.write('{broken json\n')
        rows = self.train.head(1)
        self.assertEqual(rows[0]['_openmolspec']['split'], 'train')
        self.assertEqual(rows[0]['h_nmr'][0]['chemical_shift'], '1.2 (s, 1H)')
        with self.assertRaisesRegex(ValueError, 'invalid JSON'):
            list(self.train)

    def test_filter_does_not_convert_heldout_role_to_training(self):
        view = SpectraSplit(self.val.path, 'test', 'heldout', 'experimental')
        filtered = view.select(modalities=['1H'], limit=1)
        self.assertEqual(filtered.role, 'test')
        with self.assertRaisesRegex(ValueError, 'test views'):
            prepare_nmr_training(filtered, self.val, self.root / 'bad')
        self.assertFalse((self.root / 'bad').exists())

    def test_stereoisomers_are_together_in_connectivity_audit(self):
        train = self.write('train', [example('C[C@H](O)F', 'C2H5FO')])
        val = self.write('val', [example('C[C@@H](O)F', 'C2H5FO')])
        report = audit_splits({'train': train, 'val': val})
        self.assertFalse(report['disjoint'])
        self.assertEqual(report['overlaps'][0]['molecules'], 1)

    def test_training_preparation_and_preflight_never_launch_a_process(self):
        with patch('openmolspec.training.subprocess.run') as run:
            path = prepare_nmr_training(self.train, self.val, self.root / 'prepared')
            plan = TrainingPlan(path, self.root / 'runs', batch_size=2, epochs=1)
            self.assertFalse(plan.describe()['training_performed'])
            self.assertTrue(plan.validate()['validated'])
            run.assert_not_called()
        self.assertFalse((path / 'test.jsonl').exists())
        self.assertFalse((self.root / 'runs').exists())
        with (path / 'train.jsonl').open('a') as stream:
            stream.write('\n')
        with self.assertRaisesRegex(ValueError, 'changed since verification'):
            plan.validate()

    def test_leaking_preparation_is_rejected_without_publishing_files(self):
        val = self.write('val', [example('OCC', 'C2H6O'), example('COC', 'C2H6O')])
        with self.assertRaisesRegex(ValueError, 'overlap'):
            prepare_nmr_training(self.train, val, self.root / 'prepared')
        self.assertFalse((self.root / 'prepared').exists())

    def test_spectrum_for_absent_nucleus_is_rejected(self):
        train = self.write('train', [example('BrOBr', 'Br2O'), example('CCC', 'C3H8')])
        with self.assertRaisesRegex(ValueError, 'nucleus is absent'):
            prepare_nmr_training(train, self.val, self.root / 'prepared')

    def test_config_roundtrip_and_unsupported_nucleus(self):
        model = NMRNet(models_root=self.root, nucleus='1H')
        model.save_config(self.root / 'model.json')
        restored = NMRNet.from_config(self.root / 'model.json')
        self.assertEqual(model.config, restored.config)
        with self.assertRaises(ValueError):
            NMRNet(models_root=self.root, nucleus='29Si')

    def test_model_query_has_no_implicit_formula(self):
        model = NMRTransformer(checkpoint=self.root / 'unused.pt')
        with patch('openmolspec.model.invoke') as run:
            with self.assertRaisesRegex(ValueError, 'formula'):
                model.predict({'h_nmr': '1.2'})
            run.assert_not_called()

    def test_registry_and_version_check_distinguish_sources(self):
        self.assertEqual(dataset_info('opendatalab_nmr')['domain'], 'experimental')
        self.assertEqual(dataset_info('openspec_test')['domain'], 'computed')
        ds = MolecularSpectra({'version': 'test', 'reference_sha256': {'train': sha256(self.train.path)}}, {'train': self.train})
        self.assertTrue(ds.verify()['verified'])
        self.train.path.write_text('{}\n')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            ds.verify()


if __name__ == '__main__':
    unittest.main()
