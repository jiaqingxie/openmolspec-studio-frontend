"""Build figures and portable examples exclusively from recorded frozen inference.

The same rendering functions run inside the documentation notebooks. No model is
trained or fitted here. Figure panels retain poor predictions and sample scope.
"""
from collections import defaultdict
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from openmolspec_bench.catalog import TASKS

ASSETS = ROOT / 'documentation/assets'


def read(name):
    return json.loads((ROOT/'results'/name).read_text())


def load_evidence(task_id):
    return json.loads((ASSETS/'examples'/f'{task_id.replace(".","-")}.json').read_text())


def compact(value, limit=8):
    """Readable previews explicitly label truncated arrays; downloads keep all data."""
    if isinstance(value,dict):return {k:compact(v,limit) for k,v in value.items()}
    if isinstance(value,list):
        return [compact(v,limit) for v in value] if len(value)<=limit else {'length':len(value),'first_values':[compact(v,limit) for v in value[:limit]]}
    return value


def hsqc_evidence():
    name = 'transpeaknet_hsqc_479.json'
    report = read(name)
    row, = report['results']
    if row['status'] != 'passed' or row['spectra'] != 479:
        raise ValueError('Expected a completed evaluation on the full HSQC ZIP')
    notebook = row['notebook_protocol']
    return {'task': row['task'], 'enabled': True, 'status': 'recorded_results',
            'training_performed': False, 'source_files': [name],
            'source_hashes': {name: hashlib.sha256((ROOT/'results'/name).read_bytes()).hexdigest()},
            'runs': [{'dataset': '479 expert spectra', 'status': 'passed', 'metrics': row['metrics']},
                     {'dataset': 'Author notebook (511 solvent rows)', 'status': 'passed', 'metrics': notebook['metrics']}],
            'examples': [row['example']], 'plot': {'kind': 'hsqc', 'label': row['example']['sample_id']},
            'selection_policy': 'Butanenitrile, the existing website example (32869.csv).'}


