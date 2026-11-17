"""Export cleaned experimental peak-list views from the OpenDataLab source."""
import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from audit_platform_data import family,nmr_nucleus_counts,peak_kind


@lru_cache(maxsize=4096)
def classify(label):
    modality=family(label)
    if modality!='NMR':return modality,None
    counts=nmr_nucleus_counts({label:1})
    nucleus=next((key for key in ['11B','19F','29Si','31P'] if counts.get(key)),None)
    return modality,nucleus


def positions(peaks):
    values=[]
    for item in peaks:
        if isinstance(item,dict):value=next(item[k] for k in ['mz','m/z','m_z','mass','wavenumber','frequency'] if k in item)
        else:value=item[0] if isinstance(item,(list,tuple)) else item
        values.append(float(value))
    return values


def intensities(peaks):
    return [float(next(item[k] for k in ['intensity','relative_intensity','abundance'] if k in item)) if isinstance(item,dict) else float(item[1]) for item in peaks]


def shifts(text):
    text=re.sub(r'[({][^)}]*[)}]',' ',str(text or '')).replace('−','-')
    pattern=r'(?<![\w.])([+-]?\d{1,4}(?:\.\d+)?)(?:\s*(?:[-–—]|to)\s*([+-]?\d{1,4}(?:\.\d+)?))?(?![\w.])'
    return [(float(m.group(1))+float(m.group(2)))/2 if m.group(2) else float(m.group(1)) for m in re.finditer(pattern,text)]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--identity-database',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--max-seconds',type=int,default=1200);parser.add_argument('--limit-documents',type=int)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if args.report.exists():print('Completed report exists');return
    from rdkit import Chem,RDLogger
    from rdkit.Chem import Descriptors
    RDLogger.DisableLog('rdApp.*')
    identities=sqlite3.connect('file:'+str(args.identity_database.resolve())+'?mode=ro&immutable=1',uri=True)
    identities.execute('PRAGMA cache_size=-200000')
    excluded={r[0] for r in identities.execute('select connectivity from benchmark_exclusions_v1')}
    @lru_cache(maxsize=150000)
    def structure(smiles):
        mol=Chem.MolFromSmiles(smiles)
        if mol is None or not mol.GetNumAtoms():return None
        key=Chem.MolToInchiKey(mol)
        if not key or key[:14] in excluded:return None
        row=identities.execute('select split from normalized_v2 where identity=?',(key,)).fetchone()
        if not row:return None
        return key,Chem.MolToSmiles(mol,isomericSmiles=True),row[0],mol.GetNumHeavyAtoms(),int(Descriptors.MolWt(mol)//10)*10,sorted({a.GetSymbol() for a in mol.GetAtoms()})
    db=sqlite3.connect(args.output/'cleaning.sqlite');db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA cache_size=-64000')
    db.execute('CREATE TABLE IF NOT EXISTS spectra(digest TEXT PRIMARY KEY,modality TEXT,identity TEXT,role TEXT,heavy INTEGER,mw_bin INTEGER,elements TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS state(name TEXT PRIMARY KEY,value TEXT)');prior=db.execute("select value from state where name='progress'").fetchone()
    state=json.loads(prior[0]) if prior else {'offset':0,'documents':0,'counts':{},'files':{},'histograms':{},'examples':{}}
    source_stat={'bytes':args.source.stat().st_size,'mtime_ns':args.source.stat().st_mtime_ns}
    if 'source_stat' in state:assert state['source_stat']==source_stat,'Source changed'
    state['source_stat']=source_stat
    # Restore every generated stream to its committed checkpoint, including
    # a view that receives no further rows after a resumed run.
    for path in args.output.glob('*.jsonl'):
        with path.open('r+b') as stream:stream.truncate(state['files'].get(path.name,0))
    counts=Counter(state['counts']);hist={k:Counter(v) for k,v in state['histograms'].items()};streams={}
    def increment(name,key,n=1):hist.setdefault(name,Counter())[str(key)]+=n
    def stream_for(name):
        if name not in streams:
            path=args.output/name;offset=state['files'].get(name,0)
            if path.exists():
                with path.open('r+b') as f:f.truncate(offset)
            streams[name]=path.open('ab')
        return streams[name]
    def save(offset):
        for name,stream in streams.items():stream.flush();state['files'][name]=stream.tell()
        state.update(offset=offset,counts=dict(counts),histograms={k:dict(v) for k,v in hist.items()})
        db.execute("insert or replace into state values ('progress',?)",(json.dumps(state),));db.commit()
    started=time.monotonic()
    with args.source.open('rb') as source:
        source.seek(state['offset'])
        while True:
            line=source.readline()
            if not line:break
            document=json.loads(line);meta=document.get('meta_info') or {};state['documents']+=1
            for compound in document.get('compounds') or []:
                smiles=compound.get('smiles_std') or compound.get('smiles')
                if not isinstance(smiles,str) or not smiles.strip():continue
                for spectrum in compound.get('spectra') or []:
                    label=str(spectrum.get('spectrum_type') or '');modality,nucleus=classify(label)
                    if modality=='NMR' and not nucleus or modality not in ['NMR','MS','IR','Raman']:continue
                    name=nucleus if nucleus else modality;values=[];heights=None
                    if nucleus:
                        values=shifts(spectrum.get('chemical_shift'))
                        if not values:continue
                    else:
                        kind,size=peak_kind(spectrum.get('peaks'),modality)
                        if size<2 or kind not in ['numeric_positions_only','numeric_position_intensity_pairs']:continue
                        if modality=='MS' and kind!='numeric_position_intensity_pairs':continue
                        values=positions(spectrum['peaks'])
                        if kind=='numeric_position_intensity_pairs':heights=intensities(spectrum['peaks'])
                    counts[name+':numeric_source_records']+=1
                    normalized=structure(smiles)
                    if not normalized:counts[name+':excluded_structure_or_partition']+=1;continue
                    key,canonical,role,heavy,mw,elements=normalized
                    if nucleus and {'11B':'B','19F':'F','29Si':'Si','31P':'P'}[nucleus] not in elements:
                        counts[name+':excluded_absent_nucleus']+=1;continue
                    value={'smiles':canonical,'standard_inchikey':key,'modality':modality,'source':'OpenDataLab',
                           'source_document':meta.get('upstream_path'),'source_spectrum_type':label,
                           'solvent':spectrum.get('solvent'),'frequency':spectrum.get('frequency')}
                    if nucleus:value.update(nucleus=nucleus,peaks_ppm=values,chemical_shift=spectrum.get('chemical_shift'))
                    elif modality in ['IR','Raman']:value.update(wavenumber_cm1=values)
                    else:value.update(peaks=list(map(list,zip(values,heights))))
                    if heights is not None and modality in ['IR','Raman']:value['intensities']=heights
                    identity_payload=[key,name,values,heights,value['solvent'],value['frequency']]
                    fingerprint=hashlib.sha256(json.dumps(identity_payload,sort_keys=True,allow_nan=False).encode()).hexdigest()
                    inserted=db.execute('INSERT OR IGNORE INTO spectra VALUES (?,?,?,?,?,?,?)',(fingerprint,name,key,role,heavy,mw,','.join(elements))).rowcount
                    if not inserted:counts[name+':duplicate_spectra']+=1;continue
                    counts[name+':cleaned_spectra']+=1;counts[name+':peaks']+=len(values)
                    stream_for(name+'-'+role+'.jsonl').write((json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode())
                    increment(name+':heavy_atoms',heavy);increment(name+':molecular_weight_10Da',mw)
                    for symbol in elements:increment(name+':elements',symbol)
                    for x in values:increment(name+':positions',math.floor(x*10)/10 if nucleus else int(x//10)*10)
                    if len(state['examples'].setdefault(name,[]))<3:state['examples'][name].append(value)
            if state['documents']%200==0:
                save(source.tell());print('Documents',state['documents'],'cleaned spectra',sum(v for k,v in counts.items() if k.endswith(':cleaned_spectra')),flush=True)
                if time.monotonic()-started>args.max_seconds:print('Checkpoint saved');return
            if args.limit_documents and state['documents']>=args.limit_documents:break
        save(source.tell())
    for stream in streams.values():stream.close()
    report={'completed':True,'provider':'OpenDataLab','domain':'experimental','counts':dict(counts),'histograms':{k:dict(v) for k,v in hist.items()},'examples':state['examples'],
            'source_documents_processed':state['documents'],'sample_limit':args.limit_documents,
            'processing':'Valid standard identities; supported fixed benchmark membership; at least two numerical peaks for MS/IR/Raman; positive finite m/z and nonnegative intensities for MS; numeric shifts and matching element for heteronuclear NMR; exact spectrum/condition deduplication',
            'views':{name:{'spectra':db.execute('select count(*) from spectra where modality=?',(name,)).fetchone()[0],
                           'molecules':db.execute('select count(distinct identity) from spectra where modality=?',(name,)).fetchone()[0],
                           'splits':{role:db.execute('select count(*) from spectra where modality=? and role=?',(name,role)).fetchone()[0] for role in ['train','val','test']}} for (name,) in db.execute('select distinct modality from spectra')},
            'files':state['files']}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');db.close();identities.close();print('Clean experimental peak-list views complete',flush=True)


if __name__=='__main__':main()
