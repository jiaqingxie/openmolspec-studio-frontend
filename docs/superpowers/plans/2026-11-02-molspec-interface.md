# molspec conversation interface

## Intent and design

Implement the user's three requested changes in the existing Next.js/FastAPI checkout. The user has explicitly requested execution; preserve the migration and current branch. Do not commit or publish.

- Brand: lowercase **molspec**, a small friendly spectrum-shaped mascot, sage green, warm ivory, calm typography. Use scalable original SVG artwork for the logo, favicon and assistant identity.
- One primary interaction: a conversation. Remove manual calculation launchers, operation selectors, quick/deep controls and model configuration UI. The existing Agent selects MCP tools; server validation and resource limits remain authoritative. Calculation output remains viewable from actual Agent results.
- Composer: upload research files or open a molecular editor directly. The editor supports drawing and loading SMILES, then either inserting SMILES into the current draft or attaching a saved structure.
- Attachments: previews are clickable in the composer and saved messages. Molecules open the exact persisted ID in 2D/3D; spectra open their saved plot. Editing an attachment creates a new structure rather than changing the scientific input already sent.

The existing mixed workbench and its direct launch buttons cannot provide this flow without retaining the unwanted task selection. Use dedicated molecule, attachment preview and read-only result dialogs; reuse Ketcher, 3Dmol, spectrum charts and calculation rendering.

## Implementation and verification

1. [x] Add test-first durable structure attachment API, verifying molecule ID, missing IDs, reopen and message/history persistence.
2. [x] Add test-first composer helpers for insertion without lost text and attachment-only messages.
3. [x] Implement the molecular editor, clickable previews and read-only calculation results.
4. [x] Replace the conversation shell and visual identity; remove all manual task/mode/model controls from the rendered app.
5. [x] Run frontend tests/typecheck/build and affected API/service tests. Verify desktop/mobile, actual drawing, SMILES insertion, attachment preview/reopen/removal and history persistence in the browser.
6. [x] Fresh independent review, address material findings, save screenshots and a requirement-by-requirement verification record; leave the new app running.

## Review focus

- Inserting SMILES must preserve the user's question and caret selection.
- Closing an editor without applying must leave the draft and attachments untouched.
- Opening a saved XYZ must never regenerate its coordinates from SMILES.
- Structure attachments must persist server-side and remain visible after a conversation reload.
- Hidden task/configuration controls must not survive in mobile menus or attachment previews.
- Errors/unconfigured services must remain honest without exposing configuration workflows in the product.

## Outcome

Completed and reviewed in the current checkout. 28 frontend and 83 available Python tests passed; production build, typecheck and real desktop/mobile interactions verified. Invalid editor imports and async draft ownership have regression coverage. See docs/molspec_interface_validation.md for the requirement audit, evidence and runtime limitations. No commit or publication.
