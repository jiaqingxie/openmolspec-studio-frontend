import json

import httpx
from fastapi.testclient import TestClient

from services.api.app import create_app, history_for_run
from services.api.config import Settings
from services.api.store import Store


def test_editor_structure_attachment_keeps_saved_id_across_message_and_reload(tmp_path, postgres_dsn):
    paths = []
    molecule = {"id": "saved-ethanol", "smiles": "CCO", "formula": "C2H6O", "molblock": "original molblock", "xyz": "original coordinates"}

    def chemistry(request):
        paths.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/v1/molecules/saved-ethanol":
            return httpx.Response(200, json=molecule)
        return httpx.Response(404, json={"error": {"code": "not_found", "message": "结构不存在"}})

    settings = Settings(database=postgres_dsn, internal_key="test-key", environment="test", mock_enabled=True, upload_dir=tmp_path / "uploads")
    with TestClient(create_app(settings, chemistry_transport=httpx.MockTransport(chemistry))) as client:
        owner = client.post("/api/auth/mock", json={"identity": "researcher"}).json()["user"]["id"]
        response = client.post("/api/attachments/molecule", json={"molecule_id": molecule["id"]})
        assert response.status_code == 201
        attachment = response.json()
        assert attachment["kind"] == "molecule"
        assert attachment["molecule_id"] == molecule["id"]
        assert attachment["smiles"] == "CCO"
        assert attachment["name"] == "C2H6O.mol"
        conversation = client.post("/api/conversations", json={}).json()
        client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "看看这个结构", "attachment_ids": [attachment["id"]]})
        stored = Store(settings.database)
        with stored.as_user(owner):
            message = stored.get_conversation(conversation["id"])["messages"][0]
            assert message["attachments"] == [attachment]
            assert message["context"]["molecule_id"] == molecule["id"]
            assert molecule["id"] in history_for_run(stored, conversation["id"], {})[0].parts[0].content
        assert client.get("/api/molecules/" + attachment["molecule_id"]).json() == molecule
        assert client.post("/api/attachments/molecule", json={"molecule_id": "missing"}).status_code == 404
        assert client.post("/api/attachments/molecule", json={"molecule_id": ""}).status_code == 422
    assert all(method == "GET" for method, _ in paths)
