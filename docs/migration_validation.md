# Migration validation — 2026-11-02

## Implemented boundaries

- Next.js 16.4.3 / React 18.3.1 / TypeScript front end with runtime same-origin API proxy.
- FastAPI application process with no scientific-model imports, durable conversations, per-message input context snapshots, Agent runs and replayable SSE.
- Independent chemistry process with persisted molecules/spectra/jobs, immutable inputs and serialized existing-model execution.
- Official MCP Python SDK 1.30 Streamable HTTP server/client; actual tool discovery and calls over HTTP.
- OpenAI-compatible streaming provider, fragmented tool-call assembly, strict tool arguments, execution limits, total provider deadline and explicit incomplete-stream errors.

## Passing checks

```text
.venv/bin/python -m pytest tests/services tests/test_chemistry.py tests/test_spectra.py tests/test_config.py tests/test_inference.py tests/test_theoretical.py -q --tb=short
82 passed

cd web && npm test
19 passed

cd web && npm run typecheck
exit 0

cd web && npm run build
exit 0, static / and dynamic /api/[...path]

.venv/bin/python -m pip check
No broken requirements found.

docker compose config --quiet
exit 0

git diff --check
exit 0
```

The service suite includes real loopback HTTP + official MCP, real RDKit conformer resolution and exact XYZ preservation,
tiny real LMDB retrieval/cache-generation fixtures, durable restart recovery, queue cancellation, finite numeric validation,
SSE disconnect survival and replay, provider errors/deadlines, and a local test-provider→application→MCP→chemistry integration.
The provider fixture is confined to tests; no fake responses or inference results are installed in the product.

Frontend tests cover SSE chunk boundaries/UTF-8/replay, persisted tool states, runtime multipart/SSE proxy behavior,
exact-ID XYZ loading, scientific argument validation, NMR parsing and selected-input label/ID consistency.

Native production launch was tested at both default ports (3000/8000/8001) and custom API/chemistry ports (8100/8101),
including actual browser-origin `/api/health` through the runtime proxy. Shutdown/restart cleans owned process groups,
accepts recently closed TCP ports and preserves durable data. Current final instance uses default ports.

Browser verification and source comparisons are recorded in `../design-qa.md`. Actual molecule editing, 2D/3D viewing,
spectral upload, context consistency and responsive controls passed.

## Independent review and corrections

Two fresh-context reviews identified material boundary issues and all were addressed before delivery:

- Incomplete upstream streams no longer become completed answers; deadlines include continuously active streams.
- Runtime Next proxy correctly honors deployment API URLs; Docker's runtime environment includes the API service name.
- Stop/cleanup handles descendants even after the process-group leader exits, including the macOS inaccessible/dead-group case.
- SSE cursors and non-finite proxy/context numbers fail cleanly before response streaming.
- XYZ upload/history use the saved conformer ID, not a new SMILES-generated conformer.
- Selected input labels stay bound to IDs; dirty structures cannot silently enter chat context, and NMR peaks are preserved.
- User-message input references survive reload and follow-up turns; existing database schema is upgraded.
- Setup requires Python 3.11–3.12 and `.env` asset configuration is no longer overridden by the startup wrapper.

## Existing upstream test limitation

Running bare `.venv/bin/python -m pytest -q --tb=line` stops during collection with **27 errors** because the portable
repository does not include the upstream `benchmarks` package. The complete captured output is local at
`artifacts/migration/full-suite.log`. Affected files are the benchmark/equiformer/hessian/spectroscopy-model/
vib2mol training and evaluation tests (listed in that log). These are not hidden or reported as passing.
An existing preload unit test was updated to observe the already implemented individual-model preload calls;
the numerical implementation itself was not rewritten.

## Environment and deployment limits

- No live LLM key/model or scientific checkpoints, theoretical reference LMDB, or upstream model implementations were supplied.
  Real external-model quality and checkpoint-backed numerical predictions therefore remain unverified.
- Docker Compose configuration is validated; Docker images were not built/run. Native production build and three-process execution were tested.
- Current persistence/scheduling is intentionally private, single-workspace and single-process per Python service. Authentication,
  multi-tenant authorization and distributed scheduling are not part of this migration.
- Next.js emits a React18 deprecation notice for a future Next17 upgrade. React18 is pinned for the published Ketcher/Miew
  dependency compatibility; the supported Pages Router build, dependency tree and browser editor were verified. Upgrade React
  together with compatible editor dependencies when moving to Next17.
- Starlette emits one TestClient/httpx deprecation warning in the Python suite; it does not affect the running application.
