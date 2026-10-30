# Legacy and compatibility commands

`extract_properties_backup.py` preserves the historical frequency-scaling
behavior for comparison. It delegates Gaussian parsing to
`openmolspec.parsing.gaussian` and is not used by the production pipeline or
the release builder.

`function.py` contains the former repository-level conversion helpers. It
depends on `mol_from_np_2`, which is not distributed here, and is therefore
reference-only as well.

`extract_spectra.py`, `extract_properties.py`, and `extract_nmr.py` preserve
the former file-map and raw-directory CLIs. New production runs should use
`openmolspec.workflows` through `python -m openmolspec`.
