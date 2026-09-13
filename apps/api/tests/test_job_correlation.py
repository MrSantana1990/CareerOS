"""Fase 2, Prompt 12 - Specific Job Correlation & Official Job Enrichment
(Core side). Testes M/N/S da Secao 20 - o resto (correlacao/status/busca
textual) vive em apps/automation-host/tests/test_company_intelligence.py,
onde o correlator generico (sem I/O) realmente mora."""

from pathlib import Path

from src.opportunity_brain import evaluate_location_work_model
from src.quality import resolve_structured_work_model

_CONTAMINATED_WORK_MODEL = {
    "value": {"work_model": "HYBRID"}, "confidence": 85,
    "evidence_snippet": "Exibir tudo\n\nAnalista de dados Presencialou Remotoou Hibrido",
}
_OFFICIAL_WORK_MODEL = {
    "value": {"work_model": "REMOTE"}, "confidence": 90,
    "evidence_snippet": "Analista de Dados Pleno - Sao Paulo. Candidate-se agora, vaga aberta! Modelo 100% remoto.",
}


# M: official field overrides contaminated discovery field ------------------------------------------------

def test_m_official_work_model_overrides_contaminated_linkedin_field():
    structured = {"work_model": _CONTAMINATED_WORK_MODEL, "work_model_official": _OFFICIAL_WORK_MODEL}
    assert resolve_structured_work_model(structured) == "REMOTE"


def test_m_official_work_model_wins_even_over_a_trustworthy_regular_field():
    clean_field = {"value": {"work_model": "ONSITE"}, "confidence": 85, "evidence_snippet": "Vaga presencial em SP"}
    structured = {"work_model": clean_field, "work_model_official": _OFFICIAL_WORK_MODEL}
    assert resolve_structured_work_model(structured) == "REMOTE"


def test_m_falls_back_to_regular_field_when_no_official_evidence_exists():
    clean_field = {"value": {"work_model": "HYBRID"}, "confidence": 85, "evidence_snippet": "Vaga hibrida em SP"}
    structured = {"work_model": clean_field}
    assert resolve_structured_work_model(structured) == "HYBRID"


def test_m_untrustworthy_official_field_never_used_either():
    contaminated_official = {"value": {"work_model": "REMOTE"}, "confidence": 90,
                              "evidence_snippet": "candidatura simplificada - vagas similares"}
    clean_field = {"value": {"work_model": "ONSITE"}, "confidence": 85, "evidence_snippet": "Vaga presencial"}
    structured = {"work_model": clean_field, "work_model_official": contaminated_official}
    assert resolve_structured_work_model(structured) == "ONSITE"


def test_m_brain_location_eval_reuses_the_same_official_priority():
    structured = {"work_model": _CONTAMINATED_WORK_MODEL, "work_model_official": _OFFICIAL_WORK_MODEL}
    result = evaluate_location_work_model(structured, job={}, profile={"work_models": ["REMOTE"]})
    assert result["work_model"] == "REMOTE"
    assert result["status"] == "COMPATIBLE"


# N: requirements/official enrichment never invents anything (route wiring) ----------------------------------

def _career_source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "career.py").read_text(encoding="utf-8")


def _route_body(source: str, path: str) -> str:
    start = source.index(f'@router.post("{path}")')
    end = source.index("\n@router.", start + 1)
    return source[start:end]


def test_n_enrich_official_route_only_merges_additively_never_deletes():
    body = _route_body(_career_source(), "/jobs/{job_id}/enrich-official")
    assert "COALESCE(structured_extraction, '{}'::jsonb) ||" in body
    assert "DELETE" not in body


def test_n_enrich_official_route_never_calls_a_send_or_submit_function():
    body = _route_body(_career_source(), "/jobs/{job_id}/enrich-official")
    for forbidden in ("send_application_email(", "urlopen(", "requests.post("):
        assert forbidden not in body


def test_n_enrich_official_route_404s_for_a_job_outside_the_organization():
    body = _route_body(_career_source(), "/jobs/{job_id}/enrich-official")
    assert "raise HTTPException(status_code=404" in body


# S: Brain re-evaluation reuses the same evaluate_job_opportunity, never duplicated ----------------------------

def test_s_official_enrichment_never_introduces_a_second_decision_engine():
    # A rota so escreve estrutura - a reavaliacao usa /jobs/{id}/score e
    # /jobs/{id}/evaluate ja existentes (chamados pelo automation-host,
    # Secao 15) - nunca um motor de decisao paralelo aqui.
    body = _route_body(_career_source(), "/jobs/{job_id}/enrich-official")
    assert "score_job(" not in body
    assert "evaluate_job_opportunity(" not in body
