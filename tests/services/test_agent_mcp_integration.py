import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from services.api.app import create_app
from services.api.config import Settings
from services.chemistry.app import create_app as chemistry_app
from test_application_streaming import running_server, openai_chunk
from test_chemistry_service import reference_assets


@pytest.mark.asyncio
async def test_application_agent_uses_real_http_mcp_and_existing_rdkit_logic(tmp_path, postgres_dsn):
    upstream = FastAPI()
    requests = []

    @upstream.post("/v1/chat/completions")
    async def completion(request: Request):
        body = await request.json()
        requests.append(body)
        if len(requests) == 1:
            names = {tool["function"]["name"] for tool in body["tools"]}
            assert {"inspect_molecule", "get_capabilities", "predict_spectra"} <= names
            deltas = [{"tool_calls": [{"index": 0, "id": "chem-call", "type": "function", "function": {"name": "inspect_molecule", "arguments": '{"smiles":"CCO"}'}}]}]
        elif len(requests) == 2:
            properties = json.loads(body["messages"][-1]["content"])
            assert properties["formula"] == "C2H6O"
            assert properties["molecule_id"]
            deltas = [{"tool_calls": [{"index": 0, "id": "availability-call", "type": "function", "function": {"name": "get_capabilities", "arguments": "{}"}}]}]
        elif len(requests) == 3:
            assert json.loads(body["messages"][-1]["content"])["domain"] == "theoretical"
            deltas = [{"content": "乙醇的分子式为 C2H6O。"}, {"content": "模型可用性已通过化学服务查询。"}]
        else:
            calls = [call["id"] for message in body["messages"] for call in message.get("tool_calls", [])]
            returns = [message["tool_call_id"] for message in body["messages"] if message["role"] == "tool"]
            assert calls == returns == ["chem-call", "availability-call"]
            assert body["messages"][-1]["content"] == "继续说明乙醇信息"
            deltas = [{"content": "沿用上一轮核实的乙醇信息。"}]

        async def chunks():
            for delta in deltas:
                yield openai_chunk(delta)
            yield openai_chunk({}, "tool_calls" if "tool_calls" in deltas[0] else "stop",
                                   {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30})
            yield "data: [DONE]\n\n"

        return StreamingResponse(chunks(), media_type="text/event-stream")

    with running_server(chemistry_app(database_url=postgres_dsn, internal_key="test-key", device="cpu")) as chemistry_url, running_server(upstream) as provider_url:
        configuration = Settings(database=postgres_dsn, internal_key="test-key", environment="test", mock_enabled=True, upload_dir=tmp_path / "files", chemistry_url=chemistry_url, base_url=provider_url + "/v1", api_key="local-test", model="wire-test")
        with running_server(create_app(configuration)) as api_url:
            async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
                (await client.post("/api/auth/mock", json={"identity": "researcher"})).raise_for_status()
                conversation = (await client.post("/api/conversations", json={})).json()
                response = await client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "检查 CCO，并查询模型可用性", "mode": "quick"})
                assert response.status_code == 200
                assert "event: tool_start" in response.text
                assert "event: tool_end" in response.text
                assert "event: done" in response.text
                assert "event: error" not in response.text
                restored = (await client.get(f"/api/conversations/{conversation['id']}")).json()
                assert restored["messages"][-1]["status"] == "completed"
                calls = restored["messages"][-1]["tool_calls"]
                assert [item["name"] for item in calls] == ["inspect_molecule", "get_capabilities"]
                assert calls[0]["result"]["molecular_weight"] == pytest.approx(46.069, abs=0.01)
                assert "xyz" not in calls[0]["result"]
                assert len(requests) == 3
                followup = await client.post(f"/api/conversations/{conversation['id']}/messages",
                                             json={"content": "继续说明乙醇信息"})
                assert "event: done" in followup.text
                assert len(requests) == 4
                ledger = (await client.get("/api/account/usage")).json()
                model_rows = [entry for entry in ledger["entries"] if entry["operation"] == "agent_reply"]
                assert len(model_rows) == 2 and all(row["usage"]["input_tokens"] for row in model_rows)