def collect():
    bundles={t.id:{'task':t.id,'enabled':t.enabled,'source_files':[],'runs':[],'examples':[],
                  'selection_policy':'First recorded example in the cited run; not selected by prediction quality.',
                  'training_performed':False} for t in TASKS}
    def attach(task,name,row):
        b=bundles[task]
        if name not in b['source_files']:b['source_files'].append(name)
        b['runs'].append({'dataset':row.get('dataset_name', 'recorded evaluation'),
                          'status':row.get('status','diagnostic_only' if task.endswith(('11B','29Si','19F','31P')) else 'completed'),
                          'metrics':row.get('metrics',{}),
                          **{k:row[k] for k in ('models','counts','reranked_metrics','training_mean_baseline','given_formula','given_nmr','sampling','seed','beam_size') if k in row}})
        return b
    name='nmr_documented_examples_20261117_v2.json'
    payload=read(name)
    assert payload.get('completed_at') and not payload.get('counts',{}).get('failed'), 'NMR example inference incomplete'
    for r in payload['results']:
        b=attach(r['task'],name,r)
        if b['examples']:continue
        if '.generation.' in r['task']:
            b['examples']=r['predictions'][:3]
            b['plot']={'kind':'molecules','reference':r['predictions'][0]['reference_smiles'],
                       'predicted':r['predictions'][0]['candidates'][0]['canonical_smiles'],
                       'label':'Formula-conditioned NMR generation; first record'}
        elif '.retrieval.' in r['task']:
            for ex in r['examples']:
                q=ex['query'];m2s=ex['direction']=='m2s'
                b['examples'].append({'input':{'smiles':q['smiles']} if m2s else {k:q[k] for k in ('h_nmr','c_nmr','modality_mask')},
                                      'reference_smiles':q['smiles'],'output':ex['ranked_candidates']})
            b['plot']={'kind':'ranking','candidates':b['examples'][0]['output'],'label':'Dual encoder scores; first query; 32 candidates'}
        else:
            model=r['models'][0];ex=model['examples'][0]
            b['examples']=[{'input':{'smiles':item['smiles']},'output':{'prediction_ppm':item['prediction_ppm'],'model':model['model']},
                            'reference':{'peaks_ppm':item['reference_ppm']}} for item in model['examples'][:3]]
            b['plot']={'kind':'nmr_peaks',**ex,'label':model['model']+'; first recorded molecule'}
    name='bsi_frozen_diagnostic_20261116.json'
    for symbol,r in read(name)['nuclei'].items():
        task='nmr.forward.'+{'B':'11B','Si':'29Si'}[symbol]
        b=attach(task,name,{'metrics':{k:r[k] for k in ('mae_ppm','rmse_ppm','molecules','atoms')}})
        b['examples']=[{'input':{'smiles':x['smiles'],'atom_indices':x['atom_indices']},'output':{'prediction_ppm':x['prediction_ppm']},
                        'reference':{'ppm':x['reference_ppm']}} for x in r['records'][:3]]
        b['plot']={'kind':'parity','x':[x['reference_ppm'][0] for x in r['records']], 'y':[x['prediction_ppm'][0] for x in r['records']],
                   'unit':'ppm','label':f'{symbol}: 32 molecules / 32 atoms; diagnostic only'}
    name='fp_frozen_fresh_diagnostic_20261115.json'
    # Invalid old pairings are never used as examples. Read the exact fresh inputs.
    import pickle
    import numpy as np
    from openmolspec_bench.data import readonly_lmdb, CpuUnpickler
    for r in read(name)['results']:
        symbol=r['nucleus'];task='nmr.forward.'+{'F':'19F','P':'31P'}[symbol]
        b=attach(task,name,{'metrics':{k:r[k] for k in ('mae_ppm','rmse_ppm','examples')}})
        directory=ROOT/'.runtime/fp_frozen_20261115'
        paths=list((directory/symbol).rglob('*.out.pkl'))
        inp=directory/f'{symbol}.lmdb'
        from audit_documentation_data import read_lmdb
        input_rows={int(row['_key']):row for row in read_lmdb(inp)}
        # Output logs contain paired target/prediction arrays even without raw data.
        pairs=[]
        for p in paths:
            with p.open('rb') as f:logs=CpuUnpickler(f).load()
            for log in logs:
                ids=np.asarray(log['matid']).reshape(-1).tolist()
                for x,y in zip(np.asarray(log['target']).reshape(-1),np.asarray(log['predict']).reshape(-1)):
                    pairs.append((float(x),float(y)))
                targets=np.asarray(log['target']).reshape(-1);predictions=np.asarray(log['predict']).reshape(-1)
                assert len(ids)==len(targets), 'Expected exactly one labeled heteronucleus per input'
                for index,x,y in zip(ids,targets,predictions):
                    row=input_rows[int(index)]
                    indices=np.flatnonzero(np.asarray(row['atoms_target_mask'])==1).tolist()
                    if len(b['examples'])<3:
                        b['examples'].append({'input':{'smiles':row['smiles'],'nucleus':symbol,'atom_indices':indices},
                                              'output':{'prediction_ppm':float(y)},'reference':{'ppm':float(x)}})
        if pairs:
            assert np.isclose(np.mean([abs(y-x) for x,y in pairs]),r['mae_ppm'],rtol=1e-5)
            b['plot']={'kind':'parity','x':[x for x,y in pairs],'y':[y for x,y in pairs],'unit':'ppm',
                       'label':f'{symbol}: solid model / solution labels; incompatible domain diagnostic'}
    name='gap_protocol_random128_20261116.json'
    for r in read(name)['results']:
        b=attach(r['task'],name,r)
        b['examples']=[{'sample_id':sid,'output':{'gap_ev':y},'reference':{'gap_ev':x}} for sid,x,y in zip(r['sample_ids'][:3],r['reference_gap_ev'][:3],r['predicted_gap_ev'][:3])]
        b['plot']={'kind':'parity','x':r['reference_gap_ev'],'y':r['predicted_gap_ev'],'unit':'eV',
                   'label':r['task'].split('.')[-1]+'; 128 distinct structures; seed 42'}
    name='vibrational_forward_paired_logs_20261116.json'
    r=read(name)['results'][0];b=attach(r['task'],name,r)
    b['examples']=[{'sample_id':x['sample_id'],'input':{'gaussian_log':Path(x['input']['path']).name,'sha256':x['input']['sha256'],'atoms':x['atoms']},
                    'output':{k:x[k] for k in ('wavenumber_cm1','predicted_ir','predicted_raman')},
                    'reference':{k:x[k] for k in ('reference_ir','reference_raman')},'metrics':x['metrics']} for x in r['records']]
    b['plot']={'kind':'vibrational',**r['records'][0],'label':'Same Gaussian geometry; first of 2 examples'}
    for name in ('smoke_vib2mol_20261115.json','vib2mol_xinyu_random64_20261116.json'):
        for r in read(name)['results']:
            if '.generation' not in r['task']:continue
            b=attach(r['task'],name,r)
            b['examples']=r['predictions'][:3]
            first=r['predictions'][0]
            b['plot']={'kind':'molecules','reference':first.get('target',first.get('reference')),
                       'predicted':first['reranked'][0] if 'reranked' in first else first['canonical_top_1'],
                       'label':'First real prediction; '+('ITM-ranked, four modalities' if r['given_nmr'] else 'missing-NMR ablation')}
    name='vibrational_ranked_examples_20261117.json';payload=read(name)
    assert payload.get('completed_at') and not payload.get('counts',{}).get('failed'), 'Vibrational ranking inference incomplete'
    for r in payload['results']:
        b=attach(r['task'],name,r);b['examples']=r['examples']
        b['plot']={'kind':'ranking','candidates':r['examples'][0]['ranked_candidates'],'label':r.get('ranking','embedding similarity')+'; 16 candidates'}
    for model in ('glacier','iceberg'):
        name=f'ms_{model}_32_molecules_20261116.json';r=read(name);b=attach(r['task'],name,r)
        rows=[x for x in r['records'] if x['status']=='passed'];x=rows[0]
        peaks=sorted(sorted(x['predicted_peaks'],key=lambda v:v[1],reverse=True)[:100])
        b['examples']=[{'input':{k:item[k] for k in ('smiles','adduct','collision_energy','instrument','precursor_mz')},
                        'sample_id':item['spec_id'],'output':{'predicted_peaks_top100':sorted(sorted(item['predicted_peaks'],key=lambda v:v[1],reverse=True)[:100])},
                        'reference':{'observed_peaks':item['reference_peaks']},'metrics':item['metrics']} for item in rows[:3]]
        b['plot']={'kind':'ms','predicted':peaks,'reference':x['reference_peaks'],'label':model.upper()+'; '+x['spec_id']+'; top 100 predicted peaks'}
    name='assignment_carbon32_20261116.json';r=read(name);b=attach(r['task'],name,r)
    b['examples']=[{'input':{'smiles':x['smiles'],'nucleus':'13C','peaks_ppm':[a['observed_ppm'] for a in sorted(x['assignments'],key=lambda a:a['peak_index'])],
                            'note':'Assigned observed peaks; unmatched indices retained in output'},'output':x} for x in r['records'][:3]]
    b['plot']={'kind':'assignment','record':r['records'][0],'label':'First molecule; predicted atom assignments, no experimental assignment labels'}
    name='solvent_transfer_reference32_20261116.json';r=read(name);b=attach(r['task'],name,r)
    b['examples']=[{'input':{'nucleus':x['nucleus'],'source_ppm':x['source_ppm'],'source_solvent':x['source_solvent'],'target_solvent':x['target_solvent'],
                           'query_connectivity':x['query_connectivity']},'output':x} for x in r['records'][:3]]
    b['plot']={'kind':'solvent','metrics':r['metrics'],'label':'32 molecules / 296 paired atoms; reference-retrieval baseline'}
    name='magma_real_test_verified_20261115.json';r=read(name);b=attach(r['task'],name,r)
    annotations=json.loads((ROOT/'.runtime/magma_real_20261115/annotations.json').read_text())['samples']
    b['examples']=[{'input':{'smiles':x['smiles'],'adduct':x['adduct'],'observed_peaks':[[p['mz'],p['intensity']] for p in x['peak_annotations']]},
                    'sample_id':x['spec_id'],'output':{'engine_smiles':x['engine_smiles'],'peak_annotations':x['peak_annotations']}} for x in annotations]
    b['plot']={'kind':'magma','records':r['records'],'label':'Algorithmic fragment matches; 2 spectra; no learned model'}
    # Attach measured input arrays to the exact sample IDs in gap/generation runs.
    needed={sid for b in bundles.values() for ex in b['examples'] for sid in [ex.get('sample_id')] if sid}
    from audit_documentation_data import read_lmdb
    lmdb_path=ROOT.parents[1]/'openmolspec-studio-portable/benchmark_data/release_v1_ks200k_hc_nmr_minmax/vib2mol/openspec_test.lmdb'
    lookup={}
    from rdkit import Chem
    canonical=lambda s:Chem.MolToSmiles(Chem.MolFromSmiles(s),isomericSmiles=True)
    desired_smiles={canonical(b['plot']['reference']) for b in bundles.values() if b.get('plot',{}).get('kind')=='molecules' and b['task'].startswith('vibrational')}
    for row in read_lmdb(lmdb_path):
        identity=Chem.MolToSmiles(Chem.MolFromSmiles(row['kekule_smiles']),isomericSmiles=True)
        sid=row.get('sample_id',row['_key'])
        if sid in needed or identity in desired_smiles:
            inp={k:np.asarray(row[k]).tolist() for k in ('ir','raman','nmr_h_shifts_ppm','nmr_c_shifts_ppm')}
            inp['nmr_reference_id']=row['nmr_reference_id'];lookup[sid]=inp;lookup[identity]=inp
    for task,b in bundles.items():
        if task.startswith('vibrational.gap.'):
            for ex in b['examples']:
                inp=dict(lookup[ex['sample_id']]);view=task.split('.')[-1]
                if view=='ir':inp.pop('raman')
                if view=='raman':inp.pop('ir')
                if not view.endswith('hc'):
                    for key in ('nmr_h_shifts_ppm','nmr_c_shifts_ppm','nmr_reference_id'):inp.pop(key,None)
                ex['input']=inp
        if task.startswith('vibrational.generation'):
            inp=dict(lookup[canonical(b['plot']['reference'])])
            if not task.endswith('.hc'):
                for key in ('nmr_h_shifts_ppm','nmr_c_shifts_ppm','nmr_reference_id'):inp.pop(key,None)
            b['examples'][0]['input']=inp
        b['source_hashes']={name:hashlib.sha256((ROOT/'results'/name).read_bytes()).hexdigest() for name in b['source_files']}
        if not b['enabled']:b['status']='deferred_by_user'
        elif task.endswith(('11B','29Si','19F','31P')):b['status']='diagnostic_only'
        else:b['status']='recorded_results'
    bundles['nmr.hsqc.transpeaknet'] = hsqc_evidence()
    return bundles


