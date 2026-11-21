"""Internal JSON worker for optional model environments; no training dispatch."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace


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
    inputs = request['inputs']
    arrays = {k: np.asarray(inputs[k], dtype=float) if inputs.get(k) is not None else None
              for k in ('ir', 'raman', 'nmr_h', 'nmr_c')}
    if not request['allow_missing_modalities'] and any(v is None or not v.size for v in arrays.values()):
        raise ValueError('This checkpoint requires IR, Raman, 1H and 13C; explicitly opt into missing-modality ablations')
    for key, values in arrays.items():
        if values is not None and (values.ndim != 1 or not np.isfinite(values).all() or (key in ('ir', 'raman') and len(values) != 1024)):
            raise ValueError(f'Invalid {key} array')
    service = OpenMolSpecService(discover_assets(Path(request['root'])), device=request['device'])
    spectral = SpectralInput(**arrays)
    if request['backend'] == 'gap':
        result = service.predict_gap(spectral)
    elif 'candidates' not in request:
        result = service._generate_vib2mol(spectral, request['top_k'])
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
        data = service._vib2mol_input(spectral, device)
        with torch.inference_mode():
            if request['rerank']:
                order, ranked = rerank_candidates(model, tokenizer, data, strings, 32)
            else:
                query = functional.normalize(encode_spectra(model, data)['proj_output'], dim=-1)
                scores = []
                for start in range(0, len(strings), 32):
                    tokens = tokenizer(strings[start:start+32], padding=True, truncation=False, return_tensors='pt')
                    ids, mask = tokens['input_ids'].to(device), tokens['attention_mask'].to(device)
                    mask = torch.cat((mask.new_ones((len(mask), 1)), mask), dim=1)
                    molecular = functional.normalize(model.molecular_encoder(model.molecular_encoding(ids, use_cls_token=True), mask=mask)['proj_output'], dim=-1)
                    scores.extend((molecular @ query[0]).cpu().tolist())
                order = sorted(range(len(scores)), key=lambda i: -scores[i])
                ranked = [scores[i] for i in order]
        result = {'candidate_pool': len(candidates), 'ranking': 'itm_probability' if request['rerank'] else 'cosine_similarity',
                  'candidates': [{'smiles': candidates[i], 'score': float(score)}
                                 for i, score in list(zip(order, ranked))[:request['top_k']]]}
    from openmolspec.dataset import sha256
    weight_paths = ([service.assets.gap_checkpoint] if request['backend'] == 'gap' else
                    [service.assets.retrieval_checkpoint] + ([] if 'candidates' in request else [service.assets.generation_checkpoint]))
    result['checkpoints'] = [{'name': path.name, 'sha256': sha256(path)} for path in weight_paths]
    result.update(training_performed=False, inference_mode='direct_frozen_checkpoint',
                  missing_modality_ablation=any(v is None or not v.size for v in arrays.values()))
    return result


def main():
    import torch
    torch.set_num_threads(2)
    source, output = map(Path, sys.argv[1:])
    request = json.loads(source.read_text())
    if request['backend'] == 'nmrnet':
        result = nmrnet(request)
    elif request['backend'] == 'carbon_folds':
        from openmolspec_bench.carbon import predict
        result = predict(request)
    elif request['backend'] == 'nmr_transformer':
        result = nmr_transformer(request)
    elif request['backend'] in ('gap', 'vib2mol'):
        result = vibrational(request)
    elif request['backend'] == 'ms':
        from openmolspec_bench.ms import predict_request
        query = source.parent / 'molecule.json'
        query.write_text(json.dumps(request['molecule'], allow_nan=False))
        predict_request(SimpleNamespace(model=request['model'], source=Path(request['source']),
                                       weights=Path(request['weights']), device=request['device'], threads=2,
                                       predict_request=query, output=output))
        return
    else:
        raise ValueError('Unknown inference backend')
    output.write_text(json.dumps(result, indent=2, allow_nan=False,
                                 default=lambda value: value.tolist()) + '\n')


if __name__ == '__main__':
    main()
