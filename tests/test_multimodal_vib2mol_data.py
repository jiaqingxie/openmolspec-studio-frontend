import json
import pickle
import tempfile
import unittest
from pathlib import Path

import lmdb
import numpy as np
import pandas as pd
from benchmarks.data.prepare_multimodal_vib2mol import run
from benchmarks.models.vib2mol.workflow import inspect_data, training_command, task_name


class MultimodalVib2MolDataTests(unittest.TestCase):
    def test_join_and_reject_bad_pairing(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';props=root/'props'
            (source/'vib2mol').mkdir(parents=True);(props/'vib2conf').mkdir(parents=True)
            index=pd.DataFrame(dict(sample_id=list('abcdef'),split=['train']*2+['eval']*2+['test']*2,
                                    inchikey=list('ABCDEF'),source_dataset=['fixture']*6))
            for path in (source,props):index.to_parquet(path/'benchmark_split.parquet',index=False)
            (props/'summary.json').write_text(json.dumps({'state':'completed'}))
            (props/'nmr_reference.json').write_text(json.dumps({'id':'tms-test'}))
            original={}
            for mode in ('train','eval','test'):
                with lmdb.open(str(source/'vib2mol'/f'openspec_{mode}.lmdb'),subdir=False,map_size=1<<20) as a, \
                     lmdb.open(str(props/'vib2conf'/f'{mode}.lmdb'),subdir=False,map_size=1<<20) as b:
                    with a.begin(write=True) as at,b.begin(write=True) as bt:
                        for row in index[index.split==mode].itertuples():
                            spectrum=np.linspace(0,1,1024,dtype=np.float32)
                            r=dict(ir=spectrum,raman=spectrum,kekule_smiles='CO')
                            n=dict(ir=spectrum,raman=spectrum,sample_id=row.sample_id,inchikey=row.inchikey,
                                   source_dataset='fixture',spectrum_normalization={'method':'minmax'},
                                   nmr_sample_id=row.sample_id,nmr_reference_id='tms-test',nmr_shift_unit='ppm',
                                   nmr_h_shifts_ppm=np.array([1.,2.],dtype=np.float32),nmr_h_present=True,
                                   nmr_c_shifts_ppm=np.array([],dtype=np.float32),nmr_c_present=False)
                            original[row.sample_id]=pickle.dumps(r)
                            at.put(row.sample_id.encode(),original[row.sample_id]);bt.put(row.sample_id.encode(),pickle.dumps(n))
            report=run(source,props,root/'output')
            self.assertEqual(report['counts'],{'train':2,'eval':2,'test':2})
            self.assertEqual(inspect_data(root/'output',require_nmr=True)['splits']['train']['records'],2)
            with self.assertRaises(FileExistsError):run(source,props,root/'output')
            with lmdb.open(str(source/'vib2mol/openspec_train.lmdb'),subdir=False,readonly=True,lock=False) as a:
                with a.begin() as tx:self.assertEqual(tx.get(b'a'),original['a'])
            with lmdb.open(str(props/'vib2conf/train.lmdb'),subdir=False) as b:
                with b.begin(write=True) as tx:
                    r=pickle.loads(tx.get(b'a'));r['nmr_sample_id']='wrong';tx.put(b'a',pickle.dumps(r))
            with self.assertRaisesRegex(ValueError,'pairing mismatch'):run(source,props,root/'bad')
            self.assertEqual(json.loads((root/'bad/summary.json').read_text())['state'],'failed')

    def test_hc_command_and_upstream_task(self):
        command=training_command('matching',modality='ir-raman-nmr',epochs=1,batch_size=16,
                                 learning_rate=1e-4,device='cpu')
        self.assertIn('--hc-nmr',command)
        self.assertEqual(task_name('ir-raman-nmr'),'ir-raman-kekule_smiles')
        h_command=training_command('matching',modality='ir-raman-hnmr',epochs=1,
                                   batch_size=16,learning_rate=1e-4,device='cpu')
        self.assertNotIn('--hc-nmr',h_command)
        self.assertIn('ir-raman-hnmr',h_command)
        self.assertEqual(task_name('ir-raman-hnmr'),'ir-raman-kekule_smiles')


if __name__=='__main__':unittest.main()
