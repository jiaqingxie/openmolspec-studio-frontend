"""Run existing benchmark adapters through the same public Python package."""
import json
from pathlib import Path
import subprocess
import sys

from ._runtime import runtime_command, runtime_env


class Benchmark:
    def __init__(self, *, workspace, python=None, **assets):
        allowed = {'portable_root', 'models_root', 'alignment_checkpoint', 'generation_checkpoint',
                   'nmr_python', 'ms_python', 'solvent_library', 'ms_source', 'ms_weights',
                   'ms_input_csv', 'ms_metadata_tsv', 'magma_source', 'gap_lmdb', 'fp_inference_root'}
        if set(assets) - allowed:
            raise ValueError(f'Unknown asset options: {set(assets) - allowed}')
        self.python = str(python or sys.executable)
        self.workspace = Path(workspace).expanduser().resolve()
        self.assets = assets

    def run(self, tasks, *, output, datasets=None, limit=32, seed=42, sampling='reservoir', device='cpu'):
        from .task import list_tasks
        supported = {row['id'] for row in list_tasks()}
        tasks = [tasks] if isinstance(tasks, str) else list(tasks)
        if not tasks or set(tasks) - supported:
            raise ValueError('Select active task IDs from openmolspec.task.list_tasks()')
        if limit < 1 or sampling not in ('first', 'reservoir'):
            raise ValueError('Invalid sample limit or sampling method')
        output = Path(output).expanduser().resolve()
        if output.exists():
            raise FileExistsError(output)
        command = [self.python, '-m', 'openmolspec_bench', 'run', '--workspace', str(self.workspace),
                   '--tasks', *tasks, '--limit', str(limit), '--seed', str(seed), '--sampling', sampling,
                   '--device', device, '--output', str(output)]
        if datasets:
            command += ['--datasets', *([datasets] if isinstance(datasets, str) else datasets)]
        for key, value in self.assets.items():
            command += ['--' + key.replace('_', '-'), str(value)]
        subprocess.run(runtime_command(self.python, 'openmolspec_bench', command[3:]), env=runtime_env(), check=True)
        return json.loads(output.read_text())


def evaluate_nmr(prediction, references):
    """Score paired unassigned peak lists; this is not atom-assignment accuracy."""
    from openmolspec_bench.metrics import peak_metrics
    return peak_metrics([row['prediction_ppm'] for row in prediction['records']], references)
