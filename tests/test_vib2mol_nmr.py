import copy
import tempfile
import sys
import unittest
from pathlib import Path

import torch
import torch.distributed as dist
import torch.multiprocessing as mp

from benchmarks.models.vib2mol.nmr_embedding import MultimodalEmbedding
from benchmarks.models.vib2mol.nmr_data import add_nmr_batch
from benchmarks.models.vib2mol.matching import gather_tokens

STATS = {'c': {'median':100.,'scale':80.},'h': {'median':4.,'scale':3.}}


def make_batch(n=2, peaks=3):
    batch = {'ir':torch.rand(n,1,1024),'raman':torch.rand(n,1,1024),
             'smiles':{'input_ids':torch.tensor([[0,5,6,2]]*n),'attention_mask':torch.ones(n,4)}}
    rows = [{f'nmr_{x}_shifts_ppm': torch.arange(peaks if i else 0).float() for x in ('c','h')} for i in range(n)]
    return add_nmr_batch(batch,rows)


def new_model(nuclei=('c', 'h')):
    upstream=Path(__file__).resolve().parents[1]/'benchmarks/models/vib2mol/upstream'
    sys.path.insert(0,str(upstream))
    from benchmarks.models.vib2mol.train_entry import install_adapters
    install_adapters()
    from benchmarks.models.vib2mol.multimodal import MultimodalVib2Mol
    from benchmarks.models.vib2mol.contrastive import contrastive_loss
    MultimodalVib2Mol.compute_cl_loss=contrastive_loss
    return MultimodalVib2Mol(nmr_statistics=STATS,nuclei=nuclei,
                            d_model=32,d_proj=16,nhead=4,d_ff=64,
                            encoder_nlayer=2,decoder_nlayer=2,multimodal_nlayer=1)


def distributed_check(rank, uri):
    torch.set_num_threads(1)
    dist.init_process_group('gloo',init_method=uri,rank=rank,world_size=2)
    try:
        n=rank+2
        m=torch.randn(n,rank+2,4,requires_grad=True)
        s=torch.randn(n,rank+3,4,requires_grad=True)
        values=gather_tokens(m,torch.ones(n,rank+2,dtype=torch.bool),s,True,
                             torch.ones(n,rank+3,dtype=torch.bool))
        gm,mm,gs,counts,offset,sm=values
        assert gs.shape==(5,4,4) and not sm[:2,-1].any()
        remote=slice(2,5) if rank==0 else slice(0,2)
        (gm[remote].sum()+gs[remote].sum()).backward()
        torch.testing.assert_close(s.grad,torch.ones_like(s))
        for nuclei in (('c', 'h'), ('h',)):
            model=new_model(nuclei=nuclei)
            ddp=torch.nn.parallel.DistributedDataParallel(
                model,find_unused_parameters=True)
            batch=make_batch(n,rank*3+1)
            if nuclei == ('h',):
                batch.pop('nmr_c_shifts_ppm')
                batch.pop('nmr_c_mask')
            for phase in (1,2):
                model.phase=phase
                ddp.zero_grad()
                loss=ddp(batch)['loss']
                assert torch.isfinite(loss)
                loss.backward()
                assert model.spectral_encoding.nmr['h'][0].weight.grad is not None
                assert all(torch.isfinite(p.grad).all() for p in model.parameters()
                           if p.grad is not None)
    finally:
        dist.destroy_process_group()


