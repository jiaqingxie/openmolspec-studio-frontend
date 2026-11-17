"""Deterministic grouped splits for user-owned spectroscopy records.

Published benchmark views are read as supplied. This explicit export creates a
new dataset, preserving original split/source metadata and a hashed manifest.
"""
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile


def scaffold_group_id(scaffold):
    """Generate a connectivity-based key for a molecular scaffold.

    Parameters
    ----------
    scaffold : str
        Scaffold SMILES or a 14-letter standard InChIKey connectivity block.
        The optional prefix ``'scaffold:'`` is accepted.

    Returns
    -------
    str
        ``'scaffold:'`` followed by the normalized connectivity block.

    Raises
    ------
    ValueError
        If the scaffold cannot be assigned a standard molecular identity.
    """
    from rdkit import Chem
    if scaffold.startswith('scaffold:'):
        scaffold=scaffold[len('scaffold:'):]
    if re.fullmatch('[A-Z]{14}',scaffold):return 'scaffold:'+scaffold
    mol=Chem.MolFromSmiles(scaffold)
    key=Chem.MolToInchiKey(mol) if mol is not None else ''
    if not key:raise ValueError('Cannot assign a standard scaffold identity')
    return 'scaffold:'+key.split('-')[0]


def molecular_group(smiles, method='scaffold'):
    """Assign a standard molecular identity and a split-group key.

    Parameters
    ----------
    smiles : str
        Molecular structure to group.
    method : {'scaffold', 'random'}, default 'scaffold'
        Scaffold grouping uses an achiral Bemis–Murcko scaffold after standard
        InChI normalization. Random grouping uses molecular connectivity.

    Returns
    -------
    tuple of (str, str, rdkit.Chem.Mol)
        Full standard InChIKey, group key and parsed input molecule. Acyclic
        molecules use connectivity as their scaffold-group fallback.

    Raises
    ------
    ValueError
        If the structure, identity conversion or grouping method is invalid.
    """
    from rdkit import Chem
    from rdkit.Chem.Scaffolds import MurckoScaffold
    if method not in ('random','scaffold'):raise ValueError('method must be random or scaffold')
    mol=Chem.MolFromSmiles(smiles)
    if mol is None or not mol.GetNumAtoms():raise ValueError('Every split record requires a valid structure')
    inchi=Chem.MolToInchi(mol)
    key=Chem.InchiToInchiKey(inchi) if inchi else ''
    if not key:raise ValueError('Cannot assign a standard structural identity')
    connectivity=key.split('-')[0]
    if method=='random':return key,connectivity,mol
    canonical=Chem.MolFromInchi(inchi)
    if canonical is None:raise ValueError('Cannot restore the standard structural identity')
    scaffold=MurckoScaffold.MurckoScaffoldSmiles(mol=canonical,includeChirality=False)
    return key,(scaffold_group_id(scaffold) if scaffold else 'acyclic:'+connectivity),mol


