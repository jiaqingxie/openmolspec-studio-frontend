"""Build same-structure IR and atom-labelled NMR pairs for the public explorer."""
import argparse
import csv
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
import numpy as np
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from evaluate_assigned_sites import SOLVENT_LABELS
from openmolspec.assigned_shifts import AssignedShiftPredictor
from openmolspec_bench.assignment import assign_peaks
from openmolspec_bench.data import sha256
from openmolspec_ui.theoretical import harmonic_modes, mode_activities


def reference_scores(sites, annotations):
    """One observation per symmetry site; multi-shift/ambiguous sites are excluded."""
    labels = dict(annotations)
    pairs = []
    for site in sites:
        values = {v for atom in site['atom_indices'] for v in labels.get(atom, [])}
        if len(values) == 1:
            observed = next(iter(values))
            pairs.append({'atoms':site['atom_indices'], 'observed':observed, 'predicted':site['shift_ppm']})
    obs = np.array([p['observed'] for p in pairs])
    pred = np.array([p['predicted'] for p in pairs])
    ss = np.sum((obs - np.mean(obs))**2) if len(obs) else 0
    r2 = float(1 - np.sum((obs - pred)**2) / ss) if len(obs) >= 3 and ss > 0 else None
    mae = float(np.abs(obs - pred).mean()) if len(obs) else None
    return dict(r2=r2, mae=mae, sites=len(pairs), predicted_sites=len(sites), pairs=pairs)


def nmr_examples(dataset, weights):
    manifest = json.loads(dataset.with_suffix('.manifest.json').read_text())
    if sha256(dataset) != manifest['output_sha256']:
        raise ValueError('NMR reference differs from its source manifest.')
    models = {n: AssignedShiftPredictor(weights / (n + '-assigned')) for n in ('13C','1H')}
    counts = {n:0 for n in models}
    seen = set()
    examples = []
    with gzip.open(dataset,'rt') as f:
        for line_num, row in enumerate(map(json.loads, f), start=1):
            key, role, smiles, nucleus, solvent_id, annotations = row
            if role != 'test' or counts[nucleus] >= 4 or (nucleus,key) in seen or solvent_id in (0,11):
                continue
            mol = Chem.MolFromSmiles(smiles)
            if mol.GetNumHeavyAtoms() > 22 or len(annotations) < 3:
                continue
            model = models[nucleus]
            solvent = SOLVENT_LABELS[solvent_id]
            sites = model.predict(smiles, solvent)
            reference = reference_scores(sites, annotations)
            if reference['sites'] < 3:
                continue
            tolerance = 0.5 if nucleus == '1H' else 5.0
            measured = sorted({v for _, shifts in annotations for v in shifts})
            aligned = assign_peaks(smiles, 'H' if nucleus == '1H' else 'C',
                model.assignment_predictions(smiles,solvent), measured, tolerance)
            examples.append(dict(kind='nmr', id=f'assigned-{line_num}', modality=nucleus,
                formula=rdMolDescriptors.CalcMolFormula(mol), smiles=smiles, solvent=solvent,
                observed=measured, predicted=[s['predicted_ppm'] for s in aligned['sites']],
                source='nmrshiftdb2', source_id=f'{key} / {line_num}', source_url='https://nmrshiftdb.nmr.uni-koeln.de/',
                dataset_sha256=manifest['output_sha256'], record_line=line_num, split='test',
                model='OpenMolSpec assigned-site predictor', weights=model.config, reference=reference,
                matched=[{'obs':a['observed_ppm'],'pred':a['predicted_ppm'],'atoms':a['atom_indices']}
                         for a in aligned['assignments']], tolerance=tolerance))
            seen.add((nucleus,key))
            counts[nucleus] += 1
            if min(counts.values()) == 4:
                break
    if min(counts.values()) < 4:
        raise ValueError('Insufficient atom-labelled references.')
    return examples


def ir_examples(qm9s, measurements):
    # These native files have exact isomeric-SMILES matches in the released experimental split.
    ids = [128,363,474]
    targets = {}
    for idx in ids:
        native = qm9s / 'qm9s_csv' / f'{idx:06}.csv'
        with native.open() as f:
            rows = list(csv.reader(f))[1:]
        if int(float(rows[0][1])) != idx:
            raise ValueError('QM9S ID mismatch.')
        mol = Chem.MolFromSmiles(rows[0][3])
        smiles = Chem.MolToSmiles(mol, isomericSmiles=True)
        n = int(float(rows[0][4]))
        geom = np.array([r[1:5] for r in rows[10:10+n]],float)
        masses = [Chem.GetPeriodicTable().GetMostCommonIsotopeMass(int(z)) for z in geom[:,0]]
        hessian = np.array([r[1:3*n+1] for r in rows[-3*n:]],float)
        modes = harmonic_modes(hessian, geom[:,1:], masses)
        dipole = np.array([r[1:10] for r in rows[10+n:10+2*n]],float).reshape(n,3,3)
        intensities, _ = mode_activities(modes.cartesian_modes,dipole,np.zeros((n,3,3,3)))
        freq = modes.frequencies_cm1 * 0.965
        mask = freq > 1
        grid = np.arange(500.,4001.,5.)
        curve = (1 / (1+((grid[:,None]-freq[mask])/10.)**2)) @ intensities[mask]
        targets[smiles] = dict(kind='ir', modality='IR', id=f'qm9s-{idx:06}',
            formula=rdMolDescriptors.CalcMolFormula(mol), smiles=smiles,
            model='QM9S', model_id=f'{idx:06}', model_url='https://figshare.com/articles/dataset/QM9S_dataset/24235333',
            model_file_sha256=sha256(native), grid=[500,4000,5], calculated=(curve/curve.max()).round(5).tolist())
    with measurements.open() as f:
        for row in map(json.loads,f):
            pair = targets.get(row['smiles'])
            if pair is None or 'observed' in pair or len(row.get('wavenumber_cm1',[])) < 2:
                continue
            if Chem.MolToInchiKey(Chem.MolFromSmiles(pair['smiles'])) != row['standard_inchikey']:
                raise ValueError('Experimental structure identity mismatch.')
            pair.update(observed=row['wavenumber_cm1'], source=row['source'],
                        source_id=row['source_document'],split='test')
    if not all('observed' in pair for pair in targets.values()):
        raise ValueError('Missing matching experimental IR.')
    return list(targets.values())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assigned-data', type=Path, default=ROOT/'.runtime/forward-tuning/hc-assigned.jsonl.gz')
    p.add_argument('--weights', type=Path, default=ROOT.parent/'runs/forward-tuning')
    p.add_argument('--qm9s', type=Path, default=ROOT.parents[1]/'data/qm9s')
    p.add_argument('--experimental-ir', type=Path, default=ROOT/'.runtime/manual-data-v1/experimental/IR-test.jsonl')
    p.add_argument('--output', type=Path, default=ROOT/'website/assets/explore-comparisons.json')
    args = p.parse_args()
    pairs = nmr_examples(args.assigned_data,args.weights) + ir_examples(args.qm9s,args.experimental_ir)
    args.output.write_text(json.dumps({'comparisons':pairs},allow_nan=False,separators=(',',':'))+'\n')
    print('Exported',len(pairs),'same-structure pairs.')


if __name__ == '__main__':
    main()
