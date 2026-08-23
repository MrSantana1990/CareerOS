from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_main_imports_core_bridge_helpers() -> None:
    source = _source()
    assert "from .core_bridge import CoreSyncRecord, build_job_record, is_due, send_core_sync" in source


def test_core_sync_scheduler_treats_dead_letter_as_a_hard_stop_not_infinite_retry() -> None:
    source = _source()
    start = source.index("async def core_sync_scheduler(")
    end = source.index("\nasync def google_mail_scheduler(")
    body = source[start:end]
    assert "if not result.retryable or record.attempts >= 5:" in body
    assert "_dead_letter_core_sync(record)" in body


def test_core_sync_scheduler_is_registered_at_startup() -> None:
    source = _source()
    start = source.index("async def startup_scheduler(")
    body = source[start : start + 500]
    assert "asyncio.create_task(core_sync_scheduler())" in body


def test_core_sync_status_and_requeue_endpoints_exist() -> None:
    source = _source()
    assert '@app.get("/core-sync/status")' in source
    assert '@app.post("/core-sync/dead-letter/{idempotency_key:path}/requeue")' in source


def test_job_sync_never_fabricates_a_company_name() -> None:
    source = _source()
    start = source.index("async def sync_job_to_core(")
    end = source.index("\nasync def inspect_application_queue(")
    body = source[start:end]
    assert 'if not company:' in body
    assert 'event("CORE_SYNC_SKIPPED_NO_COMPANY"' in body


def test_inspect_application_queue_syncs_after_visiting_the_real_page() -> None:
    source = _source()
    start = source.index("async def inspect_application_queue(")
    body = source[start : start + 2500]
    assert 'body = (await page.locator("body").inner_text(timeout=10_000))[:80_000]' in body
    assert "await sync_job_to_core(page, job, application, body)" in body
