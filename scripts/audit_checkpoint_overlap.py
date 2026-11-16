"""Compare documented evaluation identities with fingerprint-matched training files."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a new report path')
    started = time.monotonic()
    def heartbeat():
        while True:
            time.sleep(20)
            print(f'Overlap audit active: {time.monotonic() - started:.0f}s', flush=True)
    threading.Thread(target=heartbeat, daemon=True).start()
    import torch
    from rdkit import Chem
    root = args.workspace.resolve()
    targets, target_counts = {}, {}
    for name in ('nmrspec_test', 'patent_test_10k', 'nmrexp_exp_10k', 'nmrgym_test'):
        identities = set()
        digest = hashlib.sha256()
        count = 0
        with (root / 'data/align_eval' / name / 'test.jsonl').open('rb') as stream:
            for line in stream:
                digest.update(line)
                row = json.loads(line)
                # Compare the representation actually retained by the prepared files.
                identity = row.get('inchi') or Chem.MolToInchi(Chem.MolFromSmiles(row['smiles']))
                if not identity:
                    raise ValueError('Missing evaluation identity')
                identities.add(identity)
                count += 1
        targets[name] = identities
        target_counts[name] = {'records': count, 'unique_standard_inchi': len(identities), 'sha256': digest.hexdigest()}
    union = set().union(*targets.values())
    report = {'audited_at': datetime.now(timezone.utc).isoformat(), 'training_performed': False,
              'identity': 'stored standard-InChI string; evaluation missing IDs generated with RDKit',
              'scope': 'molecular identity overlap, not exact spectral-record overlap; only these checkpoint-recorded train/val files',
              'pretraining_history_completely_audited': False, 'independence_established': False,
              'evaluation_views': target_counts, 'models': {}}
    scanned = {}
    for stage, run_id, directory in [('align', 'f90bd7f743574d18a7f72ae72ce95e59', 'mix_align_v2'),
                                     ('generation_predecessor', 'aa2fea19535f4b4ab7f472c53480316b', 'mix_align_v2'),
                                     ('generate', 'bebaecf2bca248f1a47eaa01f403002a', 'g1_all')]:
        checkpoint = root / 'runs' / run_id / 'best.pt'
        payload = torch.load(checkpoint, map_location='cpu', weights_only=True)
        fingerprint = payload['data_fingerprint']
        initialization = payload.get('alignment_checkpoint')
        del payload
        model = {'checkpoint': str(checkpoint), 'run_id': run_id,
                 'checkpoint_sha256': hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                 'initialization_checkpoint': initialization, 'splits': {}}
        for split in ('train', 'val'):
            path = root / 'data' / directory / f'{split}.jsonl'
            if str(path) in scanned:
                prior = scanned[str(path)]
                model['splits'][split] = {**prior, 'checkpoint_fingerprint_matches': prior['sha256'] == fingerprint[split],
                                         'checkpoint_recorded_sha256': fingerprint[split]}
                continue
            matched, missing, count, digest = set(), 0, 0, hashlib.sha256()
            with path.open('rb') as stream:
                for line in stream:
                    digest.update(line)
                    row = json.loads(line)
                    identity = row.get('inchi')
                    missing += int(not identity)
                    if identity in union:
                        matched.add(identity)
                    count += 1
                    if count % 500000 == 0:
                        print(stage, split, count, 'records scanned', flush=True)
            overlaps = {name: {'overlapping_identities': len(ids & matched), 'evaluated_identities': len(ids),
                               'fraction': len(ids & matched) / len(ids)} for name, ids in targets.items()}
            matches = digest.hexdigest() == fingerprint[split]
            model['splits'][split] = {'path': str(path), 'sha256': digest.hexdigest(),
                                      'checkpoint_recorded_sha256': fingerprint[split],
                                      'checkpoint_fingerprint_matches': matches,
                                      'interpretation': 'fingerprint-matched training file' if matches else 'current prepared file only; historical training-file identity unresolved',
                                      'records_scanned': count, 'records_missing_stored_inchi': missing, 'overlap': overlaps}
            scanned[str(path)] = model['splits'][split]
            print(stage, split, 'fingerprint_matches', matches, {k:v['overlapping_identities'] for k,v in overlaps.items()}, flush=True)
        report['models'][stage] = model
    alternate = root / 'data/g1_ne/train.jsonl'
    alternate_digest = hashlib.sha256()
    with alternate.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            alternate_digest.update(block)
    report['generation_fingerprint_discrepancy'] = {
        'checkpoint_digest_matches_other_file': str(alternate), 'other_file_sha256': alternate_digest.hexdigest(),
        'matches_recorded_train_digest': alternate_digest.hexdigest() == report['models']['generate']['splits']['train']['checkpoint_recorded_sha256'],
        'run_log_data_directory': 'data/g1_all',
        'interpretation': 'The historical training code copied verification.json digests without hashing the training bytes. The current g1_all train file differs; the recorded digest matches g1_ne. This does not establish which exact historical bytes were consumed.'}
    report['completed'] = True
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
