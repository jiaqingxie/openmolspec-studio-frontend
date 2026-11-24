"""Small follow-up on the previously audited 512-structure patent NMR pool."""

import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median

import numpy as np
import torch
from rdkit import Chem
from scipy.stats import rankdata

from openmolspec_bench.data import sha256
from openmolspec_bench.metrics import retrieval_metrics
from openmolspec_bench.runner import Runner
from spec2struct_fork.structured import SHIFT, SHIFT_PRESENT, WIDTH, _split_outside_parentheses, parse_nmr_record
from spec2struct_fork.train import make_collate


DATASET = 'patent_test_10k'
WINDOWS = {'h': [(7.26, 0.04), (1.56, 0.06)], 'c': [(77.16, 0.40)]}
EXTRAS = {'h': [(7.26, ' (s)'), (1.56, ' (br s)')],
          'c': [(76.84, ''), (77.16, ''), (77.48, '')]}


def sample_metrics(scores, indices, identities):
    return retrieval_metrics(scores, [identities[i] for i in indices], identities)


def sampling_check(rows, scores, identities):
    heavy_atoms = [Chem.MolFromSmiles(row['smiles']).GetNumHeavyAtoms() for row in rows]
    size = 64
    patent_order = sorted(range(len(rows)), key=lambda i: (rows[i]['patent_id'], identities[i]))
    smallest = sorted(range(len(rows)), key=lambda i: (heavy_atoms[i], identities[i]))
    groups = {'first_patent_ids': patent_order[:size], 'fewest_heavy_atoms': smallest[:size]}
    groups.update({f'random_seed_{seed}': np.random.default_rng(seed).choice(len(rows), size, replace=False).tolist()
                   for seed in range(42, 62)})
    summaries = {}
    for label, indices in groups.items():
        summaries[label] = {**sample_metrics(scores[indices], indices, identities),
                            'median_heavy_atoms': median([heavy_atoms[i] for i in indices]),
                            'queries_ids': [identities[i] for i in indices]}
    random_groups = [item for label, item in summaries.items() if label.startswith('random')]
    return {'group_size': size, 'candidate_pool': len(rows),
            'id_definition': 'Stored patent_id in lexicographic order; no PID or PubChem CID field in this pool.',
            'simplicity_definition': 'RDKit heavy atom count; ties in both selections broken by connectivity key.',
            'uniform_random_20_draws': {metric: {'mean': float(np.mean(values)), 'min': min(values), 'max': max(values)}
                for metric in ('recall_at_1', 'recall_at_5', 'median_heavy_atoms')
                for values in [[entry[metric] for entry in random_groups]]},
            'groups': summaries}


def clean_chunks(chunks, record, nucleus):
    kept, removed = [], Counter()
    for text, origin in chunks:
        peaks = parse_nmr_record({**record, 'chemical_shift': text}, nucleus)
        is_masked = (len(peaks) == 1 and peaks[0][SHIFT_PRESENT] and peaks[0][WIDTH] == 0
                     and any(abs(peaks[0][SHIFT] - center) <= width for center, width in WINDOWS[nucleus]))
        if is_masked:
            removed[origin] += 1
        else:
            kept.append(text)
    return kept, removed


def insert_peaks(chunks, record, nucleus, extra):
    """Add labeled peaks in the original spectrum's approximate shift order."""
    def center(text):
        return parse_nmr_record({**record, 'chemical_shift': text}, nucleus)[0][SHIFT]

    shifts = [center(text) for text, _ in chunks]
    descending = shifts[0] >= shifts[-1]
    for shift, text, origin in extra:
        following = (i for i, value in enumerate(shifts) if value < shift) if descending else (
            i for i, value in enumerate(shifts) if value > shift)
        where = next(following, len(shifts))
        chunks.insert(where, (text, origin))
        shifts.insert(where, shift)