class Vib2MolNMRTests(unittest.TestCase):
    def test_plain_vib2mol_uses_equivalent_cache(self):
        torch.manual_seed(9)
        torch.set_num_threads(1)
        new_model()  # Installs maintained adapters and the upstream import path.
        from models.vib2mol import Vib2Mol
        model = Vib2Mol(d_model=32, d_proj=16, nhead=4, d_ff=64, spectral_channel=2,
                        encoder_nlayer=2, decoder_nlayer=2,
                        multimodal_nlayer=1).eval()
        batch = {'ir': torch.rand(2,1,1024), 'raman': torch.rand(2,1,1024)}
        with torch.no_grad():
            cached = model.infer_lm(batch, max_len=7)
            legacy = model._infer_lm_uncached(batch, max_len=7)
            cached_beam = model.beam_infer_lm(batch, max_len=7, beam_size=2)
        torch.testing.assert_close(cached['pred_ids'], legacy['pred_ids'])
        self.assertEqual([len(row) for row in cached_beam['pred_ids']], [2, 2])
        self.assertTrue(all(len(x) <= 7 for row in cached_beam['pred_ids'] for x in row))

    def test_cached_decoder_matches_full_prefix_and_beam(self):
        from benchmarks.models.vib2mol.kv_cache import decoder_step, embed_token
        torch.manual_seed(8)
        torch.set_num_threads(1)
        model = new_model().eval()
        from models.modules import subsequent_mask
        batch = make_batch()
        memory, src_mask = model._generation_memory(batch)
        prefix = torch.tensor([[0,17,5,17,2], [0,28,6,29,2]])
        cache = None
        with torch.no_grad():
            for position in range(prefix.shape[1]):
                cached, cache = decoder_step(
                    model.molecular_decoder,
                    embed_token(model, prefix[:, position:position+1], position),
                    memory, src_mask, cache)
                embeddings = model.molecular_encoding(prefix[:, :position+1])
                full = model.molecular_decoder(
                    embeddings, memory, src_mask,
                    subsequent_mask(position+1).type_as(prefix))['proj_output'][:, -1:]
                torch.testing.assert_close(cached, full, atol=2e-6, rtol=2e-5)
            greedy = model.infer_lm(batch, max_len=8)
            legacy = model._infer_lm_uncached(batch, max_len=8)
            torch.testing.assert_close(greedy['pred_ids'], legacy['pred_ids'])
            beam = model.beam_infer_lm(batch, max_len=8, beam_size=3)
            legacy_beam = model._beam_infer_lm_uncached(batch, max_len=8, beam_size=3)
        for cached_row, legacy_row in zip(beam['pred_ids'], legacy_beam['pred_ids']):
            self.assertEqual([x.tolist() for x in cached_row],
                             [x.tolist() for x in legacy_row])
        torch.testing.assert_close(torch.tensor(beam['score']),
                                   torch.tensor(legacy_beam['score']),
                                   atol=2e-5, rtol=2e-5)

    def test_cache_projects_cross_attention_once(self):
        torch.set_num_threads(1)
        model = new_model().eval()
        counts = {'self': 0, 'src': 0}
        hooks = []
        for layer in model.molecular_decoder.layers:
            hooks.append(layer.self_attn.linears[1].register_forward_hook(
                lambda *args: counts.__setitem__('self', counts['self'] + 1)))
            hooks.append(layer.src_attn.linears[1].register_forward_hook(
                lambda *args: counts.__setitem__('src', counts['src'] + 1)))
        with torch.no_grad():
            model.infer_lm(make_batch(), max_len=7)
        for hook in hooks:
            hook.remove()
        layers = len(model.molecular_decoder.layers)
        self.assertEqual(counts['self'], layers * 6)
        self.assertEqual(counts['src'], layers)

    def test_rerank_matches_direct_matching(self):
        from transformers import AutoTokenizer
        from benchmarks.models.vib2mol.audit_tokenizer import TOKENIZER
        from benchmarks.models.vib2mol.evaluate_multimodal import rerank_candidates, spectrum_row
        torch.set_num_threads(1)
        model = new_model().eval()
        tokenizer = AutoTokenizer.from_pretrained(TOKENIZER, local_files_only=True)
        row = spectrum_row(make_batch(), 1)
        candidates = ['C', 'CC', 'CO']
        batch = {k: v.expand(len(candidates), *v.shape[1:]) for k, v in row.items()}
        batch['smiles'] = tokenizer(candidates, padding=True, return_tensors='pt')
        with torch.no_grad():
            expected = model.matching(batch).softmax(-1)[:, 1]
            order, scores = rerank_candidates(model, tokenizer, row, candidates, batch_size=2)
        torch.testing.assert_close(torch.tensor(scores), expected[order])
        self.assertEqual(order, sorted(range(3), key=lambda i: -float(expected[i])))

    def test_embedding_and_no_sequence_position(self):
        torch.manual_seed(624)
        module=MultimodalEmbedding(32,STATS).eval()
        b=make_batch()
        t,mask=module(b)
        self.assertEqual(t.shape,(2,137,32))
        self.assertEqual(mask[0].sum(),131)
        self.assertTrue(torch.isfinite(t).all())
        with self.assertRaises(ValueError):
            MultimodalEmbedding(32,{'c':{'median':0.,'scale':0.},'h':STATS['h']})

    def test_h_only_embedding_excludes_carbon_tokens(self):
        torch.manual_seed(624)
        module = MultimodalEmbedding(32, STATS, nuclei=('h',)).eval()
        batch = make_batch()
        batch.pop('nmr_c_shifts_ppm')
        batch.pop('nmr_c_mask')
        tokens, mask = module(batch)
        self.assertEqual(tokens.shape, (2, 133, 32))
        self.assertEqual(mask[0].sum(), 130)
        self.assertEqual(tuple(module.nmr), ('h',))
        self.assertNotIn('c', module.nmr)

        rows = [{'nmr_h_shifts_ppm': torch.tensor([1.0, 2.0])}]
        collated = add_nmr_batch({}, rows, nuclei=('h',))
        self.assertIn('nmr_h_mask', collated)
        self.assertNotIn('nmr_c_mask', collated)

        model = new_model(nuclei=('h',))
        batch['smiles'] = {
            'input_ids': torch.tensor([[0, 5, 6, 2]] * 2),
            'attention_mask': torch.ones(2, 4),
        }
        for phase in (1, 2):
            model.phase = phase
            model.zero_grad()
            loss = model(batch)['loss']
            self.assertTrue(torch.isfinite(loss))
            loss.backward()
            self.assertIsNotNone(
                model.spectral_encoding.nmr['h'][0].weight.grad)
        self.assertEqual(model.get_extra_state()['architecture'],
                         'vib2mol-h-v1')
        with self.assertRaises(ValueError):
            new_model().load_state_dict(model.state_dict())

    def test_matching_generation_masks_and_checkpoint(self):
        torch.set_num_threads(1)
        model=new_model().eval();b=make_batch()
        with torch.no_grad():
            expected=model.encode_spectra(b)['proj_output']
            padded=copy.deepcopy(b)
            for x in ('c','h'):
                key=f'nmr_{x}_shifts_ppm';mk=f'nmr_{x}_mask'
                padded[key]=torch.cat((padded[key].flip(1),torch.full((2,4),float('nan'))),1)
                padded[mk]=torch.cat((padded[mk].flip(1),torch.zeros(2,4,dtype=torch.bool)),1)
            torch.testing.assert_close(model.encode_spectra(padded)['proj_output'],expected)
            torch.testing.assert_close(model.matching(padded),model.matching(b))
            torch.testing.assert_close(model.infer_mlm(padded),model.infer_mlm(b))
            torch.testing.assert_close(model.infer_lm(padded,max_len=4)['pred_ids'],model.infer_lm(b,max_len=4)['pred_ids'])
            beam=model.beam_infer_lm(padded,max_len=4,beam_size=2)
            self.assertEqual(len(beam['pred_ids']),2)
            self.assertTrue(all(len(x)<=4 for row in beam['pred_ids'] for x in row))
        for phase in (1,2):
            model.phase=phase; model.train();model.zero_grad()
            loss=model(b)['loss'];self.assertTrue(torch.isfinite(loss));loss.backward()
            for x in ('c','h'):
                self.assertGreater(model.spectral_encoding.nmr[x][0].weight.grad.abs().sum(),0)
        other=new_model();other.load_state_dict(model.state_dict())
        with self.assertRaises(RuntimeError):
            other.load_state_dict({},strict=False)

    def test_two_rank_variable_nmr_and_gradients(self):
        with tempfile.TemporaryDirectory() as directory:
            mp.spawn(distributed_check,args=((Path(directory)/'rendezvous').as_uri(),),nprocs=2,join=True)


if __name__=='__main__':
    unittest.main()
