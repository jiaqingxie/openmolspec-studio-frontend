"""Validate prepared training bytes before trusting a saved fingerprint."""
import hashlib
from pathlib import Path


def verify_training_files(data_dir, verification):
    for split in ('train', 'val'):
        path = Path(data_dir) / f'{split}.jsonl'
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                digest.update(block)
        expected = verification.get('files', {}).get(split, {}).get('sha256')
        if digest.hexdigest() != expected:
            raise ValueError(f'{split}.jsonl differs from verification.json; verify the current data before training')
