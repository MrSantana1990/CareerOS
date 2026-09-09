"""Tracking + Conversion Learning (Fase 2, Prompt 6).

Fecha o ciclo PERCEIVE -> REMEMBER -> REASON -> PLAN/ACTION -> OBSERVE ->
LEARN. Pure, sem I/O - o caller (career.py) fornece os dados ja
carregados do Postgres. Nao duplica application_events (ja e o modelo de
evento de conversao real, append-only via trigger de banco) nem
recruitment_communications (ja e o modelo de comunicacao) - so calcula
por cima deles.
"""

from __future__ import annotations

from .communications import correlate_message

# ---------------------------------------------------------------------------
# Secao 5 - CORRELATION ENGINE (4 niveis, sobre correlate_message existente)
# ---------------------------------------------------------------------------

CORRELATION_STATES = ("MATCHED_HIGH_CONFIDENCE", "MATCHED_MEDIUM_CONFIDENCE", "AMBIGUOUS", "UNMATCHED")


def classify_correlation(message: dict, applications: list[dict]) -> dict:
    """Reusa correlate_message (communications.py, ja existente e
    conservador) - so refina o resultado em 4 niveis de confianca em vez
    do MATCHED/REVIEW/UNMATCHED binario atual. So HIGH confidence pode
    atualizar o lifecycle automaticamente (Secao 5); MEDIUM/AMBIGUOUS
    exigem revisao humana. Nunca fabrica um link sem evidencia real -
    correlate_message ja e a unica fonte de evidencia aqui."""
    application_id, evidence = correlate_message(message, applications)
    if evidence == ["ambiguous"]:
        return {"status": "AMBIGUOUS", "application_id": None, "evidence": evidence}
    if not application_id:
        return {"status": "UNMATCHED", "application_id": None, "evidence": evidence}
    if "sender_domain" in evidence or len(evidence) >= 2:
        return {"status": "MATCHED_HIGH_CONFIDENCE", "application_id": application_id, "evidence": evidence}
    return {"status": "MATCHED_MEDIUM_CONFIDENCE", "application_id": application_id, "evidence": evidence}


# ---------------------------------------------------------------------------
# Secao 11 - CONVERSION FUNNEL
# ---------------------------------------------------------------------------

def _rate(numerator: int, denominator: int) -> float | None:
    """Denominador zero -> None, nunca 0% falso (Secao 11)."""
    if not denominator:
        return None
    return round(100 * numerator / denominator, 1)


def calculate_conversion_funnel(*, jobs_count: int, scored_count: int, opportunities_by_status: dict[str, int],
                                 applications_by_status: dict[str, int], events_by_type: dict[str, int],
                                 confirmed_without_submitted_event: int = 0) -> dict:
    """confirmed_without_submitted_event (Secao 7, Prompt 6.1): quantas
    applications CONFIRMED (ou alem) nao tem nenhum application_event real
    registrando a transicao de envio - caso real do Deutsche Bank (Cycle
    009/Prompt 2: status setado direto via backfill historico, antes do
    modelo de evento existir). Nunca fabrica um evento SUBMITTED ou
    timestamp falso para 'consertar' a aparencia do funil - so torna a
    lacuna EXPLICITA."""
    actionable = (opportunities_by_status.get("ACTIONABLE", 0) + opportunities_by_status.get("PREPARED", 0))
    prepared = applications_by_status.get("PREPARING", 0) + applications_by_status.get("READY", 0)
    submitted = applications_by_status.get("SENT", 0) + applications_by_status.get("SUBMITTING", 0)
    confirmed = applications_by_status.get("CONFIRMED", 0)
    responses = events_by_type.get("RESPONSE", 0)
    interviews = events_by_type.get("INTERVIEW", 0)
    offers = events_by_type.get("OFFER", 0)
    hires = events_by_type.get("HIRED", 0)
    counts = {"discovered": jobs_count, "qualified": scored_count, "actionable": actionable,
              "prepared": prepared, "submitted": submitted, "confirmed": confirmed,
              "responses": responses, "interviews": interviews, "offers": offers, "hires": hires}
    rates = {
        "qualification_rate": _rate(scored_count, jobs_count),
        "application_rate": _rate(submitted, scored_count),
        "confirmation_rate": _rate(confirmed, submitted),
        "response_rate": _rate(responses, confirmed),
        "interview_rate": _rate(interviews, confirmed),
        "offer_rate": _rate(offers, interviews),
        "hire_rate": _rate(hires, offers),
    }
    gaps = {}
    if confirmed_without_submitted_event:
        gaps["historical_event_gap"] = {
            "count": confirmed_without_submitted_event,
            "explanation": ("Application(s) confirmed/beyond sem application_event de envio "
                            "registrado - historico anterior ao modelo de evento atual, nao um "
                            "erro de transicao impossivel."),
        }
    return {"counts": counts, "rates": rates, "gaps": gaps}


# ---------------------------------------------------------------------------
# Secao 12 - DIMENSIONAL LEARNING
# ---------------------------------------------------------------------------

def aggregate_by_dimension(applications: list[dict], dimension: str) -> dict:
    """Dimensao ausente fica UNKNOWN, nunca descartada/inventada.

    Achado real (Prompt 6.1, Secao 5): cada bucket precisa da sua PROPRIA
    confidence, nunca a confidence do tamanho da amostra GLOBAL. Um
    dataset com 111 applications no total mas so 1 no canal EMAIL nao
    pode herdar SUFFICIENT_DATA so porque o total geral passa do limiar -
    cada dimensao/cohort e avaliada isoladamente (Secao 6: nenhuma
    recomendacao prematura tipo 'email converte melhor' com n=1)."""
    buckets: dict[str, dict] = {}
    for item in applications:
        key = str(item.get(dimension) or "UNKNOWN")
        bucket = buckets.setdefault(key, {"total": 0, "confirmed": 0})
        bucket["total"] += 1
        if item.get("status") == "CONFIRMED":
            bucket["confirmed"] += 1
    for bucket in buckets.values():
        bucket["sample_size"] = bucket["total"]
        bucket["confirmed_rate"] = _rate(bucket["confirmed"], bucket["total"])
        bucket["confidence"] = recommendation_confidence(bucket["total"])
    return buckets


