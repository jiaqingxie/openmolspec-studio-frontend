"""Prepare train/validation data and explicitly launch the packaged NMR trainer.

Creating or inspecting a plan never starts training. This module has no torch import.
"""
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

from ._runtime import runtime_command, runtime_env
from .dataset import SpectraSplit, audit_splits, sha256


def prepare_nmr_training(train, validation, destination):
    """Prepare train/validation files for NMRTransformer training.

    Parameters
    ----------
    train : openmolspec.dataset.SpectraSplit
        Experimental H/C NMR training view with role ``'train'``.
    validation : openmolspec.dataset.SpectraSplit
        Validation view with role ``'val'``. Records contain ``smiles``,
        ``formula``, ``h_nmr``, ``c_nmr`` and a channel mask.
    destination : str or pathlib.Path
        New directory for the prepared JSONLs and verification files.

    Returns
    -------
    pathlib.Path
        Directory containing ``train.jsonl``, ``val.jsonl``, ``summary.json``
        and ``verification.json``.

    Raises
    ------
    ValueError
        If split roles, molecular formulae, nucleus labels or cross-split
        molecular identities disagree with the training format.
    FileExistsError
        If the destination already exists.
    """
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors
    if not isinstance(train, SpectraSplit) or not isinstance(validation, SpectraSplit):
        raise TypeError('Pass SpectraSplit views with explicit train/val roles')
    if train.role != 'train' or validation.role != 'val':
        raise ValueError('Training requires train and val roles; test views cannot be fitted')
    if any(v.format != 'nmr_jsonl' or v.domain != 'experimental' for v in (train, validation)):
        raise ValueError('This trainer accepts experimental H/C NMR JSONL')
    destination = Path(destination).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    counts = {}
    with tempfile.TemporaryDirectory(prefix='.openmolspec-prepare-', dir=destination.parent) as temporary:
        staging = Path(temporary) / 'data'
        staging.mkdir()
        for name, view in [('train', train), ('val', validation)]:
            counts[name] = 0
            with (staging / f'{name}.jsonl').open('w') as stream:
                for row in view:
                    molecule = Chem.MolFromSmiles(row['smiles'])
                    if molecule is None or not molecule.GetNumAtoms():
                        raise ValueError('Invalid training SMILES')
                    if row['formula'] != rdMolDescriptors.CalcMolFormula(molecule):
                        raise ValueError('Training formula is missing or disagrees with the structure')
                    elements = {a.GetSymbol() for a in Chem.AddHs(molecule).GetAtoms()}
                    if any(flag and symbol not in elements for symbol, flag in zip(('H', 'C'), row['modality_mask'])):
                        raise ValueError('NMR nucleus is absent from the molecular structure; inspect the source record')
                    row['smiles'] = Chem.MolToSmiles(molecule, isomericSmiles=True)
                    for field_name in ('h_nmr', 'c_nmr'):
                        if any(not str(r.get('chemical_shift', '')).strip() for r in row[field_name]):
                            raise ValueError('NMR record has no chemical-shift text')
                    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
                    counts[name] += 1
            if counts[name] < 2:
                raise ValueError('Both training and validation require at least two records')
        views = {k: SpectraSplit(staging / f'{k}.jsonl', k, 'prepared_training', 'experimental') for k in counts}
        audit = audit_splits(views, check_nmr=True)
        if not audit['disjoint']:
            raise ValueError(f'Train/validation structures overlap: {audit["overlaps"]}')
        counts['examples'] = sum(counts.values())
        summary = {'format_version': 2, 'domain': 'experimental', 'counts': counts,
                   'split_method': 'preserved user-supplied roles; connectivity overlap checked',
                   'test_used': False, 'source_views': [train.fingerprint(), validation.fingerprint()]}
        verification = {'status': 'passed', 'validator': 'openmolspec.training.prepare_nmr_training',
                        'counts': counts, 'files': {k: {'sha256': sha256(v.path)} for k, v in views.items()},
                        'split_audit': audit, 'test_used': False}
        (staging / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        (staging / 'verification.json').write_text(json.dumps(verification, indent=2) + '\n')
        staging.rename(destination)
    return destination


@dataclass
class TrainingPlan:
    """Training configuration for the NMR dual encoder or molecular generator.

    Parameters
    ----------
    data_dir : str or pathlib.Path
        Prepared directory returned by :func:`prepare_nmr_training`.
    run_dir : str or pathlib.Path
        New directory for logs, configuration and model checkpoints.
    stage : {'align', 'generate'}, default 'align'
        Dual-encoder alignment or autoregressive SMILES generation.
    checkpoint : str or None, default None
        Weights used to initialize the selected stage.
    alignment_checkpoint : str or None, default None
        Spectral/molecular encoder checkpoint used by the generation stage.
    python : str, default sys.executable
        Interpreter of the training environment.
    device : str, default 'cpu'
        Torch training device.
    epochs : int, default 10
        Number of training epochs.
    batch_size : int, default 32
        Number of examples per minibatch, at least two.
    learning_rate : float, default 0.0001
        Optimizer learning rate.
    seed : int, default 2026
        Seed for model initialization and data order.
    parameters : dict, optional
        Stage-specific options. Alignment accepts ``hidden_size``, ``heads``,
        ``encoder_layers``, ``decoder_layers``, ``feedforward_size``,
        ``projection_size``, ``alignment_temperature``, ``input_representation``,
        ``max_source_tokens``, ``max_val_examples`` and ``early_stop_patience``.
        Generation accepts ``alignment_loss_weight``, ``max_val_batches``,
        ``generate_examples`` and ``beam_size``. Both stages accept
        ``max_train_batches``, ``shuffle_buffer``, ``drop_h_prob``,
        ``drop_c_prob``, ``log_every`` and ``tqdm``.

    Examples
    --------
    >>> plan = TrainingPlan('prepared-nmr', 'runs/encoder',
    ...     epochs=20, batch_size=64, device='cuda:0')
    >>> settings = plan.describe()
    >>> validation = plan.validate()
    >>> result = plan.run()
    """
    data_dir: str | Path
    run_dir: str | Path
    stage: str = 'align'
    checkpoint: str | None = None
    alignment_checkpoint: str | None = None
    python: str = sys.executable
    device: str = 'cpu'
    epochs: int = 10
    batch_size: int = 32
    learning_rate: float = 1e-4
    seed: int = 2026
    parameters: dict = field(default_factory=dict)

    def __post_init__(self):
        self.data_dir = Path(self.data_dir).expanduser().resolve()
        self.run_dir = Path(self.run_dir).expanduser().resolve()
        if self.stage not in ('align', 'generate'):
            raise ValueError('stage must be align or generate')
        if self.epochs < 1 or self.batch_size < 2 or not math.isfinite(self.learning_rate) or self.learning_rate <= 0:
            raise ValueError('Require positive epochs/rate and batch_size >= 2')
        if self.stage == 'generate' and not self.alignment_checkpoint:
            raise ValueError('Generation training requires an explicit alignment_checkpoint')
        allowed = {'max_train_batches', 'shuffle_buffer', 'drop_h_prob', 'drop_c_prob', 'log_every', 'tqdm'}
        allowed |= ({'max_val_examples', 'hidden_size', 'heads', 'encoder_layers', 'decoder_layers',
                     'feedforward_size', 'projection_size', 'alignment_temperature', 'input_representation',
                     'max_source_tokens', 'early_stop_patience'} if self.stage == 'align' else
                    {'alignment_loss_weight', 'max_val_batches', 'generate_examples', 'beam_size'})
        if set(self.parameters) - allowed:
            raise ValueError(f'Unsupported training parameters: {set(self.parameters) - allowed}')

    @property
    def command(self):
        """list of str: Training command with the current plan's arguments."""
        values = {'data_dir': self.data_dir, 'run_dir': self.run_dir, 'epochs': self.epochs,
                  'batch_size': self.batch_size, 'learning_rate': self.learning_rate,
                  'seed': self.seed, 'device': self.device, **self.parameters}
        if self.checkpoint:
            values['init_checkpoint' if self.stage == 'align' else 'init_generate_checkpoint'] = Path(self.checkpoint).resolve()
        if self.alignment_checkpoint:
            values['alignment_checkpoint'] = Path(self.alignment_checkpoint).resolve()
        command = [str(self.python), '-m', 'spec2struct_fork.train', self.stage]
        for key, value in values.items():
            command += ['--' + key.replace('_', '-'), str(value)]
        return command

    def describe(self):
        """Return the training command and configuration summary.

        Returns
        -------
        dict
            Command arguments, validation state and checkpoint settings.
        """
        return {'command': self.command, 'training_performed': False,
                'validation': 'pending until validate() or fit()', 'uses_test_split': False,
                'checkpoint_recovery': 'initializes model weights; optimizer/scheduler state is not resumed'}

    def validate(self):
        """Check the prepared data, checksums, roles and checkpoint files.

        Returns
        -------
        dict
            ``validated=True`` with the train/validation split audit.

        Raises
        ------
        ValueError
            If data metadata, file checksums, batch sizes or split identities
            fail the training requirements.
        FileNotFoundError
            If a configured initialization checkpoint is absent.
        """
        summary = json.loads((self.data_dir / 'summary.json').read_text())
        verification = json.loads((self.data_dir / 'verification.json').read_text())
        if summary.get('format_version') != 2 or verification.get('status') != 'passed':
            raise ValueError('Use a verified format-2 H/C dataset')
        if verification.get('counts', {}).get('examples') != summary.get('counts', {}).get('examples'):
            raise ValueError('Summary and verification record counts disagree')
        if summary['counts'].get('train', 0) < self.batch_size or summary['counts'].get('val', 0) < 2:
            raise ValueError('Insufficient training/validation records for the batch configuration')
        views = {}
        for split in ('train', 'val'):
            path = self.data_dir / f'{split}.jsonl'
            if sha256(path) != verification['files'][split]['sha256']:
                raise ValueError(f'{split} file changed since verification')
            views[split] = SpectraSplit(path, split, 'training', 'experimental')
        audit = audit_splits(views, check_nmr=True)
        if audit['records'] != {k: summary['counts'][k] for k in ('train', 'val')}:
            raise ValueError('Actual record counts disagree with the prepared summary')
        if not audit['disjoint']:
            raise ValueError(f'Training/validation molecular leakage: {audit["overlaps"]}')
        for key in ('checkpoint', 'alignment_checkpoint'):
            path = getattr(self, key)
            if path and not Path(path).is_file():
                raise FileNotFoundError(path)
        return {'validated': True, 'training_performed': False, 'uses_test_split': False, 'split_audit': audit}

    def run(self):
        """Train, validate and return the best checkpoint.

        Returns
        -------
        dict
            ``checkpoint`` path, its ``checkpoint_sha256`` and training status.
            The run directory also contains ``plan.json``, ``training.log``
            and ``result.json``.

        Raises
        ------
        FileExistsError
            If the run directory already exists.
        RuntimeError
            If the trainer finishes without a best checkpoint.
        """
        if self.run_dir.exists():
            raise FileExistsError('Choose a new run directory to preserve existing training artifacts')
        validation = self.validate()
        self.run_dir.mkdir(parents=True)
        (self.run_dir / 'plan.json').write_text(json.dumps({**self.describe(), 'preflight': validation}, indent=2))
        with (self.run_dir / 'training.log').open('w') as log:
            subprocess.run(runtime_command(self.python, 'spec2struct_fork.train', self.command[3:]),
                           env=runtime_env(), stdout=log, stderr=subprocess.STDOUT, check=True)
        checkpoints = list(self.run_dir.glob('*/best.pt'))
        if len(checkpoints) != 1:
            raise RuntimeError('Trainer did not produce exactly one best checkpoint; inspect training.log')
        result = {'training_performed': True, 'checkpoint': str(checkpoints[0]),
                  'checkpoint_sha256': sha256(checkpoints[0]), 'uses_test_split': False}
        (self.run_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        return result