def render(task_id, evidence=None, *, example_index=0):
    """Return a reproducible Matplotlib figure from numerical inference evidence."""
    import copy
    from documentation_figures import render_task
    bundle=evidence or load_evidence(task_id)
    if example_index:
        bundle=copy.deepcopy(bundle);example=bundle['examples'][example_index]
        bundle['examples']=[example];plot=bundle['plot']
        if plot['kind']=='ms':
            plot.update(predicted=example['output']['predicted_peaks_top100'],reference=example['reference']['observed_peaks'])
        elif plot['kind']=='molecules' and task_id.startswith('nmr.generation.'):
            plot.update(reference=example['reference_smiles'],predicted=example['candidates'][0].get('canonical_smiles') or example['candidates'][0].get('smiles'))
        else:raise ValueError('Individual-example figures are defined for NMR generation and MS prediction')
    return render_task(task_id,bundle)


def recompute(evidence):
    import numpy as np
    p=evidence.get('plot',{});kind=p.get('kind')
    if kind=='parity':
        error=np.asarray(p['y'])-np.asarray(p['x'])
        return {'paired_values':len(error),'mae':float(abs(error).mean()),'rmse':float(np.sqrt((error**2).mean())),'unit':p['unit']}
    if kind=='assignment':
        a=p['record']['assignments']
        return {'matched_peaks_this_example':len(a),'residual_mae_ppm_this_example':sum(x['absolute_error_ppm'] for x in a)/len(a),'assignment_accuracy':None}
    if kind=='molecules':
        from rdkit import Chem
        def canon(s):
            m=Chem.MolFromSmiles(s) if s else None
            return Chem.MolToSmiles(m,isomericSmiles=True) if m else None
        return {'top1_matches_reference_this_example':canon(p['reference'])==canon(p['predicted'])}
    if kind=='vibrational':
        return {c+'_cosine':float(np.dot(p['reference_'+c],p['predicted_'+c])/(np.linalg.norm(p['reference_'+c])*np.linalg.norm(p['predicted_'+c]))) for c in ('ir','raman')}
    return {'scope':'Saved model outputs are shown directly; aggregate metrics are in the run table.',
            'recorded_runs':len(evidence['runs']),'real_examples':len(evidence['examples'])}


