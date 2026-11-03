from __future__ import annotations

import os
import re
from typing import Any, Callable

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ValidationError

from .runtime import ChemistryError, ChemistryRuntime, compact_job
from .schemas import Identifier, JobRequest, Limit, Peaks, StructureRequest
from .spectrum import compact_spectrum


def create_mcp(runtime: Callable[[], ChemistryRuntime], *, wait_seconds: float = 0) -> FastMCP:
    hosts = ["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", "[::1]", "[::1]:*",
             "chemistry", "chemistry:*"]
    hosts.extend(item for item in re.split(r"[,\s]+", os.environ.get("OPENMOLSPEC_MCP_ALLOWED_HOSTS", "")) if item)
    server = FastMCP(
        "OpenMolSpec Chemistry",
        instructions="Theoretical-domain spectroscopy tools. Missing models fail explicitly. Use persisted input IDs; poll unfinished calculations with get_calculation.",
        stateless_http=True, json_response=True, streamable_http_path="/mcp",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=hosts,
            allowed_origins=["http://127.0.0.1", "http://127.0.0.1:*", "http://localhost", "http://localhost:*",
                             "http://[::1]", "http://[::1]:*"],
        ),
    )

    async def calculate(ctx: Context, operation: str, inputs: dict, request_id: str | None) -> dict:
        state = ctx.request_context.request.state
        try:
            request = JobRequest.model_validate({
                "operation": operation, "request_id": request_id,
                "inputs": {key: value for key, value in inputs.items() if value is not None},
            })
            job = await runtime().submit(state.owner_id, request, source=state.source)
        except ChemistryError as error:
            return {"error": error.payload()}
        except ValidationError as error:
            return {"error": {"code": "invalid_input", "message": error.errors()[0]["msg"]}}
        if wait_seconds > 0:
            job = await runtime().wait(state.owner_id, job["id"], timeout=wait_seconds)
        return compact_job(job)

    @server.tool()
    async def get_capabilities() -> dict[str, Any]:
        """Return real model/data availability and the theoretical scientific domain."""
        return await runtime().capabilities()

    @server.tool()
    async def inspect_molecule(ctx: Context, smiles: str) -> dict[str, Any]:
        """Persist a validated molecular conformer and return compact molecular properties."""
        try:
            molecule = await runtime().resolve_molecule(ctx.request_context.request.state.owner_id, StructureRequest(smiles=smiles))
        except ChemistryError as error:
            return {"error": error.payload()}
        except ValidationError as error:
            return {"error": {"code": "invalid_input", "message": error.errors()[0]["msg"]}}
        return {"molecule_id": molecule["id"], **{key: molecule[key] for key in
                ("smiles", "formula", "molecular_weight", "atom_count", "inchi_key", "applicability")},
                "units": {"molecular_weight": "g/mol"}}

    @server.tool()
    async def inspect_spectrum(ctx: Context, spectrum_id: Identifier) -> dict[str, Any]:
        """Inspect stored spectrum units, range, origin and model eligibility without fetching arrays."""
        try:
            return compact_spectrum(runtime().spectrum(ctx.request_context.request.state.owner_id, spectrum_id))
        except ChemistryError as error:
            return {"error": error.payload()}

    @server.tool()
    async def predict_spectra(ctx: Context, smiles: str | None = None, molecule_id: str | None = None,
                              request_id: Identifier | None = None) -> dict[str, Any]:
        """Calculate theoretical IR/Raman/H-C NMR through the durable worker; return a job ID and compact summary."""
        return await calculate(ctx, "predict_spectra", {"smiles": smiles, "molecule_id": molecule_id}, request_id)

    @server.tool()
    async def retrieve_candidates(ctx: Context, ir_id: str | None = None, raman_id: str | None = None,
                                  nmr_h: Peaks | None = None, nmr_c: Peaks | None = None,
                                  limit: Limit | None = None, request_id: Identifier | None = None) -> dict[str, Any]:
        """Retrieve structures using persisted IR/Raman input and optional NMR peak shifts in ppm."""
        return await calculate(ctx, "retrieve", {"ir_id": ir_id, "raman_id": raman_id, "nmr_h": nmr_h, "nmr_c": nmr_c, "limit": limit}, request_id)

    @server.tool()
    async def predict_gap(ctx: Context, ir_id: str | None = None, raman_id: str | None = None,
                          nmr_h: Peaks | None = None, nmr_c: Peaks | None = None,
                          request_id: Identifier | None = None) -> dict[str, Any]:
        """Predict the theoretical HOMO–LUMO gap in eV from persisted spectra; return a durable job reference."""
        return await calculate(ctx, "predict_gap", {"ir_id": ir_id, "raman_id": raman_id, "nmr_h": nmr_h, "nmr_c": nmr_c}, request_id)

    @server.tool()
    async def generate_candidates(ctx: Context, ir_id: str | None = None, raman_id: str | None = None,
                                   nmr_h: Peaks | None = None, nmr_c: Peaks | None = None,
                                   limit: Limit | None = None, request_id: Identifier | None = None) -> dict[str, Any]:
        """Generate/rank structures through existing Vib2Mol paths, explicitly preserving direct/cache provenance."""
        return await calculate(ctx, "generate", {"ir_id": ir_id, "raman_id": raman_id, "nmr_h": nmr_h, "nmr_c": nmr_c, "limit": limit}, request_id)

    @server.tool()
    async def get_calculation(ctx: Context, job_id: str) -> dict[str, Any]:
        """Poll a durable calculation, returning status and bounded scientific results without full arrays."""
        try:
            return compact_job(runtime().job(ctx.request_context.request.state.owner_id, job_id))
        except ChemistryError as error:
            return {"error": error.payload()}

    return server
