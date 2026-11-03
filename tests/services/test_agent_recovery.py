from contextlib import asynccontextmanager

import httpx
import pytest
from pydantic_ai.messages import ModelRequest, ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from services.api.accounts import COOKIE
from services.api.app import create_app
from services.api.config import Settings
from test_application_streaming import running_server


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", [False, True], ids=["restart", "stop-reply"])
async def test_wait_checkpoint_survives_shutdown_and_duplicate_post(tmp_path, postgres_dsn, account_owner, stop):
    submissions = []
    polls = []
    model_requests = []
    ready = False

    class Tools:
        async def definitions(self):
            return [{"function": {"name": "predict_spectra", "description": "Submit a prediction",
                    "parameters": {"type": "object", "properties": {"smiles": {"type": "string"}},
                                   "required": ["smiles"]}}}]

        async def call(self, name, args):
            if name == "predict_spectra":
                submissions.append(args)
                return {"job_id": "fixture-job", "status": "queued"}
            assert name == "get_calculation" and args == {"job_id": "fixture-job"}
            polls.append(args)
            return {"job_id": "fixture-job", "status": "succeeded" if ready else "running", "ir_id": "fixture-ir"}

    @asynccontextmanager
    async def tools():
        yield Tools()

    async def model_stream(messages, info):
        model_requests.append(messages)
        if isinstance(messages[-1], ModelRequest) and isinstance(messages[-1].parts[0], ToolReturnPart):
            assert messages[-1].parts[0].content["ir_id"] == "fixture-ir"
            yield "计算已完成，可以继续分析光谱。"
        else:
            yield {0: DeltaToolCall(name="predict_spectra", json_args='{"smiles":"CCO"}', tool_call_id="provider-call")}

    settings = Settings(database=postgres_dsn, upload_dir=tmp_path / "uploads", internal_key="test-key",
                        environment="test", mock_enabled=True, api_key="fixture", model="fixture")

    def application():
        return create_app(settings, provider_factory=lambda _: FunctionModel(stream_function=model_stream), tools_factory=tools)

    app = application()
    payload = {"content": "预测 CCO", "request_id": "client-request"}
    with running_server(app) as base_url:
        async with httpx.AsyncClient(base_url=base_url, timeout=8) as client:
            login = await client.post("/api/auth/mock", json={"identity": "researcher"})
            assert login.status_code == 200
            assert login.json()["user"]["id"] == account_owner
            session = client.cookies[COOKIE]
            conversation = (await client.post("/api/conversations", json={})).json()
            path = f"/api/conversations/{conversation['id']}/messages"
            async with client.stream("POST", path, json=payload) as response:
                run_id = response.headers["x-run-id"]
                async for line in response.aiter_lines():
                    if "waiting_calculation" in line:
                        break
            with app.state.store.as_user(account_owner):
                checkpoint = app.state.store.checkpoint(run_id)
            assert checkpoint["results"]["provider-call"]["result"]["job_id"] == "fixture-job"
            assert submissions[0]["request_id"]
            assert (await client.post(path, json={**payload, "content": "different"})).status_code == 409
            if stop:
                cancelled = (await client.post(f"/api/runs/{run_id}/cancel")).json()
                assert cancelled["status"] == "failed"
                detail = (await client.get(f"/api/conversations/{conversation['id']}")).json()
                assert detail["messages"][-1]["tool_calls"][0]["result"]["job_id"] == "fixture-job"

    with app.state.store.as_user(account_owner):
        assert app.state.store.get_run(run_id)["status"] == ("failed" if stop else "running")
    ready = True
    with running_server(application()) as base_url:
        async with httpx.AsyncClient(base_url=base_url, timeout=8, cookies={COOKIE: session}) as client:
            replay = await client.post(path, json=payload)
            assert replay.headers["x-run-id"] == run_id
            assert ("event: error" if stop else "event: done") in replay.text
            detail = (await client.get(f"/api/conversations/{conversation['id']}")).json()
            assert len(detail["messages"]) == 2
            assert detail["active_run_id"] is None
    assert len(submissions) == 1
    assert len(model_requests) == (1 if stop else 2)
    if not stop:
        assert polls and detail["messages"][-1]["tool_calls"][0]["result"]["ir_id"] == "fixture-ir"
