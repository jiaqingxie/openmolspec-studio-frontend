from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from openmolspec_ui.config import ModelAssets, discover_assets

from .mcp_server import create_mcp
from .runtime import ChemistryError, ChemistryRuntime
from .schemas import JobRequest, ParseSpectrumRequest, StructureRequest
from .store import ChemistryStore


def create_app(*, database_url: str | None = None, internal_key: str | None = None,
               assets: ModelAssets | None = None,
               device: str | None = None, service_factory: Callable | None = None,
               mcp_wait_seconds: float = 0) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        dsn = database_url or os.environ.get("OPENMOLSPEC_DATABASE_URL")
        key = internal_key or os.environ.get("OPENMOLSPEC_INTERNAL_KEY")
        if not dsn or not key or not key.strip():
            raise RuntimeError("OPENMOLSPEC_DATABASE_URL and OPENMOLSPEC_INTERNAL_KEY are required.")
        application.state.internal_key = key.encode()
        store = ChemistryStore(dsn)
        runtime = ChemistryRuntime(store, assets or discover_assets(), device=device, service_factory=service_factory)
        application.state.runtime = runtime
        try:
            await runtime.start()
            async with mcp.session_manager.run():
                yield
        finally:
            await runtime.close()

    application = FastAPI(title="OpenMolSpec Chemistry", version="2.0.0", lifespan=lifespan)
    current = lambda: application.state.runtime
    mcp = create_mcp(current, wait_seconds=max(0, min(mcp_wait_seconds, 60)))
    mcp_http = mcp.streamable_http_app()

    @application.middleware("http")
    async def require_internal_identity(request: Request, call_next):
        if request.url.path == "/health" and request.method == "GET":
            return await call_next(request)
        key = request.headers.get("X-Molspec-Internal-Key", "").encode()
        owner_id = request.headers.get("X-Molspec-User-ID", "").strip()
        capabilities_request = request.url.path == "/v1/capabilities" and request.method == "GET"
        if not secrets.compare_digest(key, application.state.internal_key) or not (owner_id or capabilities_request):
            return JSONResponse(status_code=401, content={
                "error": {"code": "unauthorized", "message": "A valid internal service identity is required."},
            })
        source = request.headers.get("X-Molspec-Source", "mcp" if request.url.path == "/mcp" else "web")
        if source not in {"web", "mcp"}:
            return JSONResponse(status_code=400, content={
                "error": {"code": "invalid_source", "message": "Unrecognized internal request source."},
            })
        request.state.owner_id = owner_id
        request.state.source = source
        return await call_next(request)

    @application.exception_handler(ChemistryError)
    async def chemistry_error(_request: Request, error: ChemistryError):
        return JSONResponse(status_code=error.status_code, content={"error": error.payload()})

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError):
        # Invalid JSON numbers can appear in Pydantic's `input`; echoing them via
        # the default handler would itself fail strict JSON serialization.
        detail = [{key: item[key] for key in ("type", "loc", "msg") if key in item}
                  for item in error.errors()]
        return JSONResponse(status_code=422, content={"detail": detail})

    @application.get("/health")
    async def health():
        return {"status": "ok", "service": "chemistry"}

    @application.get("/v1/capabilities")
    async def capabilities():
        return await current().capabilities()

    @application.post("/v1/molecules/resolve")
    async def resolve_molecule(request: Request, payload: StructureRequest):
        return await current().resolve_molecule(request.state.owner_id, payload)

    @application.get("/v1/molecules/{molecule_id}")
    async def get_molecule(request: Request, molecule_id: str):
        return current().molecule(request.state.owner_id, molecule_id)

    @application.post("/v1/spectra/parse")
    async def parse_spectrum(request: Request, payload: ParseSpectrumRequest):
        return await current().parse_spectrum(request.state.owner_id, payload)

    @application.get("/v1/spectra/{spectrum_id}")
    async def get_spectrum(request: Request, spectrum_id: str):
        return current().spectrum(request.state.owner_id, spectrum_id)

    @application.post("/v1/jobs", status_code=202)
    async def submit_job(request: Request, payload: JobRequest):
        return await current().submit(request.state.owner_id, payload, source=request.state.source)

    @application.get("/v1/jobs")
    async def list_jobs(request: Request):
        return current().store.list_jobs(request.state.owner_id)

    @application.get("/v1/jobs/{job_id}")
    async def get_job(request: Request, job_id: str):
        return current().job(request.state.owner_id, job_id)

    @application.post("/v1/jobs/{job_id}/cancel")
    async def cancel_job(request: Request, job_id: str):
        return current().cancel(request.state.owner_id, job_id)

    # Mount the SDK router after the explicit API routes. Keeping /mcp in that
    # router provides the exact contract URL without a /mcp -> /mcp/ redirect.
    application.mount("/", mcp_http)
    return application


app = create_app()
