# Production workflows

The modules in this package implement the supported data-production stages:

- `manifest.py`: orchestrates frequency/NMR source discovery;
- `manifest_scan.py`: scans source trees, normalizes identities and writes manifests;
- `frequency.py`: parses structures, properties, IR and Raman records;
- `nmr.py`: parses NMR shielding records;
- `trajectories.py`: extracts optimization geometries, energies and forces.

Use `python -m openmolspec --stage ...` for normal production. Individual
modules remain executable for focused diagnostics.
