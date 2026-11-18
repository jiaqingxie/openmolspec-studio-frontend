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
from io import TextIOWrapper
from itertools import islice
import json
import math
from pathlib import Path
import sqlite3
import tempfile
from zipfile import ZipFile


def sha256(path):
    """Compute the SHA-256 checksum of a file.

    Parameters
    ----------
    path : str or pathlib.Path
        File to read in binary mode.

    Returns
    -------
    str
        The 64-character hexadecimal digest.
    """
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def list_datasets():
    """List the datasets available through :func:`molspectra`.

    Returns
    -------
    list of dict
        Dataset cards containing ``name``, ``version``, ``domain``, ``format``,
        split filenames, source references and dataset statistics.

    Examples
    --------
    >>> names = [card['name'] for card in list_datasets()]
    >>> 'opendatalab_nmr' in names
    True
    """
    return json.loads(files('openmolspec').joinpath('assets/datasets.json').read_text())


def dataset_info(name):
    """Look up a dataset's format, files and source information.

    Parameters
    ----------
    name : str
        Registered dataset name, such as ``'opendatalab_nmr'``.

    Returns
    -------
    dict
        Dataset card for ``name``.

    Raises
    ------
    ValueError
        If the name is absent from :func:`list_datasets`.

    Examples
    --------
    >>> dataset_info('opendatalab_nmr')['domain']
    'experimental'
    """
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


def _hsqc_records(path):
    prefix = 'HSQC_Annotation_CrossChecked/'
    with ZipFile(path) as archive:
        with TextIOWrapper(archive.open(prefix + 'all_test_smiles.csv'), encoding='utf-8-sig', newline='') as stream:
            structures = list(csv.DictReader(stream))
        for structure in structures:
            source_id = structure['File_name']
            if Path(source_id).name != source_id or not source_id.endswith('.csv'):
                raise ValueError(f'Invalid HSQC annotation ID: {source_id}')
            assignments = []
            with TextIOWrapper(archive.open(prefix + 'Annotation/' + source_id), encoding='utf-8-sig', newline='') as stream:
                for row in csv.DictReader(stream):
                    carbon_index = float(row.get('c_idx', row.get('c idx')))
                    carbon_shift = float(row['C'])
                    proton_fields = [row.get('H 1', row.get('H1', '')), row.get('H 2', row.get('H2', ''))]
                    proton_shifts = list(dict.fromkeys(float(value) for value in proton_fields if value.strip()))
                    if not carbon_index.is_integer() or carbon_index < 0 or not proton_shifts or not all(
                            math.isfinite(value) for value in [carbon_shift, *proton_shifts]):
                        raise ValueError(f'Invalid HSQC annotation in {source_id}')
                    assignments.append({'carbon_atom_index': int(carbon_index), 'carbon_ppm': carbon_shift,
                                        'proton_ppm': proton_shifts})
            if not assignments:
                raise ValueError(f'Empty HSQC annotation in {source_id}')
            peaks = [[c, h] for c, h in dict.fromkeys((row['carbon_ppm'], h)
                      for row in assignments for h in row['proton_ppm'])]
            yield source_id, {'source_id': source_id, 'smiles': structure['SMILES'], 'modality': 'HSQC',
                              'hsqc_peaks': peaks, 'hsqc_assignments': assignments,
                              'units': ['13C ppm', '1H ppm'], 'atom_index_basis': 'Original SMILES, zero based'}


