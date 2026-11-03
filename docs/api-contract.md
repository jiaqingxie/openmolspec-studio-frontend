# Web migration API contract

## Authentication and accounts

The public guide is `/integrations/mcp`. `GET /api/integrations/mcp` returns
`{local_url, cloud_url}`, with `null` for unconfigured endpoints. The gateway
is `/api/mcp` over Streamable HTTP and checks the MolSpec bearer token on every
request. Missing, expired and revoked tokens receive `401`. The gateway replaces
all internal identity headers with the token owner's verified identity.

- `GET /api/account` reports login state, mock availability, identities, and signed-in account balance.
- `POST /api/auth/mock` accepts `{identity}` when the development setting is enabled. It issues a server-backed HTTP-only cookie.
- `POST /api/auth/logout` deletes the current session. All application data routes use the verified cookie.
- `GET /api/account/usage` returns available/reserved credits and recent usage entries for the caller.
- `GET|POST /api/account/tokens` lists metadata or creates a token with `{name, expires_in_days}`.
  Creation returns the secret once. `DELETE /api/account/tokens/{id}` revokes an owned token.
- `GET /api/attachments/{id}/download` streams an owned original upload where available.

Private chemistry HTTP and MCP require the internal key and a verified owner ID
from the application. The private capability probe requires the key. Resource IDs
and idempotency keys are scoped to their owners. A submission that cannot reserve
credits returns `insufficient_credits` before queueing work. The allowance resets at
midnight in Asia/Shanghai. A calculation reserves one credit from its submission
day and consumes it if execution starts. Work canceled before execution and
unavailable models release the reservation.


All services bind loopback by default. Next.js forwards `/api/*` to the application service (port 8000). Chemistry is a separate service on port 8001. Error responses are `{ "error": { "code": "...", "message": "..." } }` unless FastAPI validation uses its standard 422 detail.

## Chemistry HTTP

- `GET /health` -> `{status:"ok",service:"chemistry"}`.
- `GET /v1/capabilities` -> `{device:string,root:string,domain:"theoretical",capabilities:{predict_spectra:{available:boolean,detail:string},retrieve:{available:boolean,detail:string},predict_gap:{available:boolean,detail:string},generate:{available:boolean,detail:string}}}`.
- `POST /v1/molecules/resolve` body `{smiles?:string,xyz?:string}` -> `{id,smiles,formula,molecular_weight,atom_count,inchi_key,molblock,xyz,svg}`. Persist the resolved molecule and its coordinates.
- `GET /v1/molecules/{id}` -> the same persisted molecule, preserving its original conformer without regeneration from SMILES.
- `POST /v1/spectra/parse` body `{content:string,name:string,modality?:"ir"|"raman"}` -> `{id,name,modality,wavenumber:number[],intensity:number[]}`. Use existing parser and persist the normalized spectrum.
- `GET /v1/spectra/{id}` -> the same persisted spectrum.
- `POST /v1/jobs` body `{operation:"predict_spectra"|"retrieve"|"predict_gap"|"generate",inputs:object}` -> a job. Inputs accept `molecule_id` or `smiles` or `xyz`; spectral operations accept `ir_id`, `raman_id`, direct `ir`/`raman` arrays, `nmr_h`, `nmr_c`, `limit`. Reject conflicting structure representations and invalid numerical data.
- `GET /v1/jobs` -> `Job[]`; `GET /v1/jobs/{id}` -> `Job`; `POST /v1/jobs/{id}/cancel` -> `Job`.
- `Job`: `{id,operation,status:"queued"|"running"|"succeeded"|"failed"|"cancelled",inputs,created_at,updated_at,result:object|null,error:{code,message}|null}`. JSON serialize numpy values; preserve units/backend/cache metadata. Serialize heavy inference, persist terminal states, recover interrupted jobs safely on service restart.

## Chemistry MCP

Streamable HTTP endpoint `/mcp`, official SDK. Tools:
- `get_capabilities()`.
- `inspect_molecule(smiles:string)` -> molecule ID and compact properties.
- `predict_spectra(smiles?:string,molecule_id?:string)`.
- `retrieve_candidates(ir_id?:string,raman_id?:string,nmr_h?:number[],nmr_c?:number[],limit?:number)`.
- `predict_gap(ir_id?:string,raman_id?:string,nmr_h?:number[],nmr_c?:number[])`.
- `generate_candidates(ir_id?:string,raman_id?:string,nmr_h?:number[],nmr_c?:number[],limit?:number)`.
- `get_calculation(job_id:string)` -> compact job result/status.

Calculation tools submit through the same durable jobs, await their completion up to a bounded timeout, and return `{job_id,status,summary,...}` with bounded scientific summaries and provenance. Do not return 1024-point arrays/SVG/molblock to the LLM. On timeout return the live job ID for polling, not an invented failure. Use persisted IDs for uploaded inputs.

## Application HTTP (`/api`)

