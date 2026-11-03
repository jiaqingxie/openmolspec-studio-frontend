from __future__ import annotations

import asyncio
import importlib
import json
import os
import pickle
import socket
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import httpx
import lmdb
import numpy as np
import pytest
import uvicorn
from fastapi.testclient import TestClient as RawTestClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from openmolspec_ui.config import discover_assets

from services.api.accounts import Accounts


INTERNAL_KEY = "chemistry-integration-test-key"


@pytest.fixture(autouse=True)
def chemistry_environment(monkeypatch, postgres_dsn, account_owner):
    monkeypatch.setenv("OPENMOLSPEC_DATABASE_URL", postgres_dsn)
    monkeypatch.setenv("OPENMOLSPEC_INTERNAL_KEY", INTERNAL_KEY)
    monkeypatch.setenv("MOLSPEC_TEST_OWNER", account_owner)


def owner_headers(owner_id=None):
    return {
        "X-Molspec-Internal-Key": INTERNAL_KEY,
        "X-Molspec-User-ID": owner_id or os.environ["MOLSPEC_TEST_OWNER"],
    }


def authenticated_client(app):
    return RawTestClient(app, headers=owner_headers())


def make_app(tmp_path: Path, **kwargs):
    try:
        module = importlib.import_module("services.chemistry.app")
    except ModuleNotFoundError as error:
        if error.name and error.name.startswith("services.chemistry"):
            pytest.fail("The independent chemistry HTTP service is not implemented")
        raise
    kwargs.setdefault("assets", discover_assets(tmp_path))
    kwargs.setdefault("device", "cpu")
    return module.create_app(**kwargs)


