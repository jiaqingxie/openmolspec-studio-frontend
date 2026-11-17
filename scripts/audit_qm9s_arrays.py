"""Validate both complete local QM9S broadened CSVs without guessing molecule IDs.

CSV indices are retained as processed row indices. The molecular mapping uses
separate identifiers; a row-order association is not inferred from equal sizes.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cache',type=Path,required=True)
    args=parser.parse_args()
    import numpy as np
    args.cache.mkdir(parents=True,exist_ok=True)
    report=json.loads(args.output.read_text()) if args.output.exists() else {
        'completed':False,'provider':'QM9S','domain':'computed',
        'source_url':'https://www.nature.com/articles/s43588-023-00550-y',
        'scope':'Complete local broadened IR/Raman numerical CSVs',
        'identity_alignment':'Processed CSV row indices are not asserted to be molecular mapping IDs',
        'channels':{}}
    for channel in ['ir','raman']:
        if channel in report['channels']:continue
        path=args.data/(channel+'_boraden.csv');counts=Counter();digest=hashlib.sha256();ids=set();good_ids=set();first=[];last=None
        with path.open('rb') as stream:
            raw=stream.readline();digest.update(raw);header=next(csv.reader([raw.decode()]))
            axis=np.array([float(value) for value in header[1:]])
            assert np.isfinite(axis).all() and (np.diff(axis)>0).all()
            for raw in stream:
                digest.update(raw)
                if not raw.strip():continue
                key,_,payload=raw.partition(b',');identifier=key.decode().strip('"')
                values=np.fromstring(payload.decode(),sep=',');counts['rows']+=1
                counts['duplicate_row_indices']+=int(identifier in ids);ids.add(identifier)
                valid=len(values)==len(axis) and bool(np.isfinite(values).all())
                nonconstant=valid and bool(np.ptp(values)>0)
                counts['finite_correct_length_rows']+=int(valid)
                counts['finite_nonconstant_rows']+=int(nonconstant)
                counts['constant_rows']+=int(valid and not nonconstant)
                counts['negative_value_rows']+=int(valid and bool((values<0).any()))
                if nonconstant:good_ids.add(identifier)
                if len(first)<3:first.append(identifier)
                last=identifier
                if counts['rows']%20000==0:print(channel,'numerical rows',counts['rows'],flush=True)
        report['channels'][channel]={'file':path.name,'sha256':digest.hexdigest(),'bytes':path.stat().st_size,
            'counts':dict(counts),'spectral_points':len(axis),'axis_min_cm1':float(axis[0]),'axis_max_cm1':float(axis[-1]),
            'first_row_indices':first,'last_row_index':last,'unique_processed_indices':len(ids)}
        (args.cache/(channel+'-indices.json')).write_text(json.dumps({'all':sorted(ids),'finite_nonconstant':sorted(good_ids)}))
        args.output.write_text(json.dumps(report,indent=2)+'\n')
    ir=json.loads((args.cache/'ir-indices.json').read_text());raman=json.loads((args.cache/'raman-indices.json').read_text())
    report['processed_row_index_overlap']={'shared_indices':len(set(ir['all'])&set(raman['all'])),
        'both_finite_nonconstant':len(set(ir['finite_nonconstant'])&set(raman['finite_nonconstant'])),
        'semantics':'Processed index overlap, not verification of shared molecular identity'}
    report['completed']=True
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:value['counts'] for key,value in report['channels'].items()}),flush=True)


if __name__=='__main__':main()
