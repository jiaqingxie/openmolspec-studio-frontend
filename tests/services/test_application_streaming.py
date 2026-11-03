import asyncio
import json
import socket
import threading
import time
from contextlib import asynccontextmanager, contextmanager

import httpx
import pytest
import uvicorn

from pydantic_ai.models.function import FunctionModel

from services.api.app import create_app
from services.api.config import Settings


@contextmanager
def running_server(app):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started, "test server did not start"
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(5)
        listener.close()
        assert not thread.is_alive()


class EmptyTools:
    async def definitions(self):
        return []


@asynccontextmanager
async def no_tools():
    yield EmptyTools()


def openai_chunk(delta, finish=None, usage=None):
    body = {"id": "test-completion", "created": 1, "object": "chat.completion.chunk",
            "model": "wire-test", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    if usage:
        body["usage"] = usage
    return "data: " + json.dumps(body) + "\n\n"


def gated_model(release):
    async def stream(messages, info):
        yield "已读取问题。"
        await asyncio.to_thread(release.wait, 5)
        yield "分析完成。"
    return FunctionModel(stream_function=stream)


@pytest.mark.asyncio
async def test_disconnect_does_not_cancel_run_and_replayed_events_restore_result(tmp_path, postgres_dsn):
    release = threading.Event()
    config = Settings(database=postgres_dsn, upload_dir=tmp_path / "files", internal_key="test-key",
                      environment="test", mock_enabled=True, api_key="test", model="test")
    app = create_app(config, provider_factory=lambda _: gated_model(release), tools_factory=no_tools)
    try:
        with running_server(app) as base_url:
            async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
                assert (await client.post("/api/auth/mock", json={"identity": "researcher"})).status_code == 200
                conversation = (await client.post("/api/conversations", json={})).json()
                async with client.stream("POST", f"/api/conversations/{conversation['id']}/messages", json={"content": "检查乙醇", "mode": "quick"}) as response:
                    run_id = response.headers["x-run-id"]
                    async for line in response.aiter_lines():
                        if line.startswith("event: run"):
                            break
                detail = (await client.get(f"/api/conversations/{conversation['id']}")).json()
                assert detail["active_run_id"] == run_id
                second = await client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "另一个问题"})
                assert second.status_code == 409
                assert (await client.delete(f"/api/conversations/{conversation['id']}")).status_code == 409
                release.set()
                replay = await client.get(f"/api/runs/{run_id}/events")
                assert "event: done" in replay.text
                assert "分析完成。" in replay.text
                ids = [int(line[4:]) for line in replay.text.splitlines() if line.startswith("id: ")]
                assert ids == sorted(set(ids))
                replay_tail = await client.get(f"/api/runs/{run_id}/events?after={ids[-1]}")
                assert replay_tail.text == ""
                detail = (await client.get(f"/api/conversations/{conversation['id']}")).json()
                assert detail["active_run_id"] is None
                assert detail["messages"][-1]["content"] == "已读取问题。分析完成。"
    finally:
        release.set()
