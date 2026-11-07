from __future__ import annotations

import os
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from rdkit import Chem

GALLERY_ROOT = Path(__file__).resolve().parent
PORTABLE_ROOT = Path(
    os.environ.get(
        "OPENMOLSPEC_ROOT",
        "/mnt/shared-storage-user/xiejiaqing/openmolspec-studio-portable",
    )
)
sys.path.insert(0, str(GALLERY_ROOT))

from openmolspec_ui.chemistry import molecule_from_smiles, smiles_png  # noqa: E402
from openmolspec_ui.config import discover_assets  # noqa: E402
from openmolspec_ui.inference import OpenMolSpecService  # noqa: E402
from openmolspec_ui.spectra import SPECTRUM_AXIS, SpectralInput, minmax  # noqa: E402

CAPABILITY_TO_SLUG = {
    "构象 → 谱图": "structure-to-spectrum",
    "谱图 → 结构检索": "spectrum-retrieval",
    "谱图 → HOMO–LUMO gap": "spectrum-to-gap",
    "谱图 → 结构生成": "spectrum-to-generation",
}

app = FastAPI(title="OpenMolSpec Tool Gallery", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3001", "http://localhost:3001"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_service: OpenMolSpecService | None = None


def service() -> OpenMolSpecService:
    global _service
    if _service is None:
        assets = discover_assets(PORTABLE_ROOT)
        if assets.spectrum_lmdb is not None:
            local_lmdb = Path("/tmp/openmolspec-gallery") / assets.spectrum_lmdb.name
            if not local_lmdb.is_file():
                local_lmdb.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(assets.spectrum_lmdb, local_lmdb)
            assets = replace(assets, spectrum_lmdb=local_lmdb)
        _service = OpenMolSpecService(assets)
        _service.preload()
    return _service


class MoleculeRequest(BaseModel):
    smiles: str


class SpectrumPayload(BaseModel):
    wavenumber: list[float] | None = None
    intensity: list[float]


class QueryRequest(BaseModel):
    ir: SpectrumPayload | None = None
    raman: SpectrumPayload | None = None
    nmr_h: list[float] | None = None
    nmr_c: list[float] | None = None
    limit: int = 8


def to_axis(payload: SpectrumPayload) -> np.ndarray:
    intensity = np.asarray(payload.intensity, dtype=np.float64)
    if payload.wavenumber and len(payload.wavenumber) == len(intensity):
        axis = np.asarray(payload.wavenumber, dtype=np.float64)
        order = np.argsort(axis)
        resampled = np.interp(SPECTRUM_AXIS, axis[order], intensity[order])
        return minmax(resampled.astype(np.float32))
    return minmax(
        np.interp(
            SPECTRUM_AXIS,
            np.linspace(400.0, 4000.0, len(intensity)),
            intensity,
        ).astype(np.float32)
    )


def to_input(request: QueryRequest) -> SpectralInput:
    if request.ir is None and request.raman is None:
        raise HTTPException(status_code=400, detail="请至少提供 IR 或 Raman 谱图。")
    return SpectralInput(
        ir=to_axis(request.ir) if request.ir else None,
        raman=to_axis(request.raman) if request.raman else None,
        nmr_h=np.sort(np.asarray(request.nmr_h, dtype=np.float32)) if request.nmr_h else None,
        nmr_c=np.sort(np.asarray(request.nmr_c, dtype=np.float32)) if request.nmr_c else None,
    )


@app.get("/api/status")
def status() -> dict:
    assets = discover_assets(PORTABLE_ROOT)
    tools = {
        slug: available
        for label, (available, _detail) in assets.capability_status().items()
        for slug in [CAPABILITY_TO_SLUG.get(label, label)]
    }
    return {"device": service().device, "tools": tools}


@app.get("/api/sample")
def sample() -> dict:
    sample, metadata = service().sample_spectrum()
    return {
        "ir": [float(value) for value in sample.ir],
        "raman": [float(value) for value in sample.raman],
        "nmr_h": [float(value) for value in sample.nmr_h],
        "nmr_c": [float(value) for value in sample.nmr_c],
        "meta": metadata,
    }


@app.post("/api/molecule")
def molecule(request: MoleculeRequest) -> dict:
    try:
        mol = molecule_from_smiles(request.smiles)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "xyz": Chem.MolToMolBlock(mol.mol),
        "formula": mol.formula,
        "atoms": int(mol.atoms),
        "source": mol.source,
    }


