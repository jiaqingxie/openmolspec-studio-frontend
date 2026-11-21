"""Frozen atomwise NMR inference and peak-to-site assignment; never train."""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile

import numpy as np

from .data import sha256


def atom_sites(smiles, symbol, predictions):
    """Indices refer to RDKit AddHs(input SMILES), never a reordered SMILES."""
    from rdkit import Chem
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise ValueError('Invalid SMILES')
    molecule = Chem.AddHs(molecule)
    for atom in molecule.GetAtoms():
        atom.SetAtomMapNum(0)
    indices = [a.GetIdx() for a in molecule.GetAtoms() if a.GetSymbol() == symbol]
    predicted = np.asarray(predictions, dtype=float)
    if predicted.shape != (len(indices),) or not np.isfinite(predicted).all():
        raise ValueError('Prediction length/values disagree with the selected atoms')
    ranks = list(Chem.CanonicalRankAtoms(molecule, breakTies=False, includeChirality=True))
    groups = defaultdict(list)
    for index, value in zip(indices, predicted):
        groups[ranks[index]].append((index, float(value)))
    sites = [{'atom_indices': [i for i, _ in pairs],
              'predicted_ppm': float(np.mean([v for _, v in pairs]))}
             for pairs in groups.values()]
    for atom in molecule.GetAtoms():
        atom.SetAtomMapNum(atom.GetIdx()+1)
    return sites, Chem.MolToSmiles(molecule, canonical=False, allHsExplicit=True)


def assign_peaks(smiles, symbol, predictions, peaks, tolerance):
    from scipy.optimize import linear_sum_assignment
    observed = np.asarray(peaks, dtype=float)
    if observed.ndim != 1 or not 1 <= len(observed) <= 512 or not np.isfinite(observed).all():
        raise ValueError('Supply 1–512 finite peaks in ppm')
    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError('Tolerance must be finite and positive')
    sites, mapped = atom_sites(smiles, symbol, predictions)
    if not sites:
        raise ValueError(f'No {symbol} atoms in the structure')
    delta = np.abs(observed[:, None] - np.array([s['predicted_ppm'] for s in sites])[None, :])
    # Dummy columns retain unmatched peaks; out-of-tolerance matches are forbidden.
    cost = np.concatenate([np.where(delta <= tolerance, delta, np.inf),
                           np.full((len(observed), len(observed)), tolerance+1e-8)], axis=1)
    rows, columns = linear_sum_assignment(cost)
    assigned, unmatched, used = [], [], set()
    for row, column in zip(rows, columns):
        if column >= len(sites):
            unmatched.append(int(row))
            continue
        used.add(int(column))
        assigned.append({'peak_index': int(row), 'observed_ppm': float(observed[row]),
                         **sites[column], 'absolute_error_ppm': float(delta[row, column]),
                         'other_sites_within_tolerance': [int(i) for i in np.flatnonzero(delta[row] <= tolerance) if i != column]})
    return {'smiles': smiles, 'symbol': symbol, 'mapped_smiles': mapped,
            'atom_index_basis': 'zero-based RDKit AddHs(input_smiles); atom-map numbers = index + 1',
            'equivalence': 'topological symmetry including chirality; not proof of magnetic equivalence',
            'assignments': assigned, 'unmatched_peak_indices': unmatched,
            'unmatched_sites': [s for i, s in enumerate(sites) if i not in used],
            'sites': sites, 'tolerance_ppm': float(tolerance),
            'matched_fraction': len(assigned)/len(observed),
            'assignment_accuracy': None,
            'accuracy_note': 'Predicted assignments; experimental atom labels are not supplied.'}


