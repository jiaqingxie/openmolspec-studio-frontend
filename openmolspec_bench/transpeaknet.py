"""Frozen TransPeakNet graph and per-carbon HSQC predictions in input SMILES order."""
import importlib.util
from pathlib import Path
import sys

import numpy as np
import torch
from rdkit import Chem
from scipy.optimize import linear_sum_assignment
from torch_geometric.data import Batch, Data

from .data import sha256

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


def load_model(source, device="cpu"):
    source = Path(source)
    checkpoint = source / "ckpt/model_2dnmr.pt"
    if sha256(checkpoint) != CHECKPOINT_SHA256:
        raise ValueError("Checkpoint digest differs from the verified author release")
    definition = source / "GraphModel/GNN_2d_hsolvent.py"
    module_name = "transpeaknet_author_" + sha256(definition)
    spec = importlib.util.spec_from_file_location(module_name, definition)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # PyG resolves message types using the defining module.
    spec.loader.exec_module(module)
    encoder = module.GNNNodeEncoder(5, 512, JK="last", gnn_type="gin", aggr="add")
    model = module.NodeEncodeInterface(encoder, hidden_channels=512, c_out_hidden=[128, 64],
        h_out_hidden=[128, 64], solvent_emb_dim=32, h_out_channels=2, use_solvent=True)
    model.load_state_dict(torch.load(checkpoint, map_location="cpu", weights_only=True), strict=True)
    return model.to(device).eval()


@torch.inference_mode()
def predict_sites(model, molecule, solvent):
    """Return zero-based carbon indices, 13C ppm and the two unmerged 1H head outputs in ppm."""
    device = next(model.parameters()).device
    (carbon, proton), indices = model(graph(molecule, solvent).to(device))
    indices = [int(index) for index in indices]
    c = carbon.flatten().cpu().numpy() * 200
    h = proton.cpu().numpy() * 10
    if c.shape != (len(indices),) or h.shape != (len(indices), 2):
        raise ValueError("Inconsistent TransPeakNet output shapes")
    if not np.isfinite(c).all() or not np.isfinite(h).all():
        raise ValueError("TransPeakNet returned nonfinite shifts")
    return indices, c, h


def peak_list(molecule, indices, carbon, proton):
    """Convert the two H heads per site to the peak list used by the website."""
    expected, atom_ids = [], []
    for index, c, h in zip(indices, carbon, proton):
        hydrogens = sum(atom.GetAtomicNum() == 1 for atom in molecule.GetAtomWithIdx(index).GetNeighbors())
        shifts = [float(np.mean(h))] if hydrogens != 2 or np.ptp(h) < .03 else h
        for shift in shifts:
            expected.append([float(c), float(shift)])
            atom_ids.append(index)
    return np.asarray(expected), atom_ids


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
