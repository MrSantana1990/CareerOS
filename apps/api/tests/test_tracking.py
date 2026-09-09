from src.tracking import (aggregate_by_dimension, aggregate_gap_intelligence,
                          calculate_conversion_funnel, classify_correlation,
                          group_interventions_by_root_cause, recommendation_confidence)

APPLICATIONS = [
    {"id": "a1", "title": "DBA Senior", "company": "Nubank", "company_domain": "nubank.com.br"},
    {"id": "a2", "title": "Suporte N3", "company": "Randstad", "company_domain": "randstad.com.br"},
]


# E: high-confidence correlation -----------------------------------------------------------------

def test_e_sender_domain_match_is_high_confidence():
    message = {"sender": "rh@nubank.com.br", "subject": "Sua candidatura"}
    result = classify_correlation(message, APPLICATIONS)
    assert result["status"] == "MATCHED_HIGH_CONFIDENCE"
    assert result["application_id"] == "a1"


# F: ambiguous correlation ------------------------------------------------------------------------

def test_f_tied_score_is_ambiguous():
    apps = [{"id": "a1", "title": "DBA Senior", "company": "Empresa X", "company_domain": ""},
            {"id": "a2", "title": "DBA Senior", "company": "Empresa X", "company_domain": ""}]
    message = {"sender": "rh@terceiros.com", "subject": "Sobre DBA Senior na Empresa X"}
    result = classify_correlation(message, apps)
    assert result["status"] == "AMBIGUOUS"
    assert result["application_id"] is None


# G: unmatched remains unmatched (Randstad/Mercado Livre real case) -------------------------------

def test_g_no_underlying_application_stays_unmatched():
    message = {"sender": "ana@randstad.com.br", "subject": "Entrevista Mercado Livre"}
    result = classify_correlation(message, [])  # nenhum Job/Application real para Mercado Livre
    assert result["status"] == "UNMATCHED"
    assert result["application_id"] is None


def test_medium_confidence_when_only_a_weaker_single_signal_matches():
    # Padrao real do caso Randstad/Mercado Livre (Secao 6): a recrutadora
    # envia de um dominio de agencia terceirizada, entao sender_domain
    # nunca bate com o dominio da empresa contratante - so o nome da
    # empresa no assunto fica disponivel como sinal (35 pts, unico).
    apps = [{"id": "a2", "title": "Suporte N3", "company": "Mercado Livre", "company_domain": "mercadolivre.com"}]
    message = {"sender": "ana@randstad.com.br", "subject": "Entrevista Online - 2a Etapa | Mercado Livre"}
    result = classify_correlation(message, apps)
    assert result["status"] == "MATCHED_MEDIUM_CONFIDENCE"
    assert result["application_id"] == "a2"


# I: conversion event idempotency (application_events ja e append-only via trigger de banco -
# aqui testamos que o calculo do funil e determinista/idempotente para o mesmo input) -------------

def test_i_funnel_calculation_is_idempotent_for_identical_inputs():
    kwargs = dict(jobs_count=183, scored_count=57, opportunities_by_status={"ACTIONABLE": 2},
                  applications_by_status={"CONFIRMED": 1, "SENT": 3}, events_by_type={"INTERVIEW": 1})
    first = calculate_conversion_funnel(**kwargs)
    second = calculate_conversion_funnel(**kwargs)
    assert first == second


# J: funnel zero denominator -----------------------------------------------------------------------

def test_j_zero_denominator_returns_none_never_fake_zero_percent():
    result = calculate_conversion_funnel(jobs_count=0, scored_count=0, opportunities_by_status={},
                                          applications_by_status={}, events_by_type={})
    assert result["rates"]["qualification_rate"] is None
    assert result["rates"]["hire_rate"] is None


def test_funnel_computes_real_rates_when_denominators_exist():
    result = calculate_conversion_funnel(jobs_count=100, scored_count=50,
                                          opportunities_by_status={}, applications_by_status={"CONFIRMED": 5},
                                          events_by_type={})
    assert result["rates"]["qualification_rate"] == 50.0


