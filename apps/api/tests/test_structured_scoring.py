"""Fase 2, Prompt 10 - Score V2 Structured Intelligence. Testes A-T da
Secao 25. Caso real usado como benchmark: Zeleno Meds (a vaga real com
e-mail explicito, channel VERIFIED_AVAILABLE, mas Brain final HUMAN_REQUIRED
por MATERIAL_UNKNOWN generico - achado real do Prompt 9)."""

from src.opportunity_brain import evaluate_job_opportunity, evaluate_requirements, find_skill_evidence
from src.quality import (
    SKILL_FAMILIES, extract_seniority_from_title, is_structured_field_trustworthy,
    resolve_required_technology_tokens, resolve_structured_language_requirements,
    resolve_structured_salary, resolve_structured_work_model, score_job,
)

PROFILE = {"city": "Sao Paulo", "state": "SP", "work_models": ["REMOTE", "HYBRID"],
           "target_roles": ["Analista de Dados"], "language_levels": {"english": "basic"}}
SKILLS = [{"name": "SQL Server", "verified": True, "evidence_count": 0},
          {"name": "Docker", "verified": False, "evidence_count": 1}]


def _score(total=80, recommendation="APPLY_HIGH", strengths=None, risks=None, blocking_rules=None):
    from src.quality import ScoreResult
    return ScoreResult(total=total, recommendation=recommendation, dimensions={"technology": 30},
                        strengths=strengths or [], gaps=[], risks=risks or [], blocking_rules=blocking_rules or [])


# A: mandatory exact skill match ------------------------------------------------------------------

def test_a_mandatory_exact_skill_match_no_block():
    structured = {"mandatory_requirements": {"value": ["Experience with SQL Server required."],
                                              "source_url": "https://x.com"}}
    result = evaluate_requirements(structured, SKILLS)
    assert result["core_missing"] == []


def test_a_score_job_recognizes_required_skill_from_structured_extraction_when_flat_is_empty():
    job = {"title": "Analista", "structured_extraction": {
        "mandatory_requirements": {"value": ["Experiencia com SQL Server e obrigatoria."]}}}
    profile = {"verified_skills": ["SQL Server"], "target_roles": []}
    result = score_job(job, profile)
    assert result.dimensions["technology"] == 30
    assert "sql server" in result.strengths


# B: preferred missing does not block --------------------------------------------------------------

def test_b_preferred_missing_never_blocks():
    structured = {"preferred_requirements": {"value": ["Kubernetes is a differential."],
                                              "source_url": "https://x.com"}}
    result = evaluate_requirements(structured, SKILLS)
    assert result["core_missing"] == []
    assert result["preferred_gaps"] == ["Kubernetes is a differential."]


# C: contextual text does not become mandatory -------------------------------------------------------

def test_c_contextual_office_attendance_never_becomes_mandatory():
    structured = {"mandatory_requirements": {
        "value": ["your presence in the city offices will be mandatory, according to the current frequency policy."],
        "source_url": "https://x.com"}}
    result = evaluate_requirements(structured, SKILLS)
    assert result["core_missing"] == []
    assert len(result["contextual_requirements"]) == 1


# D: transferable DB match -----------------------------------------------------------------------------

def test_d_postgresql_requirement_transfers_from_sql_server():
    evidence = find_skill_evidence("Solid experience with PostgreSQL", SKILLS)
    assert evidence["match_type"] == "transferable"
    assert evidence["skill"] == "SQL Server"


# E: Docker does not satisfy Kubernetes ----------------------------------------------------------------

def test_e_docker_never_satisfies_kubernetes_requirement():
    evidence = find_skill_evidence("Kubernetes experience required", SKILLS)
    assert evidence is None
    assert SKILL_FAMILIES["kubernetes"] == set()


# F: AWS does not equal Azure exact ----------------------------------------------------------------------

def test_f_azure_requirement_is_transferable_from_aws_not_exact():
    skills = [{"name": "AWS", "verified": True, "evidence_count": 0}]
    evidence = find_skill_evidence("Azure experience required", skills)
    assert evidence["match_type"] == "transferable"
    assert evidence["requirement_technology"] == "azure"


def test_f_aws_and_azure_are_never_the_same_recognized_token_pair_incorrectly():
    # nao existe fusão - cada um e uma chave distinta, so ligados por
    # transferable edge, nunca tratados como identicos.
    assert "azure" != "aws"
    assert "azure" in SKILL_FAMILIES["aws"]


# G: explicit advanced English vs real candidate level -------------------------------------------------

