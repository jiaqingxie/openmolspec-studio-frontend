"""Audit the exact selected retrieval records against the byte checkpoint limits."""
import argparse
import hashlib
import json
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--selection',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
selection=json.loads(args.selection.read_text())
report={'candidate_smiles_capacity_bytes':160,'spectral_source_capacity_tokens':512,
        'selection_sha256':hashlib.sha256(args.selection.read_bytes()).hexdigest(),'datasets':{}}
for name,rows in selection['datasets'].items():
    counts={'molecules':len(rows),'molecular_targets_exceed_capacity':sum(len(x['smiles'].encode())>160 for x in rows),'spectral_text_truncated':{}}
    for view,fields in [('h',['h_nmr']),('c',['c_nmr']),('hc',['h_nmr','c_nmr'])]:
        counts['spectral_text_truncated'][view]=sum(2+len(fields)+sum(len(' | '.join(f"{p.get('type','')}: {p.get('chemical_shift','')}" for p in row[f]).encode()) for f in fields)>512 for row in rows)
    report['datasets'][name]=counts
args.output.write_text(json.dumps(report,indent=2)+'\n')
