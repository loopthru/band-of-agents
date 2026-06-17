from fastapi.testclient import TestClient

from band_of_agents.main import app


client = TestClient(app)


def test_root_returns_app_metadata():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "name": "band-of-agents",
        "status": "ok",
    }


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
