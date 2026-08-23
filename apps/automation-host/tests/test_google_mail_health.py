from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_google_status_never_reports_connected_on_a_failed_live_check():
    source = _source()
    start = source.index('@app.get("/google/status")')
    end = source.index("\n@app.get", start + 1)
    body = source[start:end]
    assert '"connected": True' not in body.split("except Exception as exc:")[1]
    assert '"connected": False' in body.split("except Exception as exc:")[1]


def test_google_mail_scheduler_tracks_consecutive_failures_and_escalates():
    source = _source()
    start = source.index("async def google_mail_scheduler(")
    end = source.index("\n@app.on_event", start)
    body = source[start:end]
    assert "GOOGLE_HEALTH_ALERT_THRESHOLD" in body
    assert '"consecutive_failures"' in body
    assert 'event("GOOGLE_MAIL_AUTH_BROKEN"' in body
    assert 'event("GOOGLE_MAIL_RECOVERED"' in body


def test_metrics_exposes_google_mail_health_for_dashboards():
    source = _source()
    start = source.index('@app.get("/metrics")')
    end = source.index("\n@app.get", start + 1)
    body = source[start:end]
    assert '"google_mail_healthy"' in body
    assert '"google_mail_consecutive_failures"' in body
