"""Read-only chemistry checks of prepared NMR views; retain flagged source examples."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def audit(path):
    from rdkit import Chem, RDLogger
    from rdkit.Chem import rdMolDescriptors
    RDLogger.DisableLog('rdApp.warning')
    counts, examples, digest = Counter(), defaultdict(list), hashlib.sha256()
    with path.open('rb') as stream:
        for number, line in enumerate(stream, 1):
            digest.update(line)
            if not line.strip():
                continue
            row = json.loads(line)
            counts['records'] += 1
            flags = []
            molecule = Chem.MolFromSmiles(row.get('smiles', ''))
            if molecule is None or not molecule.GetNumAtoms():
                flags.append('invalid_structure')
            else:
                expected = rdMolDescriptors.CalcMolFormula(molecule)
                if not row.get('formula'):
                    flags.append('missing_formula')
                elif row['formula'] != expected:
                    flags.append('formula_string_disagreement')
                elements = {a.GetSymbol() for a in Chem.AddHs(molecule).GetAtoms()}
                for symbol, key in [('H', 'h_nmr'), ('C', 'c_nmr')]:
                    if row.get(key) and symbol not in elements:
                        flags.append(f'{symbol}_records_without_nucleus_in_structure')
            mask = [int(bool(row.get(k))) for k in ('h_nmr', 'c_nmr')]
            if row.get('modality_mask', mask) != mask:
                flags.append('mask_disagrees_with_records')
            for flag in flags:
                counts[flag] += 1
                if len(examples[flag]) < 3:
                    examples[flag].append({'line': number, 'record': row})
            counts['records_with_any_flag'] += bool(flags)
    return {'path': str(path), 'sha256': digest.hexdigest(), 'counts': dict(counts), 'examples': dict(examples)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evaluation-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a new output file')
    result = {'audited_at': datetime.now(timezone.utc).isoformat(), 'training_performed': False,
              'scope': 'Complete scans of four local evaluation JSONLs; not the full OpenDataLab corpus',
              'interpretation': 'Flags require source review. No records were changed, deleted or relabeled.', 'datasets': {}}
    for name in ('nmrspec_test', 'patent_test_10k', 'nmrexp_exp_10k', 'nmrgym_test'):
        report = audit(args.evaluation_root / name / 'test.jsonl')
        result['datasets'][name] = report
        print(name, report['counts'], flush=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
