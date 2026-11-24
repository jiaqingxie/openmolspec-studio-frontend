"""Score nested cross-source libraries using frozen, previously verified NMR embeddings."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    ref = json.loads(args.reference.read_text())
    packs = json.loads((args.cache / 'selection.json').read_text())['datasets']
    ids = {s: [r['_identity'] for r in rows] for s, rows in packs.items()}
    result = {}
    for view in ('h', 'c', 'hc'):
        bank = {}
        for s in ids:
            if ids[s] != ref['datasets'][s]['identities']:
                raise ValueError(f'Unexpected query order in {s}')
            with np.load(args.cache / f'{s}-{view}.npz', allow_pickle=False) as f:
                bank[s] = {k: f[k] for k in ('spectral', 'molecular')}
            if any(len(a) != len(ids[s]) for a in bank[s].values()):
                raise ValueError('Incomplete embedding cache')
        for source, query_ids in ids.items():
            seen = set(query_ids)
            library = [(source, i) for i in range(len(query_ids))]
            extra = []
            for other in sorted(set(ids) - {source}):
                for i, k in enumerate(ids[other]):
                    if k not in seen:
                        extra.append((hashlib.sha256(('library-v1:' + k).encode()).digest(), other, i))
                        seen.add(k)
            library.extend((s, i) for _, s, i in sorted(extra))
            out = result.setdefault(source, {}).setdefault(view, {})
            for direction, query, candidate in [('s2m','spectral','molecular'), ('m2s','molecular','spectral')]:
                scores = bank[source][query] @ np.stack([bank[s][candidate][i] for s, i in library]).T
                curve = {}
                for size in sorted({len(query_ids), min(1024,len(library)), len(library)}):
                    order = np.argsort(-scores[:, :size], axis=1, kind='stable')
                    ranks = (order == np.arange(len(query_ids))[:, None]).argmax(axis=1) + 1
                    curve[size] = {'queries':len(ranks), 'r1':float(np.mean(ranks == 1)),
                                   'r5':float(np.mean(ranks <= 5)), 'mrr':float(np.mean(1/ranks))}
                if curve[len(query_ids)]['r1'] != ref['datasets'][source]['views'][view][direction]['recall_at_1']:
                    raise ValueError('Original library ranks failed to reproduce')
                out[direction] = curve
    args.output.write_text(json.dumps({'checkpoint_sha256':ref['checkpoint_sha256'],'training_files':ref['training_files'],
        'protocol':'Same queries across sizes. Own-source identities first, then distinct cross-source distractors in fixed hash order. One positive per query. Known alignment train and validation excluded.', 'results': result}, indent=2)+'\n')


if __name__ == '__main__':
    main()