def cdcl3_query(row):
    for key in ('h_nmr', 'c_nmr'):
        records = row[key]
        if len(records) != 1 or str(records[0].get('solvent', '')).strip().lower() not in ('cdcl3', 'chloroform-d'):
            return False
    return True


def noise_conditions(row, rng):
    variants = {name: dict(row) for name in ('original_masked', 'solvent_added', 'solvent_added_masked',
                                             'solvent_and_unknown_added', 'solvent_and_unknown_added_masked')}
    removals = {key: Counter() for key in variants if key.endswith('masked')}
    for nucleus in ('h', 'c'):
        key = f'{nucleus}_nmr'
        record = row[key][0]
        original = [(chunk.strip(), 'original') for chunk in _split_outside_parentheses(record['chemical_shift']) if chunk.strip()]
        solvent = []
        for shift, suffix in EXTRAS[nucleus]:
            jitter = 0.01 if nucleus == 'h' else 0.03
            shifted = round(float(shift + rng.uniform(-jitter, jitter)), 3)
            solvent.append((shifted, f'{shifted:.3f}{suffix}', 'added_solvent_water'))
        low, high = (0.5, 9.5) if nucleus == 'h' else (10, 180)
        unknown = [(v, f'{v:.3f}', 'added_unknown') for v in rng.uniform(low, high, size=2)]
        inputs = {'original_masked': (original, [])}
        for label, extras in [('solvent_added', solvent), ('solvent_and_unknown_added', solvent + unknown)]:
            inputs[label] = (original, extras)
            inputs[label + '_masked'] = (original, extras)
        for label, (chunks, extras) in inputs.items():
            chunks = chunks.copy()
            insert_peaks(chunks, record, nucleus, extras)
            if label.endswith('masked'):
                texts, removed = clean_chunks(chunks, record, nucleus)
                removals[label].update(removed)
            else:
                texts = [text for text, _ in chunks]
            variants[label][key] = [{**record, 'chemical_shift': ', '.join(texts)}]
    return variants, removals


def embed(rows, model, collate):
    chunks = []
    with torch.inference_mode():
        for start in range(0, len(rows), 16):
            source, target, _ = collate(rows[start:start + 16])
            spectral, _ = model.alignment_embeddings(source, target)
            chunks.append(spectral.cpu().numpy())
    return np.concatenate(chunks)


def filtering_check(rows, original_spectra, library, identities, checkpoint, rng):
    eligible = [i for i, row in enumerate(rows) if cdcl3_query(row)]
    indices = rng.choice(eligible, size=96, replace=False)
    selected = [rows[i] for i in indices]
    runner = Runner(argparse.Namespace(alignment_checkpoint=checkpoint, device='cpu'))
    model, _ = runner.model('align')
    collate = make_collate(model.config, include_formula=False)
    clean = embed(selected, model, collate)
    max_error = float(np.abs(clean - original_spectra[indices]).max())
    if max_error > 1e-4:
        raise ValueError(f'Fresh and saved clean embeddings disagree ({max_error:g})')
    base = sample_metrics(clean @ library.T, indices, identities)
    variants, removals = {}, {}
    for row in selected:
        modified, removed = noise_conditions(row, rng)
        for name, value in modified.items():
            variants.setdefault(name, []).append(value)
        for name, value in removed.items():
            removals.setdefault(name, Counter()).update(value)
    summary = {'original': base}
    for name, values in variants.items():
        summary[name] = sample_metrics(embed(values, model, collate) @ library.T, indices, identities)
        print('Filter condition', name, summary[name]['recall_at_1'], flush=True)
    return {'eligible_both_cdcl3': len(eligible), 'query_ids': [identities[i] for i in indices],
            'clean_embedding_max_abs_diff_from_saved': max_error, 'solvent': 'CDCl3',
            'simulation': 'Two H and three C solvent/water peaks; mixed variant adds two unknown peaks to each nucleus.',
            'filter': 'Mask individually parsed point peaks near the declared solvent/water positions; retain intervals.',
            'windows_ppm_center_and_half_width': WINDOWS, 'removed_peak_chunks_by_origin': removals,
            'metrics': summary}


