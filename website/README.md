# OpenMolSpec project website

Public URL: https://jiaqingxie.github.io/openmolspec.github.io/

The project navigation opens the workspace, datasets, documentation and source repository. `portal.html`, `portal.css` and `portal.js` implement the active
interface. GitHub Pages hosts its static frontend; a separate Python service
executes the real model requests. The Documentation entry opens the bilingual manual bundled with the same site release at `docs/`. The documentation section also links to Read the Docs.

The Tool workspace offers NMR shift prediction and assignment, solvent transfer,
TransPeakNet HSQC prediction from SMILES and solvent, with optional measured peaks for assignment, H/C NMR search and generation, GLACIER and
ICEBERG MS/MS, conformer-based IR/Raman, multimodal gap prediction and structure
generation/retrieval, and Agent Harness.
The agent uses an OpenAI-compatible model API and the actual OpenMolSpec MCP
stdio server. Expandable tool steps adapt the interaction in Luffy202's branch
`codex/next-fastapi-migration`, commit
`11577df2236241ee28f7c8940faf6ebab5f78476`. The project presentation draws on the
section pacing of Shanghai AI Lab's [Sage–Taiyi](https://alpha-innovator.github.io/Sage-Taiyi/),
with original OpenMolSpec styling and content.
The homepage displays the three measured cross-peaks of butanenitrile (TransPeakNet spectrum 32869). Surface and contour views share the measured coordinates and use illustrative peak shapes. “Try HSQC example” loads the same molecule, solvent and peaks into the workspace. The default workspace chart displays the recorded NMRNet carbon shifts for ethanol until a user runs a model.
Under the workspace, expand “Compare ethanol and dimethyl ether” to drag oxygen between the highlighted bond positions and send either isomer to the model form.

Dataset previews contain 32 actual test records across eight experimental views,
with structures, source conditions and downloadable JSON. Missing intensities
remain missing: the chart labels them as peak positions. Counts distinguish
spectra from unique molecules. The four-channel Tool example is a computed
benchmark input, separately identified in the interface.
The external TransPeakNet dataset card links to the author's HSQC test archive.
Open that ZIP directly using `molspectra("transpeaknet_hsqc_test", root=zip_path)`.

Build from the release repository after regenerating documentation figures:

```bash
python scripts/build_dataset_preview.py --data-root /path/to/cleaned-data
python scripts/build_readthedocs.py --output .runtime/manual-site-v1 --strict
python scripts/build_project_site.py --output .runtime/github-pages-v1 --manual .runtime/manual-site-v1
python -m http.server 8769 --directory .runtime
```

Preview `http://localhost:8769/github-pages-v1/`. Publish the generated directory
to the `main` branch of `jiaqingxie/openmolspec.github.io`; GitHub Pages serves its
repository root. Keep `.nojekyll`. Relative asset paths support the project URL.

Set `website/assets/service-config.json` to the HTTPS API origin before building.
See [the API deployment instructions](../online_api/README.md). Provider keys stay
in the server process; the browser receives only the API origin. A temporary
tunnel is sufficient for a demonstration, but its URL and availability are not a
permanent deployment contract.

`assets/agent-demo/run.json` contains a completed real model API → MCP run,
including numerical outputs, timestamps and token usage. The three screenshots
show its recorded stages, explicitly labeled as a recorded API run. Replay does
not make new predictions; the Agent tab submits new requests. Scientific figures
and the manual's notebook outputs continue to come from recorded executions.
