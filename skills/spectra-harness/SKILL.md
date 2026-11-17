---
name: spectra-harness
description: Run and verify OpenMolSpec NMR, MS/MS and vibrational model calls through Spectra Harness or its MCP tools. Use for spectroscopy inference, request validation and repeatability checks with known model assets.
---

Use `python -m openmolspec.harness catalog` or the `spectra_tasks` MCP tool to discover supported direct calls. The Python interface is `from openmolspec.harness import SpectraHarness`.

Keep the modality contract attached to the request:

- **NMR Spectra Harness:** forward H/C requires a structure and model root; assignment also requires measured ppm peaks. Retrieval takes explicit candidates. Generation additionally requires a supplied molecular formula. H, C and H+C set distinct masks.
- **MS Spectra Harness:** supply SMILES, adduct, collision energy and instrument with compatible GLACIER or ICEBERG assets. A single reported molecular m/z is insufficient as an MS/MS intensity reference.
- **Vibrational Spectra Harness:** supply the checkpoint-compatible 1024-point IR/Raman channels and H/C ppm arrays. Missing-channel runs require an explicit ablation option. Exact-geometry forward prediction uses the separate benchmark adapter.

Call `validate(task, inputs, model_config)` first, then `run(...)`. Use `repeats=2` when checking identical-request stability. Inspect `completed`, each call's status, checkpoint provenance and output equality. Stop on a failed call and inspect its error rather than changing conditions silently. A successful execution trace establishes software behavior; accuracy needs paired reference data and an appropriate split.

For CLI use, store `task`, `inputs`, `model_config` and optional `repeats` in a request JSON, then run:

```bash
python -m openmolspec.harness validate --request request.json
python -m openmolspec.harness run --request request.json --output new-result.json
```

The MCP entry point is `python -m openmolspec.mcp`; install the `mcp` optional extra. It exposes discovery, dataset cards, validation and explicit inference. Model training remains an explicit SDK operation with separate train/validation data and a new run directory.
