# OpenMolSpec migration visual QA

Date: 2026-11-02. Target is the user's screenshot as a visual reference, adapted to OpenMolSpec functionality and branding.

## Evidence and normalization

- Source: `/var/folders/68/tx0676vs5rzgc9tfrkp_5ccc0000gn/T/codex-clipboard-f7e42a4e-cae0-4448-becd-796a4d694f2d.png` — 2932 × 1528 pixels. Original CSS viewport/density is unknown.
- Final implementation: `artifacts/migration/desktop.png` — 1600 × 834 pixels at a 1600 × 834 CSS viewport, empty conversation, provider honestly unconfigured.
- Full-view comparison: `artifacts/migration/comparison.png` — reference normalized to the implementation's aspect and pixel dimensions, then combined vertically with final rendered capture.
- Focused composer comparison: `artifacts/migration/composer-comparison.png` — matching 1060 × 385 regions from the normalized images, combined in one comparison image.
- Mobile: `artifacts/migration/mobile.png` — 390 × 844 CSS/pixels; `mobile-workbench.png` shows the native scrollable workbench and reachable footer actions.
- Additional rendered states: `workbench.png` (actual aspirin 3D conformer), `editor.png` (Ketcher), `spectrum.png` (explicit QA input CSV, not a model prediction).
- All browser interactions and captures used Codex's in-app browser. Screenshots are local generated artifacts, excluded from Git.

## Required fidelity surfaces

1. **Fonts/typography:** preserved the reference's large Chinese serif heading and restrained sans-serif controls. Headline and branding copy intentionally describe molecular spectroscopy. Labels and titles wrap within mobile bounds.
2. **Spacing/layout:** fixed pale sidebar, full-height paper canvas, centered heading and wide composer follow the reference composition. Mode, attachment, model and submit controls share the composer baseline. Suggestions remain below the input. Mobile uses a drawer and scrollable scientific panels rather than compressing desktop columns.
3. **Colors/tokens:** warm near-white canvas, fine neutral borders, restrained scientific blue, muted secondary text, white composer and quiet selected-navigation state. Connection/unavailable states use text and controls, not color alone.
4. **Assets:** standard Phosphor scientific/navigation icons, real RDKit structure drawings and local 3Dmol/Ketcher rendering. Third-party mascot, desktop-download promotion, unrelated navigation and legal copy are intentionally replaced by actual OpenMolSpec functions; no fake download controls or model imagery.
5. **Copy/content:** scientific domain, unavailable resources, units, file limits and model configuration states are explicit. No seeded chat history, invented model scores, or fabricated predictions. Screenshot branding is a reference, not a representation that this is the third-party product.

## Comparison history and fixes

- Initial desktop/full-view and focused-input comparisons: composition matches the selected direction. Intentional differences are OpenMolSpec copy/icons, fewer relevant navigation items and an unconfigured-provider hint.
- Mobile QA found the off-canvas sidebar remained in accessibility/keyboard traversal when closed. Added mobile hidden/visible and pointer-state rules. Final mobile AX tree excludes the closed sidebar and retains the open-menu control; opening the drawer and entering the workbench both pass.
- Initial resize capture caught a drawer transition in progress; the stable mobile capture was recaptured rather than treating animation timing as a layout defect.
- Final scientific-input review fixed XYZ re-embedding, stale context labels and dirty-SMILES selection. Recaptured/retested after a coordinated production rebuild. Uploading a water XYZ opens the persisted structure; selecting ethanol then editing ethylamine leaves the selected ethanol chip correctly labeled.
- Restarts briefly interrupted the initial browser tab. Fixed a real launcher TIME_WAIT port-check issue, verified shutdown/restart, opened a fresh in-app tab and recaptured the healthy final build.

## Primary interactions tested

- Sidebar navigation, mobile drawer open/close and scientific-workbench access.
- SMILES aspirin parsing and molecular properties from the real chemistry service.
- 2D drawing, interactive 3D display, and local Ketcher initialization.
- Clear Ketcher canvas, draw benzene via the template, apply and receive canonical `c1ccccc1` / C6H6 from RDKit.
- Upload a QA theoretical-input CSV through the file chooser, normalize to 1024 points and render the real parsed spectrum with range selection.
- Upload XYZ from the chat composer, resolve its persisted molecule ID and display the original structure.
- Selected-context labels remain attached to their input IDs across later workbench edits.
- Model absence disables unavailable computation and explains the missing assets. Provider absence disables submission and offers working scientific tools.
- Desktop and mobile console checks: no application warning/error messages observed in verified states. Mobile width equals document width (390 pixels), without horizontal page overflow.

## Findings

No remaining actionable P0/P1/P2 visual findings in the verified scope.

## Follow-up polish

- The mobile scientific workbench is vertically scrollable, including its actions; a future sticky action bar is optional.
- Fine typography and paper-pattern density can be tuned further after product copy is finalized.

## Verification limits

Live LLM generation and checkpoint inference require user-provided configuration/assets. Their protocols and complete Agent→MCP→chemistry path are verified with a local test provider and real chemistry operations, separately from visual QA. No claim of full multi-tenant accessibility/security audit or third-party pixel-identical cloning is made.

final result: passed


## molspec interface update — 2026-11-02

Final result: passed. The user requested a new molspec identity and a conversation-only flow, superseding the first migration's task shortcuts and configuration controls. The current requirement audit and desktop/mobile screenshots are recorded in [molspec interface validation](docs/molspec_interface_validation.md). Original SVG identity: web/public/molspec-mark.svg. Final homepage images: artifacts/molspec-interface/desktop-home.png and mobile-home.png. Real Ketcher drawing, SMILES insertion, draft/history attachment previews, 2D/3D structures, parsed IR input and mobile editing were exercised.
