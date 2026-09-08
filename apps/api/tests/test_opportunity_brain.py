from src.opportunity_brain import (assess_company_relevance, audit_company_data_quality,
                                    classify_requirement_domain, classify_signal_quality,
                                    evaluate_job_opportunity, evaluate_language_gap,
                                    evaluate_location_work_model, evaluate_requirements,
                                    evaluate_signal_opportunity, evaluate_watch_recheck,
                                    find_skill_evidence, opportunity_type_for_signal)
from src.quality import ScoreResult

PROFILE = {"city": "Campinas", "work_models": ["REMOTE", "HYBRID"], "language_levels": {}}
SKILLS = [
    {"name": "SQL Server", "verified": False},
    {"name": "AWS", "verified": True},
]


def _score(total=80, recommendation="APPLY_HIGH", blocking_rules=None, risks=None, strengths=None):
    return ScoreResult(total=total, recommendation=recommendation, dimensions={"technology": 30},
                        strengths=strengths or [], gaps=[], risks=risks or [],
                        blocking_rules=blocking_rules or [])


# --- A: core requirement missing -------------------------------------------------

def test_a_core_requirement_missing_blocks():
    structured = {"mandatory_requirements": {
        "value": ["You must have production Kubernetes experience with 5 years of experience."],
        "source_url": "https://example.com/job",
    }}
    decision = evaluate_job_opportunity(job={}, profile=PROFILE, candidate_skills=SKILLS,
                                         score_result=_score(), structured_extraction=structured)
    assert decision.decision == "BLOCK"
    assert "CORE_REQUIREMENT_MISSING" in decision.hard_blocks
    assert decision.reasons  # guarda o requirement, nao so uma string generica


# --- B: transferable skill ---------------------------------------------------------

def test_b_transferable_skill_does_not_block():
    structured = {"mandatory_requirements": {
        "value": ["Solid experience with PostgreSQL and query optimization."],
        "source_url": "https://example.com/job",
    }}
    decision = evaluate_job_opportunity(job={}, profile=PROFILE, candidate_skills=SKILLS,
                                         score_result=_score(), structured_extraction=structured)
    assert decision.decision != "BLOCK"
    assert decision.transferable_matches
    assert decision.transferable_matches[0]["skill"] == "SQL Server"


def test_b_transferable_never_fabricates_kubernetes_from_docker():
    evidence = find_skill_evidence("Kubernetes experience required",
                                    [{"name": "Docker", "verified": True}])
    assert evidence is None


# --- C: preferred requirement missing ----------------------------------------------

def test_c_preferred_requirement_missing_does_not_block():
    structured = {"preferred_requirements": {"value": ["Knowledge of Kubernetes is a plus."],
                                              "source_url": "https://example.com/job"}}
    result = evaluate_requirements(structured, SKILLS)
    assert result["preferred_gaps"] == ["Knowledge of Kubernetes is a plus."]
    assert result["core_missing"] == []


# --- D: ambiguous mandatory marker (CI&T real finding, Prompt 3) --------------------

def test_d_attendance_policy_marked_mandatory_is_contextual_not_core():
    text = "Important: if you reside in the Campinas Metropolitan Region, your presence in the city offices will be mandatory, according to the current frequency policy."
    assert classify_requirement_domain(text) == "CONTEXTUAL_REQUIREMENT"


def test_d_contextual_requirement_does_not_produce_core_missing():
    structured = {"mandatory_requirements": {
        "value": ["your presence in the city offices will be mandatory, according to the current frequency policy."],
        "source_url": "https://example.com/job",
    }}
    result = evaluate_requirements(structured, SKILLS)
    assert result["core_missing"] == []
    assert len(result["contextual_requirements"]) == 1


# --- E: explicit English requirement, incompatible -----------------------------------

def test_e_explicit_english_requirement_incompatible_blocks():
    structured = {"language_requirements": {"value": {"language": "English", "level": "fluent"}}}
    profile = {**PROFILE, "language_levels": {"English": "basic"}}
    result = evaluate_language_gap(structured, profile["language_levels"])
    assert result["status"] == "GAP"
    decision = evaluate_job_opportunity(job={}, profile=profile, candidate_skills=SKILLS,
                                         score_result=_score(), structured_extraction=structured)
    assert decision.decision == "BLOCK"
    assert "LANGUAGE_GAP" in decision.hard_blocks


