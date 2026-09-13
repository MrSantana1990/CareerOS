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


# Q: mesmo padrao de test_market_scan_wiring.py/test_watch_recheck_wiring.py -
# o CI do api roda os testes ANTES de aplicar migrations no Postgres real, e
# o automation-host nunca importa FastAPI/Playwright em CI, entao toda esta
# suite valida contrato de codigo via leitura de texto-fonte, nunca execucao
# contra um servidor real. A persistencia real e confirmada em producao
# (ver docs/continuous-improvement/PILOT-FORENSICS.md).

def test_opportunity_assembly_scheduler_is_registered_on_startup() -> None:
    source = _main_source()
    start = source.index("async def startup_scheduler(")
    body = source[start:start + 800]
    assert "asyncio.create_task(opportunity_assembly_scheduler())" in body


def test_opportunity_assembly_scheduler_never_lets_a_failure_propagate() -> None:
    body = _function_body(_main_source(), "opportunity_assembly_scheduler")
    assert "try:" in body
    assert "await opportunity_assembly_cycle()" in body
    assert 'event("OPPORTUNITY_ASSEMBLY_FAILED"' in body


def test_opportunity_assembly_scheduler_runs_frequently_not_once_a_day() -> None:
    # Diferente de market_scan/watch_recheck (1x/dia): Signals/Jobs chegam o
    # dia inteiro via ingest_job/market_scan, entao o loop roda a cada ciclo
    # curto (sleep), sem o gate now.hour==X usado pelos schedulers diarios.
    body = _function_body(_main_source(), "opportunity_assembly_scheduler")
    assert "now.hour ==" not in body
    assert "await asyncio.sleep(900)" in body


def test_opportunity_assembly_cycle_never_raises_when_admin_token_missing() -> None:
    body = _function_body(_main_source(), "opportunity_assembly_cycle")
    assert "if not CAREER_ADMIN_TOKEN:" in body
    assert 'event("OPPORTUNITY_ASSEMBLY_SKIPPED"' in body


def test_opportunity_assembly_cycle_emits_required_observability_events() -> None:
    body = _function_body(_main_source(), "opportunity_assembly_cycle")
    for required_event in ("OPPORTUNITY_ASSEMBLY_STARTED", "OPPORTUNITY_ASSEMBLY_COMPLETED",
                            "OPPORTUNITY_ASSEMBLY_FAILED"):
        assert f'"{required_event}"' in body, f"missing event {required_event}"


def test_opportunity_assembly_item_level_events_exist() -> None:
    source = _main_source()
    job_body = _function_body(source, "_assemble_job_opportunity")
    signal_body = _function_body(source, "_assemble_signal_opportunity")
    assert 'event("OPPORTUNITY_ASSEMBLY_JOB_EVALUATED"' in job_body
    assert 'event("OPPORTUNITY_ASSEMBLY_JOB_FAILED"' in job_body
    assert 'event("OPPORTUNITY_ASSEMBLY_SIGNAL_EVALUATED"' in signal_body
    assert 'event("OPPORTUNITY_ASSEMBLY_SIGNAL_FAILED"' in signal_body


def test_opportunity_assembly_cycle_tracks_required_metrics() -> None:
    body = _function_body(_main_source(), "opportunity_assembly_cycle")
    for metric in ("items_found", "items_processed", "opportunities_created", "channels_resolved",
                   "action_plans_created", "human_required", "failed", "duration_ms"):
        assert f'"{metric}"' in body, f"missing metric {metric}"


def test_opportunity_assembly_excludes_job_discovered_signals_to_avoid_duplicate_opportunity() -> None:
    # Secao 11: Job e a entidade canonica - todo Signal JOB_DISCOVERED ja tem
    # um Job correspondente que produz sua propria Opportunity pelo caminho
    # de Job. Reavaliar o Signal tambem duplicaria a Opportunity da mesma
    # vaga real, entao o Signal e explicitamente excluido da fila aqui.
    body = _function_body(_main_source(), "opportunity_assembly_cycle")
    assert 'item.get("type") != "JOB_DISCOVERED"' in body


def test_opportunity_assembly_checkpoint_is_derived_from_persisted_state_not_a_watermark() -> None:
    # Nenhum cursor/timestamp em memoria - "pendente" e literalmente "nao
    # existe Opportunity para este Job ainda" e "signal.status == NEW",
    # ambos consultados do Postgres a cada ciclo. Sobrevive a
    # restart/deploy/crash sem estado externo para perder.
    fetch_jobs_body = _sync_function_body(_main_source(), "_fetch_pending_jobs")
    assert "pending_evaluation=true" in fetch_jobs_body
    fetch_signals_body = _sync_function_body(_main_source(), "_fetch_new_signals")
    assert "status=NEW" in fetch_signals_body


def test_opportunity_assembly_job_item_failure_is_isolated() -> None:
    body = _function_body(_main_source(), "_assemble_job_opportunity")
    assert "except Exception as exc:" in body
    assert 'metrics["failed"] += 1' in body


def test_opportunity_assembly_signal_item_failure_is_isolated() -> None:
    body = _function_body(_main_source(), "_assemble_signal_opportunity")
    assert "except Exception as exc:" in body
    assert 'metrics["failed"] += 1' in body


def test_opportunity_assembly_cycle_loop_has_no_extra_try_around_each_item() -> None:
    # A isolacao de falha vive dentro de _assemble_job_opportunity/
    # _assemble_signal_opportunity (testado acima) - o loop do ciclo em si
    # so itera, nunca precisa (nem deve) engolir excecao duas vezes.
    body = _function_body(_main_source(), "opportunity_assembly_cycle")
    assert "for job in pending_jobs:" in body
    assert "await _assemble_job_opportunity(job, metrics)" in body
    assert "for signal in new_signals:" in body
    assert "await _assemble_signal_opportunity(signal, metrics)" in body