def finish_job(client, job_id: str, timeout: float = 8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/v1/jobs/{job_id}")
        assert response.status_code == 200, response.text
        job = response.json()
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    pytest.fail(f"Calculation {job_id} did not finish")


@pytest.fixture
def reference_assets(tmp_path):
    """Two real LMDB records exercise the existing cosine/cache algorithms."""
    path = tmp_path / "reference.lmdb"
    environment = lmdb.open(str(path), subdir=False, map_size=1024 * 1024)
    with environment.begin(write=True) as transaction:
        for index, (smiles, ascending) in enumerate((("CCO", True), ("CCN", False))):
            spectrum = np.linspace(0, 1, 1024, dtype=np.float32)
            if not ascending:
                spectrum = spectrum[::-1].copy()
            transaction.put(
                str(index).encode(),
                pickle.dumps(
                    {
                        "sample_id": f"theoretical-{index}",
                        "kekule_smiles": smiles,
                        "inchikey": "",
                        "source_dataset": "ZINCV2",
                        "ir": spectrum,
                        "raman": spectrum[::-1].copy(),
                        "nmr_h_shifts_ppm": np.array([1.2, 3.7]),
                        "nmr_c_shifts_ppm": np.array([18.0, 58.0]),
                    }
                ),
            )
    environment.close()
    predictions = tmp_path / "generation_predictions.jsonl"
    predictions.write_text(
        json.dumps(
            {"index": 0, "unique_candidates": ["CCO", "CO", "CCN"],
             "positive_probabilities": [0.9, 0.7, 0.4]}
        ) + "\n"
    )
    return replace(
        discover_assets(tmp_path),
        spectrum_lmdb=path,
        generation_predictions=predictions,
    )


def test_startup_and_health_do_not_initialize_compute_models(tmp_path):
    def forbidden_factory(*_args, **_kwargs):
        raise AssertionError("A model was initialized before a calculation")

    with authenticated_client(make_app(tmp_path, service_factory=forbidden_factory)) as client:
        assert client.get("/health").json() == {"status": "ok", "service": "chemistry"}
        capabilities = client.get("/v1/capabilities").json()
        assert capabilities["domain"] == "theoretical"
        assert capabilities["device"] == "cpu"
        assert not any(item["available"] for item in capabilities["capabilities"].values())


def test_resolved_molecule_is_canonical_and_persists_its_3d_conformer(tmp_path):
    with authenticated_client(make_app(tmp_path)) as client:
        response = client.post("/v1/molecules/resolve", json={"smiles": "OCC"})
        assert response.status_code == 200, response.text
        molecule = response.json()
        assert molecule["smiles"] == "CCO"
        assert molecule["formula"] == "C2H6O"
        assert molecule["atom_count"] == 9
        assert molecule["molecular_weight"] == pytest.approx(46.069, abs=0.01)
        assert molecule["inchi_key"] == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
        assert "<svg" in molecule["svg"]
        positions = np.array([list(map(float, line.split()[1:]))
                              for line in molecule["xyz"].splitlines()[2:]])
        assert positions.shape == (9, 3)
        assert np.ptp(positions[:, 2]) > 0.1  # Drawing must not replace 3D with 2D.
    with authenticated_client(make_app(tmp_path)) as client:
        response = client.post("/v1/jobs", json={
            "operation": "predict_spectra", "inputs": {"molecule_id": molecule["id"]}
        })
        assert response.status_code == 202, response.text
        job = finish_job(client, response.json()["id"])
        assert job["error"]["code"] == "model_unavailable"
        assert job["inputs"]["molecule"]["xyz"] == molecule["xyz"]


@pytest.mark.parametrize("payload", [
    {}, {"smiles": "not a molecule"}, {"smiles": ""},
    {"smiles": "C", "xyz": "1\n\nH 0 0 0\n"},
    {"xyz": "2\n\nH 0 0 0\nH nan 0 1\n"},
    {"xyz": "2\n\nH 0 0 0\nH 0 0\n"},
    {"path": "/etc/passwd"},
])
def test_invalid_or_conflicting_structures_are_rejected(tmp_path, payload):
    with authenticated_client(make_app(tmp_path)) as client:
        response = client.post("/v1/molecules/resolve", json=payload)
        assert response.status_code in {400, 422}, response.text


def test_xyz_resolution_and_spectrum_parser_persist_scientific_inputs(tmp_path):
    with authenticated_client(make_app(tmp_path)) as client:
        water = client.post("/v1/molecules/resolve", json={
            "xyz": "3\nwater\nO 0 0 0\nH 0.96 0 0\nH -0.24 0.93 0\n"
        })
        assert water.status_code == 200, water.text
        assert water.json()["formula"] == "H2O"
        parsed = client.post("/v1/spectra/parse", json={
            "name": "uploaded IR.csv", "modality": "ir",
            "axis_unit": "cm^-1", "intensity_unit": "a.u.", "domain": "theoretical",
            "content": "wavenumber,intensity\n4000,9\n2200,5\n400,1\n"
        })
        assert parsed.status_code == 200, parsed.text
        spectrum = parsed.json()
        assert spectrum["name"] == "uploaded IR.csv"
        assert len(spectrum["wavenumber"]) == len(spectrum["intensity"]) == 1024
        assert spectrum["wavenumber"][0] == 400
        assert spectrum["wavenumber"][-1] == 4000
        assert spectrum["intensity"][0] == 0
        assert spectrum["intensity"][-1] == 1
    with authenticated_client(make_app(tmp_path)) as client:
        assert client.get(f'/v1/spectra/{spectrum["id"]}').json() == spectrum
        assert client.get("/v1/spectra/unknown").status_code == 404


@pytest.mark.parametrize("content", [
    "header only", "400,1\n2200,nan\n4000,2", "400,1\n2200,1e309\n4000,2"
])
def test_parser_rejects_nonfinite_and_unreadable_spectra(tmp_path, content):
    with authenticated_client(make_app(tmp_path)) as client:
        response = client.post("/v1/spectra/parse", json={"name": "bad", "content": content})
        assert response.status_code in {400, 422}, response.text


@pytest.mark.parametrize("inputs", [
    {}, {"ir": [0, 1]}, {"ir": [0] * 1023 + ["NaN"]},
    {"ir": [True] * 1024}, {"ir": [0] * 1024, "nmr_h": ["infinity"]},
    {"ir": [0] * 1024, "ir_id": "other"},
    {"ir": [0] * 1024, "limit": 0},
    {"ir": [0] * 1024, "smiles": "CCO"},
    {"ir": [0] * 1024, "file_path": "/etc/passwd"},
    {"ir": [0] * 1022 + [-3e38, 3e38]},
])
def test_jobs_reject_invalid_scientific_input_before_queueing(tmp_path, inputs):
    with authenticated_client(make_app(tmp_path)) as client:
        response = client.post("/v1/jobs", json={"operation": "retrieve", "inputs": inputs})
        assert response.status_code in {400, 422}, response.text
        assert client.get("/v1/jobs").json() == []


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonstandard_json_nonfinite_numbers_return_a_validation_response(tmp_path, value):
    with authenticated_client(make_app(tmp_path)) as client:
        content = '{"operation":"retrieve","inputs":{"ir":[' + ",".join(["0"] * 1023 + [value]) + "]}}"
        response = client.post("/v1/jobs", content=content, headers={"Content-Type": "application/json"})
        assert response.status_code == 422, response.text
        assert response.json()["detail"]
        assert client.get("/v1/jobs").json() == []


@pytest.mark.parametrize("operation", ["predict_spectra", "retrieve", "predict_gap", "generate"])
def test_missing_assets_produce_a_durable_structured_failed_job(tmp_path, operation, postgres_dsn, account_owner):
    inputs = {"smiles": "CCO"} if operation == "predict_spectra" else {"ir": np.linspace(0, 1, 1024).tolist()}
    accounts = Accounts(postgres_dsn)
    starting_balance = accounts.balance(account_owner)
    with authenticated_client(make_app(tmp_path)) as client:
        response = client.post("/v1/jobs", json={"operation": operation, "inputs": inputs})
        assert response.status_code == 202, response.text
        job = finish_job(client, response.json()["id"])
        assert job["status"] == "failed"
        assert job["result"] is None
        assert job["error"]["code"] == "model_unavailable"
        assert job["error"]["message"]
        assert accounts.balance(account_owner) == starting_balance
    with authenticated_client(make_app(tmp_path)) as client:
        assert client.get(f'/v1/jobs/{job["id"]}').json() == job


def test_real_retrieval_and_cached_generation_retain_backend_and_cache_provenance(tmp_path, reference_assets):
    with authenticated_client(make_app(tmp_path, assets=reference_assets)) as client:
        capabilities = client.get("/v1/capabilities").json()["capabilities"]
        assert capabilities["retrieve"]["available"] is True
        assert capabilities["generate"]["available"] is True
        for operation in ("retrieve", "generate"):
            submitted = client.post("/v1/jobs", json={
                "operation": operation,
                "inputs": {"ir": np.linspace(0, 4, 1024).tolist(), "limit": 3}
            })
            assert submitted.status_code == 202, submitted.text
            job = finish_job(client, submitted.json()["id"])
            assert job["status"] == "succeeded", job
            assert job["inputs"]["ir"][0] == 0
            assert job["inputs"]["ir"][-1] == 1
            result = job["result"]
            assert result["domain"] == "theoretical"
            assert result["candidates"][0]["smiles"] == "CCO"
            if operation == "retrieve":
                assert result["candidates"][0]["backend"] == "spectral-cosine"
                assert result["candidates"][0]["similarity"] == pytest.approx(1, abs=0.001)
            else:
                assert result["provenance"]["cache"]["used"] is True
                assert "cache" in result["mode"]


def test_queued_jobs_resume_and_running_jobs_fail_after_restart(tmp_path, reference_assets, postgres_dsn, account_owner):
    make_app(tmp_path)  # Ensure the implementation exists before importing its store.
    from services.chemistry.store import ChemistryStore

    store = ChemistryStore(postgres_dsn)
    inputs = {"ir": np.linspace(0, 1, 1024).tolist(), "limit": 1}
    interrupted = store.create_job(account_owner, "retrieve", inputs, source="web")
    assert store.claim_next()[1]["id"] == interrupted["id"]
    queued = store.create_job(account_owner, "retrieve", inputs, source="mcp")
    store.close()
    with authenticated_client(make_app(tmp_path, assets=reference_assets)) as client:
        recovered = client.get(f'/v1/jobs/{interrupted["id"]}').json()
        assert recovered["status"] == "failed"
        assert recovered["error"]["code"] == "interrupted"
        assert finish_job(client, queued["id"])["status"] == "succeeded"
        usage = Accounts(postgres_dsn).usage(account_owner)
        entries = {entry["task_id"]: entry for entry in usage["entries"]}
        assert usage["reserved"] == 0
        assert entries[interrupted["id"]]["status"] == "released"
        assert entries[queued["id"]]["status"] == "settled"
        assert entries[queued["id"]]["duration_ms"] >= 0
        assert entries[queued["id"]]["source"] == "mcp"


def test_worker_serializes_jobs_and_only_queued_jobs_can_be_cancelled(
    tmp_path, reference_assets, postgres_dsn, account_owner,
):
    from openmolspec_ui.inference import OpenMolSpecService

    entered, release = threading.Event(), threading.Event()

    class BlockingService(OpenMolSpecService):
        def retrieve(self, inputs, limit=8):
            entered.set()
            assert release.wait(5), "Test did not release its numerical call"
            return super().retrieve(inputs, limit)

    with authenticated_client(make_app(tmp_path, assets=reference_assets, service_factory=BlockingService)) as client:
        payload = {"operation": "retrieve", "inputs": {"ir": np.linspace(0, 1, 1024).tolist()}}
        first = client.post("/v1/jobs", json=payload).json()
        try:
            assert entered.wait(3)
            second = client.post("/v1/jobs", json=payload).json()
            assert client.get(f'/v1/jobs/{second["id"]}').json()["status"] == "queued"
            running_cancel = client.post(f'/v1/jobs/{first["id"]}/cancel')
            assert running_cancel.status_code == 409
            assert running_cancel.json()["error"]["code"] == "job_running"
            cancelled = client.post(f'/v1/jobs/{second["id"]}/cancel').json()
            assert cancelled["status"] == "cancelled"
            usage = Accounts(postgres_dsn).usage(account_owner)
            entries = {entry["task_id"]: entry["status"] for entry in usage["entries"]}
            assert entries[first["id"]] == "reserved"
            assert entries[second["id"]] == "released"
        finally:
            release.set()
        assert finish_job(client, first["id"])["status"] == "succeeded"
        assert client.get(f'/v1/jobs/{second["id"]}').json()["status"] == "cancelled"


@contextmanager
def live_server(app):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started, "Chemistry server failed to start"
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=8)
        listener.close()
        assert not thread.is_alive(), "Chemistry server did not close its worker"


