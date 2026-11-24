"""Run existing benchmark adapters through the same public Python package."""
import json
from pathlib import Path
import subprocess
import sys

from ._runtime import runtime_command, runtime_env


class Benchmark:
    """Run spectroscopy benchmark tasks with configured model and data assets.

    Parameters
    ----------
    workspace : str or pathlib.Path
        Workspace containing the prepared evaluation datasets.
    python : str or None, default None
        Interpreter used to launch the benchmark command.
    **assets
        Model/data locations accepted by the benchmark CLI: ``models_root``,
        ``portable_root``, ``alignment_checkpoint``, ``generation_checkpoint``,
        ``transpeaknet_source``, ``nmr_python``, ``ms_python``, ``solvent_library``, ``ms_source``,
        ``ms_weights``, ``ms_input_csv``, ``ms_metadata_tsv``, ``magma_source``,
        ``gap_lmdb``, ``fp_inference_root`` and ``solution_shift_root``.

    Examples
    --------
    >>> benchmark = Benchmark(workspace='data', models_root='models')
    >>> results = benchmark.run('nmr.forward.13C',
    ...     output='results/carbon.json', limit=32)
    """
    def __init__(self, *, workspace, python=None, **assets):
        allowed = {'portable_root', 'models_root', 'alignment_checkpoint', 'generation_checkpoint',
                   'transpeaknet_source', 'nmr_python', 'ms_python', 'solvent_library', 'ms_source', 'ms_weights',
                   'ms_input_csv', 'ms_metadata_tsv', 'magma_source', 'gap_lmdb', 'fp_inference_root', 'solution_shift_root',
                   'language_checkpoint','language_data','mechfrag_root','mechfrag_study'}
        if set(assets) - allowed:
            raise ValueError(f'Unknown asset options: {set(assets) - allowed}')
        self.python = str(python or sys.executable)
        self.workspace = Path(workspace).expanduser().resolve()
        self.assets = assets

    def run(self, tasks, *, output, datasets=None, limit=32, seed=42, sampling='reservoir', device='cpu',
            allow_cross_domain_diagnostic=False, solution_reference="test"):
        """Evaluate selected tasks and save their predictions and metrics.

        Parameters
        ----------
        tasks : str or iterable of str
            Task IDs returned by ``openmolspec.task.list_tasks``.
        output : str or pathlib.Path
            New JSON results file to create.
        datasets : str or iterable of str or None, default None
            Prepared dataset views to evaluate.
        limit : int, default 32
            Maximum number of selected examples per task/data view.
        seed : int, default 42
            Seed used for example selection.
        sampling : {'reservoir', 'first'}, default 'reservoir'
            Reservoir sampling or source-file order.
        device : str, default 'cpu'
            Model runtime device.
        allow_cross_domain_diagnostic : bool, default False
            Enable the F/P comparison of solid-state model predictions with
            solution-reference records. The result retains both domain labels.

        solution_reference : {"test", "historical-pool"}, default "test"
            Reference set for the fitted 19F and 31P solution models.

        Returns
        -------
        dict
            Saved result object with task IDs, metrics, sample information,
            predictions and model/data fingerprints.

        Raises
        ------
        FileExistsError
            If the output file already exists.
        ValueError
            If task IDs or sampling options are invalid.
        """
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
        if solution_reference != "test":
            command += ["--solution-reference", solution_reference]
        if datasets:
            command += ['--datasets', *([datasets] if isinstance(datasets, str) else datasets)]
        if allow_cross_domain_diagnostic:
            command.append('--allow-cross-domain-diagnostic')
        for key, value in self.assets.items():
            command += ['--' + key.replace('_', '-'), str(value)]
        subprocess.run(runtime_command(self.python, 'openmolspec_bench', command[3:]), env=runtime_env(), check=True)
        return json.loads(output.read_text())


def evaluate_nmr(prediction, references):
    """Compare predicted NMR peaks with measured peak lists.

    Parameters
    ----------
    prediction : dict
        NMRNet prediction containing ``records[*].prediction_ppm``.
    references : iterable of iterable of float
        One reference peak list per prediction record, in ppm.

    Returns
    -------
    dict
        Peak-matching MAE/RMSE, matched coverage and peak-count statistics.
    """
    from openmolspec_bench.metrics import peak_metrics
    return peak_metrics([row['prediction_ppm'] for row in prediction['records']], references)
