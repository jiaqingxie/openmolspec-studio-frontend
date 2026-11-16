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
            b['examples']=[{'input':{'smiles':ex['smiles']},'output':{'prediction_ppm':ex['prediction_ppm'],'model':model['model']},
                            'reference':{'peaks_ppm':ex['reference_ppm']}}]
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
        b['examples']=[{'input':{k:x[k] for k in ('smiles','adduct','collision_energy','instrument','precursor_mz')},
                        'sample_id':x['spec_id'],'output':{'predicted_peaks_top100':peaks},'reference':{'observed_peaks':x['reference_peaks']},'metrics':x['metrics']}]
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
    return bundles


def render(task_id, evidence=None):
    """Return a reproducible Matplotlib figure from numerical inference evidence."""
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from rdkit import Chem
    from rdkit.Chem import Draw
    b=evidence or load_evidence(task_id);p=b['plot'];kind=p['kind']
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.hashsalt':'openmolspec'})
    fig,axes=plt.subplots(1,2 if kind in ('parity','vibrational','molecules','assignment','solvent') else 1,figsize=(10,4.2),squeeze=False)
    ax=axes[0,0]
    if kind=='parity':
        x,y=np.asarray(p['x']),np.asarray(p['y']);lo,hi=min(x.min(),y.min()),max(x.max(),y.max())
        ax.scatter(x,y,s=24,alpha=.8,color='#2879aa');ax.plot([lo,hi],[lo,hi],'--',color='#777777')
        ax.set(xlabel=f'Reference ({p["unit"]})',ylabel=f'Prediction ({p["unit"]})',title=f'MAE = {np.mean(abs(y-x)):.4f} {p["unit"]}')
        axes[0,1].hist(y-x,bins=min(16,len(x)),color='#2879aa',edgecolor='white')
        axes[0,1].axvline(0,color='#555555',ls='--');axes[0,1].set(xlabel=f'Prediction - reference ({p["unit"]})',ylabel='Count',title=f'n = {len(x)} paired values')
    elif kind=='vibrational':
        for a,channel in zip(axes[0],('ir','raman')):
            a.plot(p['wavenumber_cm1'],p['reference_'+channel],label='Gaussian reference',color='#333333',lw=1.4)
            a.plot(p['wavenumber_cm1'],p['predicted_'+channel],label='Frozen prediction',color='#df713e',alpha=.8,lw=1.2)
            a.set(xlabel='Wavenumber (cm$^{-1}$)',ylabel='Normalized intensity',title=channel.upper());a.legend(fontsize=8)
    elif kind=='nmr_peaks':
        ax.vlines(p['reference_ppm'],0,1,color='#333333',label='Experimental peaks')
        ax.vlines(p['prediction_ppm'],0,-1,color='#2879aa',label='Predicted atom shifts')
        ax.invert_xaxis();ax.set(xlabel='Chemical shift (ppm)',ylabel='Peak markers (not measured intensities)');ax.legend(fontsize=8)
    elif kind=='ms':
        for key,sign,col in [('reference',1,'#333333'),('predicted',-1,'#2879aa')]:
            values=np.asarray(p[key]);values[:,1]/=max(values[:,1].max(),1e-12)
            ax.vlines(values[:,0],0,sign*values[:,1],color=col,label='Observed' if sign==1 else 'Predicted')
        ax.set(xlabel='m/z',ylabel='Relative intensity; prediction mirrored');ax.legend(fontsize=8)
    elif kind=='ranking':
        candidates=p['candidates'][:10];colors=['#e0813f' if c['reference_match'] else '#2879aa' for c in candidates]
        ax.bar(range(1,len(candidates)+1),[c['score'] for c in candidates],color=colors)
        ax.set(xlabel='Candidate rank (orange = reference structure)',ylabel='Model score (not calibrated probability)')
    elif kind=='molecules':
        for a,smi,title in zip(axes[0],[p['reference'],p['predicted']],['Reference structure','Actual top-1 prediction']):
            molecule=Chem.MolFromSmiles(smi) if smi else None
            if molecule:a.imshow(Draw.MolToImage(molecule,size=(450,300)))
            else:a.text(.5,.5,'Invalid / missing SMILES',ha='center')
            a.set_title(title);a.axis('off')
    elif kind=='assignment':
        r=p['record'];mol=Chem.MolFromSmiles(r['smiles'])
        for atom in mol.GetAtoms():atom.SetAtomMapNum(atom.GetIdx()+1)
        ax.imshow(Draw.MolToImage(mol,size=(500,330)));ax.axis('off');ax.set_title('Atom-map labels = index + 1')
        entries=r['assignments'];a=axes[0,1]
        a.scatter([x['observed_ppm'] for x in entries],[x['predicted_ppm'] for x in entries],color='#2879aa')
        for x in entries:a.annotate(','.join(str(i+1) for i in x['atom_indices']),(x['observed_ppm'],x['predicted_ppm']),fontsize=6)
        a.set(xlabel='Observed 13C peak (ppm)',ylabel='Predicted matched site (ppm)')
    elif kind=='solvent':
        for a,nuc in zip(axes[0],('1H','13C')):
            m=p['metrics'][nuc];a.bar(['Reference transfer','Unchanged shift'],[m['mae_ppm'],m['unchanged_shift_mae_ppm']],color=['#2879aa','#888888'])
            a.set(ylabel='MAE (ppm)',title=f'{nuc}: {m["atoms"]} paired atoms')
    elif kind=='magma':
        records=p['records'];x=np.arange(len(records))
        ax.bar(x,[r['n_matched'] for r in records],label='Matched',color='#2879aa')
        ax.bar(x,[r['n_peaks']-r['n_matched'] for r in records],bottom=[r['n_matched'] for r in records],label='Unmatched',color='#bbbbbb')
        ax.set_xticks(x,[r['spec_id'] for r in records]);ax.set_ylabel('Observed peaks');ax.legend()
    else:raise ValueError(kind)
    fig.suptitle(task_id,fontsize=13,fontweight='bold');fig.text(.5,.015,p['label'],ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.06,1,.94));return fig


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
    import matplotlib.pyplot as plt
    bundles=collect();directory=ASSETS/'examples';directory.mkdir(exist_ok=True)
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
    import numpy as np
    import matplotlib.pyplot as plt
    data=json.loads((ASSETS/'dataset_audit.json').read_text())
    figures={}
    fig,ax=plt.subplots(figsize=(10,4.5))
    rows=data['datasets'][:4];positions=np.arange(len(rows));bottom=np.zeros(len(rows))
    for modality,color in [('H only','#3b8bb5'),('C only','#e99852'),('H+C','#4a9b79')]:
        counts=np.array([r['modality_records'].get(modality,0) for r in rows]);ax.bar(positions,counts,bottom=bottom,label=modality,color=color);bottom+=counts
    ax.set_xticks(positions,[r['id'].replace('_test','').replace('_10k','') for r in rows]);ax.set(ylabel='Molecular records in local evaluation files',title='Our prepared evaluation views of external NMR datasets')
    ax.legend();fig.tight_layout();figures['dataset-nmr-views']=fig
    openspec=next(r for r in data['datasets'] if r['id']=='openspec_test')
    fig,axes=plt.subplots(1,2,figsize=(11,4.8));pairs=sorted(openspec['source_records'].items(),key=lambda x:x[1])
    axes[0].barh([k for k,v in pairs],[v for k,v in pairs],color='#3b8bb5');axes[0].set(xlabel='Test records',title='Molecular-library origins of computed spectra')
    hist=openspec['heavy_atom_histogram'];axes[1].bar([int(k) for k in hist],list(hist.values()),color='#4a9b79');axes[1].set(xlabel='Heavy atoms',ylabel='Test records',title='20,390 records / 16,728 canonical structures')
    fig.tight_layout();figures['dataset-openspec-test']=fig
    fig,axes=plt.subplots(1,2,figsize=(10,4.5));counts=data['patent_corpus']['summary']['counts']
    axes[0].bar(['Train','Validation','Test'],[counts[k] for k in ('train','val','test')],color='#3b8bb5');axes[0].set(ylabel='Unique standard InChIs',title='Team-curated WanJuan patent view')
    axes[1].bar(['H only','C only','H+C'],[counts[k] for k in ('h_only','c_only','h_and_c')],color=['#3b8bb5','#e99852','#4a9b79']);axes[1].set(ylabel='Unique standard InChIs',title='Modality availability')
    fig.text(.5,.01,'Counts from existing full-corpus verification report; this audit did not rescan 2.68M molecules.',ha='center',fontsize=8);fig.tight_layout(rect=(0,.04,1,1));figures['dataset-patent-corpus']=fig
    fig,ax=plt.subplots(figsize=(9,4.2));rows=[r for r in data['external_local_views'] if r['id'].startswith('nmrexp')]
    ax.bar([r['id'].split('_')[1] for r in rows],[r['records'] for r in rows],color='#3b8bb5');ax.set_yscale('log');ax.set(ylabel='Spectral records (log scale)',title='External NMRExp: locally filtered per-nucleus records')
    for i,r in enumerate(rows):ax.text(i,r['records']*1.12,f'{r["records"]:,}',ha='center',fontsize=9)
    fig.tight_layout();figures['dataset-nmrexp-nuclei']=fig
    if save:
        for name,fig in figures.items():
            for ext in ('svg','png'):fig.savefig(ASSETS/'gallery'/f'{name}.{ext}',dpi=170,metadata={'Date':None} if ext=='svg' else None)
            plt.close(fig)
    return figures


if __name__=='__main__':main()