def open_set_check(scores, identities, rng):
    # One library for every query. Calibration and test query identities are disjoint.
    partition = rng.permutation(len(identities))
    library = partition[:384]
    present, absent = partition[:128], partition[384:]

    def features(indices, column):
        similarities = scores[np.ix_(indices, library)]
        order = np.argsort(-similarities, axis=1, kind='stable')[:, :2]
        top = np.take_along_axis(similarities, order, axis=1)
        confidence = top[:, 0] if column == 'max_cosine' else top[:, 0] - top[:, 1]
        return confidence, library[order[:, 0]] == indices

    output = {}
    for feature in ('max_cosine', 'top1_top2_margin'):
        pos_cal, _ = features(present[:64], feature)
        neg_cal, _ = features(absent[:64], feature)
        pos_test, correct = features(present[64:], feature)
        neg_test, _ = features(absent[64:], feature)
        thresholds = np.r_[np.unique(np.r_[pos_cal, neg_cal]), np.inf]
        balanced = (np.mean(pos_cal >= thresholds[:, None], axis=1) + np.mean(neg_cal < thresholds[:, None], axis=1)) / 2
        threshold = float(thresholds[np.flatnonzero(balanced == balanced.max())[-1]])
        allowed = thresholds[np.mean(neg_cal >= thresholds[:, None], axis=1) <= .05]

        def report(value):
            accepted = pos_test >= value
            return {'threshold': float(value) if np.isfinite(value) else 'reject_all',
                    'in_library_accepted': int(accepted.sum()), 'in_library_correct_accepted': int((accepted & correct).sum()),
                    'out_of_library_false_accept': int((neg_test >= value).sum())}

        ranks = rankdata(np.r_[pos_test, neg_test])
        auroc = (ranks[:64].sum() - 64 * 65 / 2) / 64**2
        output[feature] = {'held_out_auroc': float(auroc), 'test_in_library_top1_without_rejection': int(correct.sum()),
                           'max_calibration_balanced_accuracy': report(threshold),
                           'at_most_5pct_calibration_out_of_library_false_accept': report(allowed[0])}
    return {'library_size': len(library), 'calibration_in_and_out': [64, 64], 'test_in_and_out': [64, 64],
            'library_ids': [identities[i] for i in library],
            'calibration': {'in': [identities[i] for i in present[:64]], 'out': [identities[i] for i in absent[:64]]},
            'test': {'in': [identities[i] for i in present[64:]], 'out': [identities[i] for i in absent[64:]]},
            'metrics': output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-cache', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(2)
    rows = json.loads((args.audit_cache / 'selection.json').read_text())['datasets'][DATASET]
    identities = [row['_identity'] for row in rows]
    original = json.loads(Path('results/nmr_filtered_retrieval_20261117.json').read_text())
    if identities != original['datasets'][DATASET]['identities'] or len(set(identities)) != 512:
        raise ValueError('The candidate order must match the previous connectivity audit')
    digest = sha256(args.checkpoint)
    if digest != original['checkpoint_sha256']:
        raise ValueError('The checkpoint must match the saved embedding cache')
    with np.load(args.audit_cache / f'{DATASET}-hc.npz') as cache:
        spectral, molecular = cache['spectral'], cache['molecular']
    scores = spectral @ molecular.T
    report = {'dataset': DATASET, 'checkpoint_sha256': digest, 'training_performed': False,
              'scope': 'Small experimental H/C candidate-pool diagnostic; known alignment train/val connectivity overlap excluded previously.',
              'seed': 42, 'formula_input': False, 'sampling': sampling_check(rows, scores, identities),
              'out_of_library': open_set_check(scores, identities, np.random.default_rng(42)),
              'dirty_spectrum': filtering_check(rows, spectral, molecular, identities, args.checkpoint, np.random.default_rng(42))}
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    main()
