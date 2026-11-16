"""Experimental-reference solvent transfer baseline, without fitted parameters.

This is a nearest-reference baseline, not a pretrained neural solvent model.
Every query excludes all reference molecules with the same connectivity.
"""
import argparse
from collections import Counter, defaultdict
from functools import lru_cache
from itertools import combinations
import json
import math
from pathlib import Path
import random

from .data import sha256

ALIASES = {
    'CDCl3': ['Chloroform-D1 (CDCl3)', 'CDCL3', 'CDCL3,TMS', 'CDCl3'],
    'CD3OD': ['Methanol-D4 (CD3OD)', 'CD3OD'],
    'DMSO-d6': ['Dimethylsulphoxide-D6 (DMSO-D6, C2D6SO))', 'd6-DMSO', 'DMSO-D6', 'DMSO-d6'],
    'acetone-d6': ['Acetone-D6 ((CD3)2CO)', '(CD3)2CO', 'Acetone-d6', 'acetone-d6'],
    'pyridine-d5': ['Pyridin-D5 (C5D5N)', 'Pyridine -d5', 'C5D5N', 'pyridine-d5'],
    'C6D6': ['Benzene-D6 (C6D6)', 'C6D6'],
    'CD3CN': ['CD3CN', 'Acetonitrile-D3 (CD3CN)'],
    'D2O': ['Deuteriumoxide (D2O)', 'D2O'],
    'CCl4': ['TETRACHLORO-METHANE (CCl4)', 'CCl4'],
    'CD2Cl2': ['Dichloromethane-D2 (CD2Cl2)', 'CD2CL2', 'CD2Cl2'],
    'THF-d8': ['Tetrahydrofuran-D8 (C4D8O)', 'THF-d8'],
}
SOLVENTS = {value.lower(): name for name, values in ALIASES.items() for value in values}


def solvent(value):
    result = SOLVENTS.get(value.strip().lower())
    if result is None:
        raise ValueError(f'Unrecognized or mixed solvent: {value}')
    return result


@lru_cache(maxsize=100000)
def connectivity(smiles):
    from rdkit import Chem
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise ValueError('Invalid SMILES in reference/query')
    for atom in molecule.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(Chem.RemoveHs(molecule), isomericSmiles=False)


def prepare(raw_path):
    raw = json.loads(Path(raw_path).read_text())
    grouped, counts = defaultdict(lambda: defaultdict(list)), Counter()
    invalid_smiles = set()
    for record in raw['records']:
        try:
            name = solvent(record['solvent'])
            nucleus = record['spectrum_type']
            if nucleus not in ('1H','13C') or record['symbol'] != {'1H':'H','13C':'C'}[nucleus]:
                counts['other_nucleus'] += 1
                continue
            if record['smiles'] in invalid_smiles:
                counts['unknown_solvent_or_invalid_record'] += 1
                continue
            try:
                smiles = connectivity(record['smiles'])
            except ValueError:
                invalid_smiles.add(record['smiles'])
                raise
            shift = float(record['shift_ppm'])
            if not math.isfinite(shift):
                raise ValueError('Nonfinite reference')
        except ValueError:
            counts['unknown_solvent_or_invalid_record'] += 1
            continue
        key = (record['molecule_id'], record['atom_id'], nucleus, smiles)
        grouped[key][name].append((shift, record['spectrum_id']))
    pairs = []
    for (molecule_id, atom_id, nucleus, smiles), by_solvent in grouped.items():
        unambiguous = {}
        for name, rows in by_solvent.items():
            values = {shift for shift, _ in rows}
            if len(values) != 1:
                counts['conflicting_repeat_shifts'] += 1
                continue
            unambiguous[name] = {'shift_ppm': next(iter(values)),
                                 'spectrum_ids': sorted({identifier for _, identifier in rows})}
        for left, right in combinations(sorted(unambiguous),2):
            pairs.append({'molecule_id': molecule_id, 'atom_id': atom_id, 'nucleus': nucleus,
                          'smiles': smiles, 'source_solvent': left, 'target_solvent': right,
                          'source': unambiguous[left], 'target': unambiguous[right]})
    return {'schema_version': 1, 'method': 'nearest_paired_experimental_reference_delta',
            'training_performed': False, 'reference_source': raw['source'],
            'reference_source_sha256': raw.get('source_sha256') or sha256(raw['source']),
            'raw_extraction_sha256': sha256(raw_path),
            'source_filter': 'reviewed=true; 1D H/C; calculated-condition records excluded',
            'scope': 'unambiguous same-database-atom shifts in two recognized pure solvents',
            'counts': dict(counts), 'paired_atoms': len(pairs),
            'distinct_connectivities': len({r['smiles'] for r in pairs}), 'pairs': pairs}


