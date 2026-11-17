"""Export the fully qualified OpenDataLab v1 identity partition as hashed CSVs.

The manifest supplies identity-to-fold membership. It contains measurement
counts, not spectral arrays; original source records and acquisition conditions
remain necessary for each spectroscopy task.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--qualification',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=json.loads(args.qualification.read_text())
    if not report.get('completed') or report.get('database_table')!='normalized_v2':
        raise ValueError('A complete identity-normalized qualification report is required')
    db=sqlite3.connect('file:'+str(args.database.resolve())+'?mode=ro',uri=True)
    assert db.execute('select count(*) from normalized_v2').fetchone()[0]==report['unique_valid_identities']
    eligible='mask>0 and substr(identity,1,14) not in (select connectivity from benchmark_exclusions_v1)'
    for group in ['scaffold_group','substr(identity,1,14)']:
        conflict=db.execute(f'select {group} from normalized_v2 where {eligible} group by {group} having count(distinct split)>1 limit 1').fetchone()
        if conflict:raise ValueError('Cross-split group: '+str(conflict[0]))
    if args.output.exists():raise FileExistsError(args.output)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    files={}
    with tempfile.TemporaryDirectory(prefix='.oms-manifest-',dir=args.output.parent) as directory:
        staged=Path(directory)/'benchmark';staged.mkdir()
        for role in ['train','val','test']:
            path=staged/f'{role}.csv.gz';count=0
            with path.open('wb') as raw,gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as compressed,io.TextIOWrapper(compressed,encoding='utf-8',newline='') as stream:
                writer=csv.writer(stream,lineterminator='\n')
                writer.writerow(['standard_inchikey','scaffold_group_sha256','split','source_compound_records','nmr_entries','ms_entries','ir_entries','raman_entries'])
                for identity,group,records,nmr,ms,ir,raman in db.execute(f'select identity,scaffold_group,records,nmr,ms,ir,raman from normalized_v2 where {eligible} and split=? order by identity',(role,)):
                    writer.writerow([identity,hashlib.sha256(group.encode()).hexdigest(),role,records,nmr,ms,ir,raman]);count+=1
            from openmolspec.dataset import sha256
            files[role]={'file':path.name,'sha256':sha256(path),'bytes':path.stat().st_size,'identities':count}
        assert sum(row['identities'] for row in files.values())==report['benchmark_identities']
        manifest={'version':'1.0','provider':'OpenDataLab','domain':'experimental','scope':report['benchmark_identity_scope'],
                  'identity':report['identity'],'qualification_sha256':hashlib.sha256(args.qualification.read_bytes()).hexdigest(),
                  'policy':report['split_policy'],'files':files,'scaffold_groups_disjoint':True,'connectivity_groups_disjoint':True,
                  'contains_spectral_arrays':False,'notes':'Use original per-record spectra and acquisition conditions; presence counts do not establish task eligibility.'}
        (staged/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        staged.rename(args.output)
    db.close()
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