def test_official_mcp_and_http_share_durable_calculations_without_large_llm_payloads(tmp_path, reference_assets):
    with live_server(make_app(tmp_path, assets=reference_assets)) as url:
        asyncio.run(_exercise_mcp_and_http(url))


async def _exercise_mcp_and_http(url):
    async with httpx.AsyncClient(base_url=url, headers=owner_headers(), follow_redirects=False) as http:
        # Use the actual official HTTP transport and ClientSession, not tool mocks.
        async with streamable_http_client(url + "/mcp", http_client=http) as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert {tool.name for tool in tools.tools} == {
                    "get_capabilities", "inspect_molecule", "inspect_spectrum", "predict_spectra",
                    "retrieve_candidates", "predict_gap", "generate_candidates", "get_calculation",
                }
                inspected = await session.call_tool("inspect_molecule", {"smiles": "CCO"})
                molecule = inspected.structuredContent
                assert not inspected.isError, inspected
                assert molecule["formula"] == "C2H6O"
                assert molecule["molecule_id"]
                assert not {"svg", "xyz", "molblock"} & molecule.keys()
                parsed = (await http.post("/v1/spectra/parse", json={
                    "name": "IR.csv", "modality": "ir", "content": "400,0\n2200,0.5\n4000,1",
                    "axis_unit": "cm^-1", "intensity_unit": "a.u.", "domain": "theoretical",
                })).json()
                inspected = await session.call_tool("inspect_spectrum", {"spectrum_id": parsed["id"]})
                assert inspected.structuredContent["quality"]["model_eligible"] is True
                assert inspected.structuredContent["axis_range"] == [400, 4000]
                assert "intensity" not in inspected.structuredContent
                peaked = (await http.post("/v1/spectra/parse", json={
                    "name": "peaked.csv", "content": "800,0\n1010,1\n1500,0",
                    "axis_unit": "cm^-1", "intensity_unit": "a.u.", "domain": "theoretical",
                })).json()
                peak_summary = (await session.call_tool("inspect_spectrum", {"spectrum_id": peaked["id"]})).structuredContent
                assert peak_summary["raw_axis_range"] == [800, 1500]
                assert peak_summary["peak_summary"]["peaks"] == [{"position": 1010, "intensity": 1}]
                arguments = {"ir_id": parsed["id"], "limit": 2}
                key = "same-http-and-mcp-request"
                direct = (await http.post("/v1/jobs", json={
                    "operation": "retrieve", "inputs": arguments, "request_id": key,
                })).json()
                called = await session.call_tool("retrieve_candidates", {**arguments, "request_id": key})
                assert not called.isError, called
                assert called.structuredContent["job_id"] == direct["id"]
                for _ in range(100):
                    polled = await session.call_tool("get_calculation", {"job_id": direct["id"]})
                    summary = polled.structuredContent
                    if summary["status"] == "succeeded":
                        break
                    await asyncio.sleep(0.01)
                assert summary["status"] == "succeeded", summary
                assert summary["summary"]["candidates"][0]["smiles"] == "CCO"
                assert len(json.dumps(summary)) < 8000
                assert "wavenumber" not in summary["summary"]
                conflict = await session.call_tool("retrieve_candidates", {**arguments, "limit": 1, "request_id": key})
                assert conflict.structuredContent["error"]["code"] == "request_id_conflict"
                assert len((await http.get("/v1/jobs")).json()) == 1
                invalid = await session.call_tool("retrieve_candidates", {"ir_id": parsed["id"], "nmr_h": [True]})
                assert invalid.isError, "MCP must not coerce booleans into NMR measurements"


