"""Index cleaned OpenDataLab JSONL files by structure and resolve experimental spectra.

Build with python -m online_api.spectrum_library --data-root DATA --index INDEX.
The small index stores byte offsets. Keep the cleaned files alongside a running API.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import tempfile

NUCLEI = ('1H', '13C', '11B', '19F', '29Si', '31P')
MODALITIES = (*NUCLEI, 'IR', 'Raman', 'MS')
FAMILIES = ('H+C', *MODALITIES[2:])


class LibraryUnavailable(Exception):
    """A missing or stale index cannot establish a library miss."""


def source_files(root):
    for family in FAMILIES:
        for split in ('train', 'val', 'test'):
            relative = (Path('opendatalab_nmr') / (split + '.jsonl') if family == 'H+C'
                        else Path('experimental') / f'{family}-{split}.jsonl')
            yield family, split, root / relative


def build_index(root, index):
    """Atomically replace the index only after all source files have been read."""
    index.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=index.parent) as temp:
        stage = Path(temp) / 'library.sqlite'
        db = sqlite3.connect(stage)
        try:
            db.executescript('''
                PRAGMA journal_mode=OFF;
                PRAGMA temp_store=MEMORY;
                CREATE TABLE sources (id INTEGER PRIMARY KEY, family TEXT, split TEXT,
                                      file TEXT, bytes INTEGER, mtime_ns INTEGER);
                CREATE TABLE records (identity TEXT, source INTEGER, position INTEGER);
            ''')
            total = 0
            for family, split, path in source_files(root):
                signature = path.stat()
                source = db.execute('INSERT INTO sources VALUES (NULL,?,?,?,?,?)',
                    (family, split, str(path.relative_to(root)), signature.st_size,
                     signature.st_mtime_ns)).lastrowid
                with path.open('rb') as stream:
                    def entries():
                        offset = 0
                        for line in stream:
                            yield json.loads(line)['standard_inchikey'], source, offset
                            offset += len(line)
                    total += db.executemany('INSERT INTO records VALUES (?,?,?)', entries()).rowcount
                if path.stat().st_mtime_ns != signature.st_mtime_ns:
                    raise LibraryUnavailable('A library file changed during indexing.')
            db.execute('CREATE INDEX records_by_molecule ON records(identity,source)')
            db.commit()
        finally:
            db.close()
        stage.replace(index)
    return total


def canonical(smiles):
    from rdkit import Chem
    if not isinstance(smiles, str) or not 0 < len(smiles.strip()) <= 256:
        raise ValueError('Enter a SMILES of 1–256 characters.')
    if any(c.isspace() for c in smiles.strip()) or '|' in smiles:
        raise ValueError('Enter a single SMILES without a name or CXSMILES annotation.')
    mol = Chem.MolFromSmiles(smiles.strip())
    if mol is None or not mol.GetNumAtoms():
        raise ValueError('Invalid SMILES.')
    # Atom-map labels are not part of molecular identity.
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(mol, isomericSmiles=True), Chem.MolToInchiKey(mol)


def spectrum(row, modality):
    if modality in ('1H', '13C'):
        prefix = 'h' if modality == '1H' else 'c'
        peaks = row.get(prefix + '_peaks_ppm')
        conditions = [{k: rec[k] for k in ('solvent', 'frequency', 'source_line')
                       if rec.get(k) is not None} for rec in row.get(prefix + '_nmr', [])]
        origin = row.get(prefix + '_provenance') or {}
        return {'peaks': peaks, 'units': 'ppm', 'conditions': conditions,
                'source': origin.get('source') or row.get('source'), 'source_id': origin.get('patent_id') or row.get('patent_id')}
    field = 'peaks' if modality == 'MS' else 'wavenumber_cm1' if modality in ('IR', 'Raman') else 'peaks_ppm'
    record = {k: row[k] for k in ('solvent', 'frequency', 'intensities') if row.get(k) is not None}
    return {**record, 'source': row.get('source'), 'source_id': row.get('source_document'),
            'peaks': row.get(field), 'units': 'm/z' if modality == 'MS' else 'cm⁻¹' if modality in ('IR', 'Raman') else 'ppm'}


def lookup(root, index, smiles, modality, limit=12):
    if modality not in MODALITIES:
        raise ValueError('Choose a supported modality.')
    normalized, key = canonical(smiles)
    family = 'H+C' if modality in ('1H', '13C') else modality
    try:
        db = sqlite3.connect(index.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            sources = db.execute('SELECT id,split,file,bytes,mtime_ns FROM sources WHERE family=?', (family,)).fetchall()
            if len(sources) != 3:
                raise LibraryUnavailable('Incomplete experimental index.')
            records, count = [], 0
            for source, split, relative, size, mtime_ns in sources:
                path = root / relative
                stat = path.stat()
                if (stat.st_size, stat.st_mtime_ns) != (size, mtime_ns):
                    raise LibraryUnavailable('Experimental index needs rebuilding.')
                offsets = db.execute('SELECT position FROM records WHERE identity=? AND source=?', (key, source))
                with path.open('rb') as stream:
                    for (offset,) in offsets:
                        stream.seek(offset)
                        row = json.loads(stream.readline())
                        if row['standard_inchikey'] != key:
                            raise LibraryUnavailable('Experimental index needs rebuilding.')
                        signal = spectrum(row, modality)
                        actual = row.get({'1H':'h_smiles','13C':'c_smiles'}.get(modality)) or row['smiles']
                        # The standard InChI key alone can merge tautomers. Compare exact stereochemical SMILES.
                        if not signal['peaks'] or canonical_source(actual) != normalized:
                            continue
                        count += 1
                        if len(records) < limit:
                            records.append({**signal, 'split': split, 'smiles': normalized, 'modality': modality})
        finally:
            db.close()
    except (OSError, sqlite3.Error) as e:
        raise LibraryUnavailable('Experimental index or its source files are unavailable.') from e
    return {'canonical_smiles': normalized, 'modality': modality, 'match_count': count,
            'records': records, 'collection': 'OpenDataLab cleaned train/val/test'}


def canonical_source(smiles):
    from rdkit import Chem
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(mol, isomericSmiles=True)


def resolve(service, payload, client):
    if not isinstance(payload, dict):
        raise ValueError('Send an object containing smiles and modality.')
    modality = payload.get('modality')
    result = lookup(service.args.spectra_data, service.args.spectra_index, payload.get('smiles'), modality)
    if result['match_count']:
        return {**result, 'origin': 'experimental'}, 200
    if modality == 'MS':
        return {**result, 'origin': 'missing', 'reason': 'MS/MS prediction requires acquisition conditions.'}, 200
    task = 'nmr.forward.' + modality if modality in NUCLEI else 'vibrational.forward'
    if task not in service.enabled_tasks:
        return {**result, 'origin': 'missing', 'reason': 'The corresponding predictor is unavailable.'}, 200
    run = service.submit({'kind':'tool', 'task':task, 'inputs':{'smiles':result['canonical_smiles']}}, client)
    return {**result, 'origin':'prediction', 'task':task, 'run':run}, 202


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--index', type=Path, required=True)
    args = parser.parse_args()
    print('Indexed', build_index(args.data_root, args.index), 'cleaned records.')


if __name__ == '__main__':
    main()