def main():
    import argparse
    import matplotlib.pyplot as plt
    parser=argparse.ArgumentParser()
    parser.add_argument('--figures-only', action='store_true', help='Redraw the published evidence without running inference or collecting new records')
    args=parser.parse_args()
    bundles={t.id:load_evidence(t.id) for t in TASKS} if args.figures_only else collect();directory=ASSETS/'examples';directory.mkdir(exist_ok=True)
    images=ASSETS/'gallery';images.mkdir(exist_ok=True)
    index={}
    for task,b in bundles.items():
        slug=task.replace('.','-')
        (directory/(slug+'.json')).write_text(json.dumps(b,ensure_ascii=False,indent=2)+'\n')
        index[task]={'status':b['status'],'sources':b['source_files'],'example_count':len(b['examples'])}
        if b['enabled']:
            assert b.get('plot') and b['examples'],task
            fig=render(task,b)
            for ext in ('svg','png'):
                fig.savefig(images/(slug+'.'+ext),dpi=170,metadata={'Date':None} if ext=='svg' else None)
            plt.close(fig)
            index[task]['figure']='gallery/'+slug+'.png'
            print('FIGURE',task,flush=True)
    (ASSETS/'evidence_index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
    render_datasets()


def render_datasets(save=True):
    import matplotlib.pyplot as plt
    from build_manual_examples import distributions
    figures = distributions()
    if save:
        for name, fig in figures.items():
            for ext in ('svg', 'png'):
                fig.savefig(ASSETS/'gallery'/f'{name}.{ext}', dpi=180,
                            metadata={'Date': None} if ext=='svg' else None)
            plt.close(fig)
    return figures


if __name__=='__main__':main()