def test_dimensional_learning_unknown_dimension_stays_unknown():
    apps = [{"discovery_source": None, "status": "SENT"}, {"discovery_source": "LinkedIn", "status": "CONFIRMED"}]
    result = aggregate_by_dimension(apps, "discovery_source")
    assert result["UNKNOWN"]["total"] == 1
    assert result["LinkedIn"]["confirmed"] == 1


def test_recommendation_confidence_insufficient_data_below_threshold():
    assert recommendation_confidence(5) == "INSUFFICIENT_DATA"


def test_recommendation_confidence_sufficient_data_above_threshold():
    assert recommendation_confidence(25) == "SUFFICIENT_DATA"


# K: gap aggregation ---------------------------------------------------------------------------------

def test_k_gap_aggregation_maps_real_hard_blocks_to_categories():
    opportunities = [
        {"id": "o1", "fit_score": 80, "evidence": {"brain": {"hard_blocks": ["CORE_REQUIREMENT_MISSING"]}}},
        {"id": "o2", "fit_score": 40, "evidence": {"brain": {"hard_blocks": ["MINIMUM_SALARY_BLOCK"]}}},
        {"id": "o3", "fit_score": 77, "evidence": {"brain": {"unknowns": ["work_model_or_location_unknown"]}}},
    ]
    result = aggregate_gap_intelligence(opportunities)
    assert result["SKILL"]["category"] == "CANDIDATE_GAP"
    assert result["SKILL"]["count"] == 1
    assert result["SKILL"]["high_fit_affected"] == 1
    assert result["SALARY"]["category"] == "MARKET_CONSTRAINT"
    assert result["SALARY"]["high_fit_affected"] == 0
    assert result["WORK_MODEL"]["count"] == 1


def test_k_gap_aggregation_never_invents_a_category_without_a_real_reason():
    opportunities = [{"id": "o1", "fit_score": 90, "evidence": {"brain": {"hard_blocks": ["SOME_NEW_UNMAPPED_REASON"]}}}]
    result = aggregate_gap_intelligence(opportunities)
    assert result == {}


def test_k_gap_aggregation_handles_opportunity_with_no_brain_evidence():
    result = aggregate_gap_intelligence([{"id": "o1", "fit_score": None, "evidence": {}}])
    assert result == {}


# S: intervention root-cause dedup/grouping -------------------------------------------------------

def test_s_ten_identical_interventions_group_into_one_root_cause():
    interventions = [
        {"id": f"i{i}", "reason": "MATERIAL_UNKNOWN", "opportunity_id": f"opp{i}",
         "evidence": {"policy_result": {"human_requirements": ["work_model_or_location_unknown"]}}}
        for i in range(10)
    ]
    groups = group_interventions_by_root_cause(interventions)
    assert len(groups) == 1
    assert groups[0]["count"] == 10
    assert len(groups[0]["opportunity_ids"]) == 10
    assert len(groups[0]["intervention_ids"]) == 10


def test_s_grouping_never_deletes_or_merges_individual_intervention_ids():
    interventions = [
        {"id": "i1", "reason": "MATERIAL_UNKNOWN", "opportunity_id": "opp1",
         "evidence": {"policy_result": {"human_requirements": ["x"]}}},
        {"id": "i2", "reason": "MISSING_PROFILE_DATA", "opportunity_id": None,
         "evidence": {"policy_result": {"human_requirements": []}}},
    ]
    groups = group_interventions_by_root_cause(interventions)
    assert len(groups) == 2
    all_ids = {iid for group in groups for iid in group["intervention_ids"]}
    assert all_ids == {"i1", "i2"}


def test_s_grouping_sorted_by_largest_group_first():
    interventions = (
        [{"id": "small", "reason": "A", "opportunity_id": "o", "evidence": {"policy_result": {}}}]
        + [{"id": f"big{i}", "reason": "B", "opportunity_id": f"o{i}", "evidence": {"policy_result": {}}}
           for i in range(3)]
    )
    groups = group_interventions_by_root_cause(interventions)
    assert groups[0]["reason"] == "B"
    assert groups[0]["count"] == 3