class ReferenceTransfer:
    def __init__(self, library):
        from rdkit import Chem
        from rdkit.Chem import rdFingerprintGenerator
        self.generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
        self.fingerprints = {}
        self.index = defaultdict(list)
        for row in library['pairs']:
            identity = connectivity(row['smiles'])
            if identity not in self.fingerprints:
                self.fingerprints[identity] = self.generator.GetFingerprint(Chem.MolFromSmiles(identity))
            for source, target in (('source','target'),('target','source')):
                self.index[(row['nucleus'],row[source+'_solvent'],row[target+'_solvent'])].append(
                    {'identity': identity, 'molecule_id':row['molecule_id'], 'atom_id':row['atom_id'],
                     'source_ppm': row[source]['shift_ppm'], 'target_ppm': row[target]['shift_ppm'],
                     'source_spectrum_ids': row[source]['spectrum_ids'],
                     'target_spectrum_ids': row[target]['spectrum_ids']})

    def predict(self, smiles, nucleus, source_solvent, target_solvent, source_ppm):
        from rdkit import Chem, DataStructs
        if nucleus not in ('1H','13C') or not math.isfinite(source_ppm):
            raise ValueError('Finite 1H/13C source shift required')
        source_solvent, target_solvent = solvent(source_solvent), solvent(target_solvent)
        if source_solvent == target_solvent:
            raise ValueError('Source and target solvent must differ')
        identity = connectivity(smiles)
        candidates = [r for r in self.index.get((nucleus,source_solvent,target_solvent),[])
                      if r['identity'] != identity]
        if not candidates:
            raise ValueError('No independent paired reference for this nucleus/solvent pair')
        fingerprint = self.generator.GetFingerprint(Chem.MolFromSmiles(identity))
        similarities = {key: DataStructs.TanimotoSimilarity(fingerprint,self.fingerprints[key])
                        for key in {r['identity'] for r in candidates}}
        # Fixed ordering, with no fitted parameters: closest molecular fingerprint,
        # then closest measured source shift, then stable source IDs for ties.
        selected = min(candidates, key=lambda r:(-similarities[r['identity']],
                                                abs(r['source_ppm']-source_ppm), r['molecule_id'],r['atom_id']))
        delta = selected['target_ppm']-selected['source_ppm']
        return {'source_ppm':source_ppm,'predicted_target_ppm':source_ppm+delta,
                'predicted_delta_ppm':delta,'source_solvent':source_solvent,'target_solvent':target_solvent,
                'nucleus':nucleus,'query_connectivity':identity,
                'reference':selected,'tanimoto_similarity':similarities[selected['identity']],
                'same_connectivity_excluded':True,
                'method':'nearest_paired_experimental_reference_delta',
                'model_kind':'retrieval_baseline_not_neural_model'}


