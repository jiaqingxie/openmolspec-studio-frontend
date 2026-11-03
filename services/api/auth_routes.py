from __future__ import annotations

import os
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .accounts import COOKIE, Accounts
from .config import DEVELOPMENT_IDENTITIES, Settings

PUBLIC = {"/api/health", "/api/status", "/api/account", "/api/auth/mock", "/api/auth/logout",
          "/api/integrations/mcp", "/api/mcp"}


def api_error(status: int, code: str, message: str, *, headers=None):
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def private_headers(key: str, user_id: str | None = None, source: str = "web") -> dict[str, str]:
    headers = {"X-Molspec-Internal-Key": key, "X-Molspec-Source": source}
    if user_id:
        headers["X-Molspec-User-ID"] = user_id
    return headers


class MockLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identity: str = Field(max_length=50)


class NewToken(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    expires_in_days: int = Field(default=30, ge=1, le=365, strict=True)


def register_account_routes(app: FastAPI, settings: Settings, accounts: Accounts, store):
    origins = {value.strip() for value in os.getenv("OPENMOLSPEC_ALLOWED_ORIGINS", "").split(",") if value.strip()}
    for url in (settings.mcp_local_url, settings.mcp_cloud_url):
        if url:
            parsed = urlsplit(url)
            origins.add(f"{parsed.scheme}://{parsed.netloc}")

    @app.middleware("http")
    async def account_scope(request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/") or path == "/api/mcp":
            return await call_next(request)
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            request_origin = f"{request.url.scheme}://{request.url.netloc}"
            if origin not in origins and origin != request_origin:
                return api_error(403, "origin_forbidden", "请求来源不在允许范围内。")
        user = await run_in_threadpool(accounts.session_user, request.cookies.get(COOKIE))
        request.state.user = user
        if user:
            with store.as_user(user["id"]):
                response = await call_next(request)
        elif path in PUBLIC:
            response = await call_next(request)
        else:
            response = api_error(401, "authentication_required", "请先使用公司账号登录。")
        response.headers["Cache-Control"] = "no-store, no-transform"
        return response

    @app.get("/api/account")
    def account(request: Request):
        user = request.state.user
        value = {"authenticated": bool(user), "mock_enabled": settings.mock_enabled,
                 "identities": [{"id": key, "name": name} for key, name in DEVELOPMENT_IDENTITIES.items()]
                 if settings.mock_enabled else []}
        if user:
            value.update(user=user, credits=accounts.balance(user["id"]))
        return value

    @app.post("/api/auth/mock")
    def mock_login(body: MockLogin, request: Request):
        if not settings.mock_enabled:
            return api_error(503, "sso_unavailable", "公司单点登录暂未配置。")
        if body.identity not in DEVELOPMENT_IDENTITIES:
            return api_error(422, "unknown_mock_identity", "请选择一个模拟身份。")
        secret, user = accounts.login_mock(body.identity)
        accounts.logout(request.cookies.get(COOKIE))
        response = JSONResponse({"user": user})
        response.set_cookie(COOKIE, secret, max_age=settings.session_hours * 3600, httponly=True,
                            samesite="lax", secure=settings.environment == "production")
        return response

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request):
        accounts.logout(request.cookies.get(COOKIE))
        response = Response(status_code=204)
        response.delete_cookie(COOKIE, httponly=True, samesite="lax", secure=settings.environment == "production")
        return response

    @app.get("/api/account/usage")
    def usage(request: Request):
        return accounts.usage(request.state.user["id"])

    @app.get("/api/account/tokens")
    def list_tokens(request: Request):
        return {"tokens": accounts.tokens(request.state.user["id"])}

    @app.post("/api/account/tokens", status_code=201)
    def create_token(request: Request, body: NewToken):
        return accounts.create_token(request.state.user["id"], body.name, body.expires_in_days)

    @app.delete("/api/account/tokens/{token_id}", status_code=204)
    def revoke_token(request: Request, token_id: str):
        if not accounts.revoke_token(request.state.user["id"], token_id):
            return api_error(404, "not_found", "访问令牌不存在。")
        return Response(status_code=204)

    @app.get("/api/integrations/mcp")
    def integrations():
        return {"local_url": settings.mcp_local_url, "cloud_url": settings.mcp_cloud_url}

    @app.api_route("/api/mcp", methods=["POST", "GET", "DELETE"], include_in_schema=False)
    async def mcp_gateway(request: Request):
        origin = request.headers.get("origin")
        if origin and origin not in origins:
            return api_error(403, "origin_forbidden", "MCP 请求来源不在允许范围内。")
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        owner_id = await run_in_threadpool(accounts.token_user, token) if scheme.lower() == "bearer" else None
        if not owner_id:
            return api_error(401, "invalid_access_token", "需要有效的 MolSpec 访问令牌。",
                             headers={"WWW-Authenticate": "Bearer"})
        headers = private_headers(settings.internal_key, owner_id, "mcp")
        for name in ("accept", "content-type", "mcp-protocol-version", "mcp-session-id", "last-event-id"):
            if name in request.headers:
                headers[name] = request.headers[name]
        body = bytearray()
        if request.method == "POST":
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 1024 * 1024:
                    return api_error(413, "mcp_request_too_large", "MCP 请求不得超过 1 MiB。")
        client = app.state.chemistry
        try:
            upstream = await client.send(client.build_request(
                request.method, "/mcp", headers=headers,
                content=bytes(body) if request.method == "POST" else None,
            ), stream=True)
        except httpx.HTTPError:
            return api_error(503, "chemistry_unavailable", "化学计算服务暂时无法连接。")
        forwarded = {name: upstream.headers[name] for name in ("content-type", "mcp-session-id", "allow")
                     if name in upstream.headers}
        forwarded["Cache-Control"] = "no-store"

        async def relay():
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()

        return StreamingResponse(relay(), status_code=upstream.status_code, headers=forwarded)