@dataclass(frozen=True)
class SpectraSplit:
    """A streaming view of one spectroscopy dataset split.

    Parameters
    ----------
    path : str or pathlib.Path
        JSONL, MassSpecGym CSV/TSV, openSpec LMDB, or TransPeakNet test ZIP file.
    role : {'train', 'val', 'test'}
        Split to read. ``'valid'`` and ``'validation'`` are aliases for ``'val'``.
    dataset : str
        Dataset name attached to each returned record.
    domain : {'experimental', 'computed'}
        Origin of the spectral measurements.
    format : str, default 'nmr_jsonl'
        Reader format: ``'nmr_jsonl'``, ``'jsonl'``, ``'massspecgym_csv'``,
        ``'massspecgym_tsv'``, ``'openspec_lmdb'`` or ``'transpeaknet_hsqc_zip'``.
    trusted : bool, default False
        Set to ``True`` when opening a trusted pickle-based LMDB.
    modalities : tuple of str, default ()
        Channels required in each selected record: ``'1H'``, ``'13C'``,
        ``'11B'``, ``'19F'``, ``'29Si'``, ``'31P'``, ``'IR'``, ``'Raman'``,
        ``'MS'``, ``'MS/MS'`` or ``'HSQC'``.
    limit : int or None, default None
        Maximum number of selected records.

    Yields
    ------
    dict
        Molecular and spectral fields plus ``_openmolspec`` metadata containing
        the split, dataset, domain, record locator and available channels.

    Examples
    --------
    >>> split = SpectraSplit('test.jsonl', 'test', 'my_nmr', 'experimental')
    >>> first_three = split.head(3)
    >>> hc = split.select(modalities=['1H', '13C'], limit=32)
    """
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
        if self.format not in ('nmr_jsonl', 'jsonl', 'massspecgym_csv', 'massspecgym_tsv', 'openspec_lmdb', 'transpeaknet_hsqc_zip'):
            raise ValueError(f'Unsupported format: {self.format}')
        if self.format == 'openspec_lmdb' and not self.trusted:
            raise ValueError('Legacy LMDB stores Python pickles; use trusted=True only for trusted files')
        if self.limit is not None and (isinstance(self.limit, bool) or not isinstance(self.limit, int) or self.limit < 1):
            raise ValueError('limit must be positive')
        if set(self.modalities) - {'1H', '13C', '11B', '19F', '29Si', '31P', 'IR', 'Raman', 'MS', 'MS/MS', 'HSQC'}:
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
        elif self.format in ('massspecgym_csv','massspecgym_tsv'):
            with self.path.open(encoding='utf-8', newline='') as stream:
                for number, row in enumerate(csv.DictReader(stream,delimiter='\t' if self.format=='massspecgym_tsv' else ','), 1):
                    row = dict(row)
                    if self.format=='massspecgym_tsv':
                        if _role(row['fold'])!=self.role:continue
                        mz=[float(v) for v in row['mzs'].split(',')]
                        intensity=[float(v) for v in row['intensities'].split(',')]
                        if len(mz)!=len(intensity):raise ValueError(f'Peak array mismatch at row {number}')
                        row['peaks']=list(map(list,zip(mz,intensity)))
                        row['instrument']=row.get('instrument_type')
                    else:row['peaks'] = ast.literal_eval(row['peaks'])
                    row['adduct'] = row.get('prec_type', row.get('adduct'))
                    yield number, row
        elif self.format == 'transpeaknet_hsqc_zip':
            yield from _hsqc_records(self.path)
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
        """Stream the selected molecular spectra in file order.

        Yields
        ------
        dict
            Original spectral fields plus normalized ``smiles`` and
            ``_openmolspec`` dataset, role, locator and channel metadata.
        """
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
                              ('nmr_c_shifts_ppm', '13C')]:
                if row.get(key) is not None and len(row[key]):
                    present.add(name)
            if row.get('peaks'):
                present.add('MS' if row.get('modality')=='MS' else 'MS/MS')
            if row.get('hsqc_peaks'):
                present.add('HSQC')
            if row.get('peaks_ppm') and row.get('nucleus') in {'1H','13C','11B','19F','29Si','31P'}:
                present.add(row['nucleus'])
            if row.get('wavenumber_cm1') and row.get('modality') in {'IR','Raman'}:
                present.add(row['modality'])
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
        """Read the first ``n`` selected records.

        Parameters
        ----------
        n : int, default 3
            Number of records to return; zero returns an empty list.

        Returns
        -------
        list of dict
            Up to ``n`` records in source-file order.
        """
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise ValueError('n must be a nonnegative integer')
        return list(islice(iter(self), n))

    def select(self, *, modalities=(), limit=None):
        """Create a view restricted to the requested spectral channels.

        Parameters
        ----------
        modalities : str or sequence of str, default ()
            Channels that must be present together in a record.
        limit : int or None, default None
            Maximum number of matching records to read.

        Returns
        -------
        SpectraSplit
            A new view with the combined channel filters and the original split.

        Examples
        --------
        >>> paired = split.select(modalities=['1H', '13C'])
        >>> examples = paired.head(5)
        """
        if isinstance(modalities, str):
            modalities = (modalities,)
        combined = tuple(sorted(set(self.modalities) | set(modalities)))
        bounded = min(self.limit, limit) if self.limit is not None and limit is not None else self.limit or limit
        return replace(self, modalities=combined, limit=bounded)

    def fingerprint(self):
        """Return file identity and view selection settings.

        Returns
        -------
        dict
            Path, SHA-256, role, dataset, domain, channel filters and row limit.
        """
        return {'path': str(self.path), 'sha256': sha256(self.path), 'role': self.role,
                'dataset': self.dataset, 'domain': self.domain,
                'selection': {'modalities': list(self.modalities), 'limit': self.limit}}