def evaluate(library, limit=32, seed=42):
    model = ReferenceTransfer(library)
    grouped = defaultdict(list)
    for pair in library['pairs']:
        grouped[(pair['nucleus'],pair['smiles'],pair['source_solvent'],pair['target_solvent'])].append(pair)
    keys = sorted(grouped)
    random.Random(seed).shuffle(keys)
    records, skipped, selected, seen = [], [], [], set()
    for key in keys:
        nucleus, smiles, source, target = key
        if smiles in seen:
            continue
        batch = []
        try:
            for pair in grouped[key]:
                prediction = model.predict(smiles,nucleus,source,target,pair['source']['shift_ppm'])
                prediction.update(query_molecule_id=pair['molecule_id'],query_atom_id=pair['atom_id'],
                                  target_reference_ppm=pair['target']['shift_ppm'],
                                  source_spectrum_ids=pair['source']['spectrum_ids'],
                                  target_spectrum_ids=pair['target']['spectrum_ids'])
                batch.append(prediction)
        except ValueError as error:
            skipped.append({'smiles':smiles,'nucleus':nucleus,'source_solvent':source,'target_solvent':target,'reason':str(error)})
            continue
        seen.add(smiles)
        selected.append(key)
        records.extend(batch)
        if len(seen) == limit:
            break
    if not records:
        raise ValueError('No independent cross-solvent examples are available')
    metrics = {}
    for nucleus in sorted({r['nucleus'] for r in records}):
        rows = [r for r in records if r['nucleus']==nucleus]
        errors = [abs(r['predicted_target_ppm']-r['target_reference_ppm']) for r in rows]
        unchanged = [abs(r['source_ppm']-r['target_reference_ppm']) for r in rows]
        metrics[nucleus] = {'atoms':len(rows),'molecules':len({r['query_connectivity'] for r in rows}),
                            'mae_ppm':sum(errors)/len(errors),'unchanged_shift_mae_ppm':sum(unchanged)/len(unchanged),
                            'rmse_ppm':math.sqrt(sum(e*e for e in errors)/len(errors))}
    return {'task':'nmr.solvent_transfer','completed':True,'status':'passed','training_performed':False,
            'purpose':'leave_one_connectivity_out_reference_baseline','model_kind':'retrieval_baseline_not_neural_model',
            'seed':seed,'limit':limit,'metrics':metrics,'records':records,'skipped':skipped,
            'counts':{'distinct_molecules':len(seen),'paired_atoms':len(records),'skipped_pairs':len(skipped)},
            'limitations':['Existing neural solvent model is not installed; this is a reference-retrieval baseline.',
                           'No parameter fitting or test-label calibration. Query connectivity and stereoisomers excluded.',
                           'Temperature, concentration and original experimental referencing are not independently harmonized.',
                           'Low-similarity references can be inaccurate; a successful run does not establish useful accuracy.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',type=Path)
    mode.add_argument('--evaluate',action='store_true')
    mode.add_argument('--request',type=Path)
    parser.add_argument('--library',type=Path)
    parser.add_argument('--limit',type=int,default=32)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Output exists')
    if args.prepare:
        result=prepare(args.prepare)
    else:
        if not args.library or args.limit < 1:parser.error('A library and positive limit are required')
        library=json.loads(args.library.read_text())
        if args.evaluate:
            result=evaluate(library,args.limit)
        else:
            request=json.loads(args.request.read_text())
            model=ReferenceTransfer(library)
            predictions=[model.predict(request['smiles'],request['nucleus'],
                         request['source_solvent'],request['target_solvent'],float(shift)) for shift in request['source_peaks_ppm']]
            if not predictions:raise ValueError('Supply at least one source peak')
            result={'task':'nmr.solvent_transfer','completed':True,'status':'passed','predictions':predictions,
                    'training_performed':False,'model_kind':'retrieval_baseline_not_neural_model'}
        result['library']={'path':str(args.library),'sha256':sha256(args.library),
                           'reference_source':library['reference_source']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ('counts','paired_atoms','distinct_connectivities','metrics') if k in result}))


if __name__=='__main__':
    main()
