"""Public model facades. Heavy dependencies load only inside the selected runtime."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from ._runtime import invoke


class _ConfiguredModel:
    def save_config(self, path):
        """Save a relocatable configuration description, without copying weights."""
        with Path(path).open('x') as stream:
            json.dump({'class': type(self).__name__, 'parameters': self.config}, stream, indent=2)

    @classmethod
    def from_config(cls, path, **overrides):
        data = json.loads(Path(path).read_text())
        if data['class'] != cls.__name__:
            raise ValueError('Configuration belongs to a different model class')
        return cls(**{**data['parameters'], **overrides})

    def _call(self, **request):
        return invoke({**self.config, **request}, python=self.config.get('python'))


class NMRNet(_ConfiguredModel):
    """Frozen liquid H/C NMRNet, fold 0, with the original checkpoint and scaler.

    ``models_root`` contains ``nmrnet/nmrnet-orig`` and ``nmrnet/weights``.
    Atom indices follow RDKit AddHs(input SMILES). No solvent input is available.
    """
    capabilities = {'predict': True, 'assign': True, 'fit': False, 'nuclei': ('1H', '13C'),
                    'domain': 'solution NMR', 'training_overlap': 'unverified'}

    def __init__(self, *, models_root, nucleus='13C', python=None, device='cpu'):
        if nucleus not in self.capabilities['nuclei']:
            raise ValueError('Public NMRNet API supports verified H/C adapters only; B/Si/F/P remain diagnostic')
        if device != 'cpu':
            raise ValueError('This author-runtime adapter currently supports CPU inference')
        self.config = {'models_root': str(Path(models_root).expanduser().resolve()),
                       'nucleus': nucleus, 'python': str(python or sys.executable), 'device': device}

    @classmethod
    def from_pretrained(cls, models_root, **kwargs):
        return cls(models_root=models_root, **kwargs)

    def predict(self, smiles):
        if isinstance(smiles, str):
            smiles = [smiles]
        smiles = list(smiles)
        if not smiles or any(not isinstance(s, str) or not s.strip() for s in smiles):
            raise ValueError('Supply nonempty SMILES strings')
        return self._call(backend='nmrnet', smiles=smiles)

    def assign(self, smiles, peaks_ppm, *, tolerance_ppm=None):
        return self._call(backend='nmrnet', smiles=[smiles], peaks_ppm=list(peaks_ppm),
                          tolerance_ppm=tolerance_ppm)


class NMRTransformer(_ConfiguredModel):
    """Experimental NMR retrieval or formula-conditioned generation; two-stage training."""
    capabilities = {'predict': True, 'retrieve': True, 'fit': True,
                    'training_validation': 'existing trainer; new wrapper has not run a training job'}

    def __init__(self, *, checkpoint=None, stage='generate', python=None, device='cpu'):
        if stage not in ('align', 'generate'):
            raise ValueError('stage must be align or generate')
        self.config = {'checkpoint': str(Path(checkpoint).expanduser().resolve()) if checkpoint else None,
                       'stage': stage, 'python': str(python or sys.executable), 'device': device}

    @classmethod
    def from_pretrained(cls, checkpoint, **kwargs):
        return cls(checkpoint=checkpoint, **kwargs)

    def predict(self, records, *, beam_size=5):
        if self.config['stage'] != 'generate':
            raise ValueError('Prediction requires a generate-stage model; use retrieve for align')
        if beam_size < 1:
            raise ValueError('beam_size must be positive')
        records = [records] if isinstance(records, dict) else list(records)
        if not records or any(not row.get('formula') for row in records):
            raise ValueError('Each generation query requires an explicitly supplied formula')
        return self._call(backend='nmr_transformer', records=records, beam_size=beam_size)

    def retrieve(self, query, candidates, *, top_k=10):
        if self.config['stage'] != 'align':
            raise ValueError('Retrieval requires an align-stage checkpoint')
        if top_k < 1 or isinstance(candidates, str):
            raise ValueError('Supply positive top_k and a list of candidate SMILES')
        return self._call(backend='nmr_transformer', records=[query], candidates=list(candidates), top_k=top_k)

    def training_plan(self, data_dir, *, run_dir, **kwargs):
        from .training import TrainingPlan
        return TrainingPlan(data_dir=data_dir, run_dir=run_dir, stage=self.config['stage'],
                            checkpoint=self.config['checkpoint'], python=self.config['python'],
                            device=self.config['device'], **kwargs)

    def fit(self, plan):
        """Explicitly launch the training plan after file and split validation."""
        from .training import TrainingPlan
        if not isinstance(plan, TrainingPlan) or plan.stage != self.config['stage']:
            raise ValueError('Use a TrainingPlan with the same stage as this model')
        result = plan.run()
        self.config['checkpoint'] = result['checkpoint']
        return result


class GapModel(_ConfiguredModel):
    """Frozen full-input IR/Raman/H/C HOMO–LUMO-gap predictor (eV)."""
    capabilities = {'predict': True, 'fit': False, 'domain': 'computed spectra'}

    def __init__(self, *, root, python=None, device='cpu'):
        self.config = {'root': str(Path(root).expanduser().resolve()),
                       'python': str(python or sys.executable), 'device': device}

    def predict(self, inputs, *, allow_missing_modalities=False):
        return self._call(backend='gap', inputs=inputs, allow_missing_modalities=allow_missing_modalities)


class Vib2Mol(GapModel):
    """Xinyu's frozen multimodal generation and retrieval backend."""
    capabilities = {'predict': True, 'retrieve': True, 'fit': False, 'domain': 'computed spectra'}

    def predict(self, inputs, *, top_k=10, allow_missing_modalities=False):
        if not 1 <= top_k <= 10:
            raise ValueError('The beam=10 protocol supports top_k between 1 and 10')
        return self._call(backend='vib2mol', inputs=inputs, top_k=top_k,
                          allow_missing_modalities=allow_missing_modalities)

    def retrieve(self, inputs, candidates, *, top_k=10, rerank=False, allow_missing_modalities=False):
        if top_k < 1 or isinstance(candidates, str):
            raise ValueError('Supply positive top_k and a list of candidate structures')
        return self._call(backend='vib2mol', inputs=inputs, candidates=list(candidates), top_k=top_k,
                          rerank=rerank, allow_missing_modalities=allow_missing_modalities)


class MSPredictor(_ConfiguredModel):
    """GLACIER/ICEBERG frozen models with explicit acquisition conditions."""
    capabilities = {'predict': True, 'fit': False, 'domain': 'experimental MS/MS'}

    def __init__(self, *, model, source, weights, python=None, device='cpu'):
        if model not in ('glacier', 'iceberg'):
            raise ValueError('model must be glacier or iceberg')
        self.config = {'model': model, 'source': str(Path(source).expanduser().resolve()),
                       'weights': str(Path(weights).expanduser().resolve()),
                       'python': str(python or sys.executable), 'device': device}

    def predict(self, *, smiles, adduct, collision_energy, instrument, precursor_mz=None):
        return self._call(backend='ms', molecule={'smiles': smiles, 'adduct': adduct,
                          'collision_energy': collision_energy, 'instrument': instrument,
                          'precursor_mz': precursor_mz})