# ---------------------------------------------------------------------------
# Secao 13 - NO AUTOMATIC WEIGHT LEARNING
# ---------------------------------------------------------------------------

MIN_SAMPLE_FOR_RECOMMENDATION = 20


def recommendation_confidence(sample_size: int) -> str:
    """Prompt 6 so coleta evidencia - nunca muda pesos/thresholds sozinho.
    Amostra pequena = INSUFFICIENT_DATA, nunca uma recomendacao fabricada."""
    return "SUFFICIENT_DATA" if sample_size >= MIN_SAMPLE_FOR_RECOMMENDATION else "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Secao 14 - CAREER GAP INTELLIGENCE
# ---------------------------------------------------------------------------

GAP_CATEGORIES = {
    "LANGUAGE": "CANDIDATE_GAP", "SKILL": "CANDIDATE_GAP", "EDUCATION": "CANDIDATE_GAP",
    "EXPERIENCE": "CANDIDATE_GAP", "SENIORITY": "CANDIDATE_GAP",
    "LOCATION": "MARKET_CONSTRAINT", "WORK_MODEL": "MARKET_CONSTRAINT", "SALARY": "MARKET_CONSTRAINT",
    "CAPTCHA": "AUTOMATION_FRICTION", "AUTH": "AUTOMATION_FRICTION", "BOT_GATE": "AUTOMATION_FRICTION",
    "TOOLING": "AUTOMATION_FRICTION",
    "STALE": "DISCOVERY_FRICTION", "UNVERIFIABLE": "DISCOVERY_FRICTION", "MISSING_CHANNEL": "DISCOVERY_FRICTION",
}

# So mapeia hard_blocks/unknowns REAIS ja produzidos pelo Opportunity Brain
# (Prompt 4) - nunca inventa uma categoria de gap sem uma origem real.
_HARD_BLOCK_TO_GAP = {
    "CORE_REQUIREMENT_MISSING": "SKILL", "LANGUAGE_GAP": "LANGUAGE",
    "RELOCATION_REQUIRED_IMPLICIT": "LOCATION", "MINIMUM_SALARY_BLOCK": "SALARY",
    "SUPPORT_N1_MINIMUM": "SALARY", "SPANISH_FLUENT_BLOCK": "LANGUAGE", "GUPY_BLOCK": "TOOLING",
}
_UNKNOWN_TO_GAP = {
    "language_level_unknown": "LANGUAGE", "work_model_or_location_unknown": "WORK_MODEL",
    "hybrid_commute_out_of_region": "LOCATION",
}
_HIGH_FIT_THRESHOLD = 75


def aggregate_gap_intelligence(opportunities: list[dict]) -> dict:
    aggregated: dict[str, dict] = {}

    def _bucket(gap: str) -> dict:
        return aggregated.setdefault(gap, {"category": GAP_CATEGORIES[gap], "count": 0,
                                            "affected_opportunities": [], "high_fit_affected": 0})

    for opportunity in opportunities:
        brain = (opportunity.get("evidence") or {}).get("brain") or {}
        fit_score = opportunity.get("fit_score")
        is_high_fit = fit_score is not None and fit_score >= _HIGH_FIT_THRESHOLD
        reasons = list(brain.get("hard_blocks") or [])
        gaps_hit = {_HARD_BLOCK_TO_GAP[reason] for reason in reasons if reason in _HARD_BLOCK_TO_GAP}
        gaps_hit |= {_UNKNOWN_TO_GAP[unknown] for unknown in (brain.get("unknowns") or [])
                     if unknown in _UNKNOWN_TO_GAP}
        for gap in gaps_hit:
            entry = _bucket(gap)
            entry["count"] += 1
            entry["affected_opportunities"].append(opportunity["id"])
            if is_high_fit:
                entry["high_fit_affected"] += 1
    return aggregated


# ---------------------------------------------------------------------------
# Secao 25 - HUMAN ACTION QUEUE QUALITY (agrupamento por causa raiz)
# ---------------------------------------------------------------------------

def group_interventions_by_root_cause(interventions: list[dict]) -> list[dict]:
    """Agrupa intervencoes pendentes pela MESMA causa raiz (reason +
    conjunto de human_requirements ja persistido em evidence.policy_result)
    - o usuario resolve uma vez por grupo, nao uma vez por Opportunity
    (Secao 25). Nunca apaga historico: cada intervencao original continua
    existindo e rastreavel via opportunity_id/id, so a apresentacao agrupa."""
    groups: dict[tuple, dict] = {}
    for item in interventions:
        requirements = tuple(sorted((item.get("evidence") or {}).get("policy_result", {})
                                     .get("human_requirements") or []))
        key = (item.get("reason"), requirements)
        group = groups.setdefault(key, {"reason": item.get("reason"), "human_requirements": list(requirements),
                                         "count": 0, "intervention_ids": [], "opportunity_ids": []})
        group["count"] += 1
        group["intervention_ids"].append(item["id"])
        if item.get("opportunity_id"):
            group["opportunity_ids"].append(item["opportunity_id"])
    return sorted(groups.values(), key=lambda group: -group["count"])