@app.post("/api/predict")
def predict(request: MoleculeRequest) -> dict:
    try:
        mol = molecule_from_smiles(request.smiles)
        result = service().predict_spectra(mol)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(error)) from error
    return {
        "wavenumber": [float(value) for value in result["wavenumber"]],
        "ir": [float(value) for value in result["ir"]],
        "raman": [float(value) for value in result["raman"]],
        "nmr_h": [float(value) for value in result["nmr_h"]],
        "nmr_c": [float(value) for value in result["nmr_c"]],
        "modes": [
            {
                "frequency": float(frequency),
                "ir_activity": float(ir_activity),
                "raman_activity": float(raman_activity),
            }
            for frequency, ir_activity, raman_activity in zip(
                result["mode_frequencies"],
                result["ir_activities"],
                result["raman_activities"],
            )
        ],
    }


@app.post("/api/retrieve")
def retrieve(request: QueryRequest) -> dict:
    try:
        records = service().retrieve(to_input(request), request.limit)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(error)) from error
    return {
        "candidates": [
            {
                "smiles": record.get("smiles"),
                "similarity": record.get("similarity", record.get("score")),
                "backend": record.get("backend"),
            }
            for record in records
        ]
    }


@app.post("/api/gap")
def gap(request: QueryRequest) -> dict:
    try:
        result = service().predict_gap(to_input(request))
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(error)) from error
    return {
        "gap_ev": float(result["gap_ev"]),
        "benchmark_mae_ev": float(result["benchmark_mae_ev"]),
        "benchmark_r2_ev": float(result["benchmark_r2"]),
    }


@app.post("/api/generate")
def generate(request: QueryRequest) -> dict:
    try:
        result = service().generate(to_input(request), request.limit)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(error)) from error
    anchor = result.get("anchor")
    if anchor is None:
        note = (
            f"当前结果由 Vib2Mol 对输入谱图执行 {result.get('beam_size', '多路径')} 条 beam search，"
            "规范化并去除重复结构后，再由 matching head 重新排序。"
        )
    else:
        note = (
            f"缓存回退汇总了 {result.get('anchors_used', 1)} 个相近理论谱锚点的已验证 beam 候选并去重；"
            f"最高相似锚点：{anchor['sample_id']} · 谱图相似度 {result['anchor_similarity']:.4f}。"
            "这些候选不标作对输入谱图的直接生成。"
        )
    return {
        "candidates": [
            {
                "smiles": record.get("smiles"),
                "score": record.get("similarity", record.get("score")),
            }
            for record in result["candidates"]
        ],
        "note": note,
    }


@app.get("/api/render")
def render(smiles: str = Query(...)) -> Response:
    drawing = smiles_png(smiles)
    if drawing is None:
        raise HTTPException(status_code=400, detail="RDKit cannot parse this SMILES.")
    return Response(content=drawing, media_type="image/png")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


WEB_OUT = GALLERY_ROOT / "web" / "out"
if not WEB_OUT.is_dir():
    WEB_OUT = GALLERY_ROOT / "out"
if WEB_OUT.is_dir():
    app.mount("/_next/static", StaticFiles(directory=WEB_OUT / "_next" / "static"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = (WEB_OUT / path).resolve()
        if str(candidate).startswith(str(WEB_OUT)):
            if candidate.is_file():
                return FileResponse(candidate)
            for page in (candidate / "index.html", candidate.with_suffix(".html")):
                if page.is_file():
                    return FileResponse(page)
        return FileResponse(WEB_OUT / "index.html")
