"""Score raw TransPeakNet site predictions against the authors' HSQC annotations."""
import csv
import random
from collections import Counter, defaultdict

import numpy as np
from rdkit import Chem, rdBase
import torch_geometric

from openmolspec.dataset import molspectra
from .transpeaknet import SOLVENT_CLASS, assign_peaks, load_model, peak_list, predict_sites


def site_mae(prediction, annotations):
    indices, carbon, proton = prediction
    by_atom = {a['carbon_atom_index']: a for a in annotations}
    if (len(by_atom) != len(annotations) or len(set(indices)) != len(indices)
            or set(indices) != set(by_atom)):
        raise ValueError("Predicted carbon indices differ from expert indices")
    ordered = [by_atom[i] for i in indices]
    reference_c = np.array([a['carbon_ppm'] for a in ordered])
    # The author notebook compares both ordered output heads, including duplicate H labels.
    reference_h = np.array([a['proton_ppm'] if len(a['proton_ppm']) == 2
                            else a['proton_ppm'] * 2 for a in ordered])
    return {'carbon_mae_ppm': float(np.abs(carbon - reference_c).mean()),
            'proton_mae_ppm': float(np.abs(proton - reference_h).mean())}


def score_web_matches(molecule, prediction, annotations):
    gold = defaultdict(set)
    for atom in annotations:
        for h in atom['proton_ppm']:
            gold[atom['carbon_ppm'], h].add(atom['carbon_atom_index'])
    # Supply only distinct measured coordinates to the existing website matcher.
    peaks = sorted(gold)
    matches, _ = assign_peaks(np.array(peaks), *peak_list(molecule, *prediction))
    correct = sum(m['carbon_atom_index'] in gold[peaks[m['peak_index']]] for m in matches)
    return {'observed': len(peaks), 'matched': len(matches), 'correct': correct}


def run(runner):
    from .runner import require
    args = runner.args
    source = args.transpeaknet_source
    archive = require(source / 'data_annotation/HSQC_Annotation_TestData.zip')
    metadata = require(source / 'data_csv/2dnmr/all_files_testdata_solvent_mw.csv')
    checkpoint = require(source / 'ckpt/model_2dnmr.pt')
    definition = require(source / 'GraphModel/GNN_2d_hsolvent.py')
    ds = molspectra('transpeaknet_hsqc_test', root=archive)
    ds.verify()
    records = list(ds['test'])
    if len({r['source_id'] for r in records}) != len(records):
        raise ValueError("Duplicate spectrum ID in expert archive")
    if args.sampling == 'reservoir' and args.limit < len(records):
        records = random.Random(args.seed).sample(records, args.limit)
    else:
        records = records[:args.limit]
    with metadata.open(newline='', encoding='utf-8-sig') as stream:
        solvent_rows = defaultdict(list)
        for row in csv.DictReader(stream):
            solvent_rows[row['File_name']].append(row)

    model = load_model(source, args.device)
    solvent_name = {code: name for name, code in SOLVENT_CLASS.items()}
    spectra, notebook_rows = [], []
    example = None
    for record in records:
        source_id = record['source_id']
        meta = solvent_rows[source_id]
        if any(row['SMILES'] != record['smiles'] for row in meta):
            raise ValueError(f'{source_id}: original SMILES order differs between files')
        classes = [int(row['solvent_class']) for row in meta]
        unique = set(classes)
        solvent = solvent_name[classes[0]] if len(unique) == 1 else 'unknown'
        status = 'listed' if len(unique) == 1 else 'conflicting' if unique else 'missing'
        molecule = Chem.AddHs(Chem.MolFromSmiles(record['smiles']))
        annotations = record['hsqc_assignments']
        prediction = predict_sites(model, molecule, solvent)
        scores = site_mae(prediction, annotations)
        # Keep every matching metadata row, including repeated classes, in the notebook mean.
        by_solvent = {solvent: scores}
        for code in classes:
            name = solvent_name[code]
            if name not in by_solvent:
                by_solvent[name] = site_mae(predict_sites(model, molecule, name), annotations)
            notebook_rows.append({'source_id': source_id, 'solvent': name, **by_solvent[name]})
        indices, c, h = prediction
        if example is None or source_id == '32869.csv':
            predicted_peaks, atoms = peak_list(molecule, *prediction)
            example = {'sample_id': source_id, 'input': {'smiles': record['smiles'], 'solvent': solvent},
                       'output': {'peaks_c_h_ppm': predicted_peaks.tolist(), 'carbon_atom_index': atoms},
                       'reference': {'peaks_c_h_ppm': record['hsqc_peaks']}}
        spectra.append({'source_id': source_id, 'smiles': record['smiles'], 'solvent': solvent,
                        'solvent_status': status, 'metadata_classes': classes, **scores,
                        'carbon_atom_index': indices, 'carbon_ppm': c.tolist(), 'proton_ppm': h.tolist(),
                        'web_matches': score_web_matches(molecule, prediction, annotations)})

    metric_keys = ('carbon_mae_ppm', 'proton_mae_ppm')
    metrics = {k: float(np.mean([r[k] for r in spectra])) for k in metric_keys}
    counts = Counter()
    for r in spectra:
        counts.update(r['web_matches'])
    return {'dataset_name': 'transpeaknet_hsqc_test', 'dataset': runner.artifact(archive),
            'checkpoint': runner.artifact(checkpoint), 'model_source': runner.artifact(definition),
            'solvent_metadata': runner.artifact(metadata), 'rdkit': rdBase.rdkitVersion,
            'torch_geometric': torch_geometric.__version__, 'seed': args.seed, 'sampling': args.sampling,
            'protocol': 'One vote per spectrum. Unambiguous metadata class, otherwise unknown. '
                        'MAE per carbon index in original SMILES order. Two ordered H outputs per site.',
            'spectra': len(spectra), 'assigned_carbon_sites': sum(len(r['carbon_ppm']) for r in spectra),
            'solvent_status_counts': dict(Counter(r['solvent_status'] for r in spectra)),
            'metrics': metrics, 'predictions': spectra, 'example': example,
            'notebook_protocol': {'scope': 'One vote per matching solvent metadata row.',
                                  'rows': len(notebook_rows), 'spectra': len({r['source_id'] for r in notebook_rows}),
                                  'metrics': {k: float(np.mean([r[k] for r in notebook_rows]))
                                              for k in metric_keys} if notebook_rows else {},
                                  'per_row': notebook_rows},
            'website_assignment': {'protocol': 'One candidate carbon per distinct observed (C,H) pair. '
                                   'Accept any expert carbon sharing the exact pair. Unmatched peaks count as incorrect.',
                                   **counts, 'correct_fraction_of_observed': counts['correct'] / counts['observed'],
                                   'spectra_all_peaks_correct': sum(r['web_matches']['correct'] ==
                                                                    r['web_matches']['observed'] for r in spectra)}}
