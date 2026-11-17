"""Count spectra and unique molecules within the same published dataset views."""
import csv
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def readonly(path):
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)


def main():
    import h5py
    import numpy as np
    import pyarrow.parquet as pq
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog('rdApp.*')
    data = ROOT.parents[1] / 'data'
    audit = ROOT / '.runtime/data-audit'
    result = {'completed': False, 'datasets': {}, 'nmrexp_nuclei': {}}
    views = result['datasets']
    original = json.loads((ROOT / 'documentation/assets/dataset_audit.json').read_text())
    for name in ['nmrspec_test', 'nmrgym_test', 'openspec_test']:
        row = next(row for row in original['datasets'] if row['id'] == name)
        spectra = row.get('h_spectrum_records', 0) + row.get('c_spectrum_records', 0)
        if name == 'openspec_test': spectra = row['ir_records'] + row['raman_records']
        views[name] = {'spectra': spectra, 'molecules': row['unique_canonical_isomeric_smiles'],
                       'identity_basis': 'canonical isomeric SMILES',
                       'channels': ['IR', 'Raman'] if name == 'openspec_test' else ['1H', '13C']}

    spectra = 0
    identities = set()
    with (audit / 'MassSpecGym1.5.tsv').open() as stream:
        for row in csv.DictReader(stream, delimiter='\t'):
            if row['simulation_challenge'] != 'True': continue
            spectra += 1
            identities.add(row['inchikey'])
    assert spectra == 119029 and '' not in identities
    views['massspecgym_1_5'] = {'spectra': spectra, 'molecules': len(identities),
        'identity_basis': 'dataset InChIKey', 'channels': ['MS/MS']}
    print('MassSpecGym', views['massspecgym_1_5'], flush=True)

    with readonly(audit / 'massbank-numeric.sqlite') as con:
        spectra, molecules = con.execute("SELECT count(*),count(DISTINCT identity) FROM records WHERE numeric_valid=1 AND identity!='' AND ms_type='MS2'").fetchone()
    assert spectra == 120512
    views['massbank_ms2'] = {'spectra': spectra, 'molecules': molecules,
        'identity_basis': 'standard InChIKey', 'channels': ['MS/MS']}

    with readonly(audit / 'openmolspec-corpus-comparison-20261117.sqlite') as con:
        cache = dict(con.execute('SELECT smiles,identity FROM smiles_cache'))
    hc = set()
    for nucleus in ['1H', '13C', '11B', '19F', '29Si', '31P']:
        path = data / 'NMRExp' / f'nmrexp_{nucleus}_usable.parquet'
        identities = set()
        spectra = 0
        for batch in pq.ParquetFile(path).iter_batches(columns=['SMILES'], batch_size=65536):
            for smiles in batch.column(0).to_pylist():
                if not isinstance(smiles, str): continue
                if smiles not in cache:
                    mol = Chem.MolFromSmiles(smiles)
                    cache[smiles] = Chem.MolToInchiKey(mol) if mol else None
                key = cache[smiles]
                if not key: continue
                identities.add(key)
                spectra += 1
        result['nmrexp_nuclei'][nucleus] = {'spectra': spectra, 'molecules': len(identities)}
        if nucleus in ['1H', '13C']: hc.update(identities)
        print('NMRexp', nucleus, spectra, len(identities), flush=True)
    views['nmrexp_hc'] = {'spectra': sum(result['nmrexp_nuclei'][n]['spectra'] for n in ['1H', '13C']),
        'molecules': len(hc), 'identity_basis': 'standard InChIKey', 'channels': ['1H', '13C']}
    del cache

    with readonly(audit / 'qme14s-alignment.sqlite') as con:
        identities = dict(con.execute('SELECT id,identity FROM records'))
    selected = set()
    pairs = 0
    base = data / 'QMe14S/processed'
    with h5py.File(base / 'ir_broaden_processed.h5') as ir, h5py.File(base / 'raman_broaden_processed.h5') as raman:
        assert len(ir['spectra']) == len(raman['spectra']) == len(identities)
        for start in range(0, len(identities), 2048):
            a = ir['spectra'][start:start + 2048]
            b = raman['spectra'][start:start + 2048]
            good = np.isfinite(a).all(axis=1) & (np.ptp(a, axis=1) > 0) & np.isfinite(b).all(axis=1) & (np.ptp(b, axis=1) > 0)
            for index in np.flatnonzero(good) + start:
                key = identities[int(index)]
                if key: selected.add(key); pairs += 1
    assert pairs == 184252
    views['qme14s_paired'] = {'spectra': pairs * 2, 'paired_records': pairs, 'molecules': len(selected),
        'identity_basis': 'standard InChIKey', 'channels': ['IR', 'Raman']}
    print('QMe14S', views['qme14s_paired'], flush=True)
    result['completed'] = True
    result['counting'] = 'Each spectral channel is counted separately; molecules are deduplicated within exactly the same selected records.'
    result['source_reports'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in [
        'documentation/assets/dataset_audit.json', 'results/external_data_census_20261117.json',
        'results/massbank_spectrum_qualification_20261117.json', 'results/qme14s_alignment_20261117.json']}
    (ROOT / 'documentation/assets/dataset-counts.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