def test_mcp_timeout_and_disconnect_leave_the_worker_owned_job_running(tmp_path, reference_assets):
    from openmolspec_ui.inference import OpenMolSpecService

    release = threading.Event()

    class SlowRetrieval(OpenMolSpecService):
        def retrieve(self, inputs, limit=8):
            if not release.wait(5):
                raise TimeoutError("Test did not release retrieval")
            return super().retrieve(inputs, limit)

    app = make_app(tmp_path, assets=reference_assets, service_factory=SlowRetrieval, mcp_wait_seconds=0.03)
    with live_server(app) as url:
        try:
            summary = asyncio.run(_submit_slow_mcp(url))
            assert summary["status"] in {"queued", "running"}, summary
            assert summary["error"] is None
        finally:
            release.set()
        # The initiating MCP HTTP session has closed, but the persisted job finishes.
        with httpx.Client(base_url=url, headers=owner_headers()) as client:
            assert finish_job(client, summary["job_id"])["status"] == "succeeded"


async def _submit_slow_mcp(url):
    async with httpx.AsyncClient(base_url=url, headers=owner_headers()) as http:
        spectrum = (await http.post("/v1/spectra/parse", json={
            "name": "slow.csv", "content": "400,0\n4000,1", "modality": "ir",
            "axis_unit": "cm^-1", "intensity_unit": "a.u.", "domain": "theoretical",
        })).json()
        async with streamable_http_client(url + "/mcp", http_client=http) as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                result = await session.call_tool("retrieve_candidates", {"ir_id": spectrum["id"]})
                assert not result.isError
                return result.structuredContent


