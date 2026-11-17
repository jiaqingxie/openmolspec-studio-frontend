"""Prepare numeric, nucleus-compatible NMR views and their distributions.

Source JSONLs remain unchanged. Output and source-byte checkpoints are local;
the portable report supplies the cleaned counts used by the user manual.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]


def clean_row(row):
    from rdkit import Chem,RDLogger
    from rdkit.Chem import Descriptors,rdMolDescriptors
    from spec2struct_fork.structured import parse_nmr_record,SHIFT,SHIFT_PRESENT
    RDLogger.DisableLog('rdApp.*')
    try:
        mol=Chem.MolFromSmiles(row.get('smiles',''))
        if mol is None or not mol.GetNumAtoms():return None,'invalid_structure'
        hydrogen=any(a.GetAtomicNum()==1 and a.GetIsotope() in (0,1) for a in Chem.AddHs(mol).GetAtoms())
        carbon=any(a.GetAtomicNum()==6 for a in mol.GetAtoms())
        cleaned=dict(row);shifts={};removed={};solvents=Counter();frequencies=[]
        for field,nucleus,present in [('h_nmr','h',hydrogen),('c_nmr','c',carbon)]:
            accepted=[];values=[];original=row.get(field) or []
            for record in original:
                if not present or not isinstance(record,dict):continue
                peaks=[float(v[SHIFT]) for v in parse_nmr_record(record,nucleus) if v[SHIFT_PRESENT] and math.isfinite(v[SHIFT])]
                if not peaks:continue
                accepted.append(record);values.extend(peaks)
                solvents[str(record.get('solvent') or 'Unspecified')]+=1
                import re
                match=re.search(r'\d+(?:\.\d+)?',str(record.get('frequency') or ''))
                if match and float(match.group())>0:frequencies.append(float(match.group()))
            cleaned[field]=accepted;shifts[nucleus]=values;removed[field]=len(original)-len(accepted)
        if not any(shifts.values()):return None,'no_usable_nmr'
        identity=Chem.InchiToInchiKey(row.get('inchi','')) if row.get('inchi') else Chem.MolToInchiKey(mol)
        if not identity:return None,'invalid_identity'
        formula=rdMolDescriptors.CalcMolFormula(mol)
        if cleaned.get('formula')!=formula:cleaned['source_formula']=cleaned.get('formula')
        cleaned.update(smiles=Chem.MolToSmiles(mol,isomericSmiles=True),formula=formula,
                       standard_inchikey=identity,modality_mask=[int(bool(shifts['h'])),int(bool(shifts['c']))],
                       h_peaks_ppm=shifts['h'],c_peaks_ppm=shifts['c'])
        features={'heavy':mol.GetNumHeavyAtoms(),'mw_bin':int(Descriptors.MolWt(mol)//10)*10,
                  'elements':sorted({a.GetSymbol() for a in mol.GetAtoms()}),'solvents':dict(solvents),
                  'frequencies':frequencies,'shifts':shifts,'removed':removed,'year':str(row.get('year','Unspecified'))}
        return (cleaned,features),None
    except Exception as error:return None,type(error).__name__


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True);parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--max-seconds',type=int,default=1200);parser.add_argument('--limit',type=int)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    checkpoint=args.output/'cleaning-checkpoint.json'
    if args.report.exists():print('Completed cleaned-data report exists');return
    state=json.loads(checkpoint.read_text()) if checkpoint.exists() else {'files':{},'counts':{},'histograms':{},'examples':[]}
    counters=Counter(state['counts']);hist={k:Counter(v) for k,v in state['histograms'].items()}
    def count(name,value,n=1):hist.setdefault(name,Counter())[str(value)]+=n
    started=time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for role in ['train','val','test']:
            source=args.source/f'{role}.jsonl'
            if not source.exists():continue
            progress=state['files'].setdefault(role,{'source_bytes':source.stat().st_size,'offset':0,'output_bytes':0,'ids_bytes':0,'processed':0,'accepted':0,'done':False})
            assert progress['source_bytes']==source.stat().st_size,'Input changed'
            if progress['done']:continue
            output=args.output/f'{role}.jsonl';ids=args.output/f'{role}.ids.txt'
            for path,offset in [(output,progress['output_bytes']),(ids,progress['ids_bytes'])]:
                if path.exists():
                    with path.open('r+b') as stream:stream.truncate(offset)
            with source.open('rb') as stream,output.open('ab') as target,ids.open('ab') as identities:
                stream.seek(progress['offset'])
                while True:
                    rows=[]
                    for _ in range(5000):
                        if args.limit and progress['processed']+len(rows)>=args.limit:break
                        line=stream.readline()
                        if not line:break
                        rows.append(json.loads(line))
                    if not rows:progress['done']=True;break
                    for original,(result,reason) in zip(rows,pool.map(clean_row,rows,chunksize=100)):
                        counters['source_records']+=1
                        if result is None:counters['excluded:'+reason]+=1;continue
                        row,f=result;progress['accepted']+=1;counters['cleaned_records']+=1
                        target.write((json.dumps(row,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode())
                        identities.write((row['standard_inchikey']+'\n').encode())
                        count('heavy_atoms',f['heavy']);count('molecular_weight_10Da',f['mw_bin']);count('year',f['year'])
                        for symbol in f['elements']:count('elements',symbol)
                        for solvent,n in f['solvents'].items():count('solvents',solvent,n)
                        for frequency in f['frequencies']:count('frequency_MHz',frequency)
                        mask=row['modality_mask'];count('modalities','H+C' if all(mask) else 'H' if mask[0] else 'C')
                        for nucleus in ['h','c']:
                            counters[nucleus+'_spectra']+=len(row[nucleus+'_nmr'])
                            counters[nucleus+'_peaks']+=len(f['shifts'][nucleus])
                            for value in f['shifts'][nucleus]:count(nucleus+'_shift_0.1ppm',round(math.floor(value*10)/10,1))
                            counters['removed_'+nucleus+'_spectra']+=f['removed'][nucleus+'_nmr']
                        if len(state['examples'])<3:state['examples'].append(row)
                    progress.update(offset=stream.tell(),output_bytes=target.tell(),ids_bytes=identities.tell(),processed=progress['processed']+len(rows))
                    target.flush();identities.flush()
                    state.update(counts=dict(counters),histograms={k:dict(v) for k,v in hist.items()})
                    staged=checkpoint.with_suffix('.partial');staged.write_text(json.dumps(state));staged.replace(checkpoint)
                    print(role,progress['processed'],'processed /',progress['accepted'],'cleaned',flush=True)
                    if time.monotonic()-started>args.max_seconds:print('Checkpoint saved');return
            state.update(counts=dict(counters),histograms={k:dict(v) for k,v in hist.items()});checkpoint.write_text(json.dumps(state))
    all_ids=set();split_ids={};outputs={}
    for role,progress in state['files'].items():
        keys=set((args.output/f'{role}.ids.txt').read_text().splitlines());split_ids[role]=keys;all_ids.update(keys)
        output=args.output/f'{role}.jsonl';outputs[role]={'file':output.name,'records':progress['accepted'],'molecules':len(keys),'bytes':output.stat().st_size,'sha256':digest(output)}
    overlaps={a+'/'+b:len(split_ids[a]&split_ids[b]) for i,a in enumerate(split_ids) for b in list(split_ids)[i+1:]}
    report={'completed':True,'provider':'OpenDataLab','domain':'experimental','collection':'opendatalab_nmr',
            'processing':'RDKit structure validation; nucleus-presence checks; numeric shift parsing; formula normalization; preserve prepared split roles',
            'source_files':{role:{'file':f'{role}.jsonl','bytes':p['source_bytes'],'sha256':digest(args.source/f'{role}.jsonl')} for role,p in state['files'].items()},
            'counts':dict(counters),'molecular_identities':len(all_ids),'split_identity_overlaps':overlaps,'files':outputs,
            'histograms':{k:dict(v) for k,v in hist.items()},'examples':state['examples'],'sample_limit':args.limit}
    assert not any(overlaps.values()),'Source split identity overlap'
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print('Cleaned NMR dataset complete:',report['counts']['cleaned_records'],'records;',len(all_ids),'molecular identities',flush=True)


if __name__=='__main__':main()