# --- F: English-page-only, no explicit requirement -> no block -----------------------

def test_f_english_page_without_explicit_requirement_no_block():
    # structured_fields.py (Prompt 3) ja nunca gera language_requirements so
    # pela pagina estar em ingles - aqui confirmamos que a ausencia do campo
    # nao produz nenhum bloqueio/gap.
    result = evaluate_language_gap({}, {})
    assert result["status"] == "NO_EXPLICIT_REQUIREMENT"
    decision = evaluate_job_opportunity(job={}, profile=PROFILE, candidate_skills=SKILLS,
                                         score_result=_score(), structured_extraction={})
    assert decision.decision != "BLOCK"


# --- G: salary hard floor ------------------------------------------------------------

def test_g_salary_hard_floor_blocks_via_score_v2():
    decision = evaluate_job_opportunity(job={}, profile=PROFILE, candidate_skills=SKILLS,
                                         score_result=_score(blocking_rules=["MINIMUM_SALARY_BLOCK"]),
                                         structured_extraction={})
    assert decision.decision == "BLOCK"
    assert "MINIMUM_SALARY_BLOCK" in decision.hard_blocks


# --- H: salary unknown -----------------------------------------------------------------

def test_h_salary_unknown_does_not_block():
    decision = evaluate_job_opportunity(job={}, profile=PROFILE, candidate_skills=SKILLS,
                                         score_result=_score(blocking_rules=[]), structured_extraction={})
    assert decision.decision != "BLOCK"


# --- I: onsite relocation block ----------------------------------------------------------

def test_i_onsite_far_from_candidate_blocks():
    structured = {"work_model": {"value": {"work_model": "ONSITE"}},
                  "location": {"value": {"region": "Portugal"}}}
    result = evaluate_location_work_model(structured, {}, PROFILE)
    assert result["status"] == "RELOCATION_BLOCK"
    decision = evaluate_job_opportunity(job={}, profile=PROFILE, candidate_skills=SKILLS,
                                         score_result=_score(), structured_extraction=structured)
    assert decision.decision == "BLOCK"
    assert "RELOCATION_REQUIRED_IMPLICIT" in decision.hard_blocks


# --- J: viable hybrid ---------------------------------------------------------------------

def test_j_viable_hybrid_same_region_does_not_block():
    structured = {"work_model": {"value": {"work_model": "HYBRID", "frequency_days_per_week": 2}},
                  "location": {"value": {"region": "Campinas"}}}
    result = evaluate_location_work_model(structured, {}, PROFILE)
    assert result["status"] == "COMPATIBLE"
    decision = evaluate_job_opportunity(job={}, profile=PROFILE, candidate_skills=SKILLS,
                                         score_result=_score(), structured_extraction=structured)
    assert decision.decision != "BLOCK"


# --- K: Opportunity without Job -----------------------------------------------------------

def test_k_signal_opportunity_decision_never_requires_a_job():
    signal = {"type": "EXPANSION", "company_id": "c1", "headline": "x", "source_url": "u",
              "evidence": {"a": 1}, "confidence": 80}
    decision = evaluate_signal_opportunity(signal=signal, company={"br_presence": True})
    assert decision.decision == "WATCH"
    assert decision.fit_score is None  # Fit tecnico so existe quando ha Job real


# --- L: Signal -> Watch (Nubank-style) -----------------------------------------------------

def test_l_trusted_resolved_relevant_signal_becomes_watch():
    signal = {"type": "EXPANSION", "company_id": "nubank-id", "headline": "Nubank investe e expande",
              "source_url": "https://example.com", "evidence": {"query": "x"}, "confidence": 60}
    decision = evaluate_signal_opportunity(signal=signal, company={"br_presence": True},
                                            related_signals=[signal])
    assert decision.decision == "WATCH"
    assert opportunity_type_for_signal("EXPANSION") == "WATCH_ONLY"
    assert opportunity_type_for_signal("HIRING_ANNOUNCEMENT") == "FUTURE_HIRING"


# --- M: Signal noise -> no Opportunity ------------------------------------------------------

def test_m_noisy_generic_signal_is_dropped():
    signal = {"type": "OTHER_VERIFIED_SIGNAL", "company_id": None, "headline": "Como aumentar produtividade",
              "source_url": "https://example.com", "evidence": {"query": "x"}, "confidence": 60}
    assert classify_signal_quality(signal) == "NOISY"
    decision = evaluate_signal_opportunity(signal=signal)
    assert decision.decision == "DROP"