def test_mcp_trusts_loopback_and_container_hosts_while_rejecting_rebinding(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENMOLSPEC_MCP_ALLOWED_HOSTS", raising=False)
    initialization = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "transport-test", "version": "1"},
    }}
    headers = {"Accept": "application/json, text/event-stream"}
    with live_server(make_app(tmp_path)) as url, httpx.Client(base_url=url, headers=owner_headers(), follow_redirects=False) as client:
        for host in ("localhost:8001", "localhost", "127.0.0.1:8001", "chemistry:8001", "chemistry"):
            response = client.post("/mcp", headers={**headers, "Host": host}, json=initialization)
            assert response.status_code == 200, (host, response.text)
            assert response.json()["result"]["serverInfo"]["name"] == "OpenMolSpec Chemistry"
        rejected = client.post("/mcp", headers={**headers, "Host": "untrusted.example:8001"}, json=initialization)
        assert rejected.status_code == 421
        origin = client.post("/mcp", headers={**headers, "Origin": "https://untrusted.example"}, json=initialization)
        assert origin.status_code == 403


def test_mcp_trusted_hostnames_can_be_extended_explicitly(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENMOLSPEC_MCP_ALLOWED_HOSTS", "worker.internal:*,custom.internal")
    initialization = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "transport-test", "version": "1"},
    }}
    with live_server(make_app(tmp_path)) as url, httpx.Client(base_url=url, headers=owner_headers()) as client:
        for host in ("worker.internal:8001", "custom.internal"):
            response = client.post("/mcp", json=initialization, headers={
                "Host": host, "Accept": "application/json, text/event-stream"
            })
            assert response.status_code == 200, response.text


