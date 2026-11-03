import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from services.api.accounts import COOKIE, Accounts
from services.api.app import create_app
from services.api.config import Settings
from services.chemistry.app import create_app as chemistry_app
from test_application_streaming import running_server


def configuration(postgres_dsn, tmp_path, **overrides):
    return Settings(**({"database": postgres_dsn, "upload_dir": tmp_path / "files",
                        "internal_key": "test-key", "environment": "test", "mock_enabled": True} | overrides))


def test_production_refuses_mock_login(postgres_dsn, tmp_path):
    with pytest.raises(ValueError, match="Mock SSO"):
        with TestClient(create_app(configuration(postgres_dsn, tmp_path, environment="production"))):
            pass
    with TestClient(create_app(configuration(postgres_dsn, tmp_path, environment="production", mock_enabled=False))) as client:
        assert client.get("/api/account").json() == {"authenticated": False, "mock_enabled": False, "identities": []}
        assert client.post("/api/auth/mock", json={"identity": "researcher"}).json()["error"]["code"] == "sso_unavailable"


def test_sessions_tokens_and_once_only_grant_survive_restart(postgres_dsn, tmp_path):
    settings = configuration(postgres_dsn, tmp_path)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/conversations", headers={"X-Molspec-User-ID": "spoof"}).status_code == 401
        assert client.get("/api/integrations/mcp").json() == {"local_url": None, "cloud_url": None}
        assert client.post("/api/auth/mock", json={"identity": "researcher"}, headers={"Origin": "https://untrusted.invalid"}).status_code == 403
        result = client.post("/api/auth/mock", json={"identity": "researcher"})
        assert "HttpOnly" in result.headers["set-cookie"] and "SameSite=lax" in result.headers["set-cookie"]
        user = result.json()["user"]
        created = client.post("/api/account/tokens", json={"name": "Lab CLI", "expires_in_days": 2}).json()
        conversation = client.post("/api/conversations", json={}).json()
        cookie = client.cookies.get(COOKIE)

    with TestClient(create_app(settings)) as client:
        client.cookies.set(COOKIE, cookie)
        assert client.get("/api/account").json()["user"] == user
        assert client.get(f"/api/conversations/{conversation['id']}").status_code == 200
        listing = client.get("/api/account/tokens")
        assert listing.json() == {"tokens": [created["record"]]}
        assert created["token"] not in listing.text
        accounts = Accounts(postgres_dsn)
        with accounts.connect() as conn:
            stored = conn.execute("SELECT secret_hash FROM molspec_app.access_tokens").fetchone()
            assert len(stored["secret_hash"]) == 64 and stored["secret_hash"] != created["token"]
            conn.execute("UPDATE molspec_app.sessions SET expires_at=now()-interval '1 second'")
        assert client.get("/api/conversations").status_code == 401
        assert client.post("/api/auth/mock", json={"identity": "researcher"}).json()["user"] == user
        usage = client.get("/api/account/usage").json()
        assert usage["available"] == accounts.free_credits
        assert [(item["operation"], item["status"]) for item in usage["entries"]] == [("daily_credit_grant", "granted")]
        current_cookie = client.cookies.get(COOKIE, domain="testserver.local")
        assert client.post("/api/auth/logout").status_code == 204
        assert accounts.session_user(current_cookie) is None


def test_concurrent_first_login_provisions_one_grant(postgres_dsn):
    accounts = Accounts(postgres_dsn, free_credits=7)
    accounts.initialize()
    with ThreadPoolExecutor(max_workers=6) as pool:
        sessions = list(pool.map(accounts.login_mock, ["researcher"] * 6))
    users = {user["id"] for _, user in sessions}
    assert len(users) == 1
    assert len({secret for secret, _ in sessions}) == 6
    usage = accounts.usage(users.pop())
    assert usage["available"] == 7 and len(usage["entries"]) == 1