def predict_atoms(smiles_list, symbol, models_root, directory, *, backend="nmrnet", fold=0):
    """Run the author's inference program with the saved H/C checkpoint/scaler."""
    from rdkit import Chem
    from rdkit.Chem import AllChem
    import lmdb
    from .runner import read_prediction_folds

    if symbol not in ('H', 'C'):
        raise ValueError('This atom-assignment model supports H/C only')
    models_root = Path(models_root).resolve()
    if backend == "nmrnet":
        source = models_root / "nmrnet/nmrnet-orig"
        weights = models_root / "nmrnet/weights/finetune/liquid"
        runs = sorted(weights.glob(f"{symbol}_*"))
        filename = "checkpoint_best.pt"
        dictionary = weights / "mol_dict.txt"
        label = "NMRNet"
    elif backend == "nmrnetpp":
        source = models_root / "nmrnetpp/NMRNetplusplus"
        weights = models_root / "nmrnetpp/checkpoints"
        runs = sorted(weights.glob(f"scratch_{symbol}_*"))
        filename = "checkpoint_last.pt"
        dictionary = models_root / "nmrnetpp/weight/dict.txt"
        label = "NMRNet++"
    else:
        raise ValueError("Unknown atom prediction backend")
    if len(runs) != 1:
        raise FileNotFoundError(f"Expected one frozen {symbol} checkpoint directory under {weights}")
    run = runs[0]
    checkpoint = run / f"cv_seed_42_fold_{int(fold)}" / filename
    scaler = run / "target_scaler.ss"
    for path in (source/'uninmr/infer.py', checkpoint, scaler, dictionary):
        if not path.is_file():
            raise FileNotFoundError(path)
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    records, geometry = [], []
    allowed = set(dictionary.read_text().split())
    for smiles in smiles_list:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f'Invalid SMILES: {smiles}')
        mol = Chem.AddHs(mol)
        atoms = [a.GetSymbol() for a in mol.GetAtoms()]
        if len(atoms) > 256 or not set(atoms) <= allowed or symbol not in atoms:
            raise ValueError('Unsupported atom, oversized molecule, or no requested nucleus')
        if AllChem.EmbedMolecule(mol, randomSeed=42) != 0:
            raise ValueError(f'3D conformer generation failed: {smiles}')
        optimized = False
        if AllChem.MMFFHasAllMoleculeParams(mol):
            optimized = AllChem.MMFFOptimizeMolecule(mol) == 0
        xyz = mol.GetConformer().GetPositions().astype(np.float32)
        records.append({'smiles': smiles, 'atoms': atoms, 'coordinates': xyz,
                        'atoms_target_mask': np.array([a == symbol for a in atoms], dtype=np.int32),
                        'atoms_target': np.zeros(len(atoms), dtype=np.float32)})
        if backend == 'nmrnetpp':
            records[-1].update(nmr_frequency=0.0, nmr_solvent='')
        geometry.append({'smiles': smiles, 'atoms': atoms, 'coordinates_angstrom': xyz.tolist(),
                         'mmff_converged': optimized})
    with tempfile.TemporaryDirectory(prefix='openmolspec-atoms-') as temporary:
        local = Path(temporary)
        env = lmdb.open(str(local/'valid.lmdb'), subdir=False, map_size=128*1024*1024)
        with env.begin(write=True) as transaction:
            for index, row in enumerate(records):
                transaction.put(f'{index:06d}'.encode(), pickle.dumps(row))
        env.close()
        wrapper = local/'infer_checked.py'
        wrapper.write_text('''import json,runpy,sys,torch
from pathlib import Path
audit = Path(sys.argv.pop(1))
entry = sys.argv.pop(1)
original = torch.nn.Module.load_state_dict
def checked(self, state, *args, **kwargs):
    result = original(self, state, *args, **kwargs)
    audit.write_text(json.dumps({'missing_keys':result.missing_keys,'unexpected_keys':result.unexpected_keys}))
    if result.missing_keys or result.unexpected_keys:
        raise RuntimeError('Checkpoint parameters disagree with instantiated model')
    return result
torch.nn.Module.load_state_dict = checked
sys.path.insert(0,str(Path(entry).parent))
runpy.run_path(entry,run_name='__main__')
''')
        command = [sys.executable, str(wrapper), str(directory/'state_dict_audit.json'), str(source/'uninmr/infer.py'),
                   '--user-dir', str(source/'uninmr'), temporary, '--valid-subset', 'valid',
                   '--results-path', str(directory), '--saved-dir', str(run), '--num-workers', '0',
                   '--batch-size', '8', '--task', 'uninmr', '--loss', 'atom_regloss_mae',
                   '--arch', 'unimol_large', '--dict-name', str(dictionary), '--path', str(checkpoint),
                   '--selected-atom', symbol, '--gaussian-kernel', '--atom-descriptor', '0',
                   '--split-mode', 'infer', '--cpu', '--required-batch-size-multiple', '1', '--no-progress-bar']
        provenance = {'model': f'{label} liquid {symbol} fold {fold}', 'checkpoint': str(checkpoint),
                      'checkpoint_sha256': sha256(checkpoint), 'scaler_sha256': sha256(scaler),
                      'dictionary_sha256': sha256(dictionary), 'input_sha256': sha256(local/'valid.lmdb'),
                      'geometry': geometry, 'training_performed': False, 'command': command}
        with (directory/'inference.log').open('w') as stream:
            done = subprocess.run(command, cwd=source, stdout=stream, stderr=subprocess.STDOUT,
                                  env=dict(os.environ, TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD='1', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='1'))
        provenance['exit_code'] = done.returncode
        (directory/'manifest.json').write_text(json.dumps(provenance, indent=2)+'\n')
        if done.returncode:
            raise RuntimeError(f'Frozen atom inference failed: {directory}/inference.log')
    predictions = read_prediction_folds(list(directory.glob('*.out.pkl')))
    if len(predictions) != 1 or set(predictions[0]) != set(range(len(records))):
        raise ValueError('Inference did not return each requested molecule exactly once')
    for index, row in enumerate(records):
        values = predictions[0][index]
        if len(values) != int(row['atoms_target_mask'].sum()) or not np.isfinite(values).all():
            raise ValueError('Invalid atom predictions')
    provenance['state_dict_audit'] = json.loads((directory/'state_dict_audit.json').read_text())
    return predictions[0], provenance


