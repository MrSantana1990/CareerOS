"""Fase 2, Prompt 12 - wiring/observabilidade do Job Correlation
(main.py). Complementa os testes puros de correlacao/status em
test_company_intelligence.py (o correlator generico e a maquina de
estados de vaga ativa/fechada moram em company_intelligence.py, sem I/O
proprio)."""

from pathlib import Path


def _main_source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def _function_body(source: str, name: str) -> str:
    start = source.index(f"async def {name}(")
    end = source.index("\nasync def", start + 1)
    return source[start:end]


def _sync_function_body(source: str, name: str) -> str:
    start = source.index(f"def {name}(")
    candidates = []
    for marker in ("\ndef ", "\nasync def ", "\n@app.", "\n@router."):
        index = source.find(marker, start + 1)
        if index != -1:
            candidates.append(index)
    end = min(candidates) if candidates else len(source)
    return source[start:end]


def test_job_correlation_scheduler_is_registered_on_startup() -> None:
    source = _main_source()
    start = source.index("async def startup_scheduler(")
    body = source[start:start + 1000]
    assert "asyncio.create_task(job_correlation_scheduler())" in body


def test_job_correlation_scheduler_never_lets_a_failure_propagate() -> None:
    body = _function_body(_main_source(), "job_correlation_scheduler")
    assert "try:" in body
    assert "await job_correlation_cycle()" in body
    assert 'event("JOB_CORRELATION_FAILED"' in body


def test_job_correlation_scheduler_runs_after_company_intelligence_same_day() -> None:
    # Secao 18: 5h30 - depois de Company Intelligence (5h), antes de
    # market_scan (6h), no mesmo slot diario.
    body = _function_body(_main_source(), "job_correlation_scheduler")
    assert "now.hour == 5 and now.minute >= 30" in body
    assert "slot != last_slot" in body


def test_job_correlation_cycle_never_raises_when_admin_token_missing() -> None:
    body = _function_body(_main_source(), "job_correlation_cycle")
    assert "if not CAREER_ADMIN_TOKEN:" in body
    assert 'event("JOB_CORRELATION_SKIPPED"' in body


def test_job_correlation_cycle_emits_required_observability_events() -> None:
    body = _function_body(_main_source(), "job_correlation_cycle")
    for required_event in ("JOB_CORRELATION_STARTED", "OFFICIAL_JOB_FOUND", "OFFICIAL_JOB_NOT_FOUND",
                            "OFFICIAL_JOB_AMBIGUOUS", "JOB_STATUS_RESOLVED", "JOB_CORRELATION_COMPLETED"):
        assert f'"{required_event}"' in body, f"missing event {required_event}"


def test_job_work_model_resolved_event_emitted_only_on_real_enrichment() -> None:
    body = _function_body(_main_source(), "_correlate_and_enrich_job")
    assert 'event("JOB_WORK_MODEL_RESOLVED"' in body


# E: company-only page never enriches the job (wiring level) ----------------------------------------------------

def test_e_only_high_confidence_or_exact_correlation_can_enrich() -> None:
    body = _function_body(_main_source(), "_correlate_and_enrich_job")
    assert "can_enrich_job(correlation)" in body


# F/G: enrichment only happens for a real ACTIVE status, never CLOSED/UNKNOWN/NOT_FOUND ---------------------------

def test_f_g_enrichment_requires_active_status_specifically() -> None:
    body = _function_body(_main_source(), "_correlate_and_enrich_job")
    assert 'status == "ACTIVE"' in body


def test_status_200_alone_never_short_circuits_to_active() -> None:
    body = _function_body(_main_source(), "_correlate_and_enrich_job")
    assert "classify_job_page_status(" in body


# L: salary not invented (this cycle only ever touches work_model, never salary) -----------------------------------

def test_l_job_correlation_cycle_never_touches_salary() -> None:
    body = _function_body(_main_source(), "_correlate_and_enrich_job")
    assert "salary" not in body.lower()


# N: official application endpoint creates a better channel (reuses existing channel machinery, never duplicated) --

def test_n_enrichment_refreshes_channels_only_through_existing_routes() -> None:
    body = _function_body(_main_source(), "job_correlation_cycle")
    assert "_discover_opportunity_channels" in body
    assert "_create_opportunity_action_plan" in body


# O: second run idempotent (enrich-official route is additive/COALESCE, verify-official reruns safely) -------------

def test_o_enrich_official_helper_hits_the_additive_core_route() -> None:
    body = _sync_function_body(_main_source(), "_enrich_job_official")
    assert "/enrich-official" in body
    assert 'method="POST"' in body


# P: no external action -----------------------------------------------------------------------------------------------

def test_p_job_correlation_never_calls_a_send_or_submit_function() -> None:
    source = _main_source()
    for name in ("_correlate_and_enrich_job", "job_correlation_cycle", "_enrich_job_official"):
        is_async = f"async def {name}(" in source
        body = _function_body(source, name) if is_async else _sync_function_body(source, name)
        for forbidden in ("send_application_email(", "send_security_code(", "create_calendar_event("):
            assert forbidden not in body, f"{name} must never call {forbidden}"


# S: Brain re-evaluation only after a real enrichment, reusing existing routes ----------------------------------------

def test_s_brain_reevaluation_only_triggered_by_a_real_enrichment() -> None:
    body = _function_body(_main_source(), "job_correlation_cycle")
    start = body.index('if result["enriched"]:')
    reeval_block = body[start:start + 500]
    assert "_calculate_job_score" in reeval_block
    assert "_evaluate_job_opportunity" in reeval_block


# T: rate-limit/backoff (batch bounds reused from Company Intelligence, Prompt 11) --------------------------------------

def test_t_job_correlation_is_bounded_by_fixed_batch_sizes() -> None:
    body = _function_body(_main_source(), "job_correlation_cycle")
    assert "JOB_CORRELATION_COMPANY_BATCH_SIZE" in body
    assert "JOB_CORRELATION_MAX_JOBS_PER_COMPANY" in body


def test_t_single_job_failure_never_aborts_the_batch() -> None:
    body = _function_body(_main_source(), "job_correlation_cycle")
    start = body.index("for job in canonical_jobs:")
    loop_body = body[start:start + 2500]
    assert "except Exception as job_error:" in loop_body
    assert "JOB_CORRELATION_ITEM_FAILED" in loop_body


def test_t_single_company_failure_never_aborts_the_whole_cycle() -> None:
    body = _function_body(_main_source(), "job_correlation_cycle")
    assert "except Exception as company_error:" in body
    assert "JOB_CORRELATION_COMPANY_FAILED" in body


def test_only_canonical_jobs_are_ever_considered_never_duplicates() -> None:
    body = _function_body(_main_source(), "job_correlation_cycle")
    assert 'item.get("dedup_status", "CANONICAL") != "DUPLICATE"' in body
