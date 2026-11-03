# molspec interface verification — 2026-11-02

## Requirement audit

| User requirement | Implementation | Observed evidence |
| --- | --- | --- |
| molspec name, cute spectroscopy logo, cohesive design | Original vector spectrum-peak mascot with a face and molecule motif; lowercase wordmark, sage/ivory surfaces; logo reused in favicon, sidebar, welcome and assistant identity | Real desktop 1440×900 and mobile 390×844 browser screenshots; document title is molspec |
| Agent selects tasks | Removed welcome task launchers, manual operation workbench, quick/deep controls and model configuration UI from Workspace | Desktop and mobile accessibility trees expose conversation, attachment and drawing actions; calculation view is read-only and opened from actual tool records |
| Molecular editor replaces removed composer controls | Lazy-loaded Ketcher directly from “画分子”; external SMILES load; “插入 SMILES” and “添加为附件” actions | Drew benzene on the actual canvas and attached C6H6; inserted CCO into a question without replacing it; mobile imported CCN and added C2H7N |
| Openable attachments | Clickable cards in draft and saved messages; exact molecule/spectrum ID lookup; 2D/3D or spectrum preview | Benzene 3D rendered; uploaded IR CSV opened with 1024 points; ethanol attachment survived send and page reload and reopened as CCO |
| Editing does not mutate the sent structure | Editor saves a new resolved molecule and durable attachment via POST /api/attachments/molecule | Edited historical CCO into a C2H7N draft attachment, removed it, reopened historical attachment and observed original CCO |

## Regression evidence

- 28 frontend tests passed (`cd web && npm test`).
- 83 Python service/scientific tests passed (`.venv/bin/python -m pytest tests/services tests/test_chemistry.py tests/test_spectra.py tests/test_config.py tests/test_inference.py tests/test_theoretical.py -q --tb=short`); one existing Starlette TestClient deprecation warning.
- Typecheck and `npm run build` passed. Production page and API proxy returned HTTP 200.
- Dependency check and whitespace validation passed.
- Runtime dev compilation initially exposed Paper/Ketcher Node-only resolution under Turbopack. Development now uses the same Webpack mode as production; the root page subsequently returned 200 and the actual editor ran.
- Fresh independent review found three P2 defects: stale editor export after invalid SMILES, pending POST clearing a newer draft, and an old upload entering another conversation. All fixed. Real browser reproduced the invalid import before the fix and verified it remains in the editor with an error afterward (Insert, Load and Attach). Installed Ketcher runner regression tests cover its swallowed FAILURE event. Deferred component-handler tests cover send/upload ownership; these isolate React hooks and networking and do not claim to test layout or React scheduling.
- Attachment limit checks and a retry action for result reads were added during the fix pass.
- Backend mode/job APIs remain compatible; selecting tools belongs to Agent execution, while input validation and execution limits remain server responsibilities. Rebuilding geometry is allowed only when explicitly editing a new molecule; reading attachments preserves the stored ID/coordinates.

## Artifacts

Under `artifacts/molspec-interface/` (local QA output, ignored by Git):

- `desktop-home.png`: final production desktop homepage.
- `mobile-home.png`: final production mobile homepage.
- `editor.png`, `mobile-editor.png`: real molecular editor.
- `molecule-preview.png`, `mobile-preview.png`: saved structure preview.
- `composer-attachment.png`: attachment inserted in the composer.
- `mobile-spectrum.png`: uploaded QA spectrum, explicitly input data rather than a model prediction.

## Practical limits

The environment has no configured LLM or complete spectroscopy model assets. The app reports unavailable dialogue honestly when submitted; no fabricated answer or predicted spectrum was used in browser QA. Drawing, SMILES insertion, file parsing and persisted previews were verified against the real local services. Existing upstream tests outside the available suite still require the absent `benchmarks` source package (see migration_validation.md). The React 18/Next 16 compatibility constraint is unchanged. Local services remain private single-workspace processes.
