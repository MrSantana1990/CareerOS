from pathlib import Path


def _main_source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def _function_body(source: str, name: str) -> str:
    start = source.index(f"async def {name}(")
    end = source.index("\nasync def", start + 1)
    return source[start:end]


def test_watch_recheck_scheduler_is_registered_on_startup() -> None:
    source = _main_source()
    start = source.index("async def startup_scheduler(")
    body = source[start:start + 700]
    assert "asyncio.create_task(watch_recheck_scheduler())" in body


def test_watch_recheck_scheduler_never_lets_a_failure_propagate() -> None:
    body = _function_body(_main_source(), "watch_recheck_scheduler")
    assert "try:" in body
    assert "await watch_recheck_due()" in body
    assert 'event("WATCH_RECHECK_FAILED"' in body


def test_watch_recheck_scheduler_runs_once_per_day_at_a_distinct_hour() -> None:
    # Secao 24: 7h - depois do market_scan (6h), antes do daily_scheduler (8h).
    body = _function_body(_main_source(), "watch_recheck_scheduler")
    assert "now.hour == 7" in body
    assert "slot != last_slot" in body


def test_watch_recheck_due_never_raises_when_admin_token_missing() -> None:
    body = _function_body(_main_source(), "watch_recheck_due")
    assert "if not CAREER_ADMIN_TOKEN:" in body
    assert 'event("WATCH_RECHECK_SKIPPED"' in body


def test_watch_recheck_due_emits_required_observability_events() -> None:
    body = _function_body(_main_source(), "watch_recheck_due")
    for required_event in ("WATCH_RECHECK_STARTED", "WATCH_RECHECK_COMPLETED", "WATCH_RECHECK_FAILED"):
        assert f'"{required_event}"' in body, f"missing event {required_event}"


def test_watch_recheck_due_isolates_a_single_watch_failure_from_the_rest() -> None:
    body = _function_body(_main_source(), "watch_recheck_due")
    start = body.index("for watch in due_watches:")
    loop_body = body[start:start + 400]
    assert "except Exception as item_error:" in loop_body
    assert "WATCH_RECHECK_ITEM_FAILED" in loop_body


def test_watch_recheck_due_never_creates_an_application_itself() -> None:
    # AUTO_SAFE only (Secao 24) - so chama /watches/{id}/recheck (Brain),
    # nunca /opportunities/{id}/action-plan ou qualquer rota de candidatura.
    body = _function_body(_main_source(), "watch_recheck_due")
    assert "/api/v1/opportunities" not in body
    assert "/api/v1/applications" not in body
