from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def _sync_job_to_core_body() -> str:
    source = _source()
    start = source.index("async def sync_job_to_core(")
    end = source.index("\nasync def", start + 1)
    return source[start:end]


def test_sync_job_to_core_propagates_real_recruiter_email_to_core() -> None:
    # Cycle 009: detect_email_application (via opportunity_feedback) ja
    # descobria um e-mail real de candidatura, mas ele nunca chegava ao
    # Core - application_strategy() do Core so decide EMAIL quando
    # recruiter_email vem preenchido em POST /jobs.
    body = _sync_job_to_core_body()
    assert 'email_application = application.get("email_application") or {}' in body
    assert 'recruiter_email = str(email_application.get("email") or "").strip() or None' in body
    assert "recruiter_email=recruiter_email" in body


def test_sync_job_to_core_propagates_detected_ats_as_application_channel() -> None:
    body = _sync_job_to_core_body()
    assert "ats_match = detect_ats(page.url)" in body
    assert "application_channel = ats_match.adapter.upper() if ats_match else None" in body
    assert "application_channel=application_channel" in body
