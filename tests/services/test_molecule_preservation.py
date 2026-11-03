import numpy as np
from fastapi.testclient import TestClient

from services.chemistry.app import create_app


def test_persisted_xyz_lookup_keeps_original_coordinates_and_identity(postgres_dsn, account_owner):
    original = "3\nOriginal geometry\nO 0 0 0\nH 0.95 0.1 0.1\nH -0.2 0.98 0\n"
    key = "chemistry-integration-test-key"
    headers = {"X-Molspec-Internal-Key": key, "X-Molspec-User-ID": account_owner}
    app = create_app(database_url=postgres_dsn, internal_key=key, device="cpu")
    with TestClient(app, headers=headers) as client:
        uploaded = client.post("/v1/molecules/resolve", json={"xyz": original}).json()
        fetched = client.get("/v1/molecules/" + uploaded["id"])
        assert fetched.status_code == 200
        assert fetched.json() == uploaded
        coords = np.asarray([line.split()[1:] for line in fetched.json()["xyz"].splitlines()[2:]], dtype=float)
        assert np.linalg.norm(coords[1] - coords[0]) == np.linalg.norm([0.95, 0.1, 0.1])
        assert client.get("/v1/molecules/unknown").status_code == 404