@pytest.mark.asyncio
async def test_live_web_and_mcp_gateway_are_owner_scoped(postgres_dsn, tmp_path):
    async def call_mcp(base_url, token, name, args, **extra):
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}", **extra}) as client:
            async with streamable_http_client(f"{base_url}/api/mcp", http_client=client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    names = {tool.name for tool in (await session.list_tools()).tools}
                    assert {"inspect_molecule", "inspect_spectrum", "predict_spectra"} <= names
                    return (await session.call_tool(name, args)).structuredContent

    with running_server(chemistry_app(database_url=postgres_dsn, internal_key="test-key", device="cpu")) as chem:
        settings = configuration(postgres_dsn, tmp_path, chemistry_url=chem, model="", api_key="")
        with running_server(create_app(settings)) as api:
            async with httpx.AsyncClient(base_url=api, timeout=30) as first, httpx.AsyncClient(base_url=api, timeout=30) as second:
                a, b = await asyncio.gather(
                    first.post("/api/auth/mock", json={"identity": "researcher"}),
                    second.post("/api/auth/mock", json={"identity": "analyst"}),
                )
                owner_a, owner_b = a.json()["user"]["id"], b.json()["user"]["id"]
                assert owner_a != owner_b
                a_token = (await first.post("/api/account/tokens", json={"name": "First"})).json()
                b_token = (await second.post("/api/account/tokens", json={"name": "Second"})).json()
                conversation = (await first.post("/api/conversations", json={})).json()["id"]
                events = await first.post(f"/api/conversations/{conversation}/messages", json={"content": "hello"})
                assert events.status_code == 200
                run_id = events.headers["x-run-id"]
                assert (await first.get(f"/api/runs/{run_id}/events")).status_code == 200
                data = b"400,0\n4000,1"
                uploaded = (await first.post("/api/uploads", files={"file": ("ir.csv", data)})).json()
                download = f"/api/attachments/{uploaded['id']}/download"
                assert (await first.get(download)).content == data
                for path in (download, f"/api/runs/{run_id}/events", f"/api/conversations/{conversation}",
                             f"/api/spectra/{uploaded['spectrum_id']}"):
                    assert (await second.get(path)).status_code == 404
                second_conversation = (await second.post("/api/conversations", json={})).json()["id"]
                response = await second.post(f"/api/conversations/{second_conversation}/messages",
                                             json={"content": "analyze", "context": {"ir_id": uploaded["spectrum_id"]}})
                assert response.status_code == 404
                response = await second.post(f"/api/conversations/{second_conversation}/messages",
                                             json={"content": "analyze", "attachment_ids": [uploaded["id"]]})
                assert response.status_code == 422

                molecule = await call_mcp(api, a_token["token"], "inspect_molecule", {"smiles": "CCO"})
                assert molecule["formula"] == "C2H6O"
                assert (await first.get(f"/api/molecules/{molecule['molecule_id']}")).status_code == 200
                assert (await second.get(f"/api/molecules/{molecule['molecule_id']}")).status_code == 404
                forbidden = await call_mcp(api, b_token["token"], "inspect_spectrum",
                                           {"spectrum_id": uploaded["spectrum_id"]},
                                           **{"X-Molspec-User-ID": owner_a, "X-Molspec-Internal-Key": "test-key"})
                assert forbidden["error"]["code"] == "not_found"
                assert (await first.get("/api/account/tokens")).json()["tokens"][0]["last_used_at"]
                token_route = f"/api/account/tokens/{a_token['record']['id']}"
                assert (await second.delete(token_route)).status_code == 404
                assert (await first.delete(token_route)).status_code == 204
                with Accounts(postgres_dsn).connect() as conn:
                    conn.execute("UPDATE molspec_app.access_tokens SET expires_at=%s WHERE id=%s",
                                 (datetime.now(timezone.utc) - timedelta(seconds=1), b_token["record"]["id"]))
                for token in (a_token["token"], b_token["token"], "molspec_invalid"):
                    denied = await first.post("/api/mcp", headers={"Authorization": f"Bearer {token}"})
                    assert denied.status_code == 401 and denied.headers["www-authenticate"] == "Bearer"
                assert (await first.get(chem + "/v1/jobs")).status_code == 401
