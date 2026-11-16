"""Versioned dataset descriptions and lazy local spectroscopy readers.

No model imports, downloads or resplitting occur while opening a dataset.
"""
from __future__ import annotations

import ast
import csv
from contextlib import closing
from dataclasses import dataclass, replace
import hashlib
from importlib.resources import files
from itertools import islice
import json
from pathlib import Path
import sqlite3
import tempfile


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def list_datasets():
    """Return dataset cards; counts describe audited versions, not arbitrary files."""
    return json.loads(files('openmolspec').joinpath('assets/datasets.json').read_text())


def dataset_info(name):
    for card in list_datasets():
        if card['name'] == name:
            return card
    raise ValueError(f'Unknown dataset {name!r}; use list_datasets()')


def _role(split):
    split = {'validation': 'val', 'valid': 'val'}.get(split, split)
    if split not in ('train', 'val', 'test'):
        raise ValueError('Split must be train, val/validation, or test')
    return split


def _nmr(row):
    row = dict(row)
    for key, nucleus in [('h_nmr', '1H'), ('c_nmr', '13C')]:
        value = row.get(key) or []
        if isinstance(value, str):
            value = [{'type': nucleus + ' NMR', 'chemical_shift': value}]
        if not isinstance(value, list) or any(not isinstance(r, dict) for r in value):
            raise ValueError(f'{key} must contain NMR records')
        row[key] = value
    mask = row.get('modality_mask', [int(bool(row['h_nmr'])), int(bool(row['c_nmr']))])
    if not isinstance(mask, (list, tuple)) or len(mask) != 2 or any(x not in (0, 1) for x in mask):
        raise ValueError('modality_mask must be [has_H, has_C]')
    if not any(mask) or any(m and not row[k] for m, k in zip(mask, ('h_nmr', 'c_nmr'))):
        raise ValueError('Visible modalities require nonempty NMR records')
    row['modality_mask'] = list(mask)
    row['formula'] = row.get('formula') or row.get('molecular_formula') or ''
    return row


@dataclass(frozen=True)
class SpectraSplit:
    """A reusable lazy view. The role remains attached when filtering or taking rows."""
    path: Path
    role: str
    dataset: str
    domain: str
    format: str = 'nmr_jsonl'
    trusted: bool = False
    modalities: tuple[str, ...] = ()
    limit: int | None = None

    def __post_init__(self):
        object.__setattr__(self, 'path', Path(self.path).expanduser().resolve())
        object.__setattr__(self, 'role', _role(self.role))
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        if self.format not in ('nmr_jsonl', 'jsonl', 'massspecgym_csv', 'openspec_lmdb'):
            raise ValueError(f'Unsupported format: {self.format}')
        if self.format == 'openspec_lmdb' and not self.trusted:
            raise ValueError('Legacy LMDB stores Python pickles; use trusted=True only for trusted files')
        if self.limit is not None and (isinstance(self.limit, bool) or not isinstance(self.limit, int) or self.limit < 1):
            raise ValueError('limit must be positive')
        if set(self.modalities) - {'1H', '13C', 'IR', 'Raman', 'MS/MS'}:
            raise ValueError('Unknown modality')

    def _raw(self):
        if self.format in ('nmr_jsonl', 'jsonl'):
            with self.path.open(encoding='utf-8') as stream:
                for number, line in enumerate(stream, 1):
                    if line.strip():
                        try:
                            yield number, json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise ValueError(f'{self.path}:{number}: invalid JSON') from exc
        elif self.format == 'massspecgym_csv':
            with self.path.open(encoding='utf-8', newline='') as stream:
                for number, row in enumerate(csv.DictReader(stream), 1):
                    row = dict(row)
                    row['peaks'] = ast.literal_eval(row['peaks'])
                    row['adduct'] = row.get('prec_type', row.get('adduct'))
                    yield number, row
        else:
            import pickle
            from openmolspec_bench.data import readonly_lmdb
            environment = readonly_lmdb(self.path)
            try:
                with environment.begin() as txn:
                    for key, value in txn.cursor():
                        yield key.decode(), pickle.loads(value)
            finally:
                environment.close()

    def __iter__(self):
        accepted = 0
        for number, raw in self._raw():
            if not isinstance(raw, dict):
                raise ValueError(f'{self.path}:{number}: expected a record object')
            row = _nmr(raw) if self.format == 'nmr_jsonl' else dict(raw)
            row['smiles'] = row.get('smiles') or row.get('kekule_smiles') or ''
            if not isinstance(row['smiles'], str) or not row['smiles'].strip():
                raise ValueError(f'{self.path}:{number}: missing SMILES')
            present = set()
            if self.format == 'nmr_jsonl':
                present.update(n for n, m in zip(('1H', '13C'), row['modality_mask']) if m)
            for key, name in [('ir', 'IR'), ('raman', 'Raman'), ('nmr_h_shifts_ppm', '1H'),
                              ('nmr_c_shifts_ppm', '13C'), ('peaks', 'MS/MS')]:
                if row.get(key) is not None and len(row[key]):
                    present.add(name)
            if not set(self.modalities) <= present:
                continue
            row['_openmolspec'] = {'dataset': self.dataset, 'domain': self.domain, 'split': self.role,
                                   'record_locator': f'{self.path.name}:{number}',
                                   'modalities': sorted(present)}
            yield row
            accepted += 1
            if self.limit is not None and accepted >= self.limit:
                break

    def head(self, n=3):
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise ValueError('n must be a nonnegative integer')
        return list(islice(iter(self), n))

    def select(self, *, modalities=(), limit=None):
        """Filter by available modalities; preserve measurements, provenance and role."""
        if isinstance(modalities, str):
            modalities = (modalities,)
        combined = tuple(sorted(set(self.modalities) | set(modalities)))
        bounded = min(self.limit, limit) if self.limit is not None and limit is not None else self.limit or limit
        return replace(self, modalities=combined, limit=bounded)

    def fingerprint(self):
        return {'path': str(self.path), 'sha256': sha256(self.path), 'role': self.role,
                'dataset': self.dataset, 'domain': self.domain,
                'selection': {'modalities': list(self.modalities), 'limit': self.limit}}


