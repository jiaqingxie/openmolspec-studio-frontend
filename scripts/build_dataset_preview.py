"""Export small, reproducible previews of the cleaned experimental datasets.

Only recorded peak positions and measured intensities are exported. Source files
and model environments stay on the server; the output is safe for static hosting.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWS = [
    ('opendatalab_nmr', 'H/C NMR', '1H + 13C', 'ppm'),
    ('opendatalab_11b', 'Boron NMR', '11B', 'ppm'),
    ('opendatalab_19f', 'Fluorine NMR', '19F', 'ppm'),
    ('opendatalab_29si', 'Silicon NMR', '29Si', 'ppm'),
    ('opendatalab_31p', 'Phosphorus NMR', '31P', 'ppm'),
    ('opendatalab_ir', 'Infrared', 'IR', 'cm-1'),
    ('opendatalab_raman', 'Raman', 'Raman', 'cm-1'),
    ('opendatalab_ms', 'Mass spectrometry', 'MS', 'm/z'),
]


def finite_peaks(values, *, paired=False):
    """Return original finite numeric peaks, without changing their scale."""
    if not isinstance(values, list) or not values:
        return None
    try:
        result = [[float(x), float(y)] for x, y in values] if paired else [float(x) for x in values]
    except (TypeError, ValueError):
        return None
    flattened = [value for pair in result for value in pair] if paired else result
    if not all(math.isfinite(value) for value in flattened):
        return None
    if paired and any(x <= 0 or y < 0 for x, y in result):
        return None
    return result


def metadata(row):
    """Keep only source-supplied acquisition fields suitable for a public preview."""
    return {key: row[key] for key in ('solvent', 'frequency', 'source_line')
            if row.get(key) is not None and row[key] != ''}


def sample_record(row, dataset, modality, units):
    """Build a compact preview while keeping nucleus-specific provenance."""
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors
    molecule = Chem.MolFromSmiles(row.get('smiles', ''))
    if molecule is None:
        return None, None
    spectra = []
    source_id = row.get('source_document') or row.get('patent_id')
    if dataset == 'opendatalab_nmr':
        for prefix, nucleus in [('h', '1H'), ('c', '13C')]:
            peaks = finite_peaks(row.get(prefix + '_peaks_ppm'))
            if not peaks:
                return None, None
            item = {'modality': nucleus, 'units': 'ppm', 'peaks': peaks,
                    'intensity_available': False}
            conditions = [metadata(record) for record in row.get(prefix + '_nmr', [])]
            conditions = [condition for condition in conditions if condition]
            if len(conditions) == 1:
                item.update(conditions[0])
            elif conditions:
                item['conditions'] = conditions
            provenance = row.get(prefix + '_provenance') or {}
            if provenance.get('patent_id'):
                item['source_id'] = provenance['patent_id']
            spectra.append(item)
    else:
        paired = modality == 'MS'
        field = 'peaks' if paired else 'wavenumber_cm1' if modality in ('IR', 'Raman') else 'peaks_ppm'
        peaks = finite_peaks(row.get(field), paired=paired)
        if not peaks:
            return None, None
        item = {'modality': modality, 'units': units, 'peaks': peaks,
                'intensity_available': paired, **metadata(row)}
        if paired:
            item['intensity_units'] = 'relative intensity (source scale)'
        elif modality in ('IR', 'Raman') and row.get('intensities'):
            intensities = finite_peaks(row['intensities'])
            if intensities and len(intensities) == len(peaks):
                item.update(intensities=intensities, intensity_available=True,
                            intensity_units='source intensity')
        if source_id:
            item['source_id'] = source_id
        spectra.append(item)
    sample = {'dataset': dataset, 'modality': modality, 'smiles': row['smiles'],
              'formula': row.get('formula') or rdMolDescriptors.CalcMolFormula(molecule),
              'spectra': spectra, 'split': 'test',
              'source': row.get('source') or 'OpenDataLab'}
    if source_id:
        sample['source_id'] = source_id
    if row.get('standard_inchikey'):
        sample['standard_inchikey'] = row['standard_inchikey']
    identity = json.dumps(sample, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    sample['id'] = dataset + '-' + hashlib.sha256(identity.encode()).hexdigest()[:12]
    sample['structure_svg'] = 'assets/molecules/' + sample['id'] + '.svg'
    return sample, molecule


def draw_structure(molecule, destination):
    """Draw a deterministic RDKit molecular structure without external fonts."""
    from rdkit.Chem.Draw import rdMolDraw2D
    drawer = rdMolDraw2D.MolDraw2DSVG(440, 280)
    drawer.drawOptions().padding = .08
    drawer.DrawMolecule(molecule)
    drawer.FinishDrawing()
    destination.write_text(drawer.GetDrawingText())


def build(data_root, output, limit=4):
    """Export the first valid test records and versioned collection counts."""
    from rdkit import RDLogger
    RDLogger.DisableLog('rdApp.*')
    cleaned = json.loads((ROOT / 'documentation/assets/cleaned-data-summary.json').read_text())
    counts = json.loads((ROOT / 'documentation/assets/dataset-counts.json').read_text())
    assert cleaned['nmr']['completed'] and cleaned['experimental']['completed'] and counts['completed']
    output.mkdir(parents=True, exist_ok=True)
    molecules = output / 'molecules'
    molecules.mkdir(exist_ok=True)
    payload = {
        'version': 1,
        'selection': f'First {limit} valid test records in source order for each view; H/C previews require both nuclei.',
        'summary': {
            'nmr': {'spectra': cleaned['nmr']['counts']['h_spectra'] + cleaned['nmr']['counts']['c_spectra'],
                    'molecules': cleaned['nmr']['molecular_identities'],
                    '1H_spectra': cleaned['nmr']['counts']['h_spectra'],
                    '13C_spectra': cleaned['nmr']['counts']['c_spectra']},
            'experimental_views': cleaned['experimental']['views'],
            'other_datasets': counts['datasets'],
        },
        'datasets': [], 'samples': [],
    }
    for dataset, title, modality, units in VIEWS:
        is_hc = dataset == 'opendatalab_nmr'
        path = data_root / 'opendatalab_nmr/test.jsonl' if is_hc else data_root / 'experimental' / (modality + '-test.jsonl')
        selected = []
        with path.open() as stream:
            for line in stream:
                sample, molecule = sample_record(json.loads(line), dataset, modality, units)
                if sample is None:
                    continue
                selected.append(sample)
                draw_structure(molecule, molecules / (sample['id'] + '.svg'))
                if len(selected) == limit:
                    break
        if len(selected) != limit:
            raise ValueError('Not enough valid records for ' + dataset)
        view = payload['summary']['nmr'] if is_hc else cleaned['experimental']['views'][modality]
        payload['datasets'].append({'id': dataset, 'name': title, 'modality': modality,
            'units': units, 'spectra': view['spectra'], 'molecules': view['molecules'],
            'preview_samples': len(selected), 'domain': 'experimental'})
        payload['samples'].extend(selected)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if len(encoded.encode()) >= 500_000:
        raise ValueError('Preview exceeds the 500 KB budget')
    for marker in ('/mnt/', '/root/', '/tmp/', 'sk-', 'Bearer '):
        if marker in encoded:
            raise ValueError('Private data marker in public output: ' + marker)
    destination = output / 'dataset-preview.json'
    destination.write_text(encoded)
    display_path = destination.relative_to(ROOT) if destination.is_relative_to(ROOT) else destination.name
    print(json.dumps({'file': str(display_path), 'samples': len(payload['samples']),
                      'views': len(payload['datasets']), 'json_bytes': len(encoded.encode())}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=ROOT / '.runtime/manual-data-v1')
    parser.add_argument('--output', type=Path, default=ROOT / 'website/assets')
    parser.add_argument('--limit', type=int, default=4)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error('--limit must be positive')
    build(args.data_root, args.output, args.limit)


if __name__ == '__main__':
    main()
