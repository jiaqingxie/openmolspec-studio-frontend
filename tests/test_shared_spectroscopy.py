import copy
import io
import json
import pickle
import tempfile
import unittest
from pathlib import Path

import lmdb
import numpy as np
import torch

from benchmarks.models.vib2conf.model import SpectralPropsModel
from benchmarks.models.vib2conf.dataset import LmdbPropsDataset, collate_properties
from benchmarks.engines.nmr_normalization import fit_or_load_nmr_normalizer
from benchmarks.engines.vib2conf import Vib2ConfPropertyEngine
from benchmarks.engines.normalization import TargetNormalizer
from benchmarks.trainers.vib2conf import Vib2ConfPropertyTrainer
from benchmarks.trainers.experiment import load_config, build_command
from benchmarks.models.vib2conf.props_head import build_parser


STATS = {'c': {'median': 100., 'scale': 80.}, 'h': {'median': 4., 'scale': 3.}}


def model():
    return SpectralPropsModel(property_targets=['gap'], d_model=32, nheads=4,
        nlayers=6, encoder_layers=2, pooling_layers=4, pooling_queries=8,
        fusion_channels=4, hidden_channels=16, dropout=0., nmr_statistics=STATS)


def batch():
    return collate_properties([
        dict(ir=torch.rand(1024),raman=torch.rand(1024),props={'gap':2.},
             nmr_c_shifts_ppm=torch.tensor([20., 100., 200.]), nmr_h_shifts_ppm=torch.tensor([1.,7.])),
        dict(ir=torch.rand(1024),raman=torch.rand(1024),props={'gap':3.},
             nmr_c_shifts_ppm=torch.tensor([]), nmr_h_shifts_ppm=torch.tensor([3.]))])


