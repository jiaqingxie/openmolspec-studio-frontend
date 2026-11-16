import hashlib
from pathlib import Path
import tempfile
import unittest

from spec2struct_fork.integrity import verify_training_files


class TrainingIntegrityTests(unittest.TestCase):
    def test_stale_manifest_cannot_attest_changed_training_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            verification = {'files': {}}
            for split in ('train', 'val'):
                content = ('{"split": "' + split + '"}\n').encode()
                (root / f'{split}.jsonl').write_bytes(content)
                verification['files'][split] = {'sha256': hashlib.sha256(content).hexdigest()}
            verify_training_files(root, verification)
            with (root / 'train.jsonl').open('a') as stream:
                stream.write('{"extra": true}\n')
            with self.assertRaisesRegex(ValueError, 'differs from verification'):
                verify_training_files(root, verification)


if __name__ == '__main__':
    unittest.main()