def test_opportunity_assembly_only_resolves_channel_and_plan_for_actionable_decisions() -> None:
    source = _main_source()
    assert '_ACTIONABLE_JOB_DECISIONS = {"PREPARE", "ACTIONABLE", "HUMAN_REQUIRED"}' in source
    body = _function_body(source, "_assemble_job_opportunity")
    assert "if opportunity_id and decision in _ACTIONABLE_JOB_DECISIONS:" in body
    assert "_discover_opportunity_channels" in body
    assert "_create_opportunity_action_plan" in body


def test_opportunity_assembly_never_calls_a_send_or_submit_function() -> None:
    source = _main_source()
    start = source.index("def _fetch_pending_jobs(")
    end = source.index("\n@app.post(\"/google/scan\")", start)
    body = source[start:end]
    for forbidden in ("send_application_email(", "send_security_code(", "create_application_email_draft(",
                      "create_calendar_event(", "submit"):
        assert forbidden not in body, f"opportunity assembly must never call {forbidden}"


def test_opportunity_assembly_action_plan_call_is_documented_as_dry_run() -> None:
    body = _sync_function_body(_main_source(), "_create_opportunity_action_plan")
    assert "DRY RUN" in body
    assert "AUTO_APPLY_ENABLED" in body


def test_gmail_health_classification_covers_the_four_required_states() -> None:
    body = _sync_function_body(_main_source(), "classify_gmail_health")
    for state in ('"AUTH_REQUIRED"', '"HEALTHY"', '"DEGRADED"', '"DOWN"'):
        assert state in body, f"missing state {state}"


def test_gmail_auth_failure_root_cause_never_fabricates_a_distinction_the_api_does_not_offer() -> None:
    body = _sync_function_body(_main_source(), "classify_gmail_auth_failure_root_cause")
    assert '"REFRESH_TOKEN_INVALID"' in body
    assert '"SCOPE_CHANGED"' in body
    assert '"CLIENT_CONFIGURATION"' in body
    assert '"OTHER"' in body


def test_gmail_reauth_intervention_fires_once_per_outage_via_dedup_key() -> None:
    body = _sync_function_body(_main_source(), "_create_gmail_reauth_intervention")
    assert '"reason": "AUTH_REQUIRED"' in body
    assert '"deduplication_key": "gmail:oauth_reauthorization_required"' in body


def test_gmail_reauth_intervention_only_called_when_health_classifies_as_auth_required() -> None:
    body = _function_body(_main_source(), "google_mail_scheduler")
    assert 'if classify_gmail_health(True, consecutive_failures, type(exc).__name__) == "AUTH_REQUIRED":' in body
    assert "_create_gmail_reauth_intervention" in body


def test_gmail_reauth_intervention_gate_uses_gte_not_exact_threshold_crossing() -> None:
    # Achado real de validacao em producao (Prompt 8): consecutive_failures
    # persiste em disco entre restarts do container. Um outage que ja
    # estava acima do threshold ANTES deste deploy (achado real: 165 falhas
    # consecutivas) nunca voltaria a bater no valor exato do threshold com
    # "==" - por isso o gate da intervencao usa ">=", dissociado do evento
    # GOOGLE_MAIL_AUTH_BROKEN (que continua disparando so uma vez, no
    # cruzamento exato, para nao inundar o log de eventos).
    body = _function_body(_main_source(), "google_mail_scheduler")
    assert "if consecutive_failures >= GOOGLE_HEALTH_ALERT_THRESHOLD:" in body
    auth_broken_start = body.index("if consecutive_failures == GOOGLE_HEALTH_ALERT_THRESHOLD:")
    auth_broken_block = body[auth_broken_start:auth_broken_start + 250]
    assert 'event("GOOGLE_MAIL_AUTH_BROKEN"' in auth_broken_block


def test_opportunity_assembly_cycle_updates_scheduler_health_on_success_and_failure() -> None:
    # Secao 9: last_started_at/last_completed_at/last_success_at/
    # last_failure_at/consecutive_failures/items_found/items_processed -
    # mesmo padrao ja usado por GOOGLE_HEALTH, reaproveitado aqui.
    body = _function_body(_main_source(), "opportunity_assembly_cycle")
    assert "save_json(OPPORTUNITY_ASSEMBLY_HEALTH," in body
    for field in ("consecutive_failures", "last_started_at", "last_completed_at",
                  "last_success_at", "last_failure_at", "items_found", "items_processed"):
        assert f'"{field}"' in body, f"missing health field {field}"


def test_traditional_pipeline_scheduler_is_untouched_by_opportunity_assembly() -> None:
    # Secao 12: as duas linhagens de pipeline coexistem - full_daily_pipeline
    # (job_id) continua intocado, Opportunity Assembly opera so sobre
    # opportunity_id. Nenhuma chamada nova aparece dentro de daily_scheduler.
    body = _function_body(_main_source(), "daily_scheduler")
    assert "opportunity_assembly" not in body
    assert "/api/v1/jobs/" not in body or "evaluate" not in body


def test_metrics_exposes_gmail_health_and_opportunity_assembly_health() -> None:
    source = _main_source()
    start = source.index('@app.get("/metrics")')
    end = source.index("\n@app.get", start + 1)
    body = source[start:end]
    assert '"gmail_health"' in body
    assert '"opportunity_assembly"' in body