def test_g_explicit_advanced_english_vs_basic_candidate_level_blocks():
    structured = {"language_requirements": {"value": {"language": "English", "level": "advanced"}}}
    profile = {**PROFILE, "language_levels": {"english": "basic"}}
    decision = evaluate_job_opportunity(job={}, profile=profile, candidate_skills=SKILLS,
                                         score_result=_score(), structured_extraction=structured)
    assert decision.decision == "BLOCK"
    assert "LANGUAGE_GAP" in decision.hard_blocks


# H: English job page without explicit requirement ------------------------------------------------------

def test_h_english_page_without_explicit_requirement_never_infers_language_risk():
    # structured_fields.py (automation-host) ja nunca gera language_requirements
    # so pela pagina estar em ingles - aqui confirmamos que score_job nunca
    # promove isso a partir do texto livre (sem language_requirements
    # explicito, nem flat nem estruturado).
    job = {"title": "Data Analyst", "description": "We are looking for a data analyst in English.",
           "structured_extraction": {}}
    result = score_job(job, {"verified_skills": []})
    assert result.risks == []


# I: salary below floor ------------------------------------------------------------------------------------

def test_i_structured_salary_below_floor_hard_blocks():
    job = {"title": "Analista", "structured_extraction": {
        "salary": {"value": {"salary_min": 2000}, "confidence": 85, "evidence_snippet": "R$ 2.000,00 mensais"}}}
    result = score_job(job, {"verified_skills": []})
    assert "MINIMUM_SALARY_BLOCK" in result.blocking_rules


# J: salary unknown --------------------------------------------------------------------------------------

def test_j_missing_salary_everywhere_never_blocks():
    job = {"title": "Analista", "structured_extraction": {}}
    result = score_job(job, {"verified_skills": []})
    assert "MINIMUM_SALARY_BLOCK" not in result.blocking_rules
    assert result.dimensions["compensation"] == 10


def test_j_untrustworthy_structured_salary_is_never_used():
    job = {"title": "Analista", "structured_extraction": {
        "salary": {"value": {"salary_min": 2000}, "confidence": 85,
                   "evidence_snippet": "candidatura simplificada - vagas similares"}}}
    assert resolve_structured_salary(job["structured_extraction"]) is None


# K: remote/hybrid/onsite classification --------------------------------------------------------------------

def test_k_remote_compatible_with_remote_preference():
    structured = {"work_model": {"value": {"work_model": "REMOTE"}, "confidence": 90,
                                  "evidence_snippet": "Trabalho 100% remoto"}}
    from src.opportunity_brain import evaluate_location_work_model
    result = evaluate_location_work_model(structured, {}, PROFILE)
    assert result["status"] == "COMPATIBLE"


def test_k_hybrid_same_region_compatible():
    structured = {
        "work_model": {"value": {"work_model": "HYBRID"}, "confidence": 85, "evidence_snippet": "modelo hibrido"},
        "location": {"value": {"region": "Sao Paulo"}, "confidence": 80, "evidence_snippet": "vaga em Sao Paulo"},
    }
    from src.opportunity_brain import evaluate_location_work_model
    result = evaluate_location_work_model(structured, {}, PROFILE)
    assert result["status"] == "COMPATIBLE"


def test_k_onsite_different_region_relocation_block():
    structured = {
        "work_model": {"value": {"work_model": "ONSITE"}, "confidence": 90, "evidence_snippet": "presencial"},
        "location": {"value": {"region": "Recife"}, "confidence": 80, "evidence_snippet": "vaga em Recife"},
    }
    from src.opportunity_brain import evaluate_location_work_model
    result = evaluate_location_work_model(structured, {}, PROFILE)
    assert result["status"] == "RELOCATION_BLOCK"


# Real regression: LinkedIn sidebar UI noise (achado real Zeleno Meds) -----------------------------------

def test_k_linkedin_sidebar_contaminated_work_model_is_never_trusted():
    # Achado real de producao: work_model="HYBRID" extraido de
    # "Exibir tudo\n\nAnalista de dados Presencialou Remotoou Hibrido" -
    # texto de FILTRO DE BUSCA do LinkedIn, nao da vaga real.
    field = {"value": {"work_model": "HYBRID"}, "confidence": 85,
             "evidence_snippet": "centes\nExibir tudo\n\nAnalista de dados Presencialou Remotoou Híbrido\n\nVagas"}
    assert is_structured_field_trustworthy(field) is False
    assert resolve_structured_work_model({"work_model": field}) is None


