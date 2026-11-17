"""Validate every local MassBank peak list and retain a snapshot fingerprint."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sqlite3


def parse(path, base):
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog('rdApp.*')
    content = path.read_bytes()
    text = content.decode(errors='replace')
    if not text.startswith('ACCESSION:'):
        return None
    fields = {}
    peaks = []
    reading = False
    malformed = False
    for line in text.splitlines():
        if line.startswith('PK$PEAK:'):
            reading = True
            continue
        if reading:
            if line.startswith('//'):
                reading = False
            elif line.strip():
                try:
                    mz, intensity = map(float, line.split()[:2])
                    peaks.append((mz, intensity))
                except ValueError:
                    malformed = True
        elif ': ' in line:
            key, value = line.split(': ', 1)
            if key == 'AC$MASS_SPECTROMETRY':
                key, _, value = value.partition(' ')
            fields[key] = value
    valid = bool(peaks) and not malformed and all(math.isfinite(mz) and mz > 0 and math.isfinite(v) and v >= 0 for mz, v in peaks) and any(v > 0 for _, v in peaks)
    mol = Chem.MolFromSmiles(fields.get('CH$SMILES', ''))
    identity = Chem.MolToInchiKey(mol) if mol and mol.GetNumAtoms() else ''
    heavy = mol.GetNumHeavyAtoms() if identity else -1
    try:
        declared_matches = int(fields.get('PK$NUM_PEAK', '-1')) == len(peaks)
    except ValueError:
        declared_matches = False
    return (str(path.relative_to(base)), hashlib.sha256(content).hexdigest(), fields.get('ACCESSION', ''), identity,
            fields.get('MS_TYPE', 'unknown'), int(valid), len(peaks), int(declared_matches), heavy,
            fields.get('ION_MODE', 'unknown'), fields.get('COLLISION_ENERGY', ''), fields.get('LICENSE', 'unknown'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        print('Completed report exists')
        return
    db = sqlite3.connect(args.database)
    db.execute('PRAGMA journal_mode=DELETE')
    db.execute('CREATE TABLE IF NOT EXISTS records (path TEXT PRIMARY KEY,sha256 TEXT,accession TEXT,identity TEXT,ms_type TEXT,numeric_valid INTEGER,peaks INTEGER,declared_matches INTEGER,heavy INTEGER,ion_mode TEXT,collision_energy TEXT,license TEXT)')
    done = {row[0] for row in db.execute('select path from records')}
    pending = []
    for path in sorted(args.data.rglob('*.txt')):
        if str(path.relative_to(args.data)) in done:
            continue
        record = parse(path, args.data)
        if record:
            pending.append(record)
        if len(pending) >= 2000:
            db.executemany('INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', pending)
            db.commit()
            done.update(row[0] for row in pending)
            pending.clear()
            print('MassBank numeric records', len(done), flush=True)
    db.executemany('INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', pending)
    db.commit()
    snapshot = hashlib.sha256()
    for path, digest in db.execute('select path,sha256 from records order by path'):
        snapshot.update((path + '\0' + digest + '\n').encode())
    count = lambda condition='1': db.execute('select count(*) from records where ' + condition).fetchone()[0]
    report = {'completed': True, 'provider': 'MassBank', 'domain': 'experimental',
              'source_url': 'https://github.com/MassBank/MassBank-data',
              'snapshot_sha256': snapshot.hexdigest(),
              'snapshot_hash_definition': 'SHA256 of sorted relative-path + NUL + record SHA256 + newline, UTF-8',
              'scope': 'Complete local snapshot; validates numeric peak lists, declared counts and structure parseability',
              'counts': {'spectral_records': count(), 'valid_numeric_spectra': count('numeric_valid=1'),
                         'valid_numeric_spectra_with_valid_structure': count("numeric_valid=1 and identity!=''"),
                         'valid_numeric_ms2_with_valid_structure': count("numeric_valid=1 and identity!='' and ms_type='MS2'"),
                         'declared_peak_count_disagreements': count('declared_matches=0'),
                         'unique_valid_standard_inchikeys': db.execute("select count(distinct identity) from records where identity!=''").fetchone()[0]},
              'ms_types': {key: n for key, n in db.execute('select ms_type,count(*) from records group by ms_type')},
              'ion_modes': {key: n for key, n in db.execute('select ion_mode,count(*) from records group by ion_mode')},
              'heavy_atom_histogram_spectral_records': {str(k): n for k, n in db.execute('select heavy,count(*) from records where heavy>=0 group by heavy')},
              'licenses': {key: n for key, n in db.execute('select license,count(*) from records group by license')}}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    db.close()
    print(json.dumps(report['counts']), flush=True)


if __name__ == '__main__':
    main()
