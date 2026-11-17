# Online tool service

This source-checkout service connects the GitHub Pages frontend to real local
models. Python's HTTP server accepts bounded demonstration requests and stores
run events in SQLite. An asynchronous worker calls `python -m openmolspec.mcp`.
The agent invokes an OpenAI-compatible model API to choose MCP tools and explain
their returned values. Only public answer text and explicit tool events are
retained; provider reasoning fields are discarded.

Install the SDK with its MCP extra in the service environment. Configure separate
an author environment for NMRNet/GLACIER and a separate one for openSpec/Vib2Mol, together with
their existing checkpoints. The frontend is not a substitute for those weights.

```bash
export PYTHONPATH=src:.
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
python -m online_api.serve \
  --model-python /path/to/nmr-env/bin/python \
  --models-root /path/to/nmr-models \
  --ms-source /path/to/ms-pred --ms-weights /path/to/ms-checkpoints \
  --portable-root /path/to/openmolspec-models \
  --vibrational-python /path/to/openspec-env/bin/python \
  --base-url https://hapiopen.cc/v1 \
  --model deepseek-v4.1-flash
```

Enter the provider key at the hidden prompt. A deployment secret can instead
provide `OPENAI_API_KEY`. Never put it in frontend configuration, a command-line
argument, the source tree or screenshots. The service binds to `127.0.0.1:8721`.
Run it under a process supervisor for a persistent deployment. A restart marks
unfinished runs as failed so users can resubmit them.

Use an HTTPS reverse proxy or a named tunnel with a stable hostname. Set that
origin in `website/assets/service-config.json`, rebuild and publish GitHub Pages.
The current demonstration uses a Cloudflare Quick Tunnel, which has no uptime
guarantee and must be replaced for long-term hosting. Its origin is configurable
without changing the UI. The frontend always checks actual service status.

On hosts whose outbound access requires an HTTP CONNECT proxy, the relay below
keeps TLS end to end while allowing cloudflared to use that existing proxy:

```bash
python -m online_api.tunnel_proxy
python -m online_api.edge_proxy
cloudflared tunnel --url http://127.0.0.1:8721 \
  --quick-service http://127.0.0.1:8730 --protocol http2 \
  --edge 127.0.0.1:8744 --ha-connections 1 --no-autoupdate --no-prechecks
```

Each line is a separate long-running process. The helpers bind only to loopback
and read the existing HTTPS proxy setting. Direct-connect hosts do not need them.
Keep the model service and tunnel alive together. No GitHub Pages process can
run Python inference by itself.

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
