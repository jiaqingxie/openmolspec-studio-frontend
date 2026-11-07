# OpenMolSpec Tool Gallery

Web frontend for the OpenMolSpec Studio tool gallery: four trained checkpoints exposed as
one-click tools (structure → IR/Raman/NMR, spectral retrieval, spectrum → HOMO–LUMO gap,
spectrum → structure generation). Bootstrap 5 UI + FastAPI inference server, no chat, no
accounts, no MCP.

## Layout

```
pages/ components/ lib/ styles/ public/   Next.js 16 app (static export)
server.py                                 FastAPI server wrapping openmolspec_ui
openmolspec_ui/                           Inference layer (unchanged from the portable studio)
run_web.sh                                Cluster launcher (uvicorn, port 8501)
```

## Develop (local, demo data)

```sh
npm install
npm run dev        # http://127.0.0.1:3001 — falls back to demo data when the API is offline
```

## Deploy (cluster)

```sh
npm run build                                  # emits static site to out/
rsync -a out/ server.py run_web.sh <host>:<gallery-dir>/
# on the host (needs OPENMOLSPEC_ROOT pointing at the portable studio assets):
tmux new-session -d 'cd <gallery-dir> && ./run_web.sh > web.log 2>&1'
```

`run_web.sh` reads:

- `OPENMOLSPEC_ROOT` — portable studio root (checkpoints, src, benchmark_data). Default:
  `/mnt/shared-storage-user/xiejiaqing/openmolspec-studio-portable`
- `PYTHON` — interpreter with torch/rdkit/lmdb. Default: the shared studio venv.
- `PORT` — default 8501.

Access from a laptop: `ssh -L 8501:127.0.0.1:8501 <host>` → http://localhost:8501

## Notes

- Fonts: IBM Plex Sans / Mono via `next/font/google`, self-hosted at build time — no
  runtime dependency on Google.
- The spectrum LMDB is copied to `/tmp` on first start: shared storage does not support
  the mmap mode lmdb needs.
- Molecule previews use mol blocks; candidate structures are rendered server-side by RDKit
  at `/api/render?smiles=`.
