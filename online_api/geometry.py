"""Run the original openSpec geometry models in their installed model environment."""
import json
import sys
from pathlib import Path


def main():
    payload = json.load(sys.stdin)
    from openmolspec_ui.config import discover_assets
    from openmolspec_ui.chemistry import molecule_from_smiles
    from openmolspec_ui.inference import OpenMolSpecService
    molecule = molecule_from_smiles(payload['smiles'])
    if molecule.atoms > 80: raise ValueError('The public geometry tool supports up to 80 atoms')
    result = OpenMolSpecService(discover_assets(Path(payload['root'])), device='cpu').predict_spectra(molecule)
    output = {key: result[key].tolist() for key in ['wavenumber', 'ir', 'raman', 'nmr_h', 'nmr_c']}
    output['smiles'] = payload['smiles']; output['coordinate_method'] = molecule.source
    output['model'] = 'openSpec Equiformer-v3'; output['unit'] = 'cm-1'
    print('OMS_RESULT_V1:' + json.dumps(output), flush=True)


if __name__ == '__main__': main()