class MolecularSpectra:
    def __init__(self, card, splits):
        self.card = dict(card)
        self._splits = dict(splits)

    def get_split(self):
        """Return existing split views; never randomly repartition a published test set."""
        return dict(self._splits)

    def __getitem__(self, split):
        return self._splits[_role(split)]

    def summary(self):
        return {'card': self.card, 'local_splits': {k: {'path': str(v.path), 'bytes': v.path.stat().st_size}
                                                  for k, v in self._splits.items()},
                'counts_note': 'Card counts refer to the audited source version; local files are not recounted here.'}

    def verify(self):
        """Hash local files against the packaged audited version; reject changed views."""
        expected = self.card.get('reference_sha256', {})
        if any(k not in expected for k in self._splits):
            raise ValueError('No audited checksum for this dataset version; use explicit local provenance')
        result = {}
        for key, view in self._splits.items():
            actual = sha256(view.path)
            if actual != expected[key]:
                raise ValueError(f'{key} does not match the audited {self.card["version"]} version')
            result[key] = actual
        return {'verified': True, 'sha256': result, 'scope': 'file identity, not an accuracy or license certification'}

    @classmethod
    def from_jsonl(cls, *, splits, name, domain):
        if domain not in ('experimental', 'computed'):
            raise ValueError('Declare experimental or computed domain explicitly')
        normalized = {}
        for role, path in splits.items():
            role = _role(role)
            if role in normalized:
                raise ValueError(f'Duplicate split role: {role}')
            normalized[role] = SpectraSplit(path, role, name, domain)
        if not normalized:
            raise ValueError('At least one split is required')
        return cls({'name': name, 'domain': domain, 'origin': 'user_supplied',
                    'version': 'user_supplied', 'license': 'user_supplied'}, normalized)


def molspectra(name, *, root, trusted=False):
    """Open a registered local dataset (directory of splits, or one test file)."""
    card = dataset_info(name)
    root = Path(root).expanduser().resolve()
    splits = {}
    for role, filename in card['files'].items():
        path = root if root.is_file() and len(card['files']) == 1 else root / filename
        if path.is_file():
            splits[role] = SpectraSplit(path, role, name, card['domain'], card['format'], trusted)
    if not splits:
        raise FileNotFoundError(f'No {name} files under {root}; expected {card["files"]}. No data are downloaded automatically.')
    return MolecularSpectra(card, splits)


def audit_splits(splits, *, identity='connectivity', check_nmr=False):
    """Scan supplied views for molecular overlap using a disk-backed identity index.

    RDKit standard InChIKeys are recomputed from SMILES. Connectivity grouping also
    keeps stereoisomers together. This does not audit unknown model training data.
    """
    from rdkit import Chem
    if identity not in ('connectivity', 'inchi'):
        raise ValueError('identity must be connectivity or inchi')
    views = dict(splits)
    if not views:
        raise ValueError('Supply at least one split')
    counts, duplicates, overlaps = {}, {}, []
    with tempfile.TemporaryDirectory(prefix='openmolspec-audit-') as temporary:
        with closing(sqlite3.connect(str(Path(temporary) / 'identity.sqlite'))) as db:
            db.execute('CREATE TABLE identities (identity TEXT, split TEXT, PRIMARY KEY(identity, split))')
            for label, view in views.items():
                counts[label] = duplicates[label] = 0
                for row in view:
                    mol = Chem.MolFromSmiles(row['smiles'])
                    if mol is None or not mol.GetNumAtoms():
                        raise ValueError(f'Invalid molecule in {label}')
                    if check_nmr:
                        from rdkit.Chem import rdMolDescriptors
                        if row.get('formula') != rdMolDescriptors.CalcMolFormula(mol):
                            raise ValueError(f'Formula mismatch in {label}')
                        elements = {a.GetSymbol() for a in Chem.AddHs(mol).GetAtoms()}
                        if any(flag and symbol not in elements for symbol, flag in zip(('H', 'C'), row['modality_mask'])):
                            raise ValueError(f'NMR nucleus is absent from structure in {label}')
                    key = Chem.MolToInchiKey(mol)
                    if not key:
                        raise ValueError(f'InChI conversion failed in {label}')
                    if identity == 'connectivity':
                        key = key.split('-')[0]
                    cursor = db.execute('INSERT OR IGNORE INTO identities VALUES (?, ?)', (key, label))
                    duplicates[label] += int(cursor.rowcount == 0)
                    counts[label] += 1
                db.commit()
            for i, left in enumerate(views):
                for right in list(views)[i + 1:]:
                    n = db.execute('SELECT COUNT(*) FROM identities a JOIN identities b ON a.identity=b.identity '
                                   'WHERE a.split=? AND b.split=?', (left, right)).fetchone()[0]
                    overlaps.append({'left': left, 'right': right, 'molecules': n})
    return {'identity': identity, 'nmr_chemistry_checked': check_nmr, 'records': counts, 'within_split_duplicates': duplicates,
            'overlaps': overlaps, 'disjoint': not any(r['molecules'] for r in overlaps),
            'scope': 'supplied views only; filtered/limited views do not establish full-dataset independence'}
