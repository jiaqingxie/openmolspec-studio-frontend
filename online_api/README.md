# Online tool service

This source-checkout service connects the GitHub Pages frontend to real local
models. Python's HTTP server accepts bounded demonstration requests and stores
run events in SQLite. An asynchronous worker calls `python -m openmolspec.mcp`.
The agent invokes an OpenAI-compatible model API to choose MCP tools and explain
their returned values. Only public answer text and explicit tool events are
retained; provider reasoning fields are discarded.

Install the SDK with its MCP extra in the service environment. Configure an
author environment for NMRNet, the NMR Transformer and the MS models. Configure
a separate environment for openSpec/Vib2Mol and TransPeakNet with PyTorch Geometric.

```bash
export PYTHONPATH=src:.
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
python -m online_api.serve \
  --model-python /path/to/nmr-env/bin/python \
  --ms-python /path/to/ms-env/bin/python \
  --models-root /path/to/nmr-models \
  --ms-source /path/to/ms-pred --ms-weights /path/to/ms-checkpoints \
  --nmr-alignment /path/to/nmr-alignment.pt \
  --nmr-generation /path/to/nmr-generation.pt \
  --portable-root /path/to/openmolspec-models \
  --vibrational-python /path/to/openspec-env/bin/python \
  --solvent-library /path/to/solvent_reference_library.json \
  --transpeaknet-source /path/to/2dNMR \
  --base-url https://hapiopen.cc/v1 \
  --model deepseek-v4.1-flash
```

For a model-only deployment, add `--tools-only`. The spectroscopy tools then run without a language-model provider. For the agent, enter the provider key at the hidden prompt. A deployment secret can instead
provide `OPENAI_API_KEY`. Never put it in frontend configuration, a command-line
argument, the source tree or screenshots. The service binds to `127.0.0.1:8721`.
Run it under a process supervisor for a persistent deployment. A restart marks
unfinished runs as failed so users can resubmit them.

Use an HTTPS reverse proxy or a named tunnel with a stable hostname. Set that
origin in `website/assets/service-config.json`, rebuild and publish GitHub Pages.
The current demonstration uses a Cloudflare Quick Tunnel, which has no uptime
guarantee and must be replaced for long-term hosting. Its origin is configurable
without changing the UI. The frontend always checks actual service status.

### Experimental lookup and prediction

Build the byte-offset index once for the cleaned OpenDataLab H/C and experimental
JSONL splits. Keep the source files accessible to the service and rebuild the
index after replacing them. The defaults below match the server arguments
`--spectra-data` and `--spectra-index`.

```bash
python -m online_api.spectrum_library \
  --data-root .runtime/manual-data-v1 --index .runtime/spectra-library.sqlite
curl -sS http://127.0.0.1:8721/api/spectra/resolve \
  -H 'Origin: http://localhost:8769' -H 'Content-Type: application/json' \
  -d '{"smiles":"C1CC1C#C","modality":"IR"}'
```

Supported modalities are `1H`, `13C`, `11B`, `19F`, `29Si`, `31P`, `IR`,
`Raman` and `MS`. Lookup checks canonical isomeric SMILES after an indexed
InChIKey search. A matching response contains the split, units, recorded peaks,
source ID and available acquisition fields, with at most 12 records and a total
match count. An indexed miss returns an ordinary asynchronous model run for
supported NMR/IR/Raman requests. Poll `GET /api/runs/{run.id}` for predictions.
The run uses the usual public model queue and quotas. MS/MS generation requires
acquisition conditions in Predict. An unavailable or stale index returns HTTP 503.

On hosts whose outbound access requires an HTTP CONNECT proxy, the relay below
keeps TLS end to end while allowing cloudflared to use that existing proxy:

```bash
python -m online_api.tunnel_proxy
python -m online_api.edge_proxy
cloudflared tunnel --url http://127.0.0.1:8721 \
  --quick-service http://127.0.0.1:8730 --protocol http2 \
  --edge 127.0.0.1:8744 --ha-connections 1 --no-autoupdate --no-prechecks
```

