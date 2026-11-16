"""Read-only dataset census and B/Si diagnostic review. Never trains models."""
import ast
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pickle
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from openmolspec_bench.data import readonly_lmdb, sha256


def describe(values):
    import numpy as np
    v = np.asarray(values, dtype=float)
    return {"count": len(v), "min": float(v.min()), "median": float(np.median(v)),
            "mean": float(v.mean()), "max": float(v.max())} if len(v) else {"count": 0}


def census(rows, name):
    from rdkit import Chem, RDLogger
    from rdkit.Chem import Descriptors
    RDLogger.DisableLog('rdApp.*')
    counts, elements, modalities, sources, heavy, mw = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    identities, examples = set(), []
    for row in rows:
        counts['records'] += 1
        smiles = row.get('smiles', row.get('kekule_smiles', ''))
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            counts['invalid_smiles'] += 1
            continue
        identity = Chem.MolToSmiles(mol, isomericSmiles=True)
        identities.add(identity)
        elements.update(set(a.GetSymbol() for a in mol.GetAtoms()))
        heavy[mol.GetNumHeavyAtoms()] += 1
        mw[int(Descriptors.MolWt(mol)//50)*50] += 1
        if 'modality_mask' in row:
            h, c = map(bool, row['modality_mask'])
            counts['h_spectrum_records'] += len(row.get('h_nmr', []))
            counts['c_spectrum_records'] += len(row.get('c_nmr', []))
        else:
            h, c = bool(row.get('nmr_h_present')), bool(row.get('nmr_c_present'))
            counts['ir_records'] += int('ir' in row)
            counts['raman_records'] += int('raman' in row)
            counts['h_atom_shifts'] += len(row.get('nmr_h_shifts_ppm', []))
            counts['c_atom_shifts'] += len(row.get('nmr_c_shifts_ppm', []))
        modalities['H+C' if h and c else 'H only' if h else 'C only' if c else 'neither'] += 1
        sources[row.get('source_dataset', row.get('source', name)) or name] += 1
        if len(examples) < 2:
            examples.append({k: (v.tolist() if hasattr(v,'tolist') else v)
                             for k,v in row.items() if k in ('smiles','formula','h_nmr','c_nmr','modality_mask','sample_id','source_dataset','kekule_smiles','ir','raman','nmr_h_shifts_ppm','nmr_c_shifts_ppm','gap','nmr_reference_id')})
    return {**counts, 'unique_canonical_isomeric_smiles':len(identities), 'modality_records':dict(modalities),
            'source_records':dict(sources), 'element_presence_records':dict(elements),
            'heavy_atom_histogram':dict(sorted(heavy.items())), 'molecular_weight_50Da_bins':dict(sorted(mw.items())),
            'examples':examples, 'identity_basis':'RDKit canonical isomeric SMILES', 'count_scope':'complete local file scan'}


def read_lmdb(path):
    env=readonly_lmdb(path)
    try:
        with env.begin() as t:
            for key,value in t.cursor():
                row=pickle.loads(value); row['_key']=key.decode(); yield row
    finally: env.close()


def audit_bsi(models):
    import numpy as np
    from rdkit import Chem
    recorded=json.loads((ROOT/'results/bsi_frozen_diagnostic_20261116.json').read_text())
    report={'training_performed':False,'calibration_fitted':False,'source_result':'bsi_frozen_diagnostic_20261116.json','nuclei':{}}
    for symbol in ('B','Si'):
        pools={split:list(read_lmdb(models/f'nmrnetpp/pool_{symbol}/{split}.lmdb')) for split in ('train','valid')}
        identities={split:{Chem.MolToSmiles(Chem.MolFromSmiles(r['smiles']),isomericSmiles=True) for r in rows} for split,rows in pools.items()}
        summaries={}
        for split,rows in pools.items():
            values=[float(v) for r in rows for a,m,v in zip(r['atoms'],r['atoms_target_mask'],r['atoms_target']) if a==symbol and m==1]
            summaries[split]={'records':len(rows),'unique_molecules':len(identities[split]),'target_ppm':describe(values),
                              'blank_solvent_records':sum(not r.get('nmr_solvent') for r in rows),
                              'multiple_selected_atoms':int(sum(sum(a==symbol and m==1 for a,m in zip(r['atoms'],r['atoms_target_mask']))!=1 for r in rows))}
        def fingerprint(row):
            data=[row['smiles'],row['atoms'],np.asarray(row['coordinates']).tolist(),
                  np.asarray(row['atoms_target']).tolist(),np.asarray(row['atoms_target_mask']).tolist()]
            return hashlib.sha256(json.dumps(data).encode()).hexdigest()
        source_counts={}
        source_version=None
        pool_fingerprints=Counter(fingerprint(r) for r in pools['valid'])
        for version in ('data_hetero2','data_hetero3'):
            candidate=Counter();candidate_counts={}
            for source in ('nmrexp','wanjuan'):
                p=models/f'nmrnetpp/{version}/{source}_{symbol}_valid/valid.lmdb'
                rows=list(read_lmdb(p)) if p.exists() else []
                candidate.update(fingerprint(r) for r in rows);candidate_counts[source]=len(rows)
            if candidate==pool_fingerprints:
                source_counts=candidate_counts;source_version=version
                break
        run=recorded['nuclei'][symbol]
        pred=np.concatenate([r['prediction_ppm'] for r in run['records']]);ref=np.concatenate([r['reference_ppm'] for r in run['records']]);error=pred-ref
        assert np.isclose(np.abs(error).mean(),run['mae_ppm'])
        valid={r['_key']:r for r in pools['valid']}
        for r in run['records']:
            row=valid[r['source_key']]
            assert row['smiles']==r['smiles']
            np.testing.assert_allclose(np.asarray(row['atoms_target'])[r['atom_indices']],r['reference_ppm'])
            assert sum(a==symbol for a in row['atoms'])==1
        report['nuclei'][symbol]={'pool':summaries,'valid_source_records':source_counts,
            'source_pool_version':source_version,'source_pool_contents_verified':source_version is not None,
            'pool_train_valid_structure_overlap':len(identities['train']&identities['valid']),
            'evaluated_molecules':run['molecules'],'mae_ppm':float(np.abs(error).mean()),'rmse_ppm':float(np.sqrt(np.mean(error**2))),
            'mean_signed_error_ppm':float(error.mean()),'median_absolute_error_ppm':float(np.median(np.abs(error))),
            'reference_ppm':describe(ref),'prediction_ppm':describe(pred),
            'correlation':float(np.corrcoef(ref,pred)[0,1]),'r_squared':float(1-np.sum(error**2)/np.sum((ref-ref.mean())**2)),
            'errors_within_5ppm':int(np.sum(np.abs(error)<=5)),
            'labels_rechecked_against_current_pool':True,'single_nucleus_atom_per_evaluated_molecule':True,
            'assessment':'diagnostic_only; not validated for accurate solution prediction',
            'provenance_limit':'Prepared source records omit original spectrum IDs and solvent; assigning the sole nucleus is unambiguous but original experimental conditions are not preserved.',
            'records':run['records']}
    return report


def main():
    import pyarrow.parquet as pq
    parent=ROOT.parents[1]
    datasets=[]
    for name in ('nmrspec_test','patent_test_10k','nmrexp_exp_10k','nmrgym_test'):
        path=ROOT.parent/'data/align_eval'/name/'test.jsonl'
        with path.open() as f:stats=census((json.loads(line) for line in f),name)
        datasets.append({'id':name,'ownership':'our_prepared_view_of_external_measurements',
                         'source':{'nmrspec_test':'NMRSpec / NMRTrans benchmark','patent_test_10k':'OpenDataLab / WanJuan experimental patent corpus; team-curated InChI view','nmrexp_exp_10k':'NMRExp','nmrgym_test':'NMRGym'}[name],
                         'split':'test','path':str(path),'sha256':sha256(path),**stats})
        print(name,stats['records'],flush=True)
    path=parent/'openmolspec-studio-portable/benchmark_data/release_v1_ks200k_hc_nmr_minmax/vib2mol/openspec_test.lmdb'
    stats=census(read_lmdb(path),'OpenMolSpec')
    datasets.append({'id':'openspec_test','ownership':'OpenMolSpec_computed_spectra','source':'OpenMolSpec calculated observables; source_dataset identifies molecular-library origins, not experimental spectra',
                     'split':'test','path':str(path),'sha256':sha256(path),**stats})
    print('openspec_test',stats['records'],flush=True)
    raw=[]
    for path in sorted((parent/'data/NMRExp').glob('*usable.parquet')):
        pf=pq.ParquetFile(path)
        raw.append({'id':path.stem,'ownership':'external_NMRExp_local_filtered_view','records':pf.metadata.num_rows,'count_scope':'Parquet metadata',
                    'columns':pf.schema.names,'size_bytes':path.stat().st_size,'path':str(path)})
    path=parent/'MassSpecGym-MAGMA-annotation/data/MassSpecGym_test_full.csv'
    counts=Counter();molecules=set();example=None
    with path.open() as f:
        reader=csv.DictReader(f);columns=reader.fieldnames
        for r in reader:
            counts['spectra']+=1;molecules.add(r['smiles']);counts['adduct:'+r.get('adduct','unknown')]+=1
            if example is None:example=r
    raw.append({'id':'MassSpecGym_test_full','ownership':'external_MassSpecGym_local_test_view',**counts,'distinct_smiles_strings':len(molecules),
                'columns':columns,'example':example,'path':str(path),'sha256':sha256(path),'count_scope':'complete CSV scan'})
    patent=Path('/mnt/shared-storage-user/luxinyu/nmr_project/model_data/hc_nmr_inchi_v1')
    summary=json.loads((patent/'summary.json').read_text());verification=json.loads((patent/'verification.json').read_text())
    report={'audited_at':datetime.now(timezone.utc).isoformat(),'training_performed':False,'datasets':datasets,'external_local_views':raw,
        'patent_corpus':{'provider':'OpenDataLab / WanJuan','domain':'experimental','domain_provenance':'project owner clarification, 2026-11-17; provider version and redistribution scope require release verification','ownership':'team_curated_derivative_of_WanJuan_patent_measurements','summary':summary,'verification_status':verification['status'],
                         'summary_sha256':sha256(patent/'summary.json'),'verification_sha256':sha256(patent/'verification.json'),
                         'count_scope':'existing complete-corpus verification report; not rescanned in this documentation audit'},
        'openspec_release_snapshot':{'full_unique_inchikey_molecules':1158074,'align_molecules':1030780,'trajectory_frames':32333251,
                                    'align_splits':{'train':1000000,'validation':10390,'test':20390},
                                    'source':'docs/openmolspec_core.md','source_sha256':sha256(ROOT/'docs/openmolspec_core.md'),
                                    'count_scope':'documented frozen-candidate snapshot; full release artifacts not mounted here; test LMDB independently scanned above'},
        'counting_notes':['Prepared subsets overlap their parent datasets; do not sum them.',
                          'Spectra, molecule identities, atom shifts and trajectory frames are separate units.',
                          'A local test designation does not establish independence from a pretrained model training set.']}
    target=ROOT/'documentation/assets/dataset_audit.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    bsi=audit_bsi(parent/'models')
    (ROOT/'results/bsi_model_review_20261117.json').write_text(json.dumps(bsi,ensure_ascii=False,indent=2)+'\n')
    print('Dataset and B/Si audits saved',flush=True)


if __name__=='__main__':main()
