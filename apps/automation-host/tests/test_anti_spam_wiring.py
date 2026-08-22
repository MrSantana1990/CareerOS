from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_main_imports_daily_quota_helper() -> None:
    source = _source()
    assert "from .anti_spam import remaining_daily_quota" in source


def test_execute_application_queue_computes_quota_once_per_run() -> None:
    source = _source()
    start = source.index("async def execute_application_queue(")
    body = source[start : start + 800]
    assert "remaining_quota = remaining_daily_quota(applications, settings.daily_target, datetime.now(UTC))" in body


def test_submission_gate_requires_quota_and_decrements_it() -> None:
    source = _source()
    assert "live_allowed = would_apply and not dry_run_enabled() and quota_available" in source
    assert "remaining_quota -= 1" in source


def test_daily_limit_reached_is_audited_and_explained() -> None:
    source = _source()
    assert 'event("DAILY_LIMIT_REACHED", application_id=application["id"], daily_target=settings.daily_target)' in source
    assert "limite diário de {settings.daily_target} candidaturas já atingido" in source
