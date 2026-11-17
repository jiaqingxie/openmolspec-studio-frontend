"""Resumable full-file OpenDataLab/NMRexp census and standard-InChIKey overlap.

The prepared patent corpus retains standard InChI, whereas NMRexp identities are
generated from its released SMILES. This is identity overlap, not duplicate raw
spectra or a manual extraction-accuracy assessment. Source files are read-only.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time


def structure(smiles):
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog('rdApp.*')
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None or not mol.GetNumAtoms():
            return smiles, None, 0
        key = Chem.MolToInchiKey(mol)
        mask = sum(1 << i for i, number in enumerate((1,6,9,15,5,14))
                   if any(atom.GetAtomicNum() == number or (number == 1 and atom.GetTotalNumHs() > 0)
                          for atom in mol.GetAtoms()))
        return smiles, key or None, mask
    except Exception:
        return smiles, None, 0


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def present(value):
    return value is not None and not (isinstance(value, float) and math.isnan(value)) and str(value).strip().lower() not in ('','none','nan','not available')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--patent', type=Path, required=True)
    parser.add_argument('--nmrexp', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--batch-size', type=int, default=2000)
    parser.add_argument('--max-seconds', type=int, default=90)
    args = parser.parse_args()
    if args.output.exists():
        print('Completed report already exists; no source or result changed', flush=True)
        return
    from rdkit import Chem, RDLogger
    import pyarrow.parquet as pq
    RDLogger.DisableLog('rdApp.*')
    started = time.monotonic()
    con = sqlite3.connect(args.database)
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA cache_size=-64000')
    con.execute('CREATE TABLE IF NOT EXISTS state (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS molecules (identity TEXT PRIMARY KEY, patent INTEGER DEFAULT 0, nmrexp INTEGER DEFAULT 0, ph INTEGER DEFAULT 0, pc INTEGER DEFAULT 0, nh INTEGER DEFAULT 0, nc INTEGER DEFAULT 0, smiles TEXT)')
    con.execute('CREATE TABLE IF NOT EXISTS smiles_cache (smiles TEXT PRIMARY KEY, identity TEXT, nuclei INTEGER)')
    def get(name, default):
        row = con.execute('SELECT value FROM state WHERE name=?',(name,)).fetchone()
        return json.loads(row[0]) if row else default
    def put(name, value):
        con.execute('INSERT OR REPLACE INTO state VALUES (?,?)',(name,json.dumps(value)))
    inputs = [args.patent / f'{s}.jsonl' for s in ('train','val','test')] + [args.nmrexp]
    source_files = get('sources', None)
    if source_files is None:
        source_files = {}
        for path in inputs:
            print('Fingerprint',path.name,flush=True)
            source_files[str(path)]={'sha256':digest(path),'bytes':path.stat().st_size,'mtime_ns':path.stat().st_mtime_ns}
        put('sources',source_files);con.commit()
    for path in inputs:
        assert (path.stat().st_size,path.stat().st_mtime_ns) == (source_files[str(path)]['bytes'],source_files[str(path)]['mtime_ns']), f'Source changed: {path}'
    def checkpoint():
        con.commit()
        if time.monotonic()-started > args.max_seconds:
            print('Checkpoint saved; invoke the same command to continue',flush=True)
            con.close()
            return True
        return False
    for split in ('train','val','test'):
        progress = get('patent_'+split, {'rows':0,'done':False,'counts':{}})
        if progress['done']:
            continue
        counts=Counter(progress['counts']); batch=[]
        with (args.patent/f'{split}.jsonl').open() as stream:
            for index,line in enumerate(stream,1):
                if index <= progress['rows']:
                    continue
                row=json.loads(line); identity=Chem.InchiToInchiKey(row['inchi'])
                h,c=row.get('h_nmr',[]),row.get('c_nmr',[])
                counts.update({'records':1,'h_records':len(h),'c_records':len(c),
                    'H_only':int(bool(h) and not c),'C_only':int(bool(c) and not h),'H+C':int(bool(h) and bool(c)),
                    'patent_id_present':int(present(row.get('patent_id'))),'year_present':int(present(row.get('year'))),
                    'h_c_from_different_patents':int(bool(h) and bool(c) and row.get('h_provenance',{}).get('patent_id') != row.get('c_provenance',{}).get('patent_id'))})
                counts['provider:'+str(row.get('source'))]+=1
                for record in h+c:
                    counts['spectral_records_with_frequency']+=int(present(record.get('frequency')))
                    counts['spectral_records_with_structured_solvent']+=int(present(record.get('solvent')))
                if identity:
                    batch.append((identity,1,int(bool(h)),int(bool(c)),row['smiles']))
                else:
                    counts['invalid_stored_inchi']+=1
                if index % args.batch_size == 0:
                    con.executemany('INSERT INTO molecules(identity,patent,ph,pc,smiles) VALUES (?,?,?,?,?) ON CONFLICT(identity) DO UPDATE SET patent=patent+1,ph=max(ph,excluded.ph),pc=max(pc,excluded.pc)',batch)
                    put('patent_'+split,{'rows':index,'done':False,'counts':dict(counts)});batch=[]
                    if index % 100000 == 0: print('Patent',split,index,flush=True)
                    if checkpoint(): return
            con.executemany('INSERT INTO molecules(identity,patent,ph,pc,smiles) VALUES (?,?,?,?,?) ON CONFLICT(identity) DO UPDATE SET patent=patent+1,ph=max(ph,excluded.ph),pc=max(pc,excluded.pc)',batch)
        put('patent_'+split,{'rows':counts['records'],'done':True,'counts':dict(counts)});con.commit()
        print('Patent',split,'complete',counts['records'],flush=True)
    progress=get('nmrexp',{'rows':0,'done':False,'counts':{}})
    if not progress['done']:
        counts=Counter(progress['counts']);cursor=0
        columns=['SMILES','NMR_type','Filename','NMR_solvent','NMR_frequency']
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for record_batch in pq.ParquetFile(args.nmrexp).iter_batches(batch_size=args.batch_size,columns=columns):
                rows=record_batch.to_pylist(); cursor+=len(rows)
                if cursor <= progress['rows']: continue
                assert cursor-len(rows)==progress['rows'], 'Resume requires unchanged batch size'
                unique=list({row['SMILES'] for row in rows if isinstance(row['SMILES'],str)})
                cache={}
                for start in range(0,len(unique),500):
                    chunk=unique[start:start+500]
                    if chunk:
                        query='SELECT smiles,identity,nuclei FROM smiles_cache WHERE smiles IN ('+','.join('?'*len(chunk))+')'
                        cache.update({s:(key,mask) for s,key,mask in con.execute(query,chunk)})
                missing=[s for s in unique if s not in cache]
                resolved=list(pool.map(structure,missing,chunksize=100))
                con.executemany('INSERT OR IGNORE INTO smiles_cache VALUES (?,?,?)',resolved)
                cache.update({s:(key,mask) for s,key,mask in resolved})
                batch=[]
                for row in rows:
                    nucleus=str(row['NMR_type']).split()[0]
                    key,mask=cache.get(row['SMILES'],(None,0))
                    counts.update({'records':1,'nucleus:'+nucleus:1,'source_identifier_present':int(present(row['Filename'])),
                                   'solvent_present':int(present(row['NMR_solvent'])),'frequency_present':int(present(row['NMR_frequency']))})
                    if key:
                        batch.append((key,1,int(nucleus=='1H'),int(nucleus=='13C'),row['SMILES']))
                        nuclei=('1H','13C','19F','31P','11B','29Si')
                        if nucleus in nuclei and not mask & (1<<nuclei.index(nucleus)):
                            counts['nucleus_absent_from_structure']+=1
                    else: counts['invalid_structure_or_inchi']+=1
                con.executemany('INSERT INTO molecules(identity,nmrexp,nh,nc,smiles) VALUES (?,?,?,?,?) ON CONFLICT(identity) DO UPDATE SET nmrexp=nmrexp+1,nh=max(nh,excluded.nh),nc=max(nc,excluded.nc)',batch)
                progress={'rows':cursor,'done':False,'counts':dict(counts)};put('nmrexp',progress)
                if cursor % 20000 == 0: print('NMRexp',cursor,flush=True)
                if checkpoint(): return
        progress['done']=True;put('nmrexp',progress);con.commit()
    counts=Counter()
    for split in ('train','val','test'):counts.update(get('patent_'+split,{})['counts'])
    union,patent,nmrexp,overlap=con.execute('SELECT count(*),sum(patent>0),sum(nmrexp>0),sum(patent>0 AND nmrexp>0) FROM molecules').fetchone()
    report={'completed':True,'training_performed':False,'source_files':source_files,
        'identity_policy':'full standard-InChIKey; patent from stored standard InChI, NMRexp generated from released SMILES using RDKit',
        'scope':'complete local input files; molecular identity overlap, not identical spectral records or independent historical model evaluation',
        'patent':{'counts':dict(counts),'unique_standard_inchikey':patent,
                  'splits':{s:get('patent_'+s,{})['counts']['records'] for s in ('train','val','test')}},
        'nmrexp':{'counts':get('nmrexp',{})['counts'],'unique_standard_inchikey':nmrexp},
        'overlap':{'union':union,'intersection':overlap,'patent_only':patent-overlap,'nmrexp_only':nmrexp-overlap},
        'limitations':['Stored patent identities not all regenerated from SMILES in this pass','Distinct identity is not proof of a novel measurement','No manual extraction-accuracy claim','No inference of redistribution rights from local availability']}
    for label,a,h,c in [('patent','patent','ph','pc'),('nmrexp','nmrexp','nh','nc')]:
        report[label]['unique_identities_by_modality']={name:con.execute(f'SELECT count(*) FROM molecules WHERE {a}>0 AND {condition}').fetchone()[0]
            for name,condition in [('H',f'{h}>0'),('C',f'{c}>0'),('H+C',f'{h}>0 AND {c}>0')]}
    from rdkit import rdBase
    report['rdkit_version']=rdBase.rdkitVersion
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');con.close()
    print('Full corpus comparison complete',json.dumps(report['overlap']),flush=True)


if __name__=='__main__':main()