def test_partial_spectrum_keeps_raw_measurements_and_cannot_run(tmp_path):
    with authenticated_client(make_app(tmp_path)) as client:
        parsed = client.post("/v1/spectra/parse", json={
            "content": "wavenumber,intensity\n1000,2\n1500,3\n2000,1",
            "name": "partial.csv", "axis_unit": "cm^-1", "intensity_unit": "a.u.",
            "domain": "theoretical",
        })
        assert parsed.status_code == 200, parsed.text
        spectrum = parsed.json()
        assert spectrum["raw"]["intensity"] == [2, 3, 1]
        assert spectrum["wavenumber"] == [1000, 1500, 2000]
        assert spectrum["quality"]["model_eligible"] is False
        response = client.post("/v1/jobs", json={
            "operation": "retrieve", "inputs": {"ir_id": spectrum["id"]},
        })
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "spectrum_not_eligible"


def test_durable_request_id_replays_original_job_and_detects_conflict(tmp_path):
    payload = {"operation": "predict_spectra", "request_id": "run-call-1", "inputs": {"smiles": "CCO"}}
    with authenticated_client(make_app(tmp_path)) as client:
        first = client.post("/v1/jobs", json=payload)
        assert first.status_code == 202, first.text
        identifier = first.json()["id"]
    with authenticated_client(make_app(tmp_path)) as client:
        assert client.post("/v1/jobs", json=payload).json()["id"] == identifier
        conflict = client.post("/v1/jobs", json={**payload, "inputs": {"smiles": "CCN"}})
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "request_id_conflict"
        assert len(client.get("/v1/jobs").json()) == 1


def test_charged_molecule_can_be_previewed_but_not_predicted(tmp_path):
    with authenticated_client(make_app(tmp_path)) as client:
        response = client.post("/v1/molecules/resolve", json={"smiles": "[NH4+]"})
        assert response.status_code == 200, response.text
        molecule = response.json()
        assert molecule["applicability"]["model_eligible"] is False
        assert molecule["svg"]
        job = client.post("/v1/jobs", json={
            "operation": "predict_spectra", "inputs": {"molecule_id": molecule["id"]},
        })
        assert job.status_code == 422
        assert job.json()["error"]["code"] == "molecule_not_eligible"


@pytest.mark.parametrize(("metadata", "eligible"), [
    ({}, False),
    ({"axis_unit": "cm^-1", "intensity_unit": "a.u.", "domain": "experimental"}, False),
    ({"axis_unit": "nm", "intensity_unit": "a.u.", "domain": "theoretical"}, False),
    ({"axis_unit": "cm^-1", "intensity_unit": "transmittance", "domain": "theoretical"}, False),
    ({"axis_unit": "cm^-1", "intensity_unit": "a.u.", "domain": "theoretical"}, True),
])
def test_only_declared_compatible_spectra_enter_model_grid(tmp_path, metadata, eligible):
    with authenticated_client(make_app(tmp_path)) as client:
        response = client.post("/v1/spectra/parse", json={
            "name": "spectrum.csv", "content": "4000,12\n2200,8\n400,4", **metadata,
        })
        assert response.status_code == 200, response.text
        spectrum = response.json()
        assert spectrum["quality"]["model_eligible"] is eligible
        assert spectrum["raw"]["wavenumber"] == [4000, 2200, 400]
        assert len(spectrum["wavenumber"]) == (1024 if eligible else 3)
        assert spectrum["processing"]["extrapolated"] is False


