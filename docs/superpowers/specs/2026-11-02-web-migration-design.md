# OpenMolSpec web product migration

The user approved Next.js + FastAPI + an independent chemistry service exposing MCP, with the supplied scientific-chat screenshot as the visual reference. Implement this in the existing checkout on `codex/next-fastapi-migration`.

## Product

An OpenMolSpec chat workspace with a pale fixed sidebar, warm dotted canvas, centered serif welcome heading, large composer, quick/deep mode, attachments, model status, suggested prompts, persistent conversation history, and a responsive molecule/spectrum workspace. Use OpenMolSpec branding and scientific copy. Preserve access to all four existing calculations. Molecular editing uses Ketcher; 3D structure and spectra are interactive. Never invent inference results, conversations, or model availability.

## Architecture

- `web/`: Next.js / React / TypeScript. Same-origin `/api/*` requests proxy to FastAPI. UI actions use ordinary HTTP; chat uses persisted SSE run events.
- `services/api/`: FastAPI, durable conversations/messages/run events/uploads, an OpenAI-compatible streaming tool loop, and MCP client. No PyTorch/model imports.
- `services/chemistry/`: independent FastAPI process owning a single serialized compute worker, persistent calculation jobs and parsed scientific inputs. Reuse `openmolspec_ui.inference`, `chemistry`, `spectra`, and `theoretical` functions.
- Official MCP Python SDK provides Streamable HTTP tools on chemistry `/mcp`. HTTP and MCP use the same calculation handlers and jobs.
- SQLite WAL and local artifact storage give runnable persistence without external infrastructure. Data paths and service URLs are configurable; document a private single-workspace deployment and future database/storage substitution. Do not imply multi-user authentication exists.

## Scientific contracts

Inputs and results retain theoretical-domain labels, units, calculation mode/backend, and cache provenance. LLM context uses molecule/spectrum/job IDs and compact summaries, not full spectral arrays. Missing checkpoints produce explicit capability status and structured errors. Structure preview and editing work without checkpoints. Jobs bind immutable input snapshots so subsequent editing cannot alter an existing calculation.

## Agent

The user selected a generic OpenAI-compatible endpoint. Configure `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENMOLSPEC_LLM_MODEL` on the server. No keys enter browser code or logs. An unconfigured provider is shown honestly and does not generate fake assistant responses. Bound tool turns and timeouts; persist tool events and final replies. Runs survive a browser disconnect, and failed/interrupted runs are visible after reload.

## Visual thesis

Quiet ivory paper, fine neutral dividers, restrained scientific blue, large Chinese serif heading, generous whitespace and functional controls. The main composer is the dominant interaction. The selected screenshot is a reference rather than third-party branding to reproduce.

Content: sidebar navigation/history; welcoming chat empty state and three useful starter actions; conversation with tool progress and scientific results; an optional molecule/spectrum workbench.

Interaction: a short welcome entrance, clear composer focus/submit state, and a restrained workspace/modal transition. Respect reduced motion.

## Verification

Exercise molecule resolution, spectral parsing, missing-model errors, durable calculation jobs, MCP discovery and a real MCP call, persisted conversations, streamed tool loop with a local fake provider, disconnect/recovery, invalid inputs and unavailable services. Build/typecheck Next.js, run existing relevant spectroscopy tests, and inspect desktop/mobile rendering and real browser interactions against the screenshot. Provide one-command setup/start, environment example, service tests and deployment instructions.