def evaluate(dataset, symbol, limit, models_root, directory):
    from .data import load_rows
    from spec2struct_fork.structured import parse_nmr_record, SHIFT, SHIFT_PRESENT
    rows, selection = load_rows(dataset, symbol.lower(), limit)
    predictions, provenance = predict_atoms([r['smiles'] for r in rows], symbol, models_root, directory)
    records = []
    for index, row in enumerate(rows):
        peaks = [float(f[SHIFT]) for entry in row[f'{symbol.lower()}_nmr']
                 for f in parse_nmr_record(entry, symbol.lower()) if f[SHIFT_PRESENT]]
        records.append(assign_peaks(row['smiles'], symbol, predictions[index], peaks,
                                    0.5 if symbol == 'H' else 5.0))
    residuals = [a['absolute_error_ppm'] for r in records for a in r['assignments']]
    return {'completed': True, 'task': 'nmr.assignment', 'status': 'passed',
            'training_performed': False, 'inference_mode': 'direct_frozen_checkpoint',
            'purpose': 'real_peak_assignment_execution_not_atom_accuracy_benchmark',
            'dataset': {'path': str(dataset), 'sha256': sha256(dataset)}, 'selection': selection,
            'symbol': symbol, 'provenance': provenance, 'records': records,
            'metrics': {'molecules': len(records), 'matched_peaks': len(residuals),
                        'matched_peak_fraction_macro': float(np.mean([r['matched_fraction'] for r in records])),
                        'matched_residual_mae_ppm': float(np.mean(residuals)) if residuals else None,
                        'assignment_accuracy': None},
            'limitations': ['No experimental atom assignment ground truth supplied.',
                            'Symmetry is topological; conformer/solvent effects can change observed equivalence.',
                            'Residual and coverage are diagnostics, not assignment accuracy.',
                            'Training overlap unverified; frozen model is not solvent-conditioned.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models-root', type=Path, required=True)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--request', type=Path)
    inputs.add_argument('--dataset-jsonl', type=Path)
    parser.add_argument('--nucleus', choices=('1H', '13C'), default='13C')
    parser.add_argument('--limit', type=int, default=32)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists')
    if args.dataset_jsonl:
        if args.limit < 1:
            parser.error('limit must be positive')
        with tempfile.TemporaryDirectory(prefix='openmolspec-assignment-bench-') as temporary:
            result = evaluate(args.dataset_jsonl, {'1H': 'H', '13C': 'C'}[args.nucleus], args.limit,
                              args.models_root, Path(temporary)/'run')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
        return
    request = json.loads(args.request.read_text())
    symbol = {'1H': 'H', '13C': 'C'}.get(request['nucleus'])
    if symbol is None:
        raise ValueError('Supported nuclei: 1H, 13C')
    peaks = request['peaks_ppm']
    tolerance = request.get('tolerance_ppm', 0.5 if symbol == 'H' else 5.0)
    # Validate the matching request before loading a model.
    from rdkit import Chem
    mol = Chem.MolFromSmiles(request['smiles'])
    if mol is None:
        raise ValueError('Invalid SMILES')
    count = sum(a.GetSymbol() == symbol for a in Chem.AddHs(mol).GetAtoms())
    assign_peaks(request['smiles'], symbol, [0.0]*count, peaks, tolerance)
    with tempfile.TemporaryDirectory(prefix='openmolspec-assignment-') as temporary:
        predictions, provenance = predict_atoms([request['smiles']], symbol, args.models_root, Path(temporary)/'run')
    result = assign_peaks(request['smiles'], symbol, predictions[0], peaks, tolerance)
    result.update(completed=True, task='nmr.assignment', status='passed', training_performed=False,
                  inference_mode='direct_frozen_checkpoint', provenance=provenance)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    main()
