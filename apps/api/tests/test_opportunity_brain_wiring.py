from pathlib import Path


def _career_source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "career.py").read_text(encoding="utf-8")


def _route_body(source: str, path: str) -> str:
    start = source.index(f'@router.post("{path}")')
    end = source.index("\n@router.", start + 1)
    return source[start:end]


# Q: Opportunity persistence - validado aqui como contrato de codigo (o CI
# do api roda os testes ANTES de aplicar migrations no Postgres real, entao
# nenhum teste desta suite pode depender de uma sessao de banco de fato -
# mesmo padrao ja usado em test_market_scan_wiring.py no Prompt 3). A
# persistencia real e confirmada em producao (Secao 22/38 do relatorio).

def test_evaluate_job_route_exists_and_handles_already_terminal():
    body = _route_body(_career_source(), "/jobs/{job_id}/evaluate")
    assert "evaluate_job_opportunity(" in body
    assert "already_terminal=already_terminal" in body
    assert "_TERMINAL_OPPORTUNITY_STATUSES" in body


def test_evaluate_job_route_is_idempotent_via_dedup_fingerprint():
    body = _route_body(_career_source(), "/jobs/{job_id}/evaluate")
    assert "opportunity_fingerprint(" in body
    assert "ON CONFLICT (organization_id, dedup_fingerprint) DO UPDATE" in body


def test_evaluate_job_route_never_reruns_score_from_stale_job_scores_reasons():
    # Score V2 (quality.score_job) e reusado, nao recriado - decisao A da
    # Secao 16 (Fit != segundo score redundante).
    body = _route_body(_career_source(), "/jobs/{job_id}/evaluate")
    assert "score_job(dict(job), profile_data, codes)" in body


def test_evaluate_signal_route_never_creates_opportunity_for_drop():
    body = _route_body(_career_source(), "/signals/{signal_id}/evaluate")
    assert 'if decision.decision != "WATCH":' in body
    assert "return {**decision.as_dict(), \"opportunity_id\": None}" in body


def test_evaluate_signal_route_creates_watch_alongside_opportunity():
    body = _route_body(_career_source(), "/signals/{signal_id}/evaluate")
    assert "INSERT INTO watches" in body
    assert "opportunity_type_for_signal(signal[\"type\"])" in body


def test_evaluate_signal_route_marks_signal_promoted_on_watch():
    body = _route_body(_career_source(), "/signals/{signal_id}/evaluate")
    assert "UPDATE signals SET status='PROMOTED'" in body


def test_recheck_watch_route_extends_next_check_at():
    body = _route_body(_career_source(), "/watches/{watch_id}/recheck")
    assert "evaluate_watch_recheck(" in body
    assert "next_check_at=now() + make_interval(days => :days)" in body


def test_recheck_watch_route_only_moves_opportunity_to_recheck_status_when_material():
    body = _route_body(_career_source(), "/watches/{watch_id}/recheck")
    assert 'if decision.decision == "RECHECK" and watch["opportunity_id"]:' in body


def test_recheck_watch_route_stamps_brain_columns_on_the_opportunity_too():
    # Achado real na validacao em producao do Prompt 4: o RECHECK atualizava
    # status/evidence da Opportunity mas deixava evaluated_at/brain_confidence/
    # brain_version nulos, inconsistente com /jobs/evaluate e /signals/evaluate.
    body = _route_body(_career_source(), "/watches/{watch_id}/recheck")
    recheck_start = body.index("if decision.decision == \"RECHECK\"")
    recheck_block = body[recheck_start:]
    assert "brain_confidence=:confidence" in recheck_block
    assert "evaluated_at=now()" in recheck_block
    assert "brain_version=:brain_version" in recheck_block


# JOB_DISCOVERED gap (Secao 22): resolvido cirurgicamente dentro de
# ingest_job (mesma transacao, sem tocar o outbox do automation-host) - so
# para eventos NOVOS, nunca em massa para o historico, e nunca duplicando
# descricao/requisitos (provenance pura).

def test_ingest_job_creates_job_discovered_signal_only_when_newly_created():
    source = _career_source()
    start = source.index("async def ingest_job(")
    end = source.index("\n@router.", start + 1)
    body = source[start:end]
    assert "if created:" in body
    assert "'JOB_DISCOVERED'" in body
    assert "signal_fingerprint(" in body


def test_ingest_job_job_discovered_signal_never_duplicates_description():
    source = _career_source()
    start = source.index("async def ingest_job(")
    end = source.index("\n@router.", start + 1)
    body = source[start:end]
    signal_block_start = body.index("if created:")
    signal_block = body[signal_block_start:]
    assert "description" not in signal_block
    assert "required_skills" not in signal_block


# Fase 2, Prompt 8 - Opportunity Assembly: estas rotas passam a ser chamadas
# de forma autonoma pelo automation-host (apps/automation-host/src/main.py,
# opportunity_assembly_scheduler). Os testes abaixo validam so o contrato de
# codigo que o novo scheduler depende - o checkpoint (pending_evaluation) e a
# provenance (triggered_by) - nunca reimplementam o scheduler em si (ver
# apps/automation-host/tests/test_opportunity_assembly_wiring.py).

def test_list_jobs_pending_evaluation_filter_is_derived_from_persisted_state():
    source = _career_source()
    start = source.index('@router.get("/jobs")')
    end = source.index("\n@router.", start + 1)
    body = source[start:end]
    assert "pending_evaluation: bool = False" in body
    assert "NOT EXISTS (SELECT 1 FROM opportunities o WHERE o.job_id=j.id)" in body
    assert "j.company_id IS NOT NULL" in body


def test_list_jobs_default_behavior_is_unchanged_when_pending_evaluation_is_false():
    # Nenhum caller existente (dashboard web, etc.) pode ser afetado por este
    # filtro aditivo - ordenacao padrao continua DESC e a clausula extra so
    # entra quando pending_evaluation=True e explicitamente pedido.
    source = _career_source()
    start = source.index('@router.get("/jobs")')
    end = source.index("\n@router.", start + 1)
    body = source[start:end]
    assert 'order_by = "j.discovered_at DESC"' in body
    assert 'extra_where = ""' in body


def test_evaluate_job_route_accepts_triggered_by_for_autonomy_provenance():
    body = _route_body(_career_source(), "/jobs/{job_id}/evaluate")
    assert "triggered_by: str | None = None" in body
    assert '"orchestration"' in body


def test_evaluate_signal_route_accepts_triggered_by_for_autonomy_provenance():
    body = _route_body(_career_source(), "/signals/{signal_id}/evaluate")
    assert "triggered_by: str | None = None" in body
    assert '"orchestration"' in body


def test_evaluate_job_triggered_by_is_optional_and_never_required():
    # A rota continua utilizavel exatamente como antes (Prompts 4-6) por
    # qualquer caller que nao envie triggered_by - o campo so enriquece a
    # evidence quando presente, nunca bloqueia a chamada quando ausente.
    body = _route_body(_career_source(), "/jobs/{job_id}/evaluate")
    assert "if triggered_by:" in body