def test_prediction_persists_reusable_spectra_with_origin(tmp_path, reference_assets):
    checkpoint = tmp_path / "run/artifacts/fixture.pt"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.touch()
    (checkpoint.parent.parent / "resolved_config.yaml").touch()
    for name in ("models/equiformer_v3/hessian.py", "models/equiformer_v3/nmr.py", "engines/hessian_physics.py"):
        module = tmp_path / "benchmarks" / name
        module.parent.mkdir(parents=True, exist_ok=True)
        module.touch()
    assets = replace(reference_assets, hessian_hi_checkpoint=checkpoint, hessian_hij_checkpoint=checkpoint,
                     dedipole_checkpoint=checkpoint, depolar_checkpoint=checkpoint, nmr_checkpoint=checkpoint)

    class FixtureInference:
        def __init__(self, _assets, *, device):
            pass

        def predict_spectra(self, _molecule):
            return {"wavenumber": np.linspace(400, 4000, 1024), "ir": np.linspace(0, 1, 1024),
                    "raman": np.linspace(1, 0, 1024), "nmr_h": np.array([1.1]), "nmr_c": np.array([12.0])}

    with authenticated_client(make_app(tmp_path, assets=assets, service_factory=FixtureInference)) as client:
        submitted = client.post("/v1/jobs", json={"operation": "predict_spectra", "inputs": {"smiles": "CCO"}})
        job = finish_job(client, submitted.json()["id"])
        assert job["status"] == "succeeded", job
    with authenticated_client(make_app(tmp_path, assets=reference_assets)) as client:
        for modality in ("ir", "raman"):
            spectrum = client.get(f'/v1/spectra/{job["result"][modality + "_id"]}').json()
            assert spectrum["modality"] == modality
            assert spectrum["quality"]["model_eligible"] is True
            assert spectrum["provenance"]["source"] == "prediction"
            assert spectrum["provenance"]["job_id"] == job["id"]
            assert spectrum["provenance"]["molecule_id"] == job["inputs"]["molecule_id"]
        submitted = client.post("/v1/jobs", json={
            "operation": "retrieve", "inputs": {"ir_id": job["result"]["ir_id"]},
        })
        assert finish_job(client, submitted.json()["id"])["status"] == "succeeded"


def test_private_transport_requires_shared_key_and_owner(tmp_path, account_owner):
    with RawTestClient(make_app(tmp_path)) as client:
        assert client.get("/health").status_code == 200
        for headers in ({}, {"X-Molspec-User-ID": account_owner}, {"X-Molspec-Internal-Key": INTERNAL_KEY}):
            assert client.get("/v1/jobs", headers=headers).status_code == 401
            assert client.post("/mcp", headers=headers, json={}).status_code == 401
        assert client.get("/v1/capabilities").status_code == 401
        assert client.get("/v1/capabilities", headers={"X-Molspec-Internal-Key": INTERNAL_KEY}).status_code == 200


def test_object_refs_and_job_idempotency_are_owner_scoped(tmp_path, postgres_dsn):
    _, other = Accounts(postgres_dsn).login_mock("analyst")
    headers = owner_headers(other["id"])
    with authenticated_client(make_app(tmp_path)) as client:
        molecule = client.post("/v1/molecules/resolve", json={"smiles": "CCO"}).json()
        spectrum = client.post("/v1/spectra/parse", json={
            "name": "IR.csv", "modality": "ir", "content": "400,0\n4000,1",
            "axis_unit": "cm^-1", "intensity_unit": "a.u.", "domain": "theoretical",
        }).json()
        payload = {"operation": "predict_spectra", "inputs": {"smiles": "CCO"}, "request_id": "shared"}
        job = client.post("/v1/jobs", json=payload).json()

        assert client.get(f'/v1/molecules/{molecule["id"]}', headers=headers).status_code == 404
        assert client.get(f'/v1/spectra/{spectrum["id"]}', headers=headers).status_code == 404
        assert client.get(f'/v1/jobs/{job["id"]}', headers=headers).status_code == 404
        assert client.post(f'/v1/jobs/{job["id"]}/cancel', headers=headers).status_code == 404
        assert client.get("/v1/jobs", headers=headers).json() == []
        for operation, inputs in (
            ("predict_spectra", {"molecule_id": molecule["id"]}),
            ("retrieve", {"ir_id": spectrum["id"]}),
        ):
            result = client.post("/v1/jobs", json={"operation": operation, "inputs": inputs}, headers=headers)
            assert result.status_code == 404, result.text
        other_job = client.post("/v1/jobs", json=payload, headers=headers).json()
        assert job["id"] != other_job["id"]
        assert client.post("/v1/jobs", json=payload).json()["id"] == job["id"]
        assert client.post("/v1/jobs", json=payload, headers=headers).json()["id"] == other_job["id"]


