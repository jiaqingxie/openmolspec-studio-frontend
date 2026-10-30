import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pickle

import h5py
import lmdb
import numpy as np
import pandas as pd

from benchmarks.data.nmr_reference import hc_shift_record, load_tms_reference
from benchmarks.data.prepare_multimodal_properties import run
from benchmarks.data.scalar_properties import ACTIVE_PROPERTY_TARGETS, PROPERTY_UNITS


REF = {"id": "test-tms", "sigma_ref_ppm": {"H": 31.706375, "C": 191.483675}}


class MultimodalPropertiesTests(unittest.TestCase):
    def test_reference_validation(self):
        text = ('Optimization completed.\n'
                '#p B3LYP/6-311+G** em=gd3bj int=ultrafine\n'
                '#p OPBE/6-311+G(2D,P) IOP(3/76=0770002300,3/77=1000010000,3/78=1000010000)\n'
                'Frequencies -- ' + ' '.join(['100.0'] * 45) + '\n')
        text += ''.join(f'{i+1} {e} Isotropic = {v}\n' for i,(e,v) in
                        enumerate([('H',31.)]*12+[('C',191.)]*4+[('Si',365.)]))
        text += 'Normal termination of Gaussian 16\n'
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'tms.log'
            p.write_text(text)
            r=load_tms_reference(p)
            self.assertEqual(r['sigma_ref_ppm'],{'H':31.,'C':191.})
            for bad in (text.replace('100.0','-100.0',1), text+'new unfinished job\n',
                        text.replace('OPBE/','B3LYP/'), text.replace('1 H Isotropic','1 O Isotropic')):
                p.write_text(bad)
                with self.assertRaises(ValueError):
                    load_tms_reference(p)

    def test_active_configs(self):
        import yaml
        root=Path(__file__).resolve().parents[1]
        for size in (200,1000):
            for target in ACTIVE_PROPERTY_TARGETS:
                p=root/f'benchmarks/configs/spectrum2property/{target}_ks{size}k.yaml'
                config=yaml.safe_load(p.read_text())
                self.assertEqual(config['task']['modality'],'ir-raman-nmr')
                self.assertEqual(config['task']['targets'],[target])
                self.assertEqual(config['training']['max_steps'],312500)
                self.assertEqual(config['training']['eval_every_steps'],2500)
                self.assertTrue(config['data']['root'].endswith('_hc_nmr_minmax'))

    def test_shifts_and_permutation(self):
        z = np.array([1, 6, 1, 8])
        s = np.array([30., 200., 32., 150.])
        result = hc_shift_record(z, s, REF)
        np.testing.assert_allclose(result['nmr_h_shifts_ppm'], [-.293625, 1.706375])
        np.testing.assert_allclose(result['nmr_c_shifts_ppm'], [-8.516325])
        self.assertEqual(result['nmr_h_shifts_ppm'].dtype, np.float32)
        p = [3, 2, 1, 0]
        perm = hc_shift_record(z[p], s[p], REF)
        np.testing.assert_array_equal(result['nmr_h_shifts_ppm'], perm['nmr_h_shifts_ppm'])
        self.assertNotIn('atomic_numbers', result)
        self.assertFalse(hc_shift_record([6], [180], REF)['nmr_h_present'])
        for a, b in [([1], [np.nan]), ([1, 6], [1]), ([1.5], [1])]:
            with self.assertRaises(ValueError):
                hc_shift_record(a, b, REF)

    def test_build_preserves_splits_and_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, payload = root/'source', root/'nmr'
            (source/'vib2conf').mkdir(parents=True)
            payload.mkdir()
            index = pd.DataFrame({'sample_id': ['a', 'b', 'v', 't'],
                'split': ['train', 'train', 'eval', 'test'], 'inchikey': ['A', 'B', 'V', 'T'],
                'source_dataset': ['fixture'] * 4})
            index.to_parquet(source/'benchmark_split.parquet')
            original = {}
            for mode in ('train', 'eval', 'test'):
                with lmdb.open(str(source/'vib2conf'/f'{mode}.lmdb'), subdir=False, map_size=1<<20) as env:
                    with env.begin(write=True) as txn:
                        for row in index[index.split==mode].itertuples():
                            record = dict(ir=np.linspace(0,1,1024,dtype=np.float32),
                                raman=np.linspace(0,1,1024,dtype=np.float32),
                                sample_id=row.sample_id, inchikey=row.inchikey, source_dataset='fixture',
                                spectrum_normalization={'method':'minmax'}, units=PROPERTY_UNITS,
                                **{field:2. for field in PROPERTY_UNITS})
                            original[row.sample_id] = record
                            txn.put(row.sample_id.encode(), pickle.dumps(record))
            frozen=index.rename(columns={'sample_id':'align_sample_id', 'source_dataset':'align_source'})
            frozen['split']=frozen.split.replace({'eval':'validation'})
            frozen.to_parquet(root/'full.parquet')
            frozen[frozen.align_sample_id!='b'].to_parquet(root/'small.parquet')
            pd.DataFrame({'sample_id':list('abvt'), 'shard':['shard-00000']*4,
                          'row_in_shard':range(4)}).to_parquet(payload/'index.parquet')
            with h5py.File(payload/'shard-00000.h5','w') as f:
                for name, values in [('atomic_numbers', [1,6]), ('nmr_isotropic',[30.,180.])]:
                    group=f.create_group('arrays/'+name)
                    group['values']=np.tile(values,4)
                    group['offsets']=np.arange(0,9,2)
                    group['shapes']=np.full((4,1),2)
                    group['present']=np.ones(4,dtype=bool)
            outputs={'small':root/'small', 'full':root/'full'}
            with patch('benchmarks.data.prepare_multimodal_properties.load_tms_reference', return_value=REF):
                summary=run(source,payload,{'small':root/'small.parquet','full':root/'full.parquet'},
                            outputs,root/'unused.log')
                self.assertEqual(summary['small']['counts'],{'train':1,'eval':1,'test':1})
                self.assertEqual(summary['full']['counts'],{'train':2,'eval':1,'test':1})
                with self.assertRaises(FileExistsError):
                    run(source,payload,{'small':root/'small.parquet','full':root/'full.parquet'},outputs,root/'unused.log')
            for name in outputs:
                for mode in ('train','eval','test'):
                    with lmdb.open(str(outputs[name]/'vib2conf'/f'{mode}.lmdb'),readonly=True,subdir=False,lock=False) as env:
                        with env.begin() as txn:
                            for key,value in txn.cursor():
                                r=pickle.loads(value); old=original[key.decode()]
                                for field in ('ir','raman'):
                                    np.testing.assert_array_equal(r[field],old[field])
                                for field in PROPERTY_UNITS:
                                    self.assertEqual(r[field],old[field])
                                self.assertEqual(r['nmr_sample_id'],key.decode())
                                np.testing.assert_allclose(r['nmr_c_shifts_ppm'],[11.483675])


if __name__ == '__main__':
    unittest.main()
