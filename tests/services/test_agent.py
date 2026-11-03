import asyncio
import json

import httpx2
import pytest
from openai import AsyncOpenAI
from pydantic_ai.messages import ModelRequest, UserPromptPart

from services.api.agent import AgentError, chat_model, run_agent
from services.api.config import Settings
from test_application_streaming import openai_chunk


class ExampleTools:
    def __init__(self):
        self.calls = []

    async def definitions(self):
        return [{"type": "function", "function": {"name": "inspect_molecule", "description": "Inspect a molecule", "parameters": {"type": "object", "properties": {"smiles": {"type": "string"}}, "required": ["smiles"]}}}]

    async def call(self, name, arguments):
        self.calls.append((name, arguments))
        return {"molecule_id": "mol-1", "smiles": "CCO", "formula": "C2H6O"}


USAGE = {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}


def tool_delta(arguments, call_id="call-1"):
    return {"tool_calls": [{"index": 0, "id": call_id, "type": "function",
                            "function": {"name": "inspect_molecule", "arguments": arguments}}]}


def response(deltas, finish="stop"):
    content = "".join(openai_chunk(delta) for delta in deltas)
    if finish:
        content += openai_chunk({}, finish, USAGE) + "data: [DONE]\n\n"
    return httpx2.Response(200, content=content.encode(), headers={"content-type": "text/event-stream"})


async def execute(upstream, tools, events, *, timeout=5):
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(upstream)) as transport:
        async with AsyncOpenAI(base_url="https://model.test/v1", api_key="test", http_client=transport) as client:
            model = chat_model(Settings(model="wire-test"), client)
            return await run_agent(
                model, tools, [ModelRequest(parts=[UserPromptPart("检查 CCO")])], "quick",
                run_id="test-run", emit=lambda kind, data: events.append((kind, data)),
                save=lambda _: None, model_timeout=timeout,
            )


@pytest.mark.asyncio
async def test_sdk_streaming_tool_fragments_round_trip_and_measure_usage():
    requests = []

    def upstream(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return response([tool_delta('{"smiles":'), {"tool_calls": [{"index": 0, "function": {"arguments": '"CCO"}'}}]}], "tool_calls")
        tool = body["messages"][-1]
        assert tool["role"] == "tool"
        assert tool["tool_call_id"] == "call-1"
        assert json.loads(tool["content"])["formula"] == "C2H6O"
        return response([{"content": "乙醇的分子式是 "}, {"content": "C2H6O。"}])

    tools, events = ExampleTools(), []
    transcript, usage = await execute(upstream, tools, events)
    assert requests[0]["stream"] is True
    assert tools.calls == [("inspect_molecule", {"smiles": "CCO"})]
    assert [data["args"] for kind, data in events if kind == "tool_start"] == [{"smiles": "CCO"}]
    assert "".join(data["content"] for kind, data in events if kind == "delta") == "乙醇的分子式是 C2H6O。"
    assert usage["requests"] == 2 and usage["input_tokens"] == 40
    assert any(part.get("tool_call_id") == "call-1" for message in transcript for part in message["parts"])


@pytest.mark.asyncio
async def test_bad_arguments_get_corrected_before_execution():
    count = 0

    def upstream(request):
        nonlocal count
        count += 1
        if count == 1:
            return response([tool_delta('{"smiles":42}')], "tool_calls")
        if count == 2:
            assert "参数无效" in json.loads(request.content)["messages"][-1]["content"]
            return response([tool_delta('{"smiles":"CCO"}', "call-2")], "tool_calls")
        return response([{"content": "已核实 C2H6O。"}])

    tools, events = ExampleTools(), []
    await execute(upstream, tools, events)
    assert tools.calls == [("inspect_molecule", {"smiles": "CCO"})]
    assert any(kind == "tool_end" and data["result"].get("error", {}).get("code") == "invalid_tool_arguments"
               for kind, data in events)


@pytest.mark.asyncio
async def test_unfinished_provider_stream_is_not_a_completed_answer():
    with pytest.raises(AgentError, match="完整"):
        await execute(lambda _: response([{"content": "partial"}], None), ExampleTools(), [])


@pytest.mark.asyncio
async def test_continuously_active_stream_has_wall_clock_timeout():
    class SlowStream(httpx2.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(40):
                yield openai_chunk({"content": "x"}).encode()
                await asyncio.sleep(0.02)

    with pytest.raises(AgentError) as failure:
        await execute(lambda _: httpx2.Response(200, stream=SlowStream(), headers={"content-type": "text/event-stream"}),
                      ExampleTools(), [], timeout=0.05)
    assert failure.value.code == "provider_timeout"