class MolecularSpectra:
    """A dataset card together with its train, validation and test views.

    Parameters
    ----------
    card : dict
        Dataset metadata, including the name, version and source information.
    splits : mapping of str to SpectraSplit
        Named split views, indexed by ``'train'``, ``'val'`` and ``'test'``.

    Examples
    --------
    >>> data = molspectra('opendatalab_nmr', root='data/nmr')
    >>> test = data['test']
    >>> record = test.head(1)[0]
    >>> print(record['smiles'])
    """
    def __init__(self, card, splits):
        self.card = dict(card)
        self._splits = dict(splits)

    def get_split(self):
        """Return the dataset's named split views.

        Returns
        -------
        dict of str to SpectraSplit
            Mapping from split names to streaming readers.
        """
        return dict(self._splits)

    def __getitem__(self, split):
        """Select a named dataset split with ``data[split]``.

        Parameters
        ----------
        split : {'train', 'val', 'validation', 'valid', 'test'}
            Requested split role; validation aliases normalize to ``'val'``.

        Returns
        -------
        SpectraSplit
            Streaming reader for the selected local file.

        Raises
        ------
        KeyError
            If the dataset has no file for the requested role.
        """
        return self._splits[_role(split)]

    def summary(self):
        """Describe the dataset card and locally available files.

        Returns
        -------
        dict
            Dataset card and each split's local path and file size.
        """
        return {'card': self.card, 'local_splits': {k: {'path': str(v.path), 'bytes': v.path.stat().st_size}
                                                  for k, v in self._splits.items()},
                'counts_note': 'Card counts refer to the audited source version; local files are not recounted here.'}

    def verify(self):
        """Verify local split files against the dataset card's SHA-256 values.

        Returns
        -------
        dict
            ``verified=True`` and the checksum of each split.

        Raises
        ------
        ValueError
            If a reference checksum is missing or a local file differs.
        """
        expected = self.card.get('reference_sha256', {})
        if any(k not in expected for k in self._splits):
            raise ValueError('No audited checksum for this dataset version; use explicit local provenance')
        result = {}
        for key, view in self._splits.items():
            actual = sha256(view.path)
            if actual != expected[key]:
                raise ValueError(f'{key} does not match the audited {self.card["version"]} version')
            result[key] = actual
        return {'verified': True, 'sha256': result, 'scope': 'SHA-256 identity of versioned local split files'}

    @classmethod
    def from_jsonl(cls, *, splits, name, domain, format='nmr_jsonl'):
        """Create a dataset from your own JSONL files.

        Parameters
        ----------
        splits : mapping of str to path-like
            JSONL files keyed by split, for example
            ``{'train': 'train.jsonl', 'val': 'val.jsonl'}``.
        name : str
            Name to attach to returned records.
        domain : {'experimental', 'computed'}
            Spectral data origin.
        format : {'nmr_jsonl', 'jsonl'}, default 'nmr_jsonl'
            Use ``'nmr_jsonl'`` for H/C peak-text records and ``'jsonl'`` for
            general molecular/spectral dictionaries.

        Returns
        -------
        MolecularSpectra
            Dataset with the supplied split files.

        Examples
        --------
        >>> custom = MolecularSpectra.from_jsonl(
        ...     splits={'train': 'train.jsonl', 'val': 'val.jsonl'},
        ...     name='my_measurements', domain='experimental')
        """
        if domain not in ('experimental', 'computed'):
            raise ValueError('Declare experimental or computed domain explicitly')
        normalized = {}
        for role, path in splits.items():
            role = _role(role)
            if role in normalized:
                raise ValueError(f'Duplicate split role: {role}')
            normalized[role] = SpectraSplit(path, role, name, domain,format=format)
        if not normalized:
            raise ValueError('At least one split is required')
        return cls({'name': name, 'domain': domain, 'origin': 'user_supplied',
                    'version': 'user_supplied', 'license': 'user_supplied'}, normalized)


def molspectra(name, *, root, trusted=False):
    """Load a registered molecular spectroscopy dataset.

    Parameters
    ----------
    name : str
        Name returned by :func:`list_datasets`.
    root : str or pathlib.Path
        Directory containing the dataset card's split files. Single-file
        datasets also accept the file path directly.
    trusted : bool, default False
        Enable the reader for a trusted pickle-based LMDB.

    Returns
    -------
    MolecularSpectra
        Dataset with lazy split readers.

    Raises
    ------
    FileNotFoundError
        If no expected split file exists under ``root``.
    ValueError
        If ``name`` is unknown.

    Examples
    --------
    >>> data = molspectra('opendatalab_nmr', root='data/nmr')
    >>> records = data['test'].select(modalities=['1H', '13C']).head(3)
    """
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

    Parameters
    ----------
    splits : mapping of str to iterable of dict
        Named molecular record streams, usually ``data.get_split()``.
    identity : {'connectivity', 'inchi'}, default 'connectivity'
        Compare the connectivity block or the full standard InChIKey.
        Connectivity grouping keeps stereoisomers together.
    check_nmr : bool, default False
        Validate each record's H/C peak representation while scanning.

    Returns
    -------
    dict
        Record and unique-identity counts, repeated identities, cross-split
        overlaps and molecular-identity policy. Standard InChIKeys are
        recomputed from SMILES.

    Examples
    --------
    >>> report = audit_splits(data.get_split(), identity='connectivity')
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
