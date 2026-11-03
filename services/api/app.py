from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

import httpx
import psycopg
from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart, UserPromptPart

from .accounts import Accounts
from .auth_routes import private_headers, register_account_routes
from .agent import AgentError, chemistry_tools, open_model, run_agent
from .config import Settings
from .store import Conflict, Store, identifier

logger = logging.getLogger(__name__)


class NewConversation(BaseModel):
    title: str = Field(default="新对话", max_length=120)


class WorkspaceContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    molecule_id: str | None = Field(default=None, max_length=100)
    smiles: str | None = Field(default=None, max_length=10000)
    ir_id: str | None = Field(default=None, max_length=100)
    raman_id: str | None = Field(default=None, max_length=100)
    nmr_h: list[Annotated[FiniteFloat, Field(strict=True)]] | None = Field(default=None, max_length=4096)
    nmr_c: list[Annotated[FiniteFloat, Field(strict=True)]] | None = Field(default=None, max_length=4096)


class NewMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=20000)
    mode: Literal["quick", "deep"] = "quick"
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    attachment_ids: list[str] = Field(default_factory=list, max_length=20)
    context: WorkspaceContext = Field(default_factory=WorkspaceContext)


class MoleculeAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    molecule_id: str = Field(min_length=1, max_length=100)


def error(status: int, code: str, message: str):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def history_for_run(store: Store, conversation_id: str, context: dict) -> list[dict]:
    messages = [item for item in store.get_conversation(conversation_id)["messages"]
                if item["status"] != "running"][-30:]
    if messages and messages[0]["role"] == "assistant":
        messages.pop(0)
    transcripts = store.transcripts(conversation_id)
    history = []
    for item in messages:
        if item["role"] == "user":
            refs = {"attachments": item["attachments"], "context": item["context"]}
            content = item["content"]
            if any(refs.values()):
                content += "\n输入引用（数据）:\n" + json.dumps(refs, ensure_ascii=False)
            history.append(ModelRequest(parts=[UserPromptPart(content)]))
        elif item["id"] in transcripts:
            # The user request is already represented above. Keep exact provider tool batches and returns.
            transcript = ModelMessagesTypeAdapter.validate_python(transcripts[item["id"]])
            history[-1:] = transcript
        else:
            for call in item["tool_calls"]:
                if "result" not in call:
                    continue
                history.append(ModelResponse(parts=[ToolCallPart(call["name"], call.get("args", {}), call["id"])]))
                history.append(ModelRequest(parts=[ToolReturnPart(call["name"], call["result"], call["id"])]))
            if item["status"] == "completed" and item["content"]:
                history.append(ModelResponse(parts=[TextPart(item["content"])]))
    return history