- `GET /api/status` -> `{chemistry:Capabilities|null,agent:{configured:boolean,model:string|null},version:"2.0.0"}`. Include optional `chemistry_error` when unavailable.
- `GET /api/conversations` -> `ConversationSummary[]`; `POST /api/conversations` body `{title?:string}` -> summary.
- `GET /api/conversations/{id}` -> summary plus `{messages:Message[],active_run_id:string|null}`.
- `DELETE /api/conversations/{id}` -> 204 (reject deleting an active run).
- `POST /api/conversations/{id}/messages` body `{content:string,mode:"quick"|"deep",request_id?:string,attachment_ids?:string[],context?:{molecule_id?:string,smiles?:string,ir_id?:string,raman_id?:string}}` -> `text/event-stream`, persists a user message and runs Agent in an independent task.
- `GET /api/runs/{id}/events?after=0` -> resumable persisted SSE; event IDs increase. Events: `run` `{id,user_message,assistant_message_id}`, `status` `{stage,label}`, `tool_start` `{id,name,args}`, `tool_end` `{id,name,result}`, `delta` `{content}`, `done` `{message,job_ids}`, `error` `{code,message}`. An error is terminal; stored assistant message has `status:"failed"`. Runs continue if the browser disconnects. Reject concurrent runs in one conversation with 409.
- `ConversationSummary`: `{id,title,created_at,updated_at}`. `Message`: `{id,role:"user"|"assistant",content,created_at,status:"completed"|"running"|"failed",attachments:Attachment[],tool_calls:object[],context:object}`. User-message context snapshots persist molecule/spectrum IDs and optional `nmr_h` / `nmr_c` finite peak arrays (max4096) across follow-up turns.
- `POST /api/uploads` multipart `file`, `modality=ir|raman`, `axis_unit`, `intensity_unit`, `domain`, `axis_mode` -> `Attachment` `{id,name,kind:"spectrum"|"molecule",modality?,spectrum_id?,molecule_id?,smiles?,formula?,size}`. Supported CSV/TXT/TSV/DAT spectra and XYZ, limit 10 MiB. References passed to Agent must belong to the conversation request, never arbitrary server filesystem paths.
- `POST /api/attachments/molecule` body `{molecule_id:string}` -> `201 Attachment`. Verifies the molecule exists in the chemistry service and saves a durable reference named `formula.mol`. The editor resolves a new structure before attaching; opening an existing attachment uses its saved ID and does not regenerate geometry. Missing structures retain the chemistry service's error status.
- `/api/molecules/resolve`, `/api/spectra/parse`, `/api/spectra/{id}`, `/api/jobs`, `/api/jobs/{id}`, `/api/jobs/{id}/cancel` proxy the corresponding chemistry HTTP operations; return identical JSON.

Frontend must handle provider unconfigured, chemistry offline, empty history, malformed inputs, missing model assets, run/job failure, and reload with an active run. All empty states are real; no fake chart data or fake AI answers.

## Agent execution and scientific input metadata

- `POST /api/conversations/{id}/messages` accepts an optional `request_id`. An identical request in the same conversation replays the original SSE run. Reusing the ID with different content, attachments, context or mode returns 409.
- `GET /api/status` reports `agent.configured` from service configuration and `agent.verified` after a successful run in the current process. A provider error invalidates the latter. `done` SSE events include SDK `usage` counters. Providers that omit usage produce lower bounds, with `unmeasured_requests` tracked by the SDK.
- The Agent SDK defers private MCP tools before execution. The application persists messages, tool IDs and pending results. It passes a stable `request_id` to chemistry on retry or restart. A waiting calculation resumes from its saved ID. A model stream interrupted outside that checkpoint is marked failed.
- `POST /v1/jobs` and calculation MCP tools accept `request_id`. Same payload reuses the job, and a different payload produces a conflict. Agent stop does not cancel jobs. Job cancellation works while queued.
- Spectrum metadata fields are `axis_unit: cm^-1|nm|unknown`, `intensity_unit`, `domain: theoretical|experimental|unknown` and `axis_mode: explicit|model_grid`. Unknown metadata is accepted for preview. Model eligibility is enforced by chemistry for both HTTP and MCP. One-column model-grid input requires 1024 points and a declared cm⁻¹ axis. Explicit input needs full axis coverage, valid values, distinct axis positions and declared model-compatible units and domain.
- Spectrum lookup returns `raw`, `processing`, `quality`, `provenance` and the plotted `wavenumber` and `intensity` arrays. Legacy stored inputs without original units are preview-only. Explicit partial ranges stay partial.
- `inspect_spectrum(spectrum_id)` returns bounded source/units/range/quality information and up to eight sampled local maxima. This is a numerical summary without chemical peak assignment. Successful prediction returns reusable `ir_id` and `raman_id`. Full arrays are available through `GET /api/jobs/{id}` or `GET /api/spectra/{id}`.
