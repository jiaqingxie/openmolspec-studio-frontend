# OpenMolSpec Web Migration Implementation Plan

> **For agentic workers:** Use the approved architecture below, implement bounded components in parallel, then integrate and independently review. Track checked steps here.

**Goal:** Deliver a runnable Next.js scientific chat workspace, FastAPI Agent API, independent spectroscopy calculation service, and working MCP access.

**Architecture:** The browser talks only to the application API. Explicit operations and MCP Agent tools share one chemistry calculation implementation. Existing numerical routines are reused; durable jobs/messages/events store input snapshots and preserve truthful availability/provenance.

**Tech Stack:** Next.js, React, TypeScript, Ketcher, 3Dmol.js; FastAPI, httpx, official MCP Python SDK, SQLite WAL; existing RDKit/PyTorch models.

**Spec:** `docs/superpowers/specs/2026-11-02-web-migration-design.md`; exact interfaces: `docs/api-contract.md`.

## Global Constraints

- Work on `codex/next-fastapi-migration` in the current checkout; preserve existing unrelated generated-file changes.
- Provider is a configurable OpenAI-compatible API; no browser keys and no fabricated inference/AI outputs.
- Screenshot guides layout and spacing; adapt scientific functionality and OpenMolSpec branding.
- Loopback defaults, separate API and chemistry processes, configurable data directories and URLs.
- Do not publish or push. Legacy numerical behavior remains covered by existing tests.

## Review Focus

- A molecule edited during prediction must not change a submitted job's input snapshot.
- Browser disconnect/reload must preserve conversations and expose run/task terminal states.
- Malformed spectra, invalid SMILES, numerical NaN/Infinity, and conflicting input representations must fail clearly.
- Missing model assets or unavailable chemistry/provider services must never produce invented scientific results.
- MCP and direct HTTP must execute the same handlers and retain theoretical/cache provenance.

## Task 1: Independent chemistry service and MCP

Files: create `services/chemistry/`, `tests/services/test_chemistry_service.py`; reuse `openmolspec_ui/` numerical modules without changing their public behavior.

Produces: all chemistry HTTP/MCP interfaces in `docs/api-contract.md`.

- [x] Write/run failing tests for molecule resolution, invalid/conflicting input, spectrum persistence, calculation status/failure and restart recovery.
- [x] Implement durable SQLite jobs, a serialized worker, science adapters, capability status, HTTP endpoints and official MCP tools sharing handlers.
- [x] Pass tests, then verify MCP discovery and `inspect_molecule` over a real HTTP connection.

## Task 2: Next.js scientific chat frontend

Files: create `web/`; consumes application HTTP/SSE contract, never direct Python imports.

- [x] Build the screenshot-inspired responsive shell and functional sidebar, composer, modes, suggestions and history.
- [x] Implement API client, persisted SSE parsing/reconnect, attachments and failure states.
- [x] Add SMILES/Ketcher editing, 3D visualization, spectral import/display, job submission/results/provenance.
- [x] Test stream parser/state behavior, typecheck and production build.

## Task 3: FastAPI application and Agent runtime

Files: create `services/api/`, `tests/services/test_application.py`, `tests/services/test_agent.py`.

Consumes chemistry HTTP/MCP; produces all `/api` interfaces in the contract.

- [x] Write/run failing persistence, conversation concurrency, event replay, invalid attachment reference, provider unconfigured and streamed tool-loop tests.
- [x] Implement SQLite conversation/run event store, chemistry proxy, uploads and streaming OpenAI-compatible provider.
- [x] Connect Agent tools through real MCP, bound turns/timeouts and persist tool results/replies independently of browser connections.
- [x] Pass API/runtime tests and exercise a local fake provider through actual MCP chemistry calls.

## Task 4: Launch, integration and visual verification

Files: update `setup.sh`, `start.sh`, README and environment/deployment examples; add service requirements, ignore rules and optional container launch files.

- [x] Provide one-command setup/start with automatic service health checks and clear startup failure reporting.
- [x] Run service tests and existing spectroscopy tests; record baseline unavailable upstream benchmark modules separately.
- [x] Build/typecheck frontend and verify all three processes with HTTP, actual MCP client, and browser primary interactions.
- [x] Compare desktop/mobile screenshots to the supplied reference, fix visual issues and save `design-qa.md`.
- [x] Obtain a fresh code review, fix material findings, rerun affected checks and leave the application running for the user.

## Decisions and progress

- User explicitly requested execution of the already agreed architecture; continue implementation without another design approval round.
- Use the current checkout and a feature branch so existing environment/assets and user file paths remain usable.
- Use actual Next.js rather than the Product Design Vite prototype starter because the requested framework and production behavior are explicit.
- Local persistence starts with SQLite and filesystem storage; service boundaries/configuration support deployment changes without UI rewrites.

## Final verification

- Completed on 2026-11-02 in the existing checkout; no commit, push or publication performed.
- 82 Python service/scientific tests and 19 frontend tests passed; typecheck, production build, dependency check and Compose configuration passed.
- Fresh independent reviews completed; all material findings fixed and covered by regression checks.
- Browser verified desktop/mobile, live SMILES/Ketcher/3D, parsed spectrum input and exact-ID context behavior.
- Full upstream suite: 27 collection errors from absent benchmarks package, captured and documented.
- Final services run on loopback ports3000/8000/8001; provider and scientific assets remain user configuration.
- See design-qa.md and docs/migration_validation.md for evidence and limits.