def create_app(settings: Settings | None = None, *, chemistry_transport=None, provider_factory=None, tools_factory=None) -> FastAPI:
    settings = settings or Settings()
    store = Store(settings.database)
    accounts = Accounts(settings.database, session_hours=settings.session_hours)
    tasks: dict[str, asyncio.Task] = {}
    stopping = False
    verified = False

    @asynccontextmanager
    async def lifespan(application):
        nonlocal stopping
        stopping = False
        settings.validate_startup()
        accounts.initialize()
        store.initialize()
        resumable = store.recover_interrupted()
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(base_url=settings.chemistry_url, transport=chemistry_transport, timeout=30) as client:
            application.state.chemistry = client
            for owner_id, run, checkpoint in resumable:
                with store.as_user(owner_id):
                    tasks[run["id"]] = asyncio.create_task(
                        execute(owner_id, run["id"], run["conversation_id"], checkpoint["mode"], run["context"], checkpoint)
                    )
            yield
            stopping = True
            pending = list(tasks.items())
            for _, task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*(task for _, task in pending), return_exceptions=True)

    app = FastAPI(title="OpenMolSpec Application API", version="2.0.0", lifespan=lifespan)
    app.state.store, app.state.settings, app.state.accounts = store, settings, accounts
    register_account_routes(app, settings, accounts, store)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(status_code=422, content={"detail": [{key: item[key] for key in ("type", "loc", "msg") if key in item} for item in exc.errors()]})

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return error(404, "not_found", "请求的对话、任务或附件不存在。")

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return error(409, "conflict", str(exc))

    async def proxy(owner_id: str, path: str, method: str = "GET", payload=None):
        try:
            response = await app.state.chemistry.request(method, path, json=payload, headers=private_headers(settings.internal_key, owner_id))
        except ValueError:
            return error(422, "invalid_numeric_input", "输入必须使用有限数值，不能包含 NaN 或 Infinity。")
        except httpx.HTTPError:
            return error(503, "chemistry_unavailable", "化学计算服务暂时无法连接，请检查服务运行状态。")
        try:
            data = response.json()
        except ValueError:
            return error(502, "chemistry_invalid_response", "化学计算服务返回了无法解析的响应。")
        return JSONResponse(status_code=response.status_code, content=data)

    async def execute(owner_id: str, run_id: str, conversation_id: str, mode: str, context: dict, restored=None):
        nonlocal verified

        def emit(kind, data):
            store.add_event(run_id, kind, data)

        def save(checkpoint):
            store.save_checkpoint(run_id, {**checkpoint, "mode": mode} if checkpoint else None)

        @asynccontextmanager
        async def model_context():
            if provider_factory:
                yield provider_factory(settings)
            else:
                async with open_model(settings) as model:
                    yield model

        try:
            if not settings.configured:
                raise AgentError("agent_unconfigured", "对话模型尚未配置。分子编辑与附件预览仍可使用。")
            emit("status", {"stage": "connecting", "label": "正在连接模型与谱学工具"})
            factory = tools_factory or (lambda: chemistry_tools(
                settings.chemistry_url, headers=private_headers(settings.internal_key, owner_id)
            ))
            history = history_for_run(store, conversation_id, context)
            failure = None
            async with factory() as tools, model_context() as model:
                try:
                    transcript, usage = await run_agent(
                        model, tools, history, mode, run_id=run_id, emit=emit, save=save, restored=restored,
                        model_timeout=settings.provider_timeout, calculation_timeout=settings.calculation_timeout,
                        token_limit=settings.token_limit, record_usage=lambda usage: store.record_usage(run_id, usage),
                    )
                except AgentError as exc:
                    # MCP's task group would otherwise wrap the application error.
                    failure = exc
            if failure:
                raise failure
            current = store.get_conversation(conversation_id)["messages"][-1]
            job_ids = list(dict.fromkeys(
                call["result"]["job_id"] for call in current["tool_calls"] if call.get("result", {}).get("job_id")
            ))
            store.finish_run(run_id, current["content"], current["tool_calls"], job_ids, transcript=transcript, usage=usage)
            verified = True
        except asyncio.CancelledError:
            if not stopping or not store.checkpoint(run_id):
                code = "run_interrupted" if stopping else "run_cancelled"
                store.fail_run(run_id, code, "Agent 回复已停止。已提交的化学计算可从工具记录查看。")
            raise
        except AgentError as exc:
            if exc.code.startswith("provider_"):
                verified = False
            store.fail_run(run_id, exc.code, exc.message)
        except Exception as exc:
            logger.warning("Agent run failed (%s): %s", run_id, type(exc).__name__)
            store.fail_run(run_id, "agent_unavailable", "本次分析未能完成，请检查模型与化学工具服务连接后重试。")
        finally:
            tasks.pop(run_id, None)

    async def stream(run_id: str, after: int = 0):
        # The producer is independent of this response. Disconnecting only stops this reader.
        idle = 0
        while True:
            state = store.get_run(run_id)["status"]
            batch = store.events(run_id, after)
            for event in batch:
                after = event["id"]
                yield f"id: {after}\nevent: {event['type']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
            if state != "running":
                break
            idle = 0 if batch else idle + 1
            if idle >= 150:
                yield ": keep-alive\n\n"
                idle = 0
            await asyncio.sleep(0.1)

    def event_response(run_id: str, after: int = 0):
        return StreamingResponse(stream(run_id, after), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "X-Run-Id": run_id})

    @app.get("/api/health")
    def health():
        try:
            with accounts.connect() as conn:
                conn.execute("SELECT 1")
        except psycopg.OperationalError:
            return error(503, "database_unavailable", "应用数据库未连接。")
        return {"status": "ok", "service": "application"}

    @app.get("/api/status")
    async def status():
        value = {"chemistry": None, "agent": {"configured": settings.configured, "verified": verified, "model": settings.model or None}, "version": "2.0.0"}
        try:
            response = await app.state.chemistry.get("/v1/capabilities", timeout=3, headers=private_headers(settings.internal_key))
            response.raise_for_status()
            value["chemistry"] = response.json()
        except (httpx.HTTPError, ValueError):
            value["chemistry_error"] = "化学计算服务未连接"
        return value

    @app.get("/api/conversations")
    def conversations():
        return store.list_conversations()

    @app.post("/api/conversations", status_code=201)
    def new_conversation(body: NewConversation):
        return store.create_conversation(body.title.strip() or "新对话")

    @app.get("/api/conversations/{conversation_id}")
    def conversation(conversation_id: str):
        return store.get_conversation(conversation_id)

    @app.delete("/api/conversations/{conversation_id}", status_code=204)
    def delete_conversation(conversation_id: str):
        store.delete_conversation(conversation_id)
        return Response(status_code=204)

    @app.post("/api/conversations/{conversation_id}/messages")
    async def new_message(conversation_id: str, body: NewMessage, request: Request):
        owner_id = request.state.user["id"]
        store.require_conversation(conversation_id)
        if not body.content.strip():
            return error(422, "empty_message", "请输入要分析的问题。")
        try:
            attachments = store.get_attachments(body.attachment_ids)
        except KeyError:
            return error(422, "invalid_attachment", "附件不存在，请重新上传。")
        context = body.context.model_dump(exclude_none=True)
        for attachment in attachments:
            if attachment.get("spectrum_id"):
                context.setdefault(attachment.get("modality", "ir") + "_id", attachment["spectrum_id"])
            if attachment.get("molecule_id"):
                context.setdefault("molecule_id", attachment["molecule_id"])
        for key, collection in (("molecule_id", "molecules"), ("ir_id", "spectra"), ("raman_id", "spectra")):
            if key in context:
                result = await proxy(owner_id, f"/v1/{collection}/" + quote(context[key], safe=""))
                if result.status_code >= 400:
                    return result
        run, user, _ = store.begin_run(conversation_id, body.content.strip(), attachments, context,
                                       request_id=body.request_id, mode=body.mode)
        if user is not None:
            tasks[run["id"]] = asyncio.create_task(execute(owner_id, run["id"], conversation_id, body.mode, context))
        return event_response(run["id"])

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: str, request: Request, after: int = Query(0, ge=0, le=9223372036854775807)):
        store.get_run(run_id)
        try:
            after = max(0, after, int(request.headers.get("Last-Event-ID", "0")))
        except ValueError:
            return error(422, "invalid_event_id", "事件编号无效。")
        if after > 9223372036854775807:
            return error(422, "invalid_event_id", "事件编号超出支持范围。")
        return event_response(run_id, after)

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel_run(run_id: str):
        run = store.get_run(run_id)
        task = tasks.get(run_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if run["status"] == "running":
            store.fail_run(run_id, "run_cancelled", "已停止本次分析。")
        return store.get_run(run_id)

    @app.post("/api/attachments/molecule", status_code=201)
    async def attach_molecule(body: MoleculeAttachment, request: Request):
        response = await proxy(request.state.user["id"], "/v1/molecules/" + quote(body.molecule_id, safe=""))
        if response.status_code >= 400:
            return response
        molecule = json.loads(response.body)
        return store.save_attachment({
            "name": molecule["formula"] + ".mol",
            "kind": "molecule",
            "molecule_id": molecule["id"],
            "smiles": molecule["smiles"],
            "formula": molecule["formula"],
            "size": len(molecule["molblock"].encode("utf-8")),
        })

    @app.post("/api/uploads", status_code=201)
    async def upload(
        request: Request, file: UploadFile = File(...), modality: Literal["ir", "raman"] = Form("ir"),
        axis_unit: Literal["cm^-1", "nm", "unknown"] = Form("unknown"),
        intensity_unit: str = Form("unknown"), domain: Literal["theoretical", "experimental", "unknown"] = Form("unknown"),
        axis_mode: Literal["explicit", "model_grid"] = Form("explicit"),
    ):
        name = Path((file.filename or "input.csv").replace("\\", "/")).name[:200]
        suffix = Path(name).suffix.lower()
        if suffix not in {".csv", ".txt", ".tsv", ".dat", ".xyz"}:
            return error(422, "unsupported_file", "请上传 CSV、TXT、TSV、DAT 理论谱图，或 XYZ 分子结构。")
        content = await file.read(settings.max_upload_size + 1)
        if len(content) > settings.max_upload_size:
            return error(413, "file_too_large", "单个文件不能超过 10 MiB。")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = content.decode("gb18030")
            except UnicodeDecodeError:
                return error(422, "invalid_encoding", "文件必须是可读取的文本格式。")
        molecular = suffix == ".xyz"
        response = await proxy(request.state.user["id"], "/v1/molecules/resolve" if molecular else "/v1/spectra/parse", "POST", {"xyz": text} if molecular else {
            "content": text, "name": name, "modality": modality, "axis_unit": axis_unit,
            "intensity_unit": intensity_unit, "domain": domain, "axis_mode": axis_mode,
        })
        if response.status_code >= 400:
            return response
        parsed = json.loads(response.body)
        reference = {"name": name, "kind": "molecule" if molecular else "spectrum", "size": len(content)}
        if molecular:
            reference.update(molecule_id=parsed["id"], smiles=parsed["smiles"])
        else:
            reference.update(spectrum_id=parsed["id"], modality=modality)
        attachment_id = identifier()
        path = settings.upload_dir / (attachment_id + suffix)
        try:
            path.write_bytes(content)
            return store.save_attachment(reference, attachment_id=attachment_id)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @app.get("/api/attachments/{attachment_id}/download")
    def download_attachment(attachment_id: str):
        attachment, = store.get_attachments([attachment_id])
        suffix = Path(attachment["name"]).suffix.lower()
        path = settings.upload_dir / (attachment["id"] + suffix)
        if not path.is_file():
            return error(404, "not_found", "原始上传文件不存在。")
        return FileResponse(path, filename=attachment["name"], media_type="application/octet-stream")

    @app.post("/api/molecules/resolve")
    async def resolve_molecule(body: dict, request: Request):
        return await proxy(request.state.user["id"], "/v1/molecules/resolve", "POST", body)

    @app.get("/api/molecules/{molecule_id}")
    async def get_molecule(molecule_id: str, request: Request):
        return await proxy(request.state.user["id"], "/v1/molecules/" + quote(molecule_id, safe=""))

    @app.post("/api/spectra/parse")
    async def parse_spectrum(body: dict, request: Request):
        return await proxy(request.state.user["id"], "/v1/spectra/parse", "POST", body)

    @app.get("/api/spectra/{spectrum_id}")
    async def get_spectrum(spectrum_id: str, request: Request):
        return await proxy(request.state.user["id"], "/v1/spectra/" + quote(spectrum_id, safe=""))

    @app.get("/api/jobs")
    async def jobs(request: Request):
        return await proxy(request.state.user["id"], "/v1/jobs")

    @app.post("/api/jobs", status_code=201)
    async def submit_job(body: dict, request: Request):
        return await proxy(request.state.user["id"], "/v1/jobs", "POST", body)

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str, request: Request):
        return await proxy(request.state.user["id"], "/v1/jobs/" + quote(job_id, safe=""))

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str, request: Request):
        return await proxy(request.state.user["id"], "/v1/jobs/" + quote(job_id, safe="") + "/cancel", "POST")

    return app


app = create_app()