def test_concurrent_reservations_and_repeated_completion(postgres_dsn, account_owner):
    from concurrent.futures import ThreadPoolExecutor

    from services.chemistry.errors import ChemistryError
    from services.chemistry.store import ChemistryStore

    accounts = Accounts(postgres_dsn)
    store = ChemistryStore(postgres_dsn)
    cost = 1
    store.connection.execute(
        "UPDATE molspec_app.credit_balances SET available=%s WHERE user_id=%s", (cost, account_owner),
    )

    def submit(request_id):
        connection = ChemistryStore(postgres_dsn)
        try:
            return connection.create_job(
                account_owner, "predict_spectra", {}, source="web",
                request_id=request_id, fingerprint="same",
            )["id"]
        except ChemistryError as error:
            assert error.code == "insufficient_credits"
            return None
        finally:
            connection.close()

    try:
        with ThreadPoolExecutor(max_workers=4) as workers:
            first, retry, other = workers.map(submit, ["same", "same", "other"])
        assert first == retry
        job_ids = {identifier for identifier in (first, other) if identifier is not None}
        assert len(job_ids) == 1
        assert accounts.balance(account_owner) == {"available": 0, "reserved": cost}
        owner_id, job = store.claim_next()
        assert job["id"] == job_ids.pop()
        store.finish_job(owner_id, job["id"], result={"ok": True}, duration_ms=5)
        store.finish_job(owner_id, job["id"], error={"code": "late"})
        assert store.get_job(owner_id, job["id"])["result"] == {"ok": True}
        assert accounts.balance(account_owner) == {"available": 0, "reserved": 0}
        assert submit("new") is None
    finally:
        store.close()


def test_private_mcp_cannot_poll_or_reference_another_owners_objects(tmp_path, postgres_dsn):
    _, other = Accounts(postgres_dsn).login_mock("analyst")
    with live_server(make_app(tmp_path)) as url:
        async def exercise():
            async with httpx.AsyncClient(base_url=url, headers=owner_headers()) as http:
                spectrum = (await http.post("/v1/spectra/parse", json={
                    "name": "IR.csv", "modality": "ir", "content": "400,0\n4000,1",
                    "axis_unit": "cm^-1", "intensity_unit": "a.u.", "domain": "theoretical",
                })).json()
                job = (await http.post("/v1/jobs", json={
                    "operation": "retrieve", "inputs": {"ir_id": spectrum["id"]},
                })).json()
            async with httpx.AsyncClient(headers=owner_headers(other["id"])) as http:
                async with streamable_http_client(url + "/mcp", http_client=http) as (reader, writer, _):
                    async with ClientSession(reader, writer) as session:
                        await session.initialize()
                        for tool, arguments in (
                            ("inspect_spectrum", {"spectrum_id": spectrum["id"]}),
                            ("retrieve_candidates", {"ir_id": spectrum["id"]}),
                            ("get_calculation", {"job_id": job["id"]}),
                        ):
                            result = await session.call_tool(tool, arguments)
                            assert result.structuredContent["error"]["code"] == "not_found"

        asyncio.run(exercise())


def test_daily_rollover_and_execution_charge(postgres_dsn, account_owner):
    from services.chemistry.store import ChemistryStore

    accounts = Accounts(postgres_dsn)
    store = ChemistryStore(postgres_dsn)
    try:
        previous = store.create_job(account_owner, "retrieve", {}, source="mcp")
        with accounts.connect() as conn:
            conn.execute("""UPDATE molspec_app.credit_balances
                            SET credit_day=credit_day-1, available=0 WHERE user_id=%s""", (account_owner,))
            conn.execute("""UPDATE molspec_app.credit_entries
                            SET credit_day=credit_day-1,
                                task_id=CASE WHEN status='granted' THEN 'previous_grant' ELSE task_id END
                            WHERE user_id=%s""", (account_owner,))

        today = store.create_job(account_owner, "generate", {}, source="mcp")
        expected = {"available": accounts.free_credits - 1, "reserved": 1}
        assert accounts.balance(account_owner) == expected
        store.cancel_job(account_owner, previous["id"])
        assert accounts.balance(account_owner) == expected

        owner_id, job = store.claim_next()
        assert job["id"] == today["id"]
        store.start_execution(owner_id, job["id"])
        store.finish_job(owner_id, job["id"], error={"code": "calculation_failed"}, duration_ms=5)
        usage = accounts.usage(account_owner)
        assert usage["available"] == accounts.free_credits - 1 and usage["reserved"] == 0
        assert sum(row["operation"] == "daily_credit_grant" for row in usage["entries"]) == 2
        charge = next(row for row in usage["entries"] if row["task_id"] == job["id"])
        assert (charge["amount"], charge["status"], charge["source"]) == (-1, "settled", "mcp")
    finally:
        store.close()