The provisioning proxy handles Quick Tunnel creation and can stop after the
tunnel registers. Keep the edge relay, tunnel and model API running to serve
new predictions. The helpers bind to loopback and use the existing HTTPS proxy.
Direct-connect hosts do not need the helpers.

Use the [author repository at commit `2e93db8`](https://github.com/siriusxiao62/2dNMR/tree/2e93db82a9d627ac01109474e9b6e594065e3d56)
for TransPeakNet. The adapter checks the original 2D checkpoint digest and loads
only tensors. Supply SMILES and solvent to predict cross-peaks. Include `hsqc_peaks`
to match measured peaks using OpenMolSpec's distance window. Its assignments preserve original
SMILES atom order and explicitly return unmatched peaks. The `--transpeaknet-source`
and `--solvent-library` workflows are available when those local assets are configured.

Public endpoints:

| Endpoint | Input / result |
| --- | --- |
| `GET /api/status` | Actual MCP connectivity and supported online task IDs |
| `POST /api/runs` | `{"kind":"agent","prompt":"Predict 13C NMR for CCO"}` or `{"kind":"tool","task":"nmr.forward.13C","inputs":{"smiles":"CCO"}}`; returns a run ID |
| `GET /api/runs/{id}` | Status, tool input/output events, final result or error |

Browser submissions require an allowed website Origin. This is an anonymous
demonstration, with a four-request queue, 12 requests per client per hour,
120 total requests per day and 30 agent requests per day. Limits apply before
provider calls; they are not user authentication. Requests cap text, peak lists
and candidate lists, and the server controls interpreter/checkpoint settings.
Run records expire after 24 hours when new work is submitted. The published
example is a deliberately retained separate recording.

The public tool-step interaction follows Luffy202's frontend branch at commit
`11577df2236241ee28f7c8940faf6ebab5f78476`; the service uses the repository's
Spectra Harness contract without requiring that branch's Postgres, SSO or credit
system. Full training and benchmark workflows remain in the Python SDK/manual.

Boundary checks: `PYTHONPATH=src:. python -m unittest tests.test_online_api`.
They cover runtime-setting isolation, invalid requests, queue and daily budgets,
bounded candidates, and path redaction. Model execution is verified separately
with actual requests to every exposed workflow, including GLACIER MS/MS with
explicit adduct, collision energy and instrument fields.

The structure form runs the validation-selected phosphorus model as `nmr.forward.31P`. Supply a phosphorus-containing SMILES and an optional solvent such as `CDCl3`. Configure the inference-only checkpoint directory with `--phosphorus-model` and its Python environment with `--solution-python`. The service advertises the task when `model.json` is available. Each result gives zero-based input atom indices, shifts in ppm and the checkpoint SHA-256. An empty solvent uses the unknown-solvent category.

### Optional language and fragment tools

Configure `--specmol-checkpoint` and `--spectrallm-checkpoint` with the respective merged local checkpoints. The operator can select a model environment with `OPENMOLSPEC_LM_PYTHON`. A SpecMol request supplies `question` and `spectrum`. A SpectraLLM request supplies spectral text in `spectrum`. The public endpoint uses server-controlled model settings.

MechFrag-MS uses `OPENMOLSPEC_MECHFRAG_ROOT` for its checkout and `OPENMOLSPEC_MS_PYTHON` for its environment. Pass a structure, adduct, instrument, collision energy and observed m/z list. A mass match returns candidate ions with atom indices. See the [tool-call diagram](../documentation/assets/harness/mcp-workflow.svg).

For cross-solvent shifts, the packaged carbon ridge model takes a source shift and two solvents. The default proton reference lookup also requires a query SMILES and an operator-configured `--solvent-library`. A library query excludes references with the query's connectivity.

For experimental peak-to-atom assignments with the held-out site model, pass `--assignment-model-root /path/to/OpenMolSpec/runs/forward-tuning` and select the model interpreter with `--solution-python`. The two checkpoint folders are `1H-assigned` and `13C-assigned`. The tool takes measured peaks in ppm, the nucleus and a SMILES string.
