from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import py3Dmol
from rdkit import Chem
from rdkit.Chem import AllChem, rdDetermineBonds, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D


@dataclass
class MoleculeInput:
    mol: Chem.Mol
    source: str

    @property
    def smiles(self) -> str:
        return Chem.MolToSmiles(Chem.RemoveHs(self.mol), canonical=True)

    @property
    def formula(self) -> str:
        return rdMolDescriptors.CalcMolFormula(self.mol)

    @property
    def atoms(self) -> int:
        return self.mol.GetNumAtoms()


def molecule_from_smiles(smiles: str) -> MoleculeInput:
    mol = Chem.MolFromSmiles(smiles.strip())
    if mol is None:
        raise ValueError("无法解析该 SMILES。")
    mol = Chem.AddHs(mol)
    parameters = AllChem.ETKDGv3()
    parameters.randomSeed = 624
    if AllChem.EmbedMolecule(mol, parameters) != 0:
        raise ValueError("无法为该分子生成三维构象，请改用 XYZ 文件。")
    if AllChem.MMFFHasAllMoleculeParams(mol):
        AllChem.MMFFOptimizeMolecule(mol, maxIters=300)
    else:
        AllChem.UFFOptimizeMolecule(mol, maxIters=300)
    return MoleculeInput(mol=mol, source="SMILES · RDKit ETKDGv3")


def molecule_from_xyz(content: bytes | str) -> MoleculeInput:
    if isinstance(content, bytes):
        text = content.decode("utf-8", errors="replace")
    else:
        text = content
    mol = Chem.MolFromXYZBlock(text)
    if mol is None:
        raise ValueError("无法解析 XYZ 文件。")
    try:
        rdDetermineBonds.DetermineBonds(mol, charge=0)
    except Exception:
        try:
            rdDetermineBonds.DetermineConnectivity(mol)
        except Exception as error:
            raise ValueError("XYZ 坐标有效，但无法推断原子连接关系。") from error
    return MoleculeInput(mol=mol, source="XYZ · uploaded conformer")


def molecule_svg(molecule: MoleculeInput, width: int = 640, height: int = 360) -> str:
    mol = Chem.RemoveHs(molecule.mol)
    return _mol_svg(mol, width, height)


def molecule_3d_html(molecule: MoleculeInput, height: int = 420) -> str:
    """Build an interactive 3Dmol.js view of the model-ready conformer."""
    mol_block = Chem.MolToMolBlock(molecule.mol)
    viewer = py3Dmol.view(width="100%", height=height)
    viewer.addModel(mol_block, "mol")
    viewer.setStyle(
        {},
        {
            "stick": {"radius": 0.16, "colorscheme": "Jmol"},
            "sphere": {"scale": 0.28, "colorscheme": "Jmol"},
        },
    )
    viewer.setBackgroundColor("#f6f8f4", 0)
    viewer.zoomTo()
    viewer.zoom(1.12)
    return viewer._make_html()


def smiles_svg(smiles: str, width: int = 360, height: int = 220) -> str | None:
    """Render a SMILES string as an RDKit 2D SVG, or return None if invalid."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return _mol_svg(mol, width, height)


@lru_cache(maxsize=512)
def smiles_png(smiles: str, width: int = 480, height: int = 300) -> bytes | None:
    """Render a SMILES string as RDKit PNG bytes for reliable web display."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    AllChem.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DCairo(width, height)
    drawer.drawOptions().clearBackground = True
    drawer.drawOptions().bondLineWidth = 2.2
    drawer.drawOptions().padding = 0.12
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return bytes(drawer.GetDrawingText())


def _mol_svg(mol: Chem.Mol, width: int, height: int) -> str:
    AllChem.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    drawer.drawOptions().clearBackground = False
    drawer.drawOptions().bondLineWidth = 2.2
    drawer.drawOptions().padding = 0.12
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


def molecule_to_pyg(molecule: MoleculeInput):
    import torch
    from torch_geometric.data import Data

    conformer = molecule.mol.GetConformer()
    positions = np.asarray(conformer.GetPositions(), dtype=np.float32)
    atomic_numbers = np.asarray(
        [atom.GetAtomicNum() for atom in molecule.mol.GetAtoms()], dtype=np.int64
    )
    return Data(
        pos=torch.from_numpy(positions),
        atomic_numbers=torch.from_numpy(atomic_numbers),
        natoms=torch.tensor([len(atomic_numbers)], dtype=torch.long),
    )
