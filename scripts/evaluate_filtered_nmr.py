"""Frozen NMR retrieval after excluding checkpoint-recorded train/val identities.

Uses the same H/C-complete molecules for all three input ablations. Exclusions
group standard-InChIKey connectivity blocks, including stereoisomers. This does
not audit unknown pretraining history or remove related molecular scaffolds.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspace',type=Path,default=ROOT.parent,help='Workspace containing data/align_eval, data/mix_align_v2 and runs/')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=512)
    args=parser.parse_args()
    if args.output.exists(): raise ValueError('Use a new output path')
    import numpy as np
    import torch
    from rdkit import Chem, RDLogger
    from openmolspec_bench.data import normalize_record, sha256
    from spec2struct_fork.model import SpectrumToSmiles, ModelConfig
    from spec2struct_fork.train import make_collate
    RDLogger.DisableLog('rdApp.*');torch.set_num_threads(2)
    args.work.mkdir(parents=True,exist_ok=True)
    audit=json.loads((ROOT/'results/nmr_checkpoint_overlap_20261117.json').read_text())
    checkpoint=args.workspace/'runs'/audit['models']['align']['run_id']/'best.pt'
    assert sha256(checkpoint)==audit['models']['align']['checkpoint_sha256']
    prepared=args.work/'selection.json'
    if not prepared.exists():
        pools={};metadata={};wanted=set()
        for name,source in audit['evaluation_views'].items():
            path=args.workspace/'data/align_eval'/name/'test.jsonl'
            assert sha256(path)==source['sha256']
            rows=[];counts=Counter();seen=set()
            for line in path.open():
                row=normalize_record(json.loads(line));counts['read']+=1
                if row['modality_mask'] != [1,1]: counts['missing_HC']+=1;continue
                mol=Chem.MolFromSmiles(row['smiles']);key=Chem.MolToInchiKey(mol)
                if not key: counts['invalid_identity']+=1;continue
                if not any(a.GetTotalNumHs()>0 or a.GetAtomicNum()==1 for a in mol.GetAtoms()) or not any(a.GetAtomicNum()==6 for a in mol.GetAtoms()):
                    counts['absent_nucleus']+=1;continue
                identity=key.split('-')[0]
                if identity in seen: counts['duplicate_connectivity']+=1;continue
                seen.add(identity);wanted.add(identity);rows.append({**row,'_identity':identity})
            pools[name]=rows;metadata[name]={'counts':dict(counts),'source_sha256':source['sha256']}
        excluded=set();training={}
        for split,info in audit['models']['align']['splits'].items():
            path=args.workspace/'data/mix_align_v2'/f'{split}.jsonl';digest=hashlib.sha256();count=0
            with path.open('rb') as stream:
                for line in stream:
                    digest.update(line);row=json.loads(line);count+=1
                    key=Chem.InchiToInchiKey(row['inchi'])
                    if not key: raise ValueError('Training identity missing')
                    identity=key.split('-')[0]
                    if identity in wanted: excluded.add(identity)
                    if count%500000==0:print('Training exclusion scan',split,count,flush=True)
            assert digest.hexdigest()==info['checkpoint_recorded_sha256'], 'Training source changed'
            training[split]={'sha256':digest.hexdigest(),'records':count}
        selected={}
        for name,rows in pools.items():
            eligible=[r for r in rows if r['_identity'] not in excluded]
            metadata[name]['excluded_train_val_connectivities']=len(rows)-len(eligible)
            metadata[name]['eligible_HC_connectivities']=len(eligible)
            random.Random(42).shuffle(eligible)
            selected[name]=eligible[:args.limit]
            assert len(selected[name])==args.limit,(name,len(selected[name]))
        prepared.write_text(json.dumps({'datasets':selected,'selection':metadata,'training':training}))
    selection=json.loads(prepared.read_text())
    payload=torch.load(checkpoint,map_location='cpu',weights_only=True)
    model=SpectrumToSmiles(ModelConfig(**payload['config']));model.load_state_dict(payload['model']);model.eval();del payload
    collate=make_collate(model.config,include_formula=False)
    report={'completed':False,'training_performed':False,'checkpoint_sha256':sha256(checkpoint),
        'sampling':'Seed 42 uniform shuffled eligible connectivity identities; same H+C records for all views',
        'exclusion':'Both fingerprint-matched alignment train and validation, grouped by standard-InChIKey connectivity',
        'known_limits':['Unknown pretraining history remains unaudited','Related scaffolds and source documents are not excluded','Small candidate-library evaluation, not a full-database search','Missing-channel ablations use the same frozen checkpoint'],
        'protocol':{'candidate_pool':args.limit,'seed':42,'bootstrap_replicates':2000,'formula_input':False},
        'training_files':selection['training'],'selection':selection['selection'],'datasets':{}}
    started=time.monotonic()
    for name,rows in selection['datasets'].items():
        result={'identities':[r['_identity'] for r in rows],'views':{}}
        for view,mask in [('hc',[1,1]),('h',[1,0]),('c',[0,1])]:
            cache=args.work/f'{name}-{view}.npz'
            if cache.exists():
                saved=np.load(cache);s,m=saved['spectral'],saved['molecular']
            else:
                spectral=[];molecular=[]
                with torch.inference_mode():
                    for start in range(0,len(rows),16):
                        batch=[{**r,'modality_mask':mask} for r in rows[start:start+16]]
                        source,target,_=collate(batch);a,b=model.alignment_embeddings(source,target)
                        spectral.append(a.numpy());molecular.append(b.numpy())
                        if start%128==0:print('Encoding',name,view,start,len(rows),flush=True)
                s,m=np.concatenate(spectral),np.concatenate(molecular)
                np.savez_compressed(cache,spectral=s,molecular=m)
            scores=s@m.T;directions={}
            for direction,matrix in [('s2m',scores),('m2s',scores.T)]:
                # Stable ordering makes the identity-index tie policy explicit.
                order=np.argsort(-matrix,axis=1,kind='stable');ranks=np.argmax(order==np.arange(len(rows))[:,None],axis=1)+1
                hits=ranks==1;rng=np.random.default_rng(42)
                bootstrap=hits[rng.integers(0,len(rows),size=(2000,len(rows)))].mean(axis=1)
                controls=[]
                for seed in (42,43,44):
                    wrong=np.random.default_rng(seed).permutation(len(rows))
                    controls.append(float((order[:,0]==wrong).mean()))
                directions[direction]={'recall_at_1':float(hits.mean()),'recall_at_5':float((ranks<=5).mean()),'recall_at_10':float((ranks<=10).mean()),'mrr':float((1/ranks).mean()),
                    'recall_at_1_bootstrap_95ci':np.quantile(bootstrap,[.025,.975]).tolist(),'shuffled_pairing_recall_at_1':controls,'ranks':ranks.tolist()}
            result['views'][view]=directions
            print('Evaluated',name,view,directions['s2m']['recall_at_1'],flush=True)
        report['datasets'][name]=result
        (args.work/'progress.json').write_text(json.dumps(report,indent=2))
    report['completed']=True;report['elapsed_seconds']=time.monotonic()-started
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('Filtered NMR evaluation complete',flush=True)


if __name__=='__main__':main()
