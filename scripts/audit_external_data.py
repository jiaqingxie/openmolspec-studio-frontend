"""Full local MassSpecGym v1.5, QMe14S arrays, QM9S index and MassBank census."""
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import sys


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    import numpy as np
    import h5py
    from rdkit import Chem,RDLogger
    RDLogger.DisableLog('rdApp.*')
    root=Path(__file__).resolve().parents[1];data=root.parent.parent/'data';report={'completed':False,'datasets':{}}
    dest=root/'results/external_data_census_20261117.json'
    if dest.exists():report=json.loads(dest.read_text())
    def save():dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    if 'massspecgym_1_5' not in report['datasets']:
        path=root/'.runtime/data-audit/MassSpecGym1.5.tsv';counts=Counter();folds=Counter();adducts=Counter();instruments=Counter();peak_hist=Counter();heavy=Counter();identities=set();fold_ids={};cache={}
        assert digest(path)=='50cfdd1d22f79543c59555f9ce43c6893bd788a19a42b21fb4e2e3a54673c06a'
        with path.open() as f:
            for row in csv.DictReader(f,delimiter='\t'):
                counts['spectra']+=1;folds[row['fold']]+=1;adducts[row['adduct']]+=1;instruments[row['instrument_type']]+=1
                smiles=row['smiles']
                if smiles not in cache:
                    mol=Chem.MolFromSmiles(smiles);cache[smiles]=(Chem.MolToInchiKey(mol).split('-')[0],mol.GetNumHeavyAtoms()) if mol else (None,None)
                key,n=cache[smiles]
                if key:identities.add(key);fold_ids.setdefault(row['fold'],set()).add(key);heavy[n]+=1
                else:counts['invalid_smiles']+=1
                try:
                    mz=np.fromstring(row['mzs'],sep=',');intensity=np.fromstring(row['intensities'],sep=',')
                    good=len(mz)==len(intensity) and len(mz)>0 and np.isfinite(mz).all() and np.isfinite(intensity).all() and (mz>0).all() and (intensity>=0).all() and intensity.sum()>0
                    counts['valid_numeric_spectra']+=int(good);peak_hist[len(mz)]+=1
                except (ValueError,TypeError):counts['invalid_peak_lists']+=1
                try:counts['finite_collision_energy']+=int(np.isfinite(float(row['collision_energy'])))
                except ValueError:pass
                counts['simulation_challenge_eligible']+=int(row['simulation_challenge']=='True')
                if counts['spectra']%50000==0:print('MassSpecGym v1.5',counts['spectra'],flush=True)
        overlaps={a+' / '+b:len(fold_ids[a]&fold_ids[b]) for i,a in enumerate(fold_ids) for b in list(fold_ids)[i+1:]}
        report['datasets']['massspecgym_1_5']={'provider':'MassSpecGym','domain':'experimental','version':'1.5','source_url':'https://huggingface.co/datasets/roman-bushuiev/MassSpecGym','revision':'018a9542378725cf5620423f930608730c36dd8c','sha256':digest(path),'scope':'complete versioned TSV scan','counts':dict(counts),'unique_connectivities':len(identities),'fold_spectra':dict(folds),'fold_unique_connectivities':{k:len(v) for k,v in fold_ids.items()},'fold_connectivity_overlap':overlaps,'adducts':dict(adducts),'instruments':dict(instruments),'peak_count_histogram':dict(peak_hist),'heavy_atom_histogram_spectral_records':dict(heavy)};save()
    if 'qme14s' not in report['datasets']:
        channels={}
        for channel in ('ir','raman'):
            path=data/'QMe14S/processed'/f'{channel}_broaden_processed.h5'
            with h5py.File(path) as f:
                spectra=f['spectra'];axis=f['x_axis'][:];finite=constant=negative=0
                for start in range(0,len(spectra),2048):
                    block=spectra[start:start+2048];finite+=int(np.isfinite(block).all(axis=1).sum());constant+=int((np.ptp(block,axis=1)==0).sum());negative+=int((block<0).any(axis=1).sum())
                channels[channel]={'records':len(spectra),'shape':list(spectra.shape),'axis_min':float(axis.min()),'axis_max':float(axis.max()),'axis_strictly_increasing':bool((np.diff(axis)>0).all()),'finite_rows':finite,'constant_rows':constant,'negative_intensity_rows':negative,'sha256':digest(path)}
            print('QMe14S',channel,channels[channel]['records'],flush=True)
        report['datasets']['qme14s']={'provider':'QMe14S','domain':'computed','source_url':'https://arxiv.org/abs/2501.18876','scope':'complete local processed HDF5 arrays; row correspondence to original molecules requires the processing map','channels':channels};save()
    if 'qm9s' not in report['datasets']:
        mapping=data/'qm9s/mapping.txt';ids=set();smiles=set();heavy=Counter();invalid=0
        with mapping.open() as f:
            for line in f:
                key,s=line.rstrip().split('\t',1);ids.add(key);mol=Chem.MolFromSmiles(s)
                if mol:smiles.add(Chem.MolToSmiles(mol,isomericSmiles=True));heavy[mol.GetNumHeavyAtoms()]+=1
                else:invalid+=1
        with os.scandir(data/'qm9s/qm9s_csv') as iterator:files={Path(entry.name).stem for entry in iterator if entry.name.endswith('.csv')}
        report['datasets']['qm9s']={'provider':'QM9S','domain':'computed','source_url':'https://www.nature.com/articles/s43588-023-00550-y','scope':'complete local mapping and CSV filename census; individual numeric spectra are not all parsed in this pass','mapping_sha256':digest(mapping),'mapping_ids':len(ids),'unique_canonical_isomeric_smiles':len(smiles),'invalid_smiles':invalid,'csv_files':len(files),'mapping_with_csv':len(ids&files),'mapping_without_csv':len(ids-files),'csv_without_mapping':len(files-ids),'heavy_atom_histogram_mapping_records':dict(heavy)};save();print('QM9S index complete',flush=True)
    if 'massbank' not in report['datasets']:
        base=data/'massbank-data/MassBank-data-dev';counts=Counter();licenses=Counter();modes=Counter();instruments=Counter();accessions=set();structures=set()
        for directory,_,files in os.walk(base):
            for name in files:
                if not name.endswith('.txt'):continue
                text=(Path(directory)/name).read_text(errors='replace')
                if not text.startswith('ACCESSION:'):continue
                counts['spectral_records']+=1;accession=None
                for line in text.splitlines():
                    if line.startswith('ACCESSION: '):accession=line.split(': ',1)[1];accessions.add(accession)
                    elif line.startswith('CH$SMILES: '):structures.add(line.split(': ',1)[1])
                    elif line.startswith('LICENSE: '):licenses[line.split(': ',1)[1]]+=1
                    elif line.startswith('AC$MASS_SPECTROMETRY: MS_TYPE '):modes[line.split('MS_TYPE ',1)[1]]+=1
                    elif line.startswith('AC$INSTRUMENT_TYPE: '):instruments[line.split(': ',1)[1]]+=1
                    elif line.startswith('PK$NUM_PEAK: '):
                        try:counts['numeric_peaks_declared']+=int(line.split(': ',1)[1])
                        except ValueError:counts['invalid_peak_count']+=1
        report['datasets']['massbank']={'provider':'MassBank','domain':'experimental','source_url':'https://github.com/MassBank/MassBank-data','scope':'complete local text-record metadata scan; exact snapshot version and per-peak validation remain to be recorded','counts':dict(counts),'unique_accessions':len(accessions),'unique_smiles_texts':len(structures),'ms_types':dict(modes),'instrument_types':dict(instruments),'licenses':dict(licenses)};save();print('MassBank metadata complete',flush=True)
    report['completed']=True;save()


if __name__=='__main__':main()
