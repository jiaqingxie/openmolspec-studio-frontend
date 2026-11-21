"""Use an installed TransPeakNet checkpoint to map HSQC peaks to carbon sites."""

import json
from pathlib import Path
import sys

import numpy as np
from rdkit import Chem
import torch

from openmolspec_bench.transpeaknet import (
    CHECKPOINT_SHA256, SOLVENT_CLASS, assign_peaks, load_model, peak_list, predict_sites,
)


def evaluate(payload):
    source = Path(payload['source']).resolve()
    smiles = payload.get('smiles', '')
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None or len(Chem.GetMolFrags(molecule)) != 1:
        raise ValueError('Supply the SMILES of one valid connected molecule')
    molecule = Chem.AddHs(molecule)
    if molecule.GetNumAtoms() > 180:
        raise ValueError('The public HSQC tool supports up to 180 atoms including hydrogen')
    if not any(atom.GetAtomicNum() == 6 and any(h.GetAtomicNum() == 1 for h in atom.GetNeighbors())
               for atom in molecule.GetAtoms()):
        raise ValueError('This structure has no protonated carbon for an HSQC match')
    solvent = payload.get('solvent')
    if solvent not in SOLVENT_CLASS:
        raise ValueError('Choose one of the supported solvent classes')

    torch.set_num_threads(2)
    model = load_model(source)
    expected, atom_ids = peak_list(molecule, *predict_sites(model, molecule, solvent))
    measured = np.empty((0, 2))
    matches, unmatched = [], []
    if 'hsqc_peaks' in payload:
        measured = np.asarray(payload['hsqc_peaks'], dtype=float)
        if measured.ndim != 2 or measured.shape[1] != 2 or not 1 <= len(measured) <= 256 or not np.isfinite(measured).all():
            raise ValueError('Supply 1–256 measured [13C ppm, 1H ppm] cross-peaks')
        matches, unmatched = assign_peaks(measured, expected, atom_ids)
    for index, atom in enumerate(molecule.GetAtoms()):
        atom.SetAtomMapNum(index + 1)
    return {'model': 'TransPeakNet', 'checkpoint_sha256': CHECKPOINT_SHA256, 'solvent': solvent, 'smiles': smiles,
            'mapped_smiles': Chem.MolToSmiles(molecule, canonical=False),
            'atom_index_basis': 'RDKit AddHs on input SMILES, zero based. SMILES map labels are index + 1.',
            'matcher': 'One-to-one minimum scaled H/C deviation with unmatched slots (8 ppm C, 0.65 ppm H).',
            'unit': ['13C ppm', '1H ppm'], 'hsqc_measured': measured.tolist(),
            'hsqc_predicted': [{'carbon_atom_index': i, 'ppm': pair.tolist()} for i, pair in zip(atom_ids, expected)],
            'hsqc_assignments': matches, 'unmatched_peak_indices': unmatched}


if __name__ == '__main__':
    result = evaluate(json.load(sys.stdin))
    print('OMS_RESULT_V1:' + json.dumps(result, allow_nan=False), flush=True)
