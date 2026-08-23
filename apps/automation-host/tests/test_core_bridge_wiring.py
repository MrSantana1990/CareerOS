from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_main_imports_core_bridge_helpers() -> None:
    source = _source()
    assert "from .core_bridge import (CoreSyncRecord, build_job_record, build_prepare_record," in source
    assert "build_score_record, guess_company, is_due, is_eligible_for_prepare," in source


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


def test_core_sync_chain_advances_job_to_score_to_prepare() -> None:
    source = _source()
    start = source.index("def _advance_core_sync_chain(")
    end = source.index("\nasync def core_sync_scheduler(")
    body = source[start:end]
    assert 'if record.kind == "JOB":' in body
    assert "return [build_score_record(job_id=job_id, correlation_id=record.correlation_id)]" in body
    assert 'if record.kind == "SCORE":' in body
    assert "if is_eligible_for_prepare(total, recommendation):" in body
    assert "return [build_prepare_record(job_id=job_id, correlation_id=record.correlation_id)]" in body
    assert 'if record.kind == "PREPARE":' in body


def test_core_sync_chain_never_advances_on_a_transition_already_applied_response() -> None:
    source = _source()
    start = source.index("def _advance_core_sync_chain(")
    body = source[start : start + 1200]
    assert 'if response is None or response.get("already_applied"):' in body


def test_core_sync_scheduler_advances_the_chain_only_on_success() -> None:
    source = _source()
    start = source.index("async def core_sync_scheduler(")
    end = source.index("\nasync def google_mail_scheduler(")
    body = source[start:end]
    assert "remaining.extend(_advance_core_sync_chain(record, result.response))" in body


def test_advance_core_sync_chain_never_writes_the_outbox_directly() -> None:
    # Bug real encontrado em produção: enqueue_core_sync() dentro de
    # _advance_core_sync_chain acrescentava um registro novo no outbox,
    # mas _rewrite_core_sync_outbox(remaining) - chamado no fim do MESMO
    # ciclo do scheduler - sobrescrevia o arquivo inteiro só com a lista
    # em memória, apagando o que acabara de ser acrescentado. A cadeia
    # nunca avançava além de JOB. Corrigido: a função só retorna os
    # registros novos, quem escreve é sempre o scheduler.
    source = _source()
    start = source.index("def _advance_core_sync_chain(")
    end = source.index("\nasync def core_sync_scheduler(")
    body = source[start:end]
    assert "enqueue_core_sync(" not in body
    assert "-> list[CoreSyncRecord]:" in body


def test_resolve_resume_never_blocks_when_core_has_no_link_yet() -> None:
    source = _source()
    start = source.index("async def resolve_resume_for_application(")
    body = source[start : start + 900]
    assert 'if not version_id:' in body
    assert 'return "", None' in body


def test_execute_application_queue_uses_the_core_selected_resume_when_available() -> None:
    source = _source()
    start = source.index("async def resolve_resume_for_application(")
    end = source.index("\nasync def sync_job_to_core(")
    section = source[start:end]
    assert 'CAREER_API_URL + f"/api/v1/resumes/{version_id}/file"' in section
    start = source.index("resume_override_path, core_resume_version_id = await resolve_resume_for_application(application)")
    body = source[start : start + 600]
    assert 'profile.model_copy(update={"resume_path": resume_override_path})' in body
    assert "filled.extend(await fill_known_fields(root, effective_profile))" in source