def split_records(records, destination, *, method='scaffold', seed=2026,
                  ratios=(.8,.1,.1), source='user_supplied', domain='experimental'):
    """Export deterministic grouped training, validation and test files.

    Parameters
    ----------
    records : iterable of dict
        Spectroscopy records containing ``smiles`` or ``kekule_smiles``.
        Other molecular, spectral and acquisition fields are preserved.
    destination : str or pathlib.Path
        New directory for three JSONL files and ``split-manifest.json``.
    method : {'scaffold', 'random'}, default 'scaffold'
        Group molecules by achiral normalized scaffold or connectivity.
    seed : int, default 2026
        Seed incorporated into the deterministic SHA-256 group assignment.
    ratios : tuple of float, default (0.8, 0.1, 0.1)
        Training, validation and test proportions; nonnegative and summing to
        one. Complete groups are assigned together, so row counts vary.
    source : str, default 'user_supplied'
        Data-source label written to the manifest.
    domain : {'experimental', 'computed'}, default 'experimental'
        Origin of the spectra written to the manifest.

    Returns
    -------
    dict
        Manifest with per-file counts and SHA-256 values, grouping policy,
        source fingerprint, requested ratios, seed and original split counts.

    Raises
    ------
    FileExistsError
        If the destination already exists.
    ValueError
        If records or settings are invalid, or one connectivity receives
        conflicting scaffold roles. Exports are staged before publication.

    Examples
    --------
    >>> manifest = split_records(records, 'my-data', method='scaffold', seed=42)
    >>> manifest['groups_disjoint']
    True
    """
    from rdkit import rdBase
    if method not in ('random','scaffold'):raise ValueError('method must be random or scaffold')
    if domain not in ('experimental','computed'):raise ValueError('Declare experimental or computed domain')
    if len(ratios)!=3 or any(not math.isfinite(x) or x<0 for x in ratios) or not math.isclose(sum(ratios),1):
        raise ValueError('Supply three nonnegative ratios summing to one')
    if isinstance(seed,bool) or not isinstance(seed,int):raise ValueError('seed must be an integer')
    dest=Path(destination).expanduser().resolve()
    if dest.exists():raise FileExistsError(dest)
    dest.parent.mkdir(parents=True,exist_ok=True)
    roles=('train','val','test');counts=dict.fromkeys(roles,0);group_counts={k:set() for k in roles}
    original_roles={};source_digest=hashlib.sha256();connectivity_roles={}
    with tempfile.TemporaryDirectory(prefix='.oms-split-',dir=dest.parent) as temporary:
        staged=Path(temporary)/'dataset';staged.mkdir()
        with ExitStack() as stack:
            streams={k:stack.enter_context((staged/f'{k}.jsonl').open('w')) for k in roles}
            for record in records:
                row=dict(record)
                key,group,_=molecular_group(row.get('smiles') or row.get('kekule_smiles') or '',method)
                connectivity=key.split('-')[0]
                bucket=int.from_bytes(hashlib.sha256(f'{seed}:{group}'.encode()).digest()[:8],'big')/2**64
                role='train' if bucket<ratios[0] else 'val' if bucket<sum(ratios[:2]) else 'test'
                if connectivity_roles.setdefault(connectivity,role)!=role:
                    raise ValueError('One molecular connectivity has conflicting scaffold assignments; use method="random" or resolve the structural forms before scaffold splitting')
                original=row.pop('_openmolspec',None)
                if original:
                    row['_openmolspec_original']=original
                    old_role=original.get('split','unknown');original_roles[old_role]=original_roles.get(old_role,0)+1
                row['_openmolspec_split']={'method':method,'seed':seed,'role':role,'group':group,'connectivity':connectivity}
                source_digest.update(json.dumps(record,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()+b'\n')
                streams[role].write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');counts[role]+=1;group_counts[role].add(group)
        if not sum(counts.values()):raise ValueError('Cannot split an empty dataset')
        if any(group_counts[a]&group_counts[b] for a,b in [('train','val'),('train','test'),('val','test')]):raise RuntimeError('Group leakage')
        from .dataset import sha256
        files={role:{'file':f'{role}.jsonl','sha256':sha256(staged/f'{role}.jsonl'),'records':counts[role],'groups':len(group_counts[role])} for role in roles}
        manifest={'version':'1.0','source':source,'domain':domain,'method':method,'seed':seed,'requested_ratios':list(ratios),
            'identity_normalization':'standard InChI round-trip, achiral scaffold extraction, then scaffold connectivity key',
            'assignment':'SHA-256 group hash; whole groups; expected proportions, not exact counts','rdkit_version':rdBase.rdkitVersion,
            'source_stream_sha256':source_digest.hexdigest(),'original_split_record_counts':original_roles,'files':files,'groups_disjoint':True}
        (staged/'split-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');staged.rename(dest)
    return manifest
