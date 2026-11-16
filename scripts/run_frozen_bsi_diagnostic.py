"""Bounded B/Si inference with the released All-nucleus liquid NMRNet model.

This establishes execution and label alignment, not nucleus-specific training
coverage or held-out accuracy. No parameter or reference fitting is performed.
"""
import argparse
import json
import os
from pathlib import Path
import pickle
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openmolspec_bench.data import readonly_lmdb, sha256


def main():
    import lmdb
    import numpy as np
    from rdkit import Chem
    import torch

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=32)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error('--limit must be positive')
    args.output.mkdir(parents=True, exist_ok=False)
    models = args.models_root.resolve()
    run = next((models / 'nmrnet/weights/finetune/liquid').glob('All_*'))
    checkpoint = run / 'cv_seed_42_fold_0/checkpoint_best.pt'
    source = models / 'nmrnet/nmrnet-orig'
    state = torch.load(checkpoint, map_location='cpu', weights_only=False)
    saved_args = vars(state['args'])
    assert saved_args['selected_atom'] == 'All'
    assert saved_args['num_classes'] == 1
    del state
    result = {
        'training_performed': False, 'status': 'diagnostic_only',
        'primary_score_eligible': False,
        'limitations': ['Nucleus-specific training coverage is unverified.',
                       'Training overlap with evaluation records is unaudited.',
                       'This model does not condition on solvent.',
                       'Atom labels originate from the local prepared pool; experimental assignment provenance is unverified.'],
        'checkpoint': str(checkpoint), 'checkpoint_sha256': sha256(checkpoint),
        'checkpoint_args': {k: saved_args.get(k) for k in ('task','arch','data','selected_atom','num_classes')},
        'scaler_sha256': sha256(run / 'target_scaler.ss'),
        'dictionary_sha256': sha256(run.parent / 'mol_dict.txt'),
        'nuclei': {},
    }
    env = dict(os.environ, OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='1', TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD='1')
    for symbol in ('B', 'Si'):
        destination = args.output / symbol
        destination.mkdir()
        data = models / 'nmrnetpp' / f'pool_{symbol}' / 'valid.lmdb'
        rows, seen = [], set()
        database = readonly_lmdb(data)
        with database.begin() as transaction:
            for key, value in transaction.cursor():
                row = pickle.loads(value)
                molecule = Chem.MolFromSmiles(row['smiles'])
                if molecule is None:
                    continue
                identity = Chem.MolToSmiles(molecule, isomericSmiles=True)
                if identity in seen or len(row['atoms']) > 256:
                    continue
                mask = (np.asarray(row['atoms']) == symbol) & (np.asarray(row['atoms_target_mask']) == 1)
                if not mask.any():
                    continue
                assert np.isfinite(np.asarray(row['atoms_target'])[mask]).all()
                seen.add(identity)
                rows.append((key.decode(), value, row, np.flatnonzero(mask)))
                if len(rows) == args.limit:
                    break
        database.close()
        if not rows:
            raise ValueError(f'No valid {symbol} records')
        with tempfile.TemporaryDirectory(prefix=f'openmolspec-{symbol}-all-') as temporary:
            local = Path(temporary)
            database = lmdb.open(str(local / 'valid.lmdb'), subdir=False, map_size=128*1024*1024)
            with database.begin(write=True) as transaction:
                for index, (_, value, _, _) in enumerate(rows):
                    transaction.put(str(index).zfill(6).encode(), value)
            database.close()
            shutil.copyfile(local / 'valid.lmdb', destination / 'input.lmdb')
            # The author's entry point loads strict=False. Require all instantiated
            # parameters to be restored, so no random prediction head can pass.
            wrapper = local / 'checked_infer.py'
            wrapper.write_text("""import json, runpy, sys, torch
from pathlib import Path
original = torch.nn.Module.load_state_dict
audit_path = Path(sys.argv[1])
def checked(self, state, *args, **kwargs):
    report = original(self, state, *args, **kwargs)
    audit_path.write_text(json.dumps({'missing_keys': report.missing_keys, 'unexpected_keys': report.unexpected_keys}))
    if report.missing_keys:
        raise RuntimeError('Checkpoint leaves uninitialized parameters: ' + str(report.missing_keys))
    return report
torch.nn.Module.load_state_dict = checked
entry = sys.argv.pop(2)
sys.argv.pop(1)
sys.path.insert(0, str(Path(entry).parent))
runpy.run_path(entry, run_name='__main__')
""")
            command = [sys.executable, str(wrapper), str(destination / 'state_dict_audit.json'), str(source / 'uninmr/infer.py'),
                       '--user-dir', str(source / 'uninmr'), temporary, '--valid-subset', 'valid',
                       '--results-path', str(destination), '--saved-dir', str(run), '--num-workers', '0',
                       '--batch-size', '1', '--task', 'uninmr', '--loss', 'atom_regloss_mae',
                       '--arch', 'unimol_large', '--dict-name', str(run.parent / 'mol_dict.txt'),
                       '--path', str(checkpoint), '--selected-atom', symbol, '--gaussian-kernel',
                       '--atom-descriptor', '0', '--split-mode', 'infer', '--cpu',
                       '--required-batch-size-multiple', '1', '--no-progress-bar']
            manifest = {'source_path': str(data), 'source_sha256': sha256(data),
                        'input_sha256': sha256(destination / 'input.lmdb'), 'command': command,
                        'training_performed': False}
            with (destination / 'inference.log').open('w') as stream:
                process = subprocess.run(command, cwd=source, env=env, stdout=stream, stderr=subprocess.STDOUT)
            manifest['exit_code'] = process.returncode
            (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
            if process.returncode:
                raise RuntimeError(f'{symbol} inference failed; see {destination}/inference.log')
        with next(destination.glob('*.out.pkl')).open('rb') as stream:
            logs = pickle.load(stream)
        records, observed = [], set()
        for log in logs:
            ids = np.asarray(log['matid']).reshape(-1).tolist()
            assert len(ids) == 1
            index = int(ids[0])
            assert index not in observed
            observed.add(index)
            key, _, row, indices = rows[index]
            target = np.asarray(row['atoms_target'])[indices].astype(float)
            logged_target = np.asarray(log['target']).reshape(-1)
            prediction = np.asarray(log['predict']).reshape(-1)
            np.testing.assert_allclose(logged_target, target, atol=1e-4, rtol=1e-5)
            assert prediction.shape == target.shape and np.isfinite(prediction).all()
            records.append({'source_key': key, 'smiles': row['smiles'], 'atom_indices': indices.tolist(),
                            'reference_ppm': target.tolist(), 'prediction_ppm': prediction.tolist()})
        assert observed == set(range(len(rows)))
        errors = np.concatenate([np.asarray(r['prediction_ppm'])-np.asarray(r['reference_ppm']) for r in records])
        result['nuclei'][symbol] = {'molecules': len(records), 'atoms': len(errors),
                                   'mae_ppm': float(np.abs(errors).mean()),
                                   'rmse_ppm': float(np.sqrt(np.square(errors).mean())),
                                   'label_alignment_verified': True,
                                   'records': records, 'manifest': manifest,
                                   'state_dict_audit': json.loads((destination/'state_dict_audit.json').read_text())}
        (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps({symbol: {k:v for k,v in result['nuclei'][symbol].items() if k not in ('records','manifest')}}), flush=True)
    result['completed'] = True
    (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
