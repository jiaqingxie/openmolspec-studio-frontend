# Maintenance utilities

Dataset-specific diagnostic and recovery tools live here. They are not part of
the normal full release pipeline.

`parse_zinc_v2_nmr.py` reparses only the ZINC v2 NMR logs after an HPC retry:

```bash
python -m openmolspec.maintenance.parse_zinc_v2_nmr --help
```

Use `python -m openmolspec --stage nmr` for normal all-dataset production extraction.
