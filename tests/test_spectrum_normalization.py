import hashlib
import pickle
import tempfile
import unittest
from pathlib import Path

import lmdb
import numpy as np

from benchmarks.data.normalize_spectra import minmax, run, normalize_batch, normalize_record, export_split


class SpectrumNormalizationTests(unittest.TestCase):
    def test_batch_matches_scalar_and_crosses_transaction_boundaries(self):
        rng = np.random.default_rng(624)
        items = []
        for i in range(19):
            row = dict(ir=rng.normal(size=1024), raman=rng.random(1024)*1e6,
                       smiles='CC', dipole_total=2.1)
            if i == 0:
                row['ir'][:] = 5
            items.append((f'{i:04d}'.encode(), pickle.dumps(row)))
        converted, constants = normalize_batch(items)
        self.assertEqual(constants['ir'], 1)
        for (_, original), (_, output) in zip(items, converted):
            reference = normalize_record(pickle.loads(original))
            actual = pickle.loads(output)
            for field in ('ir', 'raman'):
                np.testing.assert_array_equal(actual[field], reference[field])
            self.assertEqual(actual['spectrum_normalization'], reference['spectrum_normalization'])
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory)/'source.lmdb', Path(directory)/'target.lmdb'
            env = lmdb.open(str(source), subdir=False, map_size=4 << 20)
            with env.begin(write=True) as txn:
                for key, value in items:
                    txn.put(key, value)
            env.close()
            report = export_split(source, target, batch_size=4, commit_interval=7)
            self.assertEqual(report['records'], 19)
            digest = hashlib.sha256()
            for key, value in items:
                digest.update(len(key).to_bytes(8, 'big')); digest.update(key)
                digest.update(len(value).to_bytes(8, 'big')); digest.update(value)
            self.assertEqual(report['source_records_sha256'], digest.hexdigest())
            env = lmdb.open(str(target), subdir=False, readonly=True, lock=False)
            with env.begin() as txn:
                for key, expected in converted:
                    actual = pickle.loads(txn.get(key))
                    np.testing.assert_array_equal(actual['ir'], pickle.loads(expected)['ir'])
            env.close()

    def test_minmax_formula_preserves_peak_ratios(self):
        a = np.linspace(0, 100, 1024)
        a[-1] = 1e8
        a32 = a.astype(np.float32)
        lo, hi = a32.min(), a32.max()
        actual, bounds = minmax(a)
        np.testing.assert_array_equal(actual, np.clip((a32-lo)/(hi-lo), 0, 1))
        np.testing.assert_allclose(actual, minmax(a*1000+7)[0], rtol=3e-7, atol=1e-7)
        self.assertEqual(int((actual == 1).sum()), 1)
        self.assertEqual(actual.dtype, np.float32)
        self.assertEqual(bounds['high'], hi)

    def test_invalid_and_constant(self):
        self.assertTrue(minmax(np.ones(1024))[1]['degenerate'])
        self.assertFalse(minmax(np.ones(1024))[0].any())
        for a in (np.zeros(5), np.full(1024, np.nan), np.full(1024, np.inf)):
            with self.assertRaises(ValueError):
                minmax(a)

    def test_exports_preserve_sources_keys_labels_and_splits(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            for fmt in ('vib2mol', 'vib2conf'):
                source, target = root/f'{fmt}_raw', root/f'{fmt}_normalized'
                (source/fmt).mkdir(parents=True)
                snapshots = {}
                for split in ('train', 'eval', 'test'):
                    filename = f'openspec_{split}.lmdb' if fmt == 'vib2mol' else f'{split}.lmdb'
                    p = source/fmt/filename
                    env = lmdb.open(str(p), subdir=False, map_size=1 << 20)
                    with env.begin(write=True) as txn:
                        txn.put(b'\xff-id', pickle.dumps(dict(ir=np.arange(1024),
                            raman=np.arange(1024)*1000, dipole_total=3.2,
                            kekule_smiles='CC', units={'dipole_total': 'D'})))
                    env.close()
                    snapshots[filename] = hashlib.sha256(p.read_bytes()).hexdigest()
                report = run(source, target, fmt)
                self.assertEqual(report['state'], 'completed')
                for filename, before in snapshots.items():
                    self.assertEqual(hashlib.sha256((source/fmt/filename).read_bytes()).hexdigest(), before)
                    env = lmdb.open(str(target/fmt/filename), subdir=False, readonly=True, lock=False)
                    with env.begin() as txn:
                        self.assertEqual(txn.stat()['entries'], 1)
                        row = pickle.loads(txn.get(b'\xff-id'))
                        self.assertEqual(row['dipole_total'], 3.2)
                        self.assertEqual(row['kekule_smiles'], 'CC')
                        self.assertEqual(row['units'], {'dipole_total': 'D'})
                        np.testing.assert_allclose(row['ir'], row['raman'])
                        self.assertEqual(row['ir'].dtype, np.float32)
                        self.assertEqual(row['raman'].dtype, np.float32)
                        self.assertEqual(float(row['ir'].min()), 0)
                        self.assertEqual(float(row['ir'].max()), 1)
                    env.close()
                with self.assertRaises(FileExistsError):
                    run(source, target, fmt)
                with self.assertRaises(ValueError):
                    run(source, source, fmt)
                with self.assertRaises(ValueError):
                    run(target, root/f'{fmt}_twice', fmt)


if __name__ == '__main__':
    unittest.main()
