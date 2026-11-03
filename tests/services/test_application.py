import json
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from services.api.app import create_app, history_for_run
from services.api.config import Settings
from services.api.store import Conflict, Store


@pytest.fixture
def settings(tmp_path, postgres_dsn):
    return Settings(database=postgres_dsn, upload_dir=tmp_path / "files", internal_key="test-key",
                    environment="test", mock_enabled=True, api_key="", model="")


@contextmanager
def logged_in(app):
    with TestClient(app) as client:
        assert client.post("/api/auth/mock", json={"identity": "researcher"}).status_code == 200
        yield client


def test_run_store_is_durable_and_rejects_two_active_runs(postgres_dsn, account_owner):
    store = Store(postgres_dsn)
    store.initialize()
    with store.as_user(account_owner):
        conversation = store.create_conversation()
        run, _, _ = store.begin_run(conversation["id"], "检查乙醇", [], {})
        with pytest.raises(Conflict):
            store.begin_run(conversation["id"], "第二个请求", [], {})
        store.add_event(run["id"], "delta", {"content": "乙醇"})
        store.finish_run(run["id"], "乙醇", [], [])
    restarted = Store(postgres_dsn)
    with restarted.as_user(account_owner):
        restored = restarted.get_conversation(conversation["id"])
        assert restored["messages"][0]["content"] == "检查乙醇"
        assert restored["messages"][1]["content"] == "乙醇"
        assert restored["active_run_id"] is None
        assert restarted.events(run["id"], after=0)[1]["type"] == "delta"


def test_restart_marks_pending_assistant_interrupted(postgres_dsn, account_owner):
    store = Store(postgres_dsn)
    store.initialize()
    with store.as_user(account_owner):
        conversation = store.create_conversation()
        run, _, _ = store.begin_run(conversation["id"], "预测光谱", [], {})
    store.recover_interrupted()
    with store.as_user(account_owner):
        restored = store.get_conversation(conversation["id"])
        assert restored["active_run_id"] is None
        assert restored["messages"][-1]["status"] == "failed"
        assert store.events(run["id"])[-1]["data"]["code"] == "run_interrupted"


def test_unconfigured_agent_produces_honest_persisted_error(settings):
    app = create_app(settings)
    with logged_in(app) as client:
        conversation = client.post("/api/conversations", json={}).json()
        response = client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "你好", "mode": "quick"})
        assert response.status_code == 200
        assert "agent_unconfigured" in response.text
        assert "event: error" in response.text
        detail = client.get(f"/api/conversations/{conversation['id']}").json()
        assert len(detail["messages"]) == 2
        assert detail["messages"][-1]["status"] == "failed"
        assert detail["active_run_id"] is None


def test_unknown_attachment_is_rejected_before_message_is_saved(settings):
    with logged_in(create_app(settings)) as client:
        conversation = client.post("/api/conversations", json={}).json()
        response = client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "分析", "mode": "quick", "attachment_ids": ["not-an-upload"]})
        assert response.status_code == 422
        assert client.get(f"/api/conversations/{conversation['id']}").json()["messages"] == []


def test_offline_chemistry_is_visible_and_proxy_fails_cleanly(settings):
    async def offline(request):
        raise httpx.ConnectError("offline", request=request)

    app = create_app(settings, chemistry_transport=httpx.MockTransport(offline))
    with logged_in(app) as client:
        status = client.get("/api/status").json()
        assert status["chemistry"] is None
        assert status["agent"]["configured"] is False
        response = client.post("/api/molecules/resolve", json={"smiles": "CCO"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "chemistry_unavailable"


def test_uploaded_spectrum_uses_chemistry_parser_and_persists_reference(settings):
    def chemistry(request):
        body = json.loads(request.content)
        assert body["content"] == "400,0\n4000,1"
        return httpx.Response(200, json={"id": "spectrum-1", "name": "ir.csv", "modality": "ir", "wavenumber": [400, 4000], "intensity": [0, 1]})

    with logged_in(create_app(settings, chemistry_transport=httpx.MockTransport(chemistry))) as client:
        attachment = client.post("/api/uploads", files={"file": ("ir.csv", b"400,0\n4000,1", "text/csv")}, data={"modality": "ir"}).json()
        assert attachment["spectrum_id"] == "spectrum-1"
        assert attachment["kind"] == "spectrum"
        assert "content" not in attachment
        assert client.post("/api/uploads", files={"file": ("app.exe", b"no", "application/octet-stream")}).status_code == 422


def test_event_cursor_outside_bigint_range_is_rejected_before_streaming(settings):
    app = create_app(settings)
    with logged_in(app) as client:
        conversation = client.post("/api/conversations", json={}).json()
        response = client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "你好"})
        run_id = response.headers["x-run-id"]
        assert client.get(f"/api/runs/{run_id}/events?after=9223372036854775808").status_code == 422
        assert client.get(f"/api/runs/{run_id}/events", headers={"Last-Event-ID": "9223372036854775808"}).status_code == 422


def test_proxy_rejects_non_finite_json_instead_of_crashing(settings):
    with logged_in(create_app(settings)) as client:
        response = client.post("/api/jobs", content='{"operation":"predict_gap","inputs":{"ir":[NaN]}}', headers={"content-type": "application/json"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_numeric_input"


def test_previous_selected_input_context_survives_reload_and_followup_without_new_context(postgres_dsn, account_owner):
    store = Store(postgres_dsn)
    store.initialize()
    context = {"molecule_id": "original-conformer", "ir_id": "spectrum-1", "nmr_h": [1.2, 3.4]}
    with store.as_user(account_owner):
        conversation = store.create_conversation()
        run, _, _ = store.begin_run(conversation["id"], "记住这个分子", [], context)
        store.finish_run(run["id"], "好的。", [], [])
    restored = Store(postgres_dsn)
    with restored.as_user(account_owner):
        restored.begin_run(conversation["id"], "现在预测它的光谱", [], {})
        history = history_for_run(restored, conversation["id"], {})
        assert "original-conformer" in history[0].parts[0].content
        assert "spectrum-1" in history[0].parts[0].content
        assert restored.get_conversation(conversation["id"])["messages"][0]["context"] == context


def test_persisted_molecule_lookup_proxies_original_conformer_by_id(settings):
    def chemistry(request):
        assert request.url.path == "/v1/molecules/original-id"
        return httpx.Response(200, json={"id": "original-id", "xyz": "original coordinates"})

    with logged_in(create_app(settings, chemistry_transport=httpx.MockTransport(chemistry))) as client:
        response = client.get("/api/molecules/original-id")
        assert response.status_code == 200
        assert response.json()["xyz"] == "original coordinates"


def test_agent_context_preserves_nmr_peaks_and_rejects_non_finite_values(settings):
    with logged_in(create_app(settings)) as client:
        conversation = client.post("/api/conversations", json={}).json()
        path = f"/api/conversations/{conversation['id']}/messages"
        response = client.post(path, json={"content": "结合这些位移分析", "context": {"nmr_h": [1.2, 3.4], "nmr_c": [20, 45]}})
        assert response.status_code == 200
        saved = client.get(f"/api/conversations/{conversation['id']}").json()["messages"][0]
        assert saved["context"]["nmr_h"] == [1.2, 3.4]
        invalid = client.post(path, content='{"content":"invalid","context":{"nmr_h":[NaN]}}', headers={"content-type": "application/json"})
        assert invalid.status_code == 422