def test_m_insufficient_evidence_signal_is_dropped():
    signal = {"type": "EXPANSION", "company_id": "c1", "headline": "", "source_url": "", "evidence": {}}
    assert classify_signal_quality(signal) == "INSUFFICIENT_EVIDENCE"


def test_m_low_confidence_signal_is_dropped():
    signal = {"type": "EXPANSION", "company_id": "c1", "headline": "x", "source_url": "u",
              "evidence": {"a": 1}, "confidence": 20}
    assert classify_signal_quality(signal) == "LOW_CONFIDENCE"


def test_m_unresolved_signal_stays_unresolved_no_opportunity():
    signal = {"type": "EXPANSION", "company_id": None, "headline": "x", "source_url": "u",
              "evidence": {"a": 1}, "confidence": 80}
    assert classify_signal_quality(signal) == "TRUSTED_UNRESOLVED"
    decision = evaluate_signal_opportunity(signal=signal)
    assert decision.decision == "DROP"
    assert decision.eligibility == "COMPANY_UNRESOLVED"


# --- N: existing Applied Opportunity not duplicated (Deutsche Bank regression) ---------------

def test_n_already_applied_opportunity_preserved_as_terminal():
    decision = evaluate_job_opportunity(job={}, profile=PROFILE, candidate_skills=SKILLS,
                                         score_result=_score(), structured_extraction={},
                                         already_terminal=True)
    assert decision.decision == "ACTIONABLE"
    assert decision.eligibility == "ALREADY_APPLIED"
    assert "already_applied_terminal_state_preserved" in decision.reasons


# --- O: unknown material -> Human/Recheck ------------------------------------------------------

def test_o_material_language_unknown_requires_human():
    structured = {"language_requirements": {"value": {"language": "English", "level": "fluent"}}}
    decision = evaluate_job_opportunity(job={}, profile=PROFILE, candidate_skills=SKILLS,
                                         score_result=_score(), structured_extraction=structured)
    assert decision.decision == "HUMAN_REQUIRED"
    assert "language_level_unknown" in decision.unknowns


def test_o_watch_recheck_no_new_evidence_stays_watch():
    decision = evaluate_watch_recheck(new_signals=[])
    assert decision.decision == "WATCH"
    assert decision.eligibility == "NO_NEW_EVIDENCE"


def test_o_watch_recheck_material_new_evidence_promotes_to_recheck():
    company = {"br_presence": True}
    new_signals = [{"type": "INVESTMENT", "company_id": "c1"}]
    decision = evaluate_watch_recheck(new_signals=new_signals, company=company)
    assert decision.decision == "RECHECK"


# --- P: idempotent evaluation ------------------------------------------------------------------

def test_p_evaluation_is_idempotent_for_identical_inputs():
    structured = {"work_model": {"value": {"work_model": "REMOTE"}}}
    first = evaluate_job_opportunity(job={}, profile=PROFILE, candidate_skills=SKILLS,
                                      score_result=_score(), structured_extraction=structured)
    second = evaluate_job_opportunity(job={}, profile=PROFILE, candidate_skills=SKILLS,
                                       score_result=_score(), structured_extraction=structured)
    assert first.as_dict() == second.as_dict()


# --- company relevance / data quality (Secoes 2/3/33) -------------------------------------------

def test_company_relevance_unknown_when_no_evidence_at_all():
    assert assess_company_relevance({})["relevance"] == "UNKNOWN"


def test_company_relevance_never_low_just_for_missing_industry():
    # Secao 3: nao bloquear Company so por falta de industry/setor.
    result = assess_company_relevance({"name": "Empresa Industrial LTDA"})
    assert result["relevance"] != "LOW"


def test_company_relevance_low_only_with_real_negative_evidence():
    assert assess_company_relevance({"br_presence": False})["relevance"] == "LOW"


def test_company_relevance_high_with_prior_interaction():
    assert assess_company_relevance({}, has_prior_interaction=True)["relevance"] == "HIGH"


def test_audit_company_data_quality_flags_malformed_names_without_deleting():
    companies = [{"name": "Nubank"}, {"name": "Qlik View/Sense em Recife,- PE"}]
    report = audit_company_data_quality(companies)
    assert report["companies_total"] == 2
    assert report["suspicious_count"] == 1
    assert report["well_formed_count"] == 1