@pytest.mark.asyncio
async def test_predicted_spectrum_can_be_reused_in_a_followup_over_mcp(tmp_path, postgres_dsn, reference_assets):
    from dataclasses import replace

    import numpy as np
    from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart
    from pydantic_ai.models.function import DeltaToolCall, FunctionModel

    from openmolspec_ui.inference import OpenMolSpecService

    class FixturePrediction(OpenMolSpecService):
        def predict_spectra(self, _molecule):
            return {"wavenumber": np.linspace(400, 4000, 1024),
                    "ir": np.linspace(0, 1, 1024), "raman": np.linspace(1, 0, 1024),
                    "nmr_h": np.array([1.1]), "nmr_c": np.array([12.0])}

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

    observed = {}
    async def stream(messages, _info):
        last = messages[-1].parts[0]
        if isinstance(last, UserPromptPart) and "预测" in last.content:
            yield {0: DeltaToolCall(name="predict_spectra", json_args='{"smiles":"CCO"}', tool_call_id="prediction")}
        elif isinstance(last, UserPromptPart):
            previous = next(part for message in messages if isinstance(message, ModelRequest)
                            for part in message.parts if isinstance(part, ToolReturnPart)
                            and part.tool_name == "predict_spectra")
            observed["reused"] = previous.content["ir_id"]
            yield {0: DeltaToolCall(name="inspect_spectrum", json_args=json.dumps({"spectrum_id": observed["reused"]}),
                                    tool_call_id="inspection")}
        elif last.tool_name == "inspect_spectrum":
            assert last.content["quality"]["model_eligible"] and last.content["provenance"]["source"] == "prediction"
            yield {0: DeltaToolCall(name="retrieve_candidates", json_args=json.dumps({"ir_id": observed["reused"]}),
                                    tool_call_id="retrieval")}
        else:
            assert last.content["status"] == "succeeded"
            observed[last.tool_name] = last.content
            yield "本轮计算完成。"

    chemistry = chemistry_app(database_url=postgres_dsn, internal_key="test-key", assets=assets, device="cpu",
                              service_factory=FixturePrediction)
    with running_server(chemistry) as chemistry_url:
        settings = Settings(database=postgres_dsn, internal_key="test-key", environment="test", mock_enabled=True, upload_dir=tmp_path / "files", chemistry_url=chemistry_url,
                            api_key="fixture", model="fixture")
        with running_server(create_app(settings, provider_factory=lambda _: FunctionModel(stream_function=stream))) as api_url:
            async with httpx.AsyncClient(base_url=api_url, timeout=15) as client:
                (await client.post("/api/auth/mock", json={"identity": "researcher"})).raise_for_status()
                conversation = (await client.post("/api/conversations", json={})).json()
                path = f"/api/conversations/{conversation['id']}/messages"
                prediction = await client.post(path, json={"content": "预测 CCO 的光谱"})
                assert "event: done" in prediction.text, prediction.text
                job_id = observed["predict_spectra"]["job_id"]
                result = (await client.get(f"/api/jobs/{job_id}")).json()["result"]
                assert len(result["ir"]) == 1024 and result["raman_id"]
                followup = await client.post(path, json={"content": "使用上一轮 IR 检索候选"})
                assert "event: done" in followup.text, followup.text
                records = [json.loads(line[6:]) for line in followup.text.splitlines() if line.startswith("data: ")]
                assert any(record.get("name") == "retrieve_candidates"
                           and record.get("args", {}).get("ir_id") == result["ir_id"] for record in records)
                assert observed["retrieve_candidates"]["input_refs"]["ir_id"] == result["ir_id"]
                assert observed["retrieve_candidates"]["summary"]["candidates"][0]["smiles"] == "CCO"

                before = (await client.get("/api/account")).json()["credits"]
                token = (await client.post("/api/account/tokens", json={"name": "shared credits"})).json()["token"]
                async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as transport:
                    async with streamable_http_client(f"{api_url}/api/mcp", http_client=transport) as (read, write, _):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            arguments = {"ir_id": result["ir_id"], "request_id": "external-retry"}
                            first = (await session.call_tool("retrieve_candidates", arguments)).structuredContent
                            retry = (await session.call_tool("retrieve_candidates", arguments)).structuredContent
                            assert retry["job_id"] == first["job_id"]
                async with asyncio.timeout(5):
                    while True:
                        job = (await client.get(f"/api/jobs/{first['job_id']}")).json()
                        if job["status"] == "succeeded":
                            break
                        assert job["status"] in {"queued", "running"}, job
                        await asyncio.sleep(0.05)
                usage = (await client.get("/api/account/usage")).json()
                entries = [row for row in usage["entries"] if row["task_id"] == job["id"]]
                assert len(entries) == 1 and entries[0]["source"] == "mcp"
                assert entries[0]["status"] == "settled" and entries[0]["duration_ms"] >= 0
                assert usage["available"] == before["available"] + entries[0]["amount"]
                assert usage["reserved"] == 0
