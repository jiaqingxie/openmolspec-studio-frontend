"""Prepare the peak intensities, parent drawing and group masks for the MechFrag-MS replay."""

import argparse
import ast
import csv
import json
import math
from pathlib import Path
import re
from xml.etree import ElementTree

from rdkit import Chem
from rdkit.Chem import rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D

ASSETS = Path(__file__).resolve().parents[1] / 'website/assets/harness'
SPECTRUM = 'MassSpecGymID0013877'
# The matches describe motifs in the parent representation used by MechFrag-MS.
MOTIFS = [
    ('cyclic-ether', 'Six-membered cyclic ether', '六元环醚', 'O1CCCCC1'),
    ('ketone', 'Ketone', '酮羰基', '[#6]-[CX3](=[OX1])-[#6]'),
    ('enol', 'Enol', '烯醇', '[C]=[C]-[OX2H1]'),
    ('oxime-ether', 'Oxime ether', '肟醚', '[CX3]=[NX2]-[OX2]-[#6]'),
    ('vinyl-chloride', 'Vinylic chloride', '烯基氯', '[C]=[C]-Cl'),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spectrum-csv', type=Path, required=True, help='MassSpecGym_test_full.csv')
    args = parser.parse_args()
    result = json.loads((ASSETS / 'harness_mcp_mechfrag.json').read_text())['inference']['result']
    if result['atom_index_basis'] != 'zero-based RDKit atom order of the input SMILES':
        raise ValueError('Unexpected MechFrag-MS atom numbering')
    mol = Chem.MolFromSmiles(result['smiles'])
    with args.spectrum_csv.open(newline='') as stream:
        rows = [row for row in csv.DictReader(stream) if row['spec_id'] == SPECTRUM]
    if len(rows) != 1 or Chem.MolToSmiles(Chem.MolFromSmiles(rows[0]['smiles'])) != Chem.MolToSmiles(mol):
        raise ValueError('Spectrum identity differs from the recorded input')
    observed = [(float(mz), float(height)) for mz, height in ast.literal_eval(rows[0]['peaks'])]
    if [mz for mz, _ in observed] != [peak['observed_mz'] for peak in result['peaks']]:
        raise ValueError('Observed peaks differ from the recorded run')
    if any(not math.isfinite(height) or height < 0 for _, height in observed) or max(h for _, h in observed) != 1:
        raise ValueError('Expected base-peak-normalized measured intensities')
    for peak in result['peaks']:
        match = peak['match']
        if match:
            atoms = match['atom_indices']
            if not atoms or len(atoms) != len(set(atoms)) or min(atoms) < 0 or max(atoms) >= mol.GetNumAtoms():
                raise ValueError('Invalid heavy-atom mask')
            if '.' in Chem.MolFragmentToSmiles(mol, atomsToUse=atoms):
                raise ValueError('Disconnected fragment in this replay')
    groups = []
    for key, en, zh, query in MOTIFS:
        hits = mol.GetSubstructMatches(Chem.MolFromSmarts(query))
        if len(hits) != 1:
            raise ValueError(f'Ambiguous parent motif: {key}')
        groups.append(dict(id=key, labels=[en, zh], atoms=sorted(hits[0])))
    rdDepictor.Compute2DCoords(mol)
    drawing = rdMolDraw2D.MolDraw2DSVG(400, 205)
    options = drawing.drawOptions()
    options.clearBackground = False
    options.useBWAtomPalette()
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 6:
            # A skeleton annotation does not determine the product's hydrogen or charge site.
            options.atomLabels[atom.GetIdx()] = atom.GetSymbol()
    drawing.DrawMolecule(mol)
    drawing.FinishDrawing()
    coordinates = [[round(drawing.GetDrawCoords(i).x, 1), round(drawing.GetDrawCoords(i).y, 1)]
                   for i in range(mol.GetNumAtoms())]
    paths = []
    for path in ElementTree.fromstring(drawing.GetDrawingText()).findall('{http://www.w3.org/2000/svg}path'):
        classes = path.get('class', '')
        if not classes:  # RDKit adds short unindexed strokes for joins between bonds.
            continue
        indices = [int(value) for value in re.findall(r'\batom-(\d+)', classes)]
        if not indices:
            raise ValueError('Cannot associate a drawn path with its atoms')
        paths.append(dict(atoms=indices, d=path.attrib['d']))
    drawn_bonds = {frozenset(entry['atoms']) for entry in paths if len(entry['atoms']) == 2}
    if drawn_bonds != {frozenset((b.GetBeginAtomIdx(), b.GetEndAtomIdx())) for b in mol.GetBonds()}:
        raise ValueError('Drawing is missing a parent bond')
    payload = dict(spectrum_id=SPECTRUM, source='MassSpecGym_test_full.csv', smiles=result['smiles'],
                   adduct=rows[0]['prec_type'], observed_peaks=observed, groups=groups, coordinates=coordinates, paths=paths)
    (ASSETS / 'mechfrag-drawing.json').write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n')


if __name__ == '__main__':
    main()
