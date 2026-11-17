"""Normalize every distinct OpenDataLab structure and assign fixed v1 groups.

The census index is the input, so repeated source records retain their counts.
An achiral scaffold hash defines an OpenMolSpec split without altering any
upstream benchmark or source file. Checkpoints make CPU batches resumable.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))


def normalize(row):
    smiles,records,nmr,ms,ir,raman,mask=row
    from rdkit import Chem,RDLogger
    from rdkit.Chem import Descriptors
    from openmolspec.split import molecular_group
    RDLogger.DisableLog('rdApp.*')
    try:
        key,group,mol=molecular_group(smiles)
        bucket=int.from_bytes(hashlib.sha256(('2026:'+group).encode()).digest()[:8],'big')/2**64
        split='train' if bucket<.8 else 'val' if bucket<.9 else 'test'
        return row,(key,mol.GetNumHeavyAtoms(),int(Descriptors.MolWt(mol)//50)*50,
                    ','.join(sorted({a.GetSymbol() for a in Chem.AddHs(mol).GetAtoms()})),group,split)
    except Exception:return row,None


def normalize_scaffold(group):
    from rdkit import RDLogger
    from openmolspec.split import scaffold_group_id
    RDLogger.DisableLog('rdApp.*')
    try:return group,scaffold_group_id(group)
    except ValueError:return group,None


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--database',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=2);parser.add_argument('--max-seconds',type=int,default=1200)
    args=parser.parse_args()
    if args.output.exists():print('Completed report exists');return
    db=sqlite3.connect(args.database);db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA cache_size=-64000')
    raw=json.loads(db.execute("select value from state where name='progress'").fetchone()[0]);assert raw['done']
    db.execute('CREATE TABLE IF NOT EXISTS normalized_v2 (identity TEXT PRIMARY KEY,records INTEGER,nmr INTEGER,ms INTEGER,ir INTEGER,raman INTEGER,mask INTEGER,heavy INTEGER,mw_bin INTEGER,elements TEXT,scaffold_group TEXT,split TEXT)')
    prior=db.execute("select value from state where name='normalization_v2'").fetchone()
    state=json.loads(prior[0]) if prior else {'after':'','processed':0,'invalid_structure_texts':0,'invalid_source_records':0}
    started=time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        while True:
            rows=db.execute('select smiles,records,nmr,ms,ir,raman,mask from structures where smiles>? order by smiles limit 2000',(state['after'],)).fetchall()
            if not rows:break
            pending=[]
            for row,result in pool.map(normalize,rows,chunksize=80):
                if result is None:state['invalid_structure_texts']+=1;state['invalid_source_records']+=row[1]
                else:
                    key,heavy,mw,elements,group,split=result
                    pending.append((key,*row[1:],heavy,mw,elements,group,split))
            db.executemany('INSERT INTO normalized_v2 VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(identity) DO UPDATE SET records=records+excluded.records,nmr=nmr+excluded.nmr,ms=ms+excluded.ms,ir=ir+excluded.ir,raman=raman+excluded.raman,mask=mask|excluded.mask',pending)
            state['processed']+=len(rows);state['after']=rows[-1][0]
            db.execute("INSERT OR REPLACE INTO state VALUES ('normalization_v2',?)",(json.dumps(state),));db.commit()
            if state['processed']%20000==0:print('Normalized structure texts',state['processed'],flush=True)
            if time.monotonic()-started>args.max_seconds:print('Checkpoint saved');return
    # Older resumable batches stored the normalized scaffold SMILES. Convert
    # those group identifiers without re-reading source records. Checkpoint
    # both expensive chemistry and database updates on shared storage.
    db.execute('CREATE INDEX IF NOT EXISTS normalized_v2_scaffolds ON normalized_v2(scaffold_group)')
    db.execute('CREATE TABLE IF NOT EXISTS scaffold_map_v2 (original TEXT PRIMARY KEY,canonical TEXT,applied INTEGER DEFAULT 0)')
    db.execute('CREATE TABLE IF NOT EXISTS excluded_scaffolds_v2 AS SELECT * FROM normalized_v2 WHERE 0')
    db.commit()
    finalized=db.execute("select value from state where name='partition_v2_finalized'").fetchone()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        groups=[] if finalized else [row[0] for row in db.execute("select distinct scaffold_group from normalized_v2 where scaffold_group like 'scaffold:%' and scaffold_group not in (select original from scaffold_map_v2)")]
        for start in range(0,len(groups),5000):
            mapped=list(pool.map(normalize_scaffold,groups[start:start+5000],chunksize=40))
            db.executemany('INSERT INTO scaffold_map_v2(original,canonical) VALUES (?,?)',mapped);db.commit()
            print('Checkpointed scaffold mappings',start+len(mapped),'of',len(groups),flush=True)
            if time.monotonic()-started>args.max_seconds:print('Checkpoint saved');return
    if not finalized:
        def role_for_group(group):
            bucket=int.from_bytes(hashlib.sha256(('2026:'+group).encode()).digest()[:8],'big')/2**64
            return 'train' if bucket<.8 else 'val' if bucket<.9 else 'test'
        db.create_function('oms_role',1,role_for_group,deterministic=True)
        print('Building final partition table atomically',flush=True)
        # A sequential table rebuild avoids millions of small updates on
        # shared storage. The old table remains available for local audit.
        with db:
            db.execute('INSERT INTO excluded_scaffolds_v2 SELECT n.* FROM normalized_v2 n JOIN scaffold_map_v2 m ON n.scaffold_group=m.original WHERE m.canonical IS NULL')
            db.execute('''CREATE TABLE normalized_v2_partitioned AS
                SELECT n.identity,n.records,n.nmr,n.ms,n.ir,n.raman,n.mask,
                       n.heavy,n.mw_bin,n.elements,
                       coalesce(m.canonical,n.scaffold_group) AS scaffold_group,
                       oms_role(coalesce(m.canonical,n.scaffold_group)) AS split
                FROM normalized_v2 n LEFT JOIN scaffold_map_v2 m
                     ON n.scaffold_group=m.original
                WHERE m.original IS NULL OR m.canonical IS NOT NULL''')
            db.execute('CREATE UNIQUE INDEX normalized_v2_partitioned_identity ON normalized_v2_partitioned(identity)')
            db.execute('ALTER TABLE normalized_v2 RENAME TO normalized_v2_before_bulk_partition')
            db.execute('ALTER TABLE normalized_v2_partitioned RENAME TO normalized_v2')
            db.execute("INSERT INTO state VALUES ('partition_v2_finalized','true')")
        print('Final partition table committed',flush=True)
    print('Checking connectivity-to-scaffold ambiguity',flush=True)
    db.execute('''CREATE TABLE IF NOT EXISTS benchmark_exclusions_v1 AS
        SELECT substr(identity,1,14) AS connectivity,count(*) AS identities,
               count(distinct scaffold_group) AS scaffold_groups
        FROM normalized_v2 GROUP BY substr(identity,1,14)
        HAVING count(distinct scaffold_group)>1''')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS benchmark_exclusions_connectivity ON benchmark_exclusions_v1(connectivity)');db.commit()
    eligible="mask>0 and substr(identity,1,14) not in (select connectivity from benchmark_exclusions_v1)"
    report={'completed':True,'provider':'OpenDataLab','version':'1.0','identity':'RDKit full standard-InChIKey regenerated from structure text','qualification':state,
        'unique_valid_identities':db.execute('select count(*) from normalized_v2').fetchone()[0],
        'identity_modality_masks':{str(mask):n for mask,n in db.execute('select mask,count(*) from normalized_v2 group by mask')},
        'heavy_atom_histogram_unique_identities':{str(k):n for k,n in db.execute('select heavy,count(*) from normalized_v2 group by heavy')},
        'molecular_weight_50Da_histogram_unique_identities':{str(k):n for k,n in db.execute('select mw_bin,count(*) from normalized_v2 group by mw_bin')},
        'benchmark_identity_scope':'Qualified identities with at least one NMR, MS, IR or Raman entry; connectivity groups with more than one normalized scaffold are excluded. Measurement presence is not task-specific eligibility.',
        'benchmark_identities':db.execute(f'select count(*) from normalized_v2 where {eligible}').fetchone()[0],
        'benchmark_scaffold_ambiguities':{'connectivities':db.execute('select count(*) from benchmark_exclusions_v1').fetchone()[0],
            'identities':db.execute('select coalesce(sum(identities),0) from benchmark_exclusions_v1').fetchone()[0],
            'reason':'Same connectivity produced different normalized scaffold groups; all its forms remain in qualified availability counts but are excluded from the fixed benchmark'},
        'fixed_scaffold_split':{role:{'identities':db.execute(f'select count(*) from normalized_v2 where {eligible} and split=?',(role,)).fetchone()[0],
                                          'source_records':db.execute(f'select sum(records) from normalized_v2 where {eligible} and split=?',(role,)).fetchone()[0]} for role in ['train','val','test']},
        'split_policy':{'method':'standard-InChI round-trip, achiral Bemis–Murcko scaffold connectivity key; acyclic connectivity fallback','seed':2026,'ratios':[.8,.1,.1],
                        'assignment':'Same algorithm as openmolspec.split.split_records; expected group proportions','scope':'New OpenMolSpec v1 identity partition; existing curated and external benchmark splits remain separately identified'},
        'valid_structure_spectral_entries':{k:db.execute(f'select sum({k}) from normalized_v2').fetchone()[0] for k in ['nmr','ms','ir','raman']}}
    from rdkit import rdBase
    report['rdkit_version']=rdBase.rdkitVersion
    census=json.loads((Path(__file__).resolve().parents[1]/'results/opendatalab_all_modalities_20261117.json').read_text())
    assert census['source']['bytes']==raw['source']['bytes']
    report['source']={'file':Path(raw['source']['path']).name,'bytes':raw['source']['bytes'],
                      'sha256':census['source_sha256'],'version':census['version']}
    report['database_table']='normalized_v2'
    report['benchmark_scaffold_ambiguities']['target_modality_identities']=sum(n for mask,n in report['identity_modality_masks'].items() if int(mask)>0)-report['benchmark_identities']
    report['qualification_scope']='Requires a standard molecular identity and a sanitizable standard scaffold identity (acyclic molecules use molecular connectivity). Failures can include parsable molecules with unsupported scaffold normalization.'
    report['legacy_scaffold_quarantine']={
        'identities':db.execute('select count(*) from excluded_scaffolds_v2').fetchone()[0],
        'source_records':db.execute('select coalesce(sum(records),0) from excluded_scaffolds_v2').fetchone()[0],
        'reason':'Source structure yielded an unsupported scaffold during migration; excluded from the benchmark, retained in the local quarantine table'}
    report['modality_distributions']={}
    for modality in ['nmr','ms','ir','raman']:
        where=f'where {modality}>0'
        elements=Counter()
        for text,n in db.execute(f'select elements,count(*) from normalized_v2 {where} group by elements'):
            for symbol in text.split(','):
                if symbol:elements[symbol]+=n
        report['modality_distributions'][modality]={
            'unique_identities':db.execute(f'select count(*) from normalized_v2 {where}').fetchone()[0],
            'heavy_atom_histogram_unique_identities':{str(k):n for k,n in db.execute(f'select heavy,count(*) from normalized_v2 {where} group by heavy')},
            'molecular_weight_50Da_histogram_unique_identities':{str(k):n for k,n in db.execute(f'select mw_bin,count(*) from normalized_v2 {where} group by mw_bin')},
            'element_presence_unique_identities':dict(elements)}
    report['identity_mask_semantics']='Union of modalities across every occurrence of the same full InChIKey, not necessarily the same source record or acquisition'
    args.output.write_text(json.dumps(report,indent=2)+'\n');db.close();print('Structure qualification complete',flush=True)


if __name__=='__main__':main()
