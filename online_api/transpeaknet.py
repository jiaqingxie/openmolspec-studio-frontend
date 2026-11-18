"""Use an installed TransPeakNet checkpoint to map HSQC peaks to carbon sites."""

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from rdkit import Chem
from scipy.optimize import linear_sum_assignment
import torch
from torch_geometric.data import Batch, Data


SOLVENT_CLASS = {'CDCl3': 0, 'DMSO-d6': 1, 'acetone-d6': 2, 'acid': 3,
                 'C6D6': 4, 'CD3OD': 5, 'pyridine-d5': 6, 'D2O': 7, 'unknown': 8}
CHECKPOINT_SHA256 = 'ff72d33b422dee68b8f359536079b25bf165e81d363652308da65ecd89ed2523'


def graph(molecule, solvent):
    # Match the atom and directed bond indices used by the released checkpoint.
    chirality = (Chem.ChiralType.CHI_UNSPECIFIED, Chem.ChiralType.CHI_TETRAHEDRAL_CW,
                 Chem.ChiralType.CHI_TETRAHEDRAL_CCW)
    hybridization = (Chem.HybridizationType.S, Chem.HybridizationType.SP,
                     Chem.HybridizationType.SP2, Chem.HybridizationType.SP3,
                     Chem.HybridizationType.SP3D, Chem.HybridizationType.SP3D2,
                     Chem.HybridizationType.UNSPECIFIED)
    bond_types = (Chem.BondType.SINGLE, Chem.BondType.DOUBLE, Chem.BondType.TRIPLE, Chem.BondType.AROMATIC)
    bond_directions = (Chem.BondDir.NONE, Chem.BondDir.ENDUPRIGHT, Chem.BondDir.ENDDOWNRIGHT)
    try:
        atoms = [[atom.GetAtomicNum() - 1, chirality.index(atom.GetChiralTag()),
                  hybridization.index(atom.GetHybridization())] for atom in molecule.GetAtoms()]
        edges, attributes = [], []
        for bond in molecule.GetBonds():
            i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            edges.extend(((i, j), (j, i)))
            attributes.extend([[bond_types.index(bond.GetBondType()), bond_directions.index(bond.GetBondDir())]] * 2)
    except ValueError as error:
        raise ValueError('The released TransPeakNet graph encoder does not support this atom or bond type') from error
    if any(not 0 <= atom[0] < 118 for atom in atoms):
        raise ValueError('Use explicit elements in the input structure')
    return Batch.from_data_list([Data(x=torch.tensor(atoms), edge_index=torch.tensor(edges).T.contiguous(),
        edge_attr=torch.tensor(attributes), has_h=True, solvent_class=torch.tensor([SOLVENT_CLASS[solvent]]))])


def assign_peaks(measured, expected, atom_ids):
    # One model site per observed cross-peak. Unmatched peaks stay visible.
    # The window is a website matching rule, independent of the author's reported accuracy.
    deltas = (measured[:, None, :] - expected[None, :, :]) / np.array([8., .65])
    distance = np.linalg.norm(deltas, axis=2)
    cost = np.concatenate([np.where(distance <= 1, distance, np.inf),
                           np.full((len(measured), len(measured)), 1.001)], axis=1)
    rows, columns = linear_sum_assignment(cost)
    matches = []
    for row, col in zip(rows, columns):
        if col < len(expected):
            matches.append({'peak_index': int(row), 'carbon_atom_index': atom_ids[col],
                            'measured_ppm': measured[row].tolist(), 'predicted_ppm': expected[col].tolist(),
                            'absolute_error_ppm': np.abs(measured[row] - expected[col]).tolist()})
    return matches, [int(row) for row, col in zip(rows, columns) if col >= len(expected)]


def evaluate(payload):
    source = Path(payload['source']).resolve()
    checkpoint = source / 'ckpt/model_2dnmr.pt'
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    if digest != CHECKPOINT_SHA256:
        raise ValueError('Checkpoint digest differs from the verified author release')
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

    sys.path.insert(0, str(source))
    from GraphModel.GNN_2d_hsolvent import GNNNodeEncoder, NodeEncodeInterface

    torch.set_num_threads(2)
    encoder = GNNNodeEncoder(5, 512, JK='last', gnn_type='gin', aggr='add')
    model = NodeEncodeInterface(encoder, hidden_channels=512, c_out_hidden=[128, 64],
                                h_out_hidden=[128, 64], solvent_emb_dim=32, h_out_channels=2, use_solvent=True)
    model.load_state_dict(torch.load(checkpoint, map_location='cpu', weights_only=True), strict=True)
    model.eval()
    with torch.inference_mode():
        (carbon, proton), order = model(graph(molecule, solvent))
    expected, atom_ids = [], []
    for c, h, index in zip(carbon.flatten().tolist(), proton.tolist(), order):
        index = int(index)
        hydrogens = sum(atom.GetAtomicNum() == 1 for atom in molecule.GetAtomWithIdx(index).GetNeighbors())
        proton_shifts = np.array(h) * 10
        if hydrogens != 2 or np.ptp(proton_shifts) < .03:
            proton_shifts = [float(np.mean(proton_shifts))]
        for shift in proton_shifts:
            expected.append([c * 200, float(shift)])
            atom_ids.append(index)
    expected = np.asarray(expected)
    if not np.isfinite(expected).all():
        raise ValueError('TransPeakNet returned nonfinite shifts')
    measured = np.asarray(payload.get('hsqc_peaks', []), dtype=float)
    if measured.ndim != 2 or measured.shape[1] != 2 or not 1 <= len(measured) <= 256 or not np.isfinite(measured).all():
        raise ValueError('Supply 1–256 measured [13C ppm, 1H ppm] cross-peaks')
    matches, unmatched = assign_peaks(measured, expected, atom_ids)
    for index, atom in enumerate(molecule.GetAtoms()):
        atom.SetAtomMapNum(index + 1)
    return {'model': 'TransPeakNet', 'checkpoint_sha256': digest, 'solvent': solvent, 'smiles': smiles,
            'mapped_smiles': Chem.MolToSmiles(molecule, canonical=False),
            'atom_index_basis': 'RDKit AddHs on input SMILES, zero based. SMILES map labels are index + 1.',
            'matcher': 'One-to-one minimum scaled H/C deviation with unmatched slots (8 ppm C, 0.65 ppm H).',
            'unit': ['13C ppm', '1H ppm'], 'hsqc_measured': measured.tolist(),
            'hsqc_predicted': [{'carbon_atom_index': i, 'ppm': pair.tolist()} for i, pair in zip(atom_ids, expected)],
            'hsqc_assignments': matches, 'unmatched_peak_indices': unmatched}


if __name__ == '__main__':
    result = evaluate(json.load(sys.stdin))
    print('OMS_RESULT_V1:' + json.dumps(result, allow_nan=False), flush=True)
