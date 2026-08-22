from fastapi.testclient import TestClient

from src.main import app


def test_liveness() -> None:
    response = TestClient(app).get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_deep_health_reports_database_and_redis_checks() -> None:
    response = TestClient(app).get("/health/deep")
    assert response.status_code in (200, 503)
    checks = response.json()["checks"]
    assert "database" in checks
    assert "redis" in checks


def test_safety_defaults() -> None:
    data = TestClient(app).get("/api/v1/system/status").json()
    assert data["auto_apply_enabled"] is False
    assert "gupy" in data["blocked_platforms"]
    assert data["product_name"] == "HelpSystem Carreira"
    assert data["saas_ready"] is True
