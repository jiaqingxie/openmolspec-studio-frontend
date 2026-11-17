"""Complete, resumable OpenDataLab v1.0.3 census with explicit usability tiers.

Reads source bytes without changing them. Raw type labels, per-compound modality
combinations and numerical peak availability remain separate measurements.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import time


def family(label):
    text=re.sub(r'\s+',' ',str(label).upper()).strip()
    if 'NMR' in text or 'RMN' in text or 'DEPT' in text:return 'NMR'
    if 'RAMAN' in text:return 'Raman'
    if re.search(r'(^|[^A-Z])(FT[- ]?)?IR([^A-Z]|$)',text) or 'INFRARED' in text:return 'IR'
    if 'MS' in text or 'MASS' in text:return 'MS'
    return 'Other'


def nmr_nucleus_counts(types):
    """Partition NMR-family entry labels; decoupling braces do not add a nucleus."""
    counts=Counter({key:0 for key in ['1H','13C','19F','31P','11B','29Si','Other / multiple nuclei','Unspecified']})
    for label,n in types.items():
        if family(label)!='NMR':continue
        text=re.sub(r'\{[^}]*\}','',str(label).upper())
        compact=re.sub(r'\s+','',text).replace('NMR','').replace('RMN','')
        found=set(re.findall(r'(?<!\d)(?:1H|13C|19F|31P|11B|29SI)',compact))
        if len(found)==1:key=next(iter(found)).replace('29SI','29Si')
        elif len(found)>1:key='Other / multiple nuclei'
        elif compact.strip('-_') in ['H','H1'] or 'PROTON' in compact:key='1H'
        elif compact.strip('-_') in ['C13','F19','P31','B11','SI29']:
            key={'C13':'13C','F19':'19F','P31':'31P','B11':'11B','SI29':'29Si'}[compact.strip('-_')]
        elif re.search(r'\d+[A-Z]',compact):key='Other / multiple nuclei'
        else:key='Unspecified'
        counts[key]+=n
    return dict(counts)


def positive(value):
    try:return not isinstance(value,bool) and math.isfinite(float(value)) and float(value)>0
    except (ValueError,TypeError):return False


def peak_kind(peaks,channel):
    """Distinguish numeric positions from explicit position/intensity pairs."""
    if not isinstance(peaks,list) or not peaks:return 'unstructured_or_missing',0
    positions=[];pairs=[]
    for item in peaks:
        if isinstance(item,dict):
            x=next((item[k] for k in ('mz','m/z','m_z','mass','wavenumber','frequency') if k in item),None)
            y=next((item[k] for k in ('intensity','relative_intensity','abundance') if k in item),None)
        elif isinstance(item,(tuple,list)) and len(item)==2:x,y=item
        else:x,y=item,None
        if positive(x):
            positions.append(float(x))
            try:
                if y is not None and math.isfinite(float(y)) and float(y)>=0:pairs.append((float(x),float(y)))
            except (ValueError,TypeError):pass
    if len(pairs)==len(peaks) and len(pairs)>=2 and sum(y for x,y in pairs)>0:return 'numeric_position_intensity_pairs',len(pairs)
    if positions and len(positions)==len(peaks):return 'numeric_positions_only',len(positions)
    return 'mixed_or_text_peaks',len(positions)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--max-seconds',type=int,default=1800)
    args=parser.parse_args()
    if args.output.exists():print('Completed report exists; source remains unchanged');return
    started=time.monotonic();db=sqlite3.connect(args.database)
    # Rollback journals work on shared storage where WAL shared-memory mmap fails.
    db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA cache_size=-64000')
    db.execute('CREATE TABLE IF NOT EXISTS state (name TEXT PRIMARY KEY,value TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS structures (smiles TEXT PRIMARY KEY,records INTEGER,nmr INTEGER,ms INTEGER,ir INTEGER,raman INTEGER,mask INTEGER)')
    prior=db.execute("SELECT value FROM state WHERE name='progress'").fetchone()
    source={'path':str(args.source.resolve()),'bytes':args.source.stat().st_size,'mtime_ns':args.source.stat().st_mtime_ns}
    if prior:
        state=json.loads(prior[0]);assert state['source']==source,'Source changed'
    else:state={'source':source,'offset':0,'counts':{},'types':{},'year':{},'providers':{},'combinations':{},'quality':{},'examples':{}}
    counts=Counter(state['counts']);types=Counter(state['types']);year=Counter(state['year']);providers=Counter(state['providers']);combinations=Counter(state['combinations']);quality=Counter(state['quality']);examples=state['examples']
    pending={}
    def save(offset,done=False):
        db.executemany('INSERT INTO structures VALUES (?,?,?,?,?,?,?) ON CONFLICT(smiles) DO UPDATE SET records=records+excluded.records,nmr=nmr+excluded.nmr,ms=ms+excluded.ms,ir=ir+excluded.ir,raman=raman+excluded.raman,mask=mask|excluded.mask',[(smiles,*values) for smiles,values in pending.items()])
        pending.clear()
        state.update(offset=offset,done=done,counts=dict(counts),types=dict(types),year=dict(year),providers=dict(providers),combinations=dict(combinations),quality=dict(quality),examples=examples)
        db.execute("INSERT OR REPLACE INTO state VALUES ('progress',?)",(json.dumps(state),));db.commit()
    with args.source.open('rb') as stream:
        stream.seek(state['offset'])
        for line in stream:
            record=json.loads(line);meta=record.get('meta_info') or {};counts['source_documents']+=1
            year[str(meta.get('year','unknown'))]+=1;providers[str(meta.get('source','unknown'))]+=1
            for compound in record.get('compounds') or []:
                counts['compound_records']+=1
                smiles=compound.get('smiles_std') or compound.get('smiles')
                has_structure=isinstance(smiles,str) and bool(smiles.strip());counts['compound_records_with_structure_text']+=int(has_structure)
                families=Counter()
                for spectrum in compound.get('spectra') or []:
                    label=str(spectrum.get('spectrum_type') or 'Unspecified');category=family(label)
                    types[label]+=1;counts['spectral_entries']+=1;counts['entries:'+category]+=1;families[category]+=1
                    counts['entries_with_structure_text:'+category]+=int(has_structure)
                    if category=='NMR':
                        text=str(spectrum.get('chemical_shift') or '')
                        quality['NMR:nonempty_shift_text']+=int(bool(text.strip()))
                        quality['NMR:shift_text_contains_number']+=int(bool(re.search(r'\d',text)))
                        quality['NMR:solvent_present']+=int(bool(spectrum.get('solvent')))
                        match=re.search(r'\d+(?:\.\d+)?',str(spectrum.get('frequency') or ''))
                        quality['NMR:positive_frequency']+=int(bool(match) and float(match.group())>0)
                    elif category in ('MS','IR','Raman'):
                        kind,size=peak_kind(spectrum.get('peaks'),category)
                        quality[category+':'+kind]+=1
                        if category=='MS':
                            quality['MS:positive_measured_mz']+=int(positive(spectrum.get('measured_value')))
                            quality['MS:at_least_two_numeric_peaks']+=int(size>=2)
                            quality['MS:at_least_six_numeric_peaks']+=int(size>=6)
                            quality['MS:fragment_text_present']+=int(bool(spectrum.get('fragments') or spectrum.get('other_peaks')))
                            quality['MS:explicit_collision_energy']+=int(any(k in spectrum for k in ('collision_energy','collision energy','ce')))
                        elif size:quality[category+':numeric_peak_positions']+=size
                    if category not in examples and has_structure:
                        examples[category]={'source_document':meta.get('upstream_path'),'smiles':smiles,'spectrum':spectrum}
                combination='+'.join(k for k in ('NMR','MS','IR','Raman','Other') if families[k]) or 'No spectrum'
                combinations[combination]+=1
                if has_structure:
                    values=pending.setdefault(smiles,[0,0,0,0,0,0]);values[0]+=1
                    for index,category in enumerate(('NMR','MS','IR','Raman'),1):values[index]+=families[category]
                    values[5]|=sum((1<<i) for i,k in enumerate(('NMR','MS','IR','Raman')) if families[k])
            if counts['source_documents']%2000==0:
                save(stream.tell());print('OpenDataLab documents',counts['source_documents'],'compound records',counts['compound_records'],flush=True)
                if time.monotonic()-started>args.max_seconds:db.close();print('Saved checkpoint');return
        save(stream.tell(),True)
    digest=hashlib.sha256()
    with args.source.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):digest.update(block)
    identity_rows=db.execute('SELECT mask,count(*) FROM structures GROUP BY mask').fetchall()
    report={**state,'completed':True,'source_sha256':digest.hexdigest(),'provider':'OpenDataLab','version':'WanJuan MolSpectra v1.0.3',
        'unique_structure_texts':sum(n for mask,n in identity_rows),'unique_structure_texts_by_modality_mask':{str(mask):n for mask,n in identity_rows},
        'structure_identity_scope':'exact stored smiles_std or smiles text; validity and canonical identity are not inferred from this count',
        'quality_scope':'numeric field availability; does not establish extraction accuracy, instrument compatibility or experimental assignment correctness',
        'entry_count_scope':'spectral_entries counts every raw characterization object, including Other labels such as chromatography; family counts are reported separately',
        'nmr_nucleus_labels':nmr_nucleus_counts(state['types']),
        'nmr_nucleus_label_policy':'Explicit isotope labels and documented H/H1 or reversed aliases within the NMR/RMN/DEPT family; decoupling braces removed; unknown and multiple-nucleus labels retained separately. Raw labels remain in types.',
        'classification_policy':'NMR/RMN/DEPT; Raman; IR/FTIR/infrared; MS/mass; otherwise Other. Raw labels retained in types.',
        'elapsed_this_invocation_seconds':time.monotonic()-started}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');db.close();print('OpenDataLab census complete',flush=True)


if __name__=='__main__':main()
