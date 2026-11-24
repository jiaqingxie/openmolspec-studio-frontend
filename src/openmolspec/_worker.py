"""Internal JSON worker for optional model environments; no training dispatch."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace


def released_shift(request):
    """Return a single prediction from an installed, validation-selected solution NMR model."""
    from openmolspec_bench.data import sha256

    directory = Path(request["model_dir"])
    config = json.loads((directory / "model.json").read_text())
    nucleus = request["nucleus"]
    if config.get("nucleus") != nucleus:
        raise ValueError("Configured checkpoint nucleus differs from the requested nucleus")
    engine = config.get("engine", "lightgbm")
    if engine == "peak_spectrum":
        from .assigned_shifts import PeakSpectrumPredictor
        predictor = PeakSpectrumPredictor(directory)
    else:
        from .solution_shifts import SolutionShiftPredictor
        predictor = SolutionShiftPredictor(directory)
    record = predictor.predict(request["smiles"], request.get("solvent"))
    if engine == "peak_spectrum":
        if not record["peaks"]:
            raise ValueError("This molecule has no site of the requested nucleus")
        record["atom_indices"] = [p["atom_indices"] for p in record["peaks"]]
    digest = config.get("gnn_sha256") or config.get("booster_sha256") or sha256(directory / "model.json")
    return dict(task="nmr.forward." + nucleus, model=engine, records=[record],
                checkpoint_sha256=digest, unit="ppm")


def nmrnet(request):
    from rdkit import Chem
    from openmolspec_bench.assignment import predict_atoms, assign_peaks
    symbol = {'1H': 'H', '13C': 'C'}[request['nucleus']]
    with tempfile.TemporaryDirectory(prefix='openmolspec-nmrnet-') as temporary:
        values, provenance = predict_atoms(request['smiles'], symbol, request['models_root'], Path(temporary) / 'run')
    records = []
    for i, smiles in enumerate(request['smiles']):
        indices = [a.GetIdx() for a in Chem.AddHs(Chem.MolFromSmiles(smiles)).GetAtoms() if a.GetSymbol() == symbol]
        records.append({'smiles': smiles, 'nucleus': request['nucleus'], 'atom_indices': indices,
                        'prediction_ppm': values[i].tolist()})
    result = {'records': records, 'unit': 'ppm', 'provenance': provenance,
              'atom_index_basis': 'zero-based RDKit AddHs(input SMILES)',
              'training_performed': False, 'inference_mode': 'direct_frozen_checkpoint'}
    if 'peaks_ppm' in request:
        tolerance = request.get('tolerance_ppm')
        if tolerance is None:
            tolerance = .5 if symbol == 'H' else 5.
        result['assignment'] = assign_peaks(request['smiles'][0], symbol, values[0], request['peaks_ppm'], tolerance)
    return result


def nmr_transformer(request):
    import torch
    from rdkit import Chem
    from openmolspec.dataset import _nmr, sha256
    from spec2struct_fork.model import ModelConfig, SpectrumToSmiles, encode_source
    from spec2struct_fork.structured import encode_structured_source
    from spec2struct_fork.train import rank_candidates, make_collate
    path = Path(request['checkpoint'] or '')
    if not path.is_file():
        raise FileNotFoundError('Supply a released checkpoint for inference')
    payload = torch.load(path, map_location='cpu', weights_only=True)
    if payload['training_stage'] != request['stage']:
        raise ValueError('Checkpoint stage disagrees with model configuration')
    model = SpectrumToSmiles(ModelConfig(**payload['config']))
    model.load_state_dict(payload['model'])
    model.to(request['device']).eval()
    result = {'training_performed': False, 'inference_mode': 'direct_frozen_checkpoint',
              'provenance': {'checkpoint_sha256': sha256(path), 'stage': request['stage']}}
    with torch.inference_mode():
        if request['stage'] == 'generate':
            encoder = encode_structured_source if model.config.input_representation == 'structured' else encode_source
            records = []
            for raw in request['records']:
                row = _nmr(raw)
                source = encoder(row['formula'], row['h_nmr'], row['c_nmr'], row['modality_mask'], model.config.max_source)
                ranked = rank_candidates(model.beam_search(source, request['beam_size']), row['formula'])
                records.append({'candidates': ranked, 'given_formula': row['formula'], 'modality_mask': row['modality_mask']})
            result['records'] = records
        else:
            query = _nmr(request['records'][0])
            identities = []
            for smiles in request['candidates']:
                mol = Chem.MolFromSmiles(smiles)
                if mol is None or not mol.GetNumAtoms():
                    raise ValueError('Invalid candidate SMILES')
                identity = Chem.MolToSmiles(mol, isomericSmiles=True)
                if identity not in identities:
                    identities.append(identity)
            if not identities:
                raise ValueError('Supply at least one candidate structure')
            collate = make_collate(model.config, include_formula=False)
            scores = []
            for start in range(0, len(identities), 32):
                chunk = identities[start:start + 32]
                source, target, _ = collate([{**query, 'smiles': s} for s in chunk])
                spectra, molecules = model.alignment_embeddings(source.to(request['device']), target.to(request['device']))
                scores.extend((molecules @ spectra[0]).cpu().tolist())
            order = sorted(range(len(scores)), key=lambda i: -scores[i])[:request['top_k']]
            result.update(given_formula=False, candidate_pool=len(identities),
                          candidates=[{'smiles': identities[i], 'score': scores[i]} for i in order])
    return result


def vibrational(request):
    import numpy as np
    from openmolspec_ui.config import discover_assets
    from openmolspec_ui.inference import OpenMolSpecService
    from openmolspec_ui.spectra import SpectralInput
    from openmolspec_ui import vib_shift_adapter
    inputs = request['inputs']
    arrays = {k: np.asarray(inputs[k], dtype=float) if inputs.get(k) is not None else None
              for k in ('ir', 'raman', 'nmr_h', 'nmr_c')}
    dedicated_gap = request['backend'] == 'gap' and all(arrays[k] is None or not arrays[k].size for k in ('nmr_h', 'nmr_c'))
    for key, values in arrays.items():
        if values is not None and (values.ndim != 1 or not np.isfinite(values).all() or (key in ('ir', 'raman') and len(values) != 1024)):
            raise ValueError(f'Invalid {key} array')
    spectral = SpectralInput(**arrays)
    estimate = request.get('estimate_missing_nmr', 'candidates' not in request)
    adapted_library = ('candidates' in request and estimate and vib_shift_adapter.supports(spectral))
    if 'candidates' in request and estimate and not adapted_library:
        raise ValueError('Shift estimation requires IR + Raman without measured NMR')
    dedicated_generation = (request['backend'] == 'vib2mol' and 'candidates' not in request
                            and estimate and vib_shift_adapter.supports(spectral))
    ablation = not (dedicated_gap or dedicated_generation or adapted_library) and any(v is None or not v.size for v in arrays.values())
    if ablation and not request['allow_missing_modalities']:
        raise ValueError('Explicitly opt into missing-modality ablations for this combination of channels')
    service = OpenMolSpecService(discover_assets(Path(request['root'])), device=request['device'])
    if request['backend'] == 'gap':
        result = service.predict_gap(spectral)
    elif 'candidates' not in request:
        result = service.generate(spectral, request['top_k'], ranking=request.get('ranking','beam'),
                                  estimate_missing_nmr=estimate)
    else:
        import torch
        import torch.nn.functional as functional
        from rdkit import Chem
        model, tokenizer, device = service._load_vib2mol(1)
        from benchmarks.models.vib2mol.evaluate_multimodal import encode_spectra, rerank_candidates
        candidates = []
        for smiles in request['candidates']:
            molecule = Chem.MolFromSmiles(smiles)
            if molecule is None or not molecule.GetNumAtoms():
                raise ValueError('Invalid candidate SMILES')
            identity = Chem.MolToSmiles(molecule, isomericSmiles=True)
            if identity not in candidates:
                candidates.append(identity)
        if not candidates:
            raise ValueError('Supply at least one candidate')
        # Match the author protocol: nonisomeric Kekule input, original identities in output.
        strings = [Chem.MolToSmiles(Chem.MolFromSmiles(s), kekuleSmiles=True, isomericSmiles=False) for s in candidates]
        if adapted_library:
            spectral = vib_shift_adapter.with_estimated_shifts(spectral)
        data = service._vib2mol_input(spectral, device)
        with torch.inference_mode():
            order = list(range(len(strings)))
            shortlist = request.get('shortlist')
            if not request['rerank'] or shortlist is not None:
                query = functional.normalize(encode_spectra(model, data)['proj_output'], dim=-1)
                scores = []
                for start in range(0, len(strings), 32):
                    tokens = tokenizer(strings[start:start+32], padding=True, truncation=False, return_tensors='pt')
                    ids, mask = tokens['input_ids'].to(device), tokens['attention_mask'].to(device)
                    if ids.shape[1] > tokenizer.model_max_length or (ids == tokenizer.unk_token_id).any():
                        raise ValueError('Candidate exceeds the tokenizer vocabulary or length limit')
                    mask = torch.cat((mask.new_ones((len(mask), 1)), mask), dim=1)
                    molecular = functional.normalize(model.molecular_encoder(model.molecular_encoding(ids, use_cls_token=True), mask=mask)['proj_output'], dim=-1)
                    scores.extend((molecular @ query[0]).cpu().tolist())
                order = sorted(order, key=lambda i: -scores[i])
                ranked = [scores[i] for i in order]
            if request['rerank']:
                pool = order[:shortlist]
                indices, ranked = rerank_candidates(model, tokenizer, data, [strings[i] for i in pool], 32)
                order = [pool[i] for i in indices]
        result = {'candidate_pool': len(candidates), 'ranking': 'itm_probability' if request['rerank'] else 'cosine_similarity',
                  'itm_candidates_scored': len(order) if request['rerank'] else 0,
                  'candidates': [{'smiles': candidates[i], 'score': float(score)}
                                 for i, score in list(zip(order, ranked))[:request['top_k']]]}
    from openmolspec.dataset import sha256
    weight_paths = ([service.assets.gap_checkpoint] if request['backend'] == 'gap' else
                    [service.assets.retrieval_checkpoint] + ([] if 'candidates' in request else [service.assets.generation_checkpoint]))
    if dedicated_gap:
        from importlib.resources import files
        weight_paths = [files("openmolspec").joinpath("assets", "gap_vibrational.npz")]
    if adapted_library:
        result.update(input_modalities=["IR", "Raman"], inference_mode="vibrational_shift_estimation_then_library_ranking",
                      estimated_shifts_ppm={"1H": spectral.nmr_h.tolist(), "13C": spectral.nmr_c.tolist()})
    if dedicated_generation or adapted_library:
        weight_paths.append(vib_shift_adapter.weights_file())
    result['checkpoints'] = [{'name': path.name, 'sha256': sha256(path)} for path in weight_paths]
    result.setdefault('inference_mode', 'direct_frozen_checkpoint')
    result.update(training_performed=False, missing_modality_ablation=ablation)
    return result


def main():
    source, output = map(Path, sys.argv[1:])
    request = json.loads(source.read_text())
    if request['backend'] not in ('released_shift', 'carbon_folds','assigned_sites','vib_reference'):
        import torch
        torch.set_num_threads(2)
    if request['backend'] == 'released_shift':
        result = released_shift(request)
    elif request['backend'] == 'assigned_sites':
        from openmolspec.assigned_shifts import AssignedShiftPredictor
        from openmolspec_bench.assignment import assign_peaks
        root = Path(request['model_dir'])
        nucleus = request['nucleus']
        directory = root if (root / 'model.json').is_file() else root / (nucleus + '-assigned')
        model = AssignedShiftPredictor(directory)
        if model.nucleus != nucleus:
            raise ValueError('Assigned-site model nucleus mismatch')
        values = model.assignment_predictions(request['smiles'],request.get('solvent'))
        tolerance = request.get('tolerance')
        result = assign_peaks(request['smiles'],'H' if nucleus == '1H' else 'C',values,request['peaks'],
                              (0.5 if nucleus == '1H' else 5.0) if tolerance is None else tolerance)
        result.update(backend='assigned_sites', provenance=model.config)
    elif request['backend'] == 'nmrnet':
        result = nmrnet(request)
    elif request['backend'] == 'carbon_folds':
        from openmolspec_bench.carbon import predict
        result = predict(request)
    elif request['backend'] == 'nmr_transformer':
        result = nmr_transformer(request)
    elif request['backend'] == 'vib2mol_native':
        from openmolspec_ui.vib_native import generate
        result = generate(request["inputs"],request["formula"],request["checkout"],request["top_k"],request["device"])
    elif request['backend'] in ('gap', 'vib2mol'):
        result = vibrational(request)
    elif request['backend'] == 'vib_reference':
        from openmolspec_bench.vib_reference_library import retrieve_reference
        result = retrieve_reference(request['inputs'],request['candidates'],Path(request['root']),
                                    top_k=request['top_k'],rerank=request['rerank'],shortlist=request['shortlist'])
    elif request['backend'] == 'spectral_language':
        from openmolspec_bench.spectral_language import SpectralLanguageModel
        result = SpectralLanguageModel(request['task'],request['checkpoint'],request['device'],adapter=request.get('adapter')).answer(request['inputs'])
    elif request['backend'] == 'mechfrag_annotation':
        import os
        from openmolspec_bench.mechfrag import FragmentAnnotator
        root = Path(os.environ['OPENMOLSPEC_MECHFRAG_ROOT'])
        study = Path(os.environ.get('OPENMOLSPEC_MECHFRAG_STUDY',root/'runs/single_native_target_060_1123'))
        result = FragmentAnnotator(root,study).annotate(request['inputs'])
    elif request['backend'] == 'ms':
        from openmolspec_bench.ms import predict_request
        query = source.parent / 'molecule.json'
        query.write_text(json.dumps(request['molecule'], allow_nan=False))
        predict_request(SimpleNamespace(model=request['model'], source=Path(request['source']),
                                       weights=Path(request['weights']), device=request['device'], threads=1,
                                       author_baseline=request.get('author_baseline', False), predict_request=query, output=output))
        return
    else:
        raise ValueError('Unknown inference backend')
    output.write_text(json.dumps(result, indent=2, allow_nan=False,
                                 default=lambda value: value.tolist()) + '\n')


if __name__ == '__main__':
    main()