def test_k_linkedin_sidebar_contaminated_location_is_never_trusted():
    # Achado real: location="Campinas" extraido de uma vaga de OUTRA
    # empresa ("Fitcard") listada na barra lateral "vagas similares".
    field = {"value": {"region": "Campinas"}, "confidence": 75,
             "evidence_snippet": "Candidatura simplificada\n\nAnalista de BI II \n\nFitcard\n\nCampinas e Região"}
    assert is_structured_field_trustworthy(field) is False


def test_k_clean_evidence_snippet_is_trusted():
    field = {"value": {"work_model": "REMOTE"}, "confidence": 90, "evidence_snippet": "Trabalho remoto full-time"}
    assert is_structured_field_trustworthy(field) is True


# L: education unknown vs mismatch --------------------------------------------------------------------------

def test_l_education_requirement_without_evidence_is_material_unknown_not_block():
    structured = {"mandatory_requirements": {
        "value": ["Ensino superior completo em Ciencia da Computacao ou areas afins."],
        "source_url": "https://x.com"}}
    result = evaluate_requirements(structured, SKILLS)
    assert result["core_missing"] == []
    assert any(item.startswith("MISSING_EDUCATION_EVIDENCE") for item in result["uncertain_requirements"])


# M: experience unknown vs mismatch -----------------------------------------------------------------------

def test_m_generic_years_of_experience_without_technology_is_material_unknown_not_block():
    structured = {"mandatory_requirements": {"value": ["Minimo de 5 anos de experiencia na area."],
                                              "source_url": "https://x.com"}}
    result = evaluate_requirements(structured, SKILLS)
    assert result["core_missing"] == []
    assert any(item.startswith("MISSING_EXPERIENCE_EVIDENCE") for item in result["uncertain_requirements"])


def test_m_named_technology_with_years_of_experience_still_blocks_when_missing():
    # Teste A do Prompt 10 (regressao real): a mesma sentenca que cita uma
    # tecnologia REAL faltante continua BLOCK, mesmo mencionando anos de
    # experiencia - o requisito concreto de tecnologia nao pode virar
    # MATERIAL_UNKNOWN so porque tambem tem uma clausula de anos.
    structured = {"mandatory_requirements": {
        "value": ["You must have production Kubernetes experience with 5 years of experience."],
        "source_url": "https://x.com"}}
    result = evaluate_requirements(structured, SKILLS)
    assert len(result["core_missing"]) == 1
    assert result["core_missing"][0]["decision"] == "CORE_REQUIREMENT_MISSING"


# N: material_unknown reason specificity --------------------------------------------------------------------

def test_n_bare_section_header_is_unknown_requirement_classification_not_raw_text():
    # Achado real Zeleno Meds: mandatory_requirements.value == ["Requisitos"]
    # (so o cabecalho da secao, sem conteudo real - a extracao capturou o
    # marcador, nao o texto que vinha depois).
    structured = {"mandatory_requirements": {"value": ["Requisitos"], "source_url": "https://x.com"}}
    result = evaluate_requirements(structured, SKILLS)
    assert result["core_missing"] == []
    assert result["uncertain_requirements"] == ["UNKNOWN_REQUIREMENT_CLASSIFICATION:Requisitos"]


def test_n_material_unknown_reasons_are_never_bare_generic_strings():
    structured = {"mandatory_requirements": {"value": ["Requisitos"], "source_url": "https://x.com"}}
    decision = evaluate_job_opportunity(job={}, profile=PROFILE, candidate_skills=SKILLS,
                                         score_result=_score(), structured_extraction=structured)
    assert decision.eligibility == "MATERIAL_UNKNOWN"
    assert all(reason != "MATERIAL_UNKNOWN" for reason in decision.unknowns)
    assert any("UNKNOWN_REQUIREMENT_CLASSIFICATION" in reason for reason in decision.unknowns)


# O: Zeleno regression (real production data) -----------------------------------------------------------------

_ZELENO_STRUCTURED = {
    "location": {"value": {"region": "Campinas"}, "confidence": 75,
                 "evidence_snippet": "Candidatura simplificada\n\nAnalista de BI II \n\nFitcard\n\nCampinas e Região"},
    "work_model": {"value": {"work_model": "HYBRID"}, "confidence": 85,
                   "evidence_snippet": "Exibir tudo\n\nAnalista de dados Presencialou Remotoou Híbrido\n\nVagas"},
    "mandatory_requirements": {"value": ["Requisitos"], "confidence": 70, "evidence_snippet": "Requisitos"},
}
_ZELENO_PROFILE = {"city": "Sao Paulo", "state": "SP", "work_models": ["REMOTE", "HYBRID"],
                    "target_roles": ["Analista de Sustentação", "Analista de Suporte N3", "Analista de Sistemas",
                                     "DBA SQL Server", "Engenheiro de Dados"],
                    "language_levels": {"english": "Technical reading and writing"}}
