from fastapi.testclient import TestClient

from src.main import app


def test_liveness() -> None:
    response = TestClient(app).get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_safety_defaults() -> None:
    data = TestClient(app).get("/api/v1/system/status").json()
    assert data["auto_apply_enabled"] is False
    assert "gupy" in data["blocked_platforms"]

