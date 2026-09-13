"""Fase 2, Prompt 11 - wiring/observabilidade da Company Intelligence
(main.py). Complementa os testes puros em test_company_intelligence.py."""

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


def test_company_intelligence_scheduler_is_registered_on_startup() -> None:
    source = _main_source()
    start = source.index("async def startup_scheduler(")
    body = source[start:start + 900]
    assert "asyncio.create_task(company_intelligence_scheduler())" in body


def test_company_intelligence_scheduler_never_lets_a_failure_propagate() -> None:
    body = _function_body(_main_source(), "company_intelligence_scheduler")
    assert "try:" in body
    assert "await company_intelligence_cycle()" in body
    assert 'event("COMPANY_INTELLIGENCE_FAILED"' in body


def test_company_intelligence_scheduler_runs_once_per_day_at_a_distinct_hour() -> None:
    # Secao 20: 5h - antes de market_scan (6h)/watch_recheck (7h)/daily (8h).
    body = _function_body(_main_source(), "company_intelligence_scheduler")
    assert "now.hour == 5" in body
    assert "slot != last_slot" in body


def test_company_intelligence_cycle_never_raises_when_admin_token_missing() -> None:
    body = _function_body(_main_source(), "company_intelligence_cycle")
    assert "if not CAREER_ADMIN_TOKEN:" in body
    assert 'event("COMPANY_INTELLIGENCE_SKIPPED"' in body


def test_company_intelligence_cycle_emits_required_observability_events() -> None:
    body = _function_body(_main_source(), "company_intelligence_cycle")
    for required_event in ("COMPANY_INTELLIGENCE_STARTED", "COMPANY_DOMAIN_DISCOVERED",
                            "CAREERS_URL_DISCOVERED", "ATS_DETECTED", "COMPANY_INTELLIGENCE_COMPLETED"):
        assert f'"{required_event}"' in body, f"missing event {required_event}"


# O: second run idempotent (cooldown gate via companies.last_checked_at) --------------------------------

def test_o_needs_check_returns_false_when_domain_and_careers_already_resolved() -> None:
    body = _sync_function_body(_main_source(), "_needs_company_intelligence_check")
    assert 'if company.get("domain") and company.get("careers_url"):' in body
    assert "return False" in body


def test_o_cooldown_uses_the_real_last_checked_at_column() -> None:
    body = _sync_function_body(_main_source(), "_needs_company_intelligence_check")
    assert "COMPANY_INTELLIGENCE_COOLDOWN_DAYS" in body
    assert 'company.get("last_checked_at")' in body


# P: bounded concurrency / batch / timeout -----------------------------------------------------------------

def test_p_cycle_is_bounded_by_a_fixed_batch_size() -> None:
    body = _function_body(_main_source(), "company_intelligence_cycle")
    assert "COMPANY_INTELLIGENCE_BATCH_SIZE" in body
    assert "candidates[:COMPANY_INTELLIGENCE_BATCH_SIZE]" in body


def test_p_public_fetch_uses_a_bounded_timeout() -> None:
    body = _sync_function_body(_main_source(), "_fetch_public_page")
    assert "COMPANY_INTELLIGENCE_PROBE_TIMEOUT" in body


def test_p_public_fetch_only_ever_follows_https() -> None:
    body = _sync_function_body(_main_source(), "_fetch_public_page")
    assert 'urlsplit(url).scheme != "https"' in body


def test_p_public_fetch_never_propagates_an_exception() -> None:
    body = _sync_function_body(_main_source(), "_fetch_public_page")
    assert "except Exception:" in body


def test_p_single_company_failure_never_aborts_the_batch() -> None:
    body = _function_body(_main_source(), "company_intelligence_cycle")
    start = body.index("for company in candidates:")
    loop_body = body[start:start + 3500]
    assert "except Exception as item_error:" in loop_body
    assert "COMPANY_INTELLIGENCE_ITEM_FAILED" in loop_body


# Q: no external action -----------------------------------------------------------------------------------

def test_q_company_intelligence_never_calls_a_send_or_submit_function() -> None:
    source = _main_source()
    for name in ("_fetch_public_page", "_resolve_company_domain", "_discover_careers_url",
                 "company_intelligence_cycle"):
        body = _sync_function_body(source, name) if "def " + name + "(" in source and "async def " + name not in source \
            else _function_body(source, name)
        for forbidden in ("send_application_email(", "send_security_code(", "create_calendar_event("):
            assert forbidden not in body, f"{name} must never call {forbidden}"


def test_q_public_fetch_is_read_only_get_only() -> None:
    body = _sync_function_body(_main_source(), "_fetch_public_page")
    assert "method=" not in body  # Request() sem method= -> GET (default urllib)


# R: Score/Brain re-evaluation after enrichment -------------------------------------------------------------

def test_r_cycle_reevaluates_score_and_brain_only_after_real_enrichment() -> None:
    body = _function_body(_main_source(), "company_intelligence_cycle")
    assert 'if update_payload.get("domain") or update_payload.get("careers_url"):' in body
    assert "_calculate_job_score" in body
    assert "_evaluate_job_opportunity" in body


def test_r_reevaluation_never_creates_a_new_opportunity_route() -> None:
    # Reusa /jobs/{id}/evaluate (upsert idempotente ja existente, Prompt 4) -
    # nunca POST /opportunities (criacao direta).
    body = _function_body(_main_source(), "company_intelligence_cycle")
    assert '"/api/v1/opportunities"' not in body


# S: Channel Resolution integration --------------------------------------------------------------------------

def test_s_cycle_refreshes_channels_and_action_plan_for_actionable_decisions() -> None:
    body = _function_body(_main_source(), "company_intelligence_cycle")
    assert "_discover_opportunity_channels" in body
    assert "_create_opportunity_action_plan" in body
    assert 'result.get("decision") in _ACTIONABLE_JOB_DECISIONS' in body


# Company domain / careers discovery real evidence guards ------------------------------------------------------

def test_domain_resolution_falls_back_to_a_real_job_email_when_company_has_none() -> None:
    # Caso real Zeleno Meds: a Company nao tem official_recruiting_email,
    # mas um Job real dela tem application_instructions.recruiting_email.
    body = _function_body(_main_source(), "_resolve_company_domain")
    assert "extract_domain_candidate_from_email(company.get(\"official_recruiting_email\"))" in body
    assert "_fetch_company_jobs" in body
    assert "application_instructions" in body


def test_domain_only_persisted_after_a_real_https_verification_probe() -> None:
    body = _function_body(_main_source(), "_resolve_company_domain")
    assert "classify_domain_probe(" in body
    assert 'if classification != "VERIFIED_OFFICIAL_DOMAIN":' in body


def test_careers_discovery_never_persists_without_real_evidence() -> None:
    body = _function_body(_main_source(), "_discover_careers_url")
    assert "classify_careers_probe(" in body
    assert "detect_ats(" in body