_ZELENO_SKILLS = [{"name": "SQL Server", "verified": False, "evidence_count": 1},
                   {"name": "Oracle", "verified": False, "evidence_count": 1},
                   {"name": "PostgreSQL", "verified": False, "evidence_count": 1},
                   {"name": "Power BI", "verified": False, "evidence_count": 1}]


def test_o_zeleno_meds_never_forces_actionable():
    job = {"title": "Analista de Dados / DBA / Engenheiro(a) de Dados - Pleno", "location": "São Paulo - SP",
           "structured_extraction": _ZELENO_STRUCTURED}
    profile_data = {**_ZELENO_PROFILE, "verified_skills": [],
                     "evidence_backed_skills": [s["name"] for s in _ZELENO_SKILLS]}
    score = score_job(job, profile_data)
    decision = evaluate_job_opportunity(job=job, profile=_ZELENO_PROFILE, candidate_skills=_ZELENO_SKILLS,
                                         score_result=score, structured_extraction=_ZELENO_STRUCTURED)
    # Continua HUMAN_REQUIRED - mas agora com razoes especificas e
    # auditaveis, nunca um MATERIAL_UNKNOWN generico ou um ACTIONABLE forcado.
    assert decision.decision == "HUMAN_REQUIRED"
    assert decision.eligibility == "MATERIAL_UNKNOWN"
    assert any("UNKNOWN_REQUIREMENT_CLASSIFICATION" in reason for reason in decision.unknowns)
    assert "UNKNOWN_WORK_MODEL" in decision.unknowns  # work_model contaminado corretamente descartado


def test_o_zeleno_meds_seniority_recognized_from_title():
    assert extract_seniority_from_title("Analista de Dados / DBA / Engenheiro(a) de Dados - Pleno") == "PLENO"


def test_o_zeleno_meds_contaminated_fields_never_trusted():
    assert resolve_structured_work_model(_ZELENO_STRUCTURED) is None


# P: score distribution (structural check - real distribution measured in production) --------------------------

def test_p_seniority_now_differentiates_when_flat_column_is_empty():
    junior_job = {"title": "Analista Junior", "structured_extraction": {}}
    senior_job = {"title": "Analista Senior", "structured_extraction": {}}
    profile = {"verified_skills": [], "target_roles": []}
    junior_score = score_job(junior_job, profile)
    senior_score = score_job(senior_job, profile)
    assert junior_score.dimensions["seniority"] != senior_score.dimensions["seniority"]


# Q: Brain integration - Brain reuses Score V2, never duplicates rules --------------------------------------------

def test_q_brain_never_recomputes_hard_blocks_reuses_score_result():
    score = _score(blocking_rules=["MINIMUM_SALARY_BLOCK"])
    decision = evaluate_job_opportunity(job={}, profile=PROFILE, candidate_skills=SKILLS, score_result=score,
                                         structured_extraction=None)
    assert decision.decision == "BLOCK"
    assert decision.hard_blocks == ["MINIMUM_SALARY_BLOCK"]


# R: no external action -----------------------------------------------------------------------------------------

def test_r_quality_module_never_imports_a_send_function():
    import inspect

    import src.quality as module
    source = inspect.getsource(module)
    for forbidden in ("send_application_email", "urlopen(", "requests.post(", "submit("):
        assert forbidden not in source


# S: reprocessing idempotent -------------------------------------------------------------------------------------

def test_s_score_job_is_idempotent_for_identical_input():
    job = {"title": "Analista de Dados - Pleno",
           "structured_extraction": {"mandatory_requirements": {"value": ["Experience with SQL Server."]}}}
    profile = {"verified_skills": ["SQL Server"], "target_roles": []}
    first = score_job(job, profile)
    second = score_job(job, profile)
    assert first == second


# T: canonical Job only (wiring check on the pending_evaluation filter, Prompt 9.1) --------------------------------

def test_t_resolve_required_technology_tokens_never_invents_a_technology():
    assert resolve_required_technology_tokens({"mandatory_requirements": {"value": ["Requisitos"]}}) == []
    assert resolve_required_technology_tokens(None) == []


def test_t_resolve_structured_language_requirements_maps_to_flat_shape():
    structured = {"language_requirements": {"value": {"language": "Spanish", "level": "fluent"}, "confidence": 80,
                                             "evidence_snippet": "Espanhol fluente obrigatorio"}}
    result = resolve_structured_language_requirements(structured)
    assert result == [{"language": "Spanish", "level": "fluent", "required": True}]
