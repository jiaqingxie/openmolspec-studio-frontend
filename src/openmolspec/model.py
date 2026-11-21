"""Public model facades. Heavy dependencies load only inside the selected runtime."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from ._runtime import invoke
from .solution_shifts import SolutionShiftPredictor as SolutionShiftPredictor
from .assigned_shifts import PeakSpectrumPredictor as PeakSpectrumPredictor


class _ConfiguredModel:
    def save_config(self, path):
        """Save model and runtime settings as JSON.

        Parameters
        ----------
        path : str or pathlib.Path
            New configuration file to create. It stores the model class,
            checkpoint paths, runtime interpreter and device settings.

        Raises
        ------
        FileExistsError
            If the destination already exists.
        """
        with Path(path).open('x') as stream:
            json.dump({'class': type(self).__name__, 'parameters': self.config}, stream, indent=2)

    @classmethod
    def from_config(cls, path, **overrides):
        """Construct a model from a saved configuration.

        Parameters
        ----------
        path : str or pathlib.Path
            JSON file written by :meth:`save_config`.
        **overrides
            Constructor options to replace, such as ``python`` or ``device``.

        Returns
        -------
        model instance
            Configured instance of the requested model class.
        """
        data = json.loads(Path(path).read_text())
        if data['class'] != cls.__name__:
            raise ValueError('Configuration belongs to a different model class')
        return cls(**{**data['parameters'], **overrides})

    def _call(self, **request):
        return invoke({**self.config, **request}, python=self.config.get('python'))


class NMRNet(_ConfiguredModel):
    """Predict atomwise H/C chemical shifts and assign NMR peaks.

    Parameters
    ----------
    models_root : str or pathlib.Path
        Directory containing ``nmrnet/nmrnet-orig`` and ``nmrnet/weights``.
    nucleus : {'1H', '13C'}, default '13C'
        Nucleus to predict with the liquid-state fold-0 checkpoint and scaler.
    python : str or None, default None
        Interpreter of the NMR model environment. ``None`` selects the current
        Python interpreter.
    device : {'cpu'}, default 'cpu'
        Device used by the NMRNet runtime adapter.

    Examples
    --------
    >>> model = NMRNet.from_pretrained('models', nucleus='13C',
    ...     python='/path/to/nmr-env/bin/python')
    >>> prediction = model.predict('CCO')
    >>> shifts = prediction['records'][0]['prediction_ppm']

    Atom indices follow the zero-based RDKit ``AddHs`` graph of the input SMILES.
    """
    capabilities = {'predict': True, 'assign': True, 'fit': False, 'nuclei': ('1H', '13C'),
                    'domain': 'solution NMR', 'training_overlap': 'unverified'}

    def __init__(self, *, models_root, nucleus='13C', python=None, device='cpu'):
        if nucleus not in self.capabilities['nuclei']:
            raise ValueError('NMRNet supports 1H and 13C here. Use SolutionShiftPredictor for 19F and 31P.')
        if device != 'cpu':
            raise ValueError('This author-runtime adapter currently supports CPU inference')
        self.config = {'models_root': str(Path(models_root).expanduser().resolve()),
                       'nucleus': nucleus, 'python': str(python or sys.executable), 'device': device}

    @classmethod
    def from_pretrained(cls, models_root, **kwargs):
        """Create an NMRNet predictor from a model-assets directory.

        Parameters
        ----------
        models_root : str or pathlib.Path
            Directory containing the NMRNet source and weights.
        **kwargs
            ``nucleus``, ``python`` and ``device`` constructor settings.

        Returns
        -------
        NMRNet
            Configured chemical-shift predictor.
        """
        return cls(models_root=models_root, **kwargs)

    def predict(self, smiles):
        """Predict chemical shifts for one molecule or a batch.

        Parameters
        ----------
        smiles : str or iterable of str
            Molecular structures as SMILES strings.

        Returns
        -------
        dict
            ``records`` contains one dictionary per molecule, with ``smiles``,
            ``nucleus``, ``atom_indices`` and ``prediction_ppm``. Runtime and
            checkpoint information is returned in ``provenance``.
        """
        if isinstance(smiles, str):
            smiles = [smiles]
        smiles = list(smiles)
        if not smiles or any(not isinstance(s, str) or not s.strip() for s in smiles):
            raise ValueError('Supply nonempty SMILES strings')
        return self._call(backend='nmrnet', smiles=smiles)

    def assign(self, smiles, peaks_ppm, *, tolerance_ppm=None):
        """Match measured peak positions to predicted atomic environments.

        Parameters
        ----------
        smiles : str
            Known molecular structure.
        peaks_ppm : iterable of float
            Measured chemical shifts in ppm, in the desired peak-index order.
        tolerance_ppm : float or None, default None
            Maximum peak/site residual. The default is 0.5 ppm for H and 5 ppm
            for C.

        Returns
        -------
        dict
            Assignments with peak indices, candidate atom indices, predicted
            shifts, residuals and unmatched peaks/sites.
        """
        return self._call(backend='nmrnet', smiles=[smiles], peaks_ppm=list(peaks_ppm),
                          tolerance_ppm=tolerance_ppm)


class NMRTransformer(_ConfiguredModel):
    """Retrieve and generate molecular structures from experimental NMR.

    Parameters
    ----------
    checkpoint : str or pathlib.Path or None, default None
        Alignment or generation checkpoint for prediction or initialization.
    stage : {'align', 'generate'}, default 'generate'
        ``'align'`` selects the dual encoder; ``'generate'`` selects the molecular
        decoder. The stage also determines the training plan.
    python : str or None, default None
        Interpreter containing the NMR Transformer dependencies.
    device : str, default 'cpu'
        Torch device, for example ``'cpu'`` or ``'cuda:0'``.

    Examples
    --------
    >>> model = NMRTransformer.from_pretrained('alignment.pt', stage='align')
    >>> ranking = model.retrieve(query, ['CCO', 'COC'], top_k=2)
    """
    capabilities = {'predict': True, 'retrieve': True, 'fit': True,
                    'training_validation': 'encoder and generator each completed one-step train/save/reload inference verification; software integration only'}

    def __init__(self, *, checkpoint=None, stage='generate', python=None, device='cpu'):
        if stage not in ('align', 'generate'):
            raise ValueError('stage must be align or generate')
        self.config = {'checkpoint': str(Path(checkpoint).expanduser().resolve()) if checkpoint else None,
                       'stage': stage, 'python': str(python or sys.executable), 'device': device}

    @classmethod
    def from_pretrained(cls, checkpoint, **kwargs):
        """Configure a pretrained alignment or generation model.

        Parameters
        ----------
        checkpoint : str or pathlib.Path
            Trained checkpoint file.
        **kwargs
            Model ``stage``, runtime ``python`` and ``device`` settings.

        Returns
        -------
        NMRTransformer
            Model configured for the requested stage.
        """
        return cls(checkpoint=checkpoint, **kwargs)

    def predict(self, records, *, beam_size=5):
        """Generate SMILES candidates from NMR spectra and molecular formulae.

        Parameters
        ----------
        records : dict or iterable of dict
            Each query contains ``formula``, ``h_nmr``, ``c_nmr`` and optional
            ``modality_mask``. NMR records store ``chemical_shift`` text and
            optional multiplicity, integration, coupling, solvent and frequency.
        beam_size : int, default 5
            Number of candidate sequences explored by beam search.

        Returns
        -------
        dict
            Generated candidates with SMILES, model scores, validity and
            molecular-formula agreement.
        """
        if self.config['stage'] != 'generate':
            raise ValueError('Prediction requires a generate-stage model; use retrieve for align')
        if beam_size < 1:
            raise ValueError('beam_size must be positive')
        records = [records] if isinstance(records, dict) else list(records)
        if not records or any(not row.get('formula') for row in records):
            raise ValueError('Each generation query requires an explicitly supplied formula')
        return self._call(backend='nmr_transformer', records=records, beam_size=beam_size)

    def retrieve(self, query, candidates, *, top_k=10):
        """Rank candidate molecules for an NMR query.

        Parameters
        ----------
        query : dict
            H/C NMR records and their ``modality_mask``.
        candidates : iterable of str
            Candidate molecular SMILES.
        top_k : int, default 10
            Number of ranked candidates to return.

        Returns
        -------
        dict
            Candidate identities and embedding similarity scores in rank order.
        """
        if self.config['stage'] != 'align':
            raise ValueError('Retrieval requires an align-stage checkpoint')
        if top_k < 1 or isinstance(candidates, str):
            raise ValueError('Supply positive top_k and a list of candidate SMILES')
        return self._call(backend='nmr_transformer', records=[query], candidates=list(candidates), top_k=top_k)

    def training_plan(self, data_dir, *, run_dir, **kwargs):
        """Create a training plan for the current model stage.

        Parameters
        ----------
        data_dir : str or pathlib.Path
            Directory returned by ``prepare_nmr_training``.
        run_dir : str or pathlib.Path
            New output directory for logs and checkpoints.
        **kwargs
            :class:`openmolspec.training.TrainingPlan` options, including
            ``epochs``, ``batch_size``, ``learning_rate`` and ``parameters``.

        Returns
        -------
        openmolspec.training.TrainingPlan
            Plan that can be inspected, validated and passed to :meth:`fit`.
        """
        from .training import TrainingPlan
        return TrainingPlan(data_dir=data_dir, run_dir=run_dir, stage=self.config['stage'],
                            checkpoint=self.config['checkpoint'], python=self.config['python'],
                            device=self.config['device'], **kwargs)

    def fit(self, plan):
        """Train the model and select the best validation checkpoint.

        Parameters
        ----------
        plan : openmolspec.training.TrainingPlan
            Training settings for the same stage as this model.

        Returns
        -------
        dict
            Best checkpoint path and SHA-256. The model's configuration is
            updated to use the newly trained checkpoint.
        """
        from .training import TrainingPlan
        if not isinstance(plan, TrainingPlan) or plan.stage != self.config['stage']:
            raise ValueError('Use a TrainingPlan with the same stage as this model')
        result = plan.run()
        self.config['checkpoint'] = result['checkpoint']
        return result


class GapModel(_ConfiguredModel):
    """Predict the HOMO–LUMO energy gap from molecular spectra.

    Parameters
    ----------
    root : str or pathlib.Path
        openSpec model-assets directory.
    python : str or None, default None
        Interpreter containing the openSpec model dependencies.
    device : str, default 'cpu'
        Torch device used for inference.

    Examples
    --------
    >>> model = GapModel(root='models/openspec', python='/path/to/model/python')
    >>> result = model.predict(inputs)
    >>> gap_ev = result['gap_ev']
    """
    capabilities = {'predict': True, 'fit': False, 'domain': 'computed spectra'}

    def __init__(self, *, root, python=None, device='cpu'):
        self.config = {'root': str(Path(root).expanduser().resolve()),
                       'python': str(python or sys.executable), 'device': device}

    def predict(self, inputs, *, allow_missing_modalities=False):
        """Predict a molecular energy gap in eV.

        Parameters
        ----------
        inputs : dict
            ``ir`` and ``raman`` are 1024-point intensity arrays on the
            400–4000 cm⁻¹ grid; ``nmr_h`` and ``nmr_c`` contain shifts in ppm.
        allow_missing_modalities : bool, default False
            Set to ``True`` to evaluate a selected subset of channels.

        Returns
        -------
        dict
            Predicted ``gap_ev``, checkpoint information and channel settings.
        """
        return self._call(backend='gap', inputs=inputs, allow_missing_modalities=allow_missing_modalities)


class Vib2Mol(GapModel):
    """Generate, retrieve and rerank structures with the openSpec Vib2Mol model.

    Parameters
    ----------
    root : str or pathlib.Path
        Directory containing spectral encoders, molecular decoder, tokenizer
        and matching checkpoints.
    python : str or None, default None
        Interpreter containing the openSpec dependencies.
    device : str, default 'cpu'
        Torch inference device.
    """
    capabilities = {'predict': True, 'retrieve': True, 'fit': False, 'domain': 'computed spectra'}

    def predict(self, inputs, *, top_k=10, allow_missing_modalities=False):
        """Generate molecular structures from IR, Raman and NMR spectra.

        Parameters
        ----------
        inputs : dict
            Spectral arrays with keys ``ir``, ``raman``, ``nmr_h`` and ``nmr_c``;
            see :meth:`GapModel.predict` for their units and shapes.
        top_k : int, default 10
            Number of candidates to return, between 1 and 10.
        allow_missing_modalities : bool, default False
            Enable inference on a subset of spectral channels.

        Returns
        -------
        dict
            Canonical candidate structures, decoding/matching scores and
            checkpoint metadata, using beam size 10 and ITM reranking.
        """
        if not 1 <= top_k <= 10:
            raise ValueError('The beam=10 protocol supports top_k between 1 and 10')
        return self._call(backend='vib2mol', inputs=inputs, top_k=top_k,
                          allow_missing_modalities=allow_missing_modalities)

    def retrieve(self, inputs, candidates, *, top_k=10, rerank=False, allow_missing_modalities=False):
        """Rank a supplied molecular library against a spectral query.

        Parameters
        ----------
        inputs : dict
            IR/Raman intensity arrays and H/C shift arrays.
        candidates : iterable of str
            Candidate structures as SMILES.
        top_k : int, default 10
            Number of ranked structures to return.
        rerank : bool, default False
            Use the ITM matching head when ``True``; otherwise use embedding
            cosine similarity.
        allow_missing_modalities : bool, default False
            Enable inference with selected channels omitted.

        Returns
        -------
        dict
            ``candidate_pool``, ranking method, and ``candidates`` with SMILES
            and their scores in descending order.
        """
        if top_k < 1 or isinstance(candidates, str):
            raise ValueError('Supply positive top_k and a list of candidate structures')
        return self._call(backend='vib2mol', inputs=inputs, candidates=list(candidates), top_k=top_k,
                          rerank=rerank, allow_missing_modalities=allow_missing_modalities)


class MSPredictor(_ConfiguredModel):
    """Predict tandem mass spectra with GLACIER or ICEBERG.

    Parameters
    ----------
    model : {'glacier', 'iceberg'}
        Spectrum-prediction architecture.
    source : str or pathlib.Path
        Directory containing the ``ms-pred`` implementation.
    weights : str or pathlib.Path
        Checkpoint or checkpoint directory for the selected architecture.
    python : str or None, default None
        Interpreter of the MS model environment.
    device : str, default 'cpu'
        Inference device.
    author_baseline : bool, default False
        Return the original checkpoint intensities for comparison.
    """
    capabilities = {'predict': True, 'fit': False, 'domain': 'experimental MS/MS'}

    def __init__(self, *, model, source, weights, python=None, device='cpu', author_baseline=False):
        if model not in ('glacier', 'iceberg'):
            raise ValueError('model must be glacier or iceberg')
        if not isinstance(author_baseline, bool):
            raise ValueError('author_baseline must be a boolean')
        self.config = {'model': model, 'author_baseline': author_baseline, 'source': str(Path(source).expanduser().resolve()),
                       'weights': str(Path(weights).expanduser().resolve()),
                       'python': str(python or sys.executable), 'device': device}

    def predict(self, *, smiles, adduct, collision_energy, instrument, precursor_mz=None):
        """Predict fragment m/z values and relative intensities.

        Parameters
        ----------
        smiles : str
            Molecular structure.
        adduct : str
            Ion type, for example ``'[M+H]+'`` or ``'[M+Na]+'``.
        collision_energy : float
            Collision energy in the checkpoint's acquisition convention.
        instrument : str
            Instrument category, for example ``'Orbitrap'`` or ``'QTOF'``.
        precursor_mz : float or None, default None
            Measured precursor mass-to-charge ratio when available.

        Returns
        -------
        dict
            Numerical predicted MS/MS peaks and the acquisition/model metadata.
        """
        return self._call(backend='ms', molecule={'smiles': smiles, 'adduct': adduct,
                          'collision_energy': collision_energy, 'instrument': instrument,
                          'precursor_mz': precursor_mz})
