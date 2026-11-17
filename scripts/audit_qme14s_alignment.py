"""Audit all QMe14S filename identities against both processed spectral arrays.

Raw 3500-point spectra are compared after linear interpolation on an explicitly
stated 500–4000 cm-1 grid. This numerical consistency test checks the proposed
filename-id → HDF5-row mapping; it does not recover undocumented processing code.
SQLite checkpoints avoid repeating a full raw-file scan after interruption.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import time


def read_pair(item):
    base, index = item
    from rdkit import Chem, RDLogger
    from rdkit.Chem import Descriptors
    import numpy as np
    RDLogger.DisableLog('rdApp.*')
    spectra = []
    smiles = []
    hashes = []
    for channel in ['IR', 'Raman']:
        content = (base / (channel + '_broaden') / f'{channel}_{index:06d}.csv').read_bytes()
        lines = content.decode().splitlines()
        smiles.append(lines[0].strip())
        spectra.append(np.fromstring(next(line for line in reversed(lines) if line.strip()), sep=','))
        hashes.append(hashlib.sha256(content).hexdigest())
    mol = Chem.MolFromSmiles(smiles[0])
    identity = Chem.MolToInchiKey(mol) if mol else ''
    heavy = mol.GetNumHeavyAtoms() if mol else -1
    mw = int(Descriptors.MolWt(mol) // 50) * 50 if mol else -1
    elements = ','.join(sorted({a.GetSymbol() for a in Chem.AddHs(mol).GetAtoms()})) if mol else ''
    return (index, identity, heavy, mw, elements, int(smiles[0] == smiles[1]), *hashes), spectra


def paired_array_quality(base):
    import h5py
    import numpy as np
    counts=Counter()
    with h5py.File(base/'processed/ir_broaden_processed.h5') as ir,h5py.File(base/'processed/raman_broaden_processed.h5') as raman:
        assert len(ir['spectra'])==len(raman['spectra'])
        for start in range(0,len(ir['spectra']),2048):
            a=ir['spectra'][start:start+2048];b=raman['spectra'][start:start+2048]
            ir_good=np.isfinite(a).all(axis=1)&(np.ptp(a,axis=1)>0)
            raman_good=np.isfinite(b).all(axis=1)&(np.ptp(b,axis=1)>0)
            counts['ir_finite_nonconstant_rows']+=int(ir_good.sum())
            counts['raman_finite_nonconstant_rows']+=int(raman_good.sum())
            counts['both_finite_nonconstant_rows']+=int((ir_good&raman_good).sum())
            counts['ir_only_finite_nonconstant_rows']+=int((ir_good&~raman_good).sum())
            counts['raman_only_finite_nonconstant_rows']+=int((raman_good&~ir_good).sum())
            counts['neither_finite_nonconstant_rows']+=int((~ir_good&~raman_good).sum())
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--max-seconds', type=int, default=1200)
    args = parser.parse_args()
    if args.output.exists():
        report=json.loads(args.output.read_text())
        if 'paired_array_quality' not in report:
            report['paired_array_quality']=paired_array_quality(args.data)
            args.output.write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report['paired_array_quality']))
        print('Completed report exists')
        return
    import h5py
    import numpy as np
    from rdkit import rdBase
    db = sqlite3.connect(args.database)
    db.execute('PRAGMA journal_mode=DELETE')
    db.execute('CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY,identity TEXT,heavy INTEGER,mw_bin INTEGER,elements TEXT,matched_smiles INTEGER,ir_sha256 TEXT,raman_sha256 TEXT,ir_relative_error REAL,raman_relative_error REAL)')
    last = db.execute('select max(id) from records').fetchone()[0]
    start_index = 0 if last is None else last + 1
    started = time.monotonic()
    with h5py.File(args.data / 'processed/ir_broaden_processed.h5') as ir, h5py.File(args.data / 'processed/raman_broaden_processed.h5') as raman, ThreadPoolExecutor(max_workers=args.workers) as pool:
        assert len(ir['spectra']) == len(raman['spectra'])
        total = len(ir['spectra'])
        axis = ir['x_axis'][:]
        assert np.array_equal(axis, raman['x_axis'][:])
        for start in range(start_index, total, 256):
            stop = min(start + 256, total)
            blocks = [ir['spectra'][start:stop], raman['spectra'][start:stop]]
            pending = []
            for row, spectra in pool.map(read_pair, ((args.data, i) for i in range(start, stop))):
                errors = []
                for channel, raw in enumerate(spectra):
                    expected = np.interp(axis, np.linspace(500, 4000, len(raw)), raw)
                    observed = blocks[channel][row[0] - start]
                    error = float(np.max(np.abs(expected - observed)) / max(float(np.max(np.abs(expected))), 1e-12))
                    if not np.isfinite(error):
                        raise ValueError(f'Nonfinite spectrum at row {row[0]}')
                    errors.append(error)
                pending.append((*row, *errors))
            db.executemany('INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?)', pending)
            db.commit()
            if stop % 4096 == 0 or stop == total:
                print('QMe14S paired identities and arrays', stop, '/', total, flush=True)
            if time.monotonic() - started > args.max_seconds:
                print('Checkpoint saved', flush=True)
                return
    threshold = 2e-3
    counts = {'rows': total, 'valid_identity_rows': db.execute("select count(*) from records where identity!=''").fetchone()[0],
              'unique_standard_inchikeys': db.execute("select count(distinct identity) from records where identity!=''").fetchone()[0],
              'ir_raman_structure_text_disagreements': db.execute('select count(*) from records where matched_smiles=0').fetchone()[0]}
    for channel in ['ir', 'raman']:
        counts[channel + '_interpolation_disagreements'] = db.execute(f'select count(*) from records where {channel}_relative_error>?', (threshold,)).fetchone()[0]
    histogram = lambda field: {str(k): n for k, n in db.execute(f'select {field},count(*) from records group by {field}')}
    elements = Counter()
    for text, n in db.execute('select elements,count(*) from records group by elements'):
        for element in text.split(','):
            if element:
                elements[element] += n
    report = {'completed': True, 'provider': 'QMe14S', 'domain': 'computed', 'counts': counts,
              'paired_array_quality':paired_array_quality(args.data),
              'source_url': 'https://arxiv.org/abs/2501.18876', 'rdkit_version': rdBase.rdkitVersion,
              'scope': 'All local IR/Raman raw files and both complete processed HDF5 arrays',
              'alignment': {'proposed_mapping': 'zero-padded raw filename integer = HDF5 row index',
                            'check': 'raw spectrum linearly interpolated from an assumed uniform 500–4000 cm-1 grid',
                            'relative_max_absolute_error_threshold': threshold,
                            'interpretation': 'Numerical mapping consistency under the explicit grid assumption; processing code is not attested'},
              'heavy_atom_histogram_molecular_records': histogram('heavy'),
              'molecular_weight_50Da_histogram_molecular_records': histogram('mw_bin'),
              'element_presence_molecular_records': dict(elements)}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    db.close()
    print(json.dumps(counts), flush=True)


if __name__ == '__main__':
    main()