class SharedSpectroscopyTests(unittest.TestCase):
    def test_permutation_padding_missing_and_checkpoint(self):
        m=model().eval(); b=batch()
        with torch.no_grad():
            expected=m(b)['gap']
            perm=copy.deepcopy(b)
            for label in ('c','h'):
                for suffix in ('shifts_ppm','mask'):
                    key=f'nmr_{label}_{suffix}'
                    perm[key]=perm[key].flip(1)
            torch.testing.assert_close(m(perm)['gap'],expected,atol=1e-6,rtol=1e-5)
            padded=copy.deepcopy(b)
            for label in ('c','h'):
                key=f'nmr_{label}_shifts_ppm'; mask=f'nmr_{label}_mask'
                padded[key][~padded[mask]]=float('nan')
                padded[key]=torch.cat([padded[key],torch.full((2,5),float('nan'))],dim=1)
                padded[mask]=torch.cat([padded[mask],torch.zeros((2,5),dtype=torch.bool)],dim=1)
            torch.testing.assert_close(m(padded)['gap'],expected,atol=1e-6,rtol=1e-5)
            # Batch padding/composition cannot change a molecule's prediction.
            one={k:(v[:1] if torch.is_tensor(v) else v) for k,v in b.items()}
            torch.testing.assert_close(m(one)['gap'],expected[:1],atol=1e-6,rtol=1e-5)
            missing={k:v for k,v in b.items() if not k.startswith('nmr_')}
            self.assertTrue(torch.isfinite(m(missing)['gap']).all())
            tokens,mask=m.embed_tokens(missing)
            self.assertEqual(tokens.shape[1],128+2)
            self.assertEqual(m.encode_queries(missing).shape, (2,9,32))
            self.assertEqual(len(m.encoder.layers),2)
            self.assertEqual(len(m.pooling),4)
            self.assertFalse(mask.any())
            altered=copy.deepcopy(b);altered['nmr_c_shifts_ppm']+=25
            self.assertGreater(float((m(altered)['gap']-expected).abs().max()),1e-6)
            stream=io.BytesIO();torch.save(m.state_dict(),stream);stream.seek(0)
            other=model().eval();other.nmr_center.zero_()
            other.load_state_dict(torch.load(stream,weights_only=True))
            torch.testing.assert_close(other(b)['gap'],expected)

    def test_gradients_shared_encoder_and_physical_axis(self):
        m=model(); b=batch()
        b['ir'].requires_grad_();b['raman'].requires_grad_()
        engine=Vib2ConfPropertyEngine(model=m, train_loader=[],eval_loader=[],test_loader=[],
            normalizer=TargetNormalizer({'gap':2.},{'gap':1.}),optimizer=None,
            device='cpu',progress_mode='log',targets=['gap'])
        loss=engine.compute_loss(engine.move_batch(b));loss.backward()
        for module in (m.channel_fusion,m.patch_embedding,m.carbon_embedding,m.hydrogen_embedding,m.encoder,m.pooling):
            self.assertTrue(any(p.grad is not None and p.grad.abs().sum()>0 for p in module.parameters()))
        self.assertTrue(b['ir'].grad.abs().sum()>0 and b['raman'].grad.abs().sum()>0)
        self.assertTrue(m.no_c.grad.abs().sum()>0)
        self.assertTrue(m.pool_queries.grad.abs().sum()>0)
        self.assertEqual(sum(isinstance(x,torch.nn.TransformerEncoder) for x in m.modules()),1)
        self.assertTrue((torch.diff(m.wavenumber_centers_cm1)>0).all())
        self.assertTrue(m.wavenumber_centers_cm1.min()>400)
        self.assertTrue(m.wavenumber_centers_cm1.max()<4000)

    def test_data_normalization_cache_train_only_and_debug_training(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); path=root/'train.lmdb'
            def write(file, records):
                with lmdb.open(str(file),subdir=False,map_size=1<<20) as env:
                    with env.begin(write=True) as tx:
                        for i,r in enumerate(records): tx.put(str(i).encode(),pickle.dumps(r))
            records=[]
            for i in range(4):
                records.append(dict(ir=np.linspace(0,1,1024,dtype=np.float32),
                    raman=np.linspace(1,0,1024,dtype=np.float32),gap=float(i),units={'gap':'eV'},
                    nmr_h_shifts_ppm=np.array([i,2*i],dtype=np.float32),
                    nmr_c_shifts_ppm=np.array([50*i],dtype=np.float32) if i else np.array([],dtype=np.float32),
                    nmr_h_present=True,nmr_c_present=bool(i),nmr_shift_unit='ppm',nmr_reference_id='test-tms'))
            write(path,records)
            for mode in ('eval','test'): write(root/f'{mode}.lmdb',records[:2])
            uncached=fit_or_load_nmr_normalizer(path,cache_enabled=False,max_records=2)
            self.assertEqual(uncached['train_records'],2)
            self.assertFalse((root/'.cache').exists())
            result=fit_or_load_nmr_normalizer(path)
            for label in ('c','h'):
                values=np.concatenate([r[f'nmr_{label}_shifts_ppm'] for r in records])
                q=np.percentile(values,[25,50,75]);s=result['statistics'][label]
                self.assertEqual(s['median'],q[1]);self.assertEqual(s['scale'],q[2]-q[0])
            cache=root/'.cache/nmr_median_iqr.json';mtime=cache.stat().st_mtime_ns
            self.assertEqual(fit_or_load_nmr_normalizer(path),result)
            self.assertEqual(cache.stat().st_mtime_ns,mtime)
            with self.assertRaises(ValueError):fit_or_load_nmr_normalizer(root/'eval.lmdb')
            # Source mutation invalidates the full-train cache.
            changed=copy.deepcopy(records);changed[3]['nmr_h_shifts_ppm']+=100
            write(path,changed)
            self.assertNotEqual(fit_or_load_nmr_normalizer(path)['source'],result['source'])
            ds=LmdbPropsDataset(path,['gap'],include_nmr=True,reference_id='test-tms')
            mixed=collate_properties([ds[0],ds[1]])
            self.assertEqual(mixed['nmr_c_mask'].tolist(),[[False],[True]])
            del ds
            # End-to-end CPU debug: both normalizers, fit/val/test, backward, no checkpoint/cache writes.
            before={str(p):p.stat().st_mtime_ns for p in (root/'.cache').rglob('*') if p.is_file()}
            trainer=Vib2ConfPropertyTrainer(data_dir=str(root),output=str(root/'debug'),epochs=1,
                max_steps=2,eval_every_steps=1,batch_size=2,learning_rate=1e-4,weight_decay=1e-4,
                seed=624,device='cpu',workers=0,concat_spectrum=True,modality='ir-raman-nmr',
                targets=['gap'],debug=True,debug_train_samples=4,debug_eval_samples=2,debug_test_samples=2,
                model_parameters=dict(d_model=32,nheads=4,nlayers=2,encoder_layers=1,
                    pooling_layers=1,pooling_queries=8,hidden_channels=16,fusion_channels=4,dropout=0.))
            summary=trainer.run()
            self.assertEqual(summary['global_step'],2)
            self.assertTrue(np.isfinite(summary['best_test']['MAE_gap']))
            self.assertFalse(list((root/'debug').glob('*.pt')))
            self.assertEqual(before,{str(p):p.stat().st_mtime_ns for p in (root/'.cache').rglob('*') if p.is_file()})

    def test_yaml_to_cli(self):
        for size in (200,1000):
            c=load_config(f'benchmarks/configs/spectrum2property/dipole_total_ks{size}k.yaml')
            command=build_command(c,Path('unused'))
            args=build_parser().parse_args(command[3:])
            self.assertEqual(args.modality,'ir-raman-nmr')
            self.assertEqual(args.model_config['patch_size'],8)
            self.assertEqual(args.model_config['encoder_layers'],2)
            self.assertEqual(args.model_config['pooling_layers'],4)
            self.assertEqual(args.model_config['pooling_queries'],128)
            self.assertEqual(args.max_steps,312500)


if __name__=='__main__':
    torch.set_num_threads(1)
    unittest.main()
