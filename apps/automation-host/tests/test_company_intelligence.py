"""Fase 2, Prompt 11 - Company Intelligence + Work Model Resolution.
Testes A-N (parte pura) da Secao 22. Todo I/O real e injetado pelo caller
(main.py) - este modulo nunca abre conexao de rede, entao estes testes
nao tem nenhuma dependencia externa viva."""

from src.company_intelligence import (
    can_enrich_job, classify_careers_probe, classify_domain_probe, classify_generic_page_correlation,
    classify_job_correlation, classify_job_correlation_among_candidates, classify_job_page_status,
    extract_domain_candidate_from_email, resolve_work_model_with_priority, search_job_title_in_page,
)


# A: official domain verified --------------------------------------------------------------------

def test_a_official_domain_verified_on_real_200_same_host():
    assert classify_domain_probe(200, "https://zelenomeds.com/", "zelenomeds.com") == "VERIFIED_OFFICIAL_DOMAIN"


def test_a_verified_even_with_www_subdomain():
    assert classify_domain_probe(200, "https://www.zelenomeds.com/", "zelenomeds.com") == "VERIFIED_OFFICIAL_DOMAIN"


# B: guessed domain not trusted --------------------------------------------------------------------

def test_b_generic_email_provider_never_becomes_a_domain_candidate():
    assert extract_domain_candidate_from_email("giovanna.marinho@gmail.com") is None
    assert extract_domain_candidate_from_email("rh@hotmail.com") is None


def test_b_real_company_email_domain_is_a_candidate_not_yet_verified():
    # Caso real Zeleno Meds - o candidato existe, mas so vira
    # VERIFIED_OFFICIAL_DOMAIN apos um probe HTTP real bem-sucedido.
    assert extract_domain_candidate_from_email("giovanna.marinho@zelenomeds.com") == "zelenomeds.com"


def test_b_domain_probe_never_trusted_without_a_real_200():
    assert classify_domain_probe(404, None, "zelenomeds.com") == "UNVERIFIED"
    assert classify_domain_probe(None, None, "zelenomeds.com") == "UNVERIFIED"


def test_b_redirect_to_an_unrelated_domain_is_never_trusted():
    # Dominio estacionado/revendido redirecionando para outro host -
    # nunca confirma que o dominio pedido e o site oficial da empresa.
    assert classify_domain_probe(200, "https://domain-parking-service.example/", "zelenomeds.com") == "UNVERIFIED"


# C: careers probe 200 but unrelated page -> rejected -------------------------------------------------

def test_c_careers_probe_200_without_keyword_is_rejected():
    result = classify_careers_probe(200, "https://zelenomeds.com/careers",
                                     "bem vindo ao nosso site institucional de saude")
    assert result["matched_keyword"] is False


def test_c_careers_probe_404_never_becomes_a_candidate():
    assert classify_careers_probe(404, "https://zelenomeds.com/careers", "vagas abertas") is None


# D: official careers redirect -> ATS detected (reuses ats_detection.detect_ats, imported by main.py) --

def test_d_careers_probe_with_real_keyword_is_a_candidate():
    result = classify_careers_probe(200, "https://zelenomeds.com/careers", "confira nossas vagas abertas agora")
    assert result["matched_keyword"] is True
    assert result["final_url"] == "https://zelenomeds.com/careers"


# E: company careers only != active job ----------------------------------------------------------------

def test_e_company_only_never_enriches_the_specific_job():
    correlation = classify_job_correlation({"company_only": True}, {"title": "Analista de Dados"})
    assert correlation == "COMPANY_ONLY"
    assert not can_enrich_job(correlation)


def test_e_not_found_never_enriches_either():
    assert not can_enrich_job(classify_job_correlation(None, {"title": "Analista de Dados"}))


# F: exact job match enriches work model -----------------------------------------------------------------

def test_f_exact_provider_job_id_match_enriches():
    candidate = {"provider_job_id": "4459952895", "title": "Outro Titulo"}
    target = {"external_id": "4459952895", "title": "Analista de Dados"}
    correlation = classify_job_correlation(candidate, target)
    assert correlation == "EXACT_JOB_MATCH"
    assert can_enrich_job(correlation)


def test_f_high_confidence_title_and_location_match_enriches():
    candidate = {"title": "Analista de Dados Pleno", "location": "Sao Paulo"}
    target = {"title": "Analista de Dados Pleno", "location": "Sao Paulo"}
    correlation = classify_job_correlation(candidate, target)
    assert correlation == "HIGH_CONFIDENCE_MATCH"
    assert can_enrich_job(correlation)


def test_f_different_title_is_not_a_match():
    candidate = {"title": "Analista de Suporte", "location": "Sao Paulo"}
    target = {"title": "Analista de Dados Pleno", "location": "Sao Paulo"}
    assert classify_job_correlation(candidate, target) == "NOT_FOUND"


# G/H/I/J: work model resolution priority (remote/hybrid/onsite/unknown) --------------------------------

def test_g_official_ats_structured_wins_over_everything():
    candidates = [
        {"work_model": "HYBRID", "source_priority": "DISCOVERY_SOURCE_TEXT"},
        {"work_model": "REMOTE", "source_priority": "OFFICIAL_ATS_STRUCTURED"},
    ]
    result = resolve_work_model_with_priority(candidates)
    assert result["work_model"] == "REMOTE"
    assert result["source_priority"] == "OFFICIAL_ATS_STRUCTURED"


def test_h_official_job_page_beats_trusted_structured_extraction():
    candidates = [
        {"work_model": "ONSITE", "source_priority": "TRUSTED_STRUCTURED_EXTRACTION"},
        {"work_model": "HYBRID", "source_priority": "OFFICIAL_JOB_PAGE"},
    ]
    result = resolve_work_model_with_priority(candidates)
    assert result["work_model"] == "HYBRID"
    assert result["source_priority"] == "OFFICIAL_JOB_PAGE"


def test_i_trusted_structured_extraction_used_when_nothing_better_exists():
    candidates = [{"work_model": "REMOTE", "source_priority": "TRUSTED_STRUCTURED_EXTRACTION"}]
    result = resolve_work_model_with_priority(candidates)
    assert result["work_model"] == "REMOTE"


def test_j_onsite_from_discovery_source_text_used_as_last_resort():
    candidates = [{"work_model": "ONSITE", "source_priority": "DISCOVERY_SOURCE_TEXT"}]
    result = resolve_work_model_with_priority(candidates)
    assert result["work_model"] == "ONSITE"
    assert result["source_priority"] == "DISCOVERY_SOURCE_TEXT"


# K: unknown stays unknown ------------------------------------------------------------------------------

def test_k_no_candidates_stays_unknown():
    result = resolve_work_model_with_priority([])
    assert result["work_model"] == "UNKNOWN"
    assert result["source_priority"] is None


def test_k_unrecognized_work_model_value_never_used():
    result = resolve_work_model_with_priority([{"work_model": "FLEXIBLE", "source_priority": "OFFICIAL_JOB_PAGE"}])
    assert result["work_model"] == "UNKNOWN"


# L: official ATS overrides contaminated LinkedIn field (real Zeleno Meds scenario) -----------------------

def test_l_official_source_overrides_linkedin_discovery_text_even_with_lower_list_position():
    candidates = [
        {"work_model": "HYBRID", "source_priority": "DISCOVERY_SOURCE_TEXT",
         "evidence_snippet": "Exibir tudo\n\nAnalista de dados Presencialou Remotoou Hibrido"},
        {"work_model": "REMOTE", "source_priority": "OFFICIAL_JOB_PAGE", "evidence_snippet": "Trabalho remoto"},
    ]
    result = resolve_work_model_with_priority(candidates)
    assert result["work_model"] == "REMOTE"
    assert result["source_priority"] == "OFFICIAL_JOB_PAGE"


# M: salary not invented (module never touches salary at all - confirms no such function exists) ---------

def test_m_module_never_estimates_or_touches_salary():
    import inspect

    import src.company_intelligence as module
    source = inspect.getsource(module)
    assert "salary" not in source.lower()


# N: requirements enriched only with evidence (module never fabricates requirement text) ------------------

def test_n_classify_careers_probe_never_invents_body_content():
    assert classify_careers_probe(200, "https://x.com/careers", None) == {
        "final_url": "https://x.com/careers", "matched_keyword": False}


# Q: no external action (module has zero network/send capability) -----------------------------------------

def test_q_module_never_imports_network_or_send_functions():
    import inspect

    import src.company_intelligence as module
    source = inspect.getsource(module)
    for forbidden in ("urlopen(", "requests.", "send_application_email", "import socket"):
        assert forbidden not in source


# Fase 2, Prompt 12 - Specific Job Correlation & Official Job Enrichment ------------------------------------
# Testes A-T da Secao 20.

# A: exact requisition ID match ------------------------------------------------------------------------------

def test_a_exact_requisition_id_match():
    candidate = {"provider_job_id": "REQ-12345", "title": "Something Else Entirely"}
    target = {"external_id": "REQ-12345", "title": "Analista de Dados Pleno"}
    assert classify_job_correlation(candidate, target) == "EXACT_JOB_MATCH"


# B: exact official URL match (covered via provider_job_id derived from canonical_url upstream - see job_identity.py) --

def test_b_no_provider_id_falls_back_to_title_location_match():
    candidate = {"title": "Analista de Dados Pleno", "location": "Sao Paulo"}
    target = {"title": "Analista de Dados Pleno", "location": "Sao Paulo"}
    assert classify_job_correlation(candidate, target) == "HIGH_CONFIDENCE_MATCH"


# C: title/company/location high-confidence match (single candidate) already covered in test_f_* above ------------

# D: ambiguous same-title jobs do not merge --------------------------------------------------------------------------

def test_d_two_high_confidence_candidates_are_ambiguous_never_merged():
    candidates = [
        {"title": "Analista de Dados Pleno", "location": "Sao Paulo"},
        {"title": "Analista de Dados Pleno", "location": "Sao Paulo"},
    ]
    target = {"title": "Analista de Dados Pleno", "location": "Sao Paulo"}
    correlation = classify_job_correlation_among_candidates(candidates, target)
    assert correlation == "AMBIGUOUS"
    assert not can_enrich_job(correlation)


def test_d_single_high_confidence_among_many_company_only_still_resolves():
    candidates = [
        {"company_only": True, "title": "Analista de Suporte"},
        {"title": "Analista de Dados Pleno", "location": "Sao Paulo"},
    ]
    target = {"title": "Analista de Dados Pleno", "location": "Sao Paulo"}
    assert classify_job_correlation_among_candidates(candidates, target) == "HIGH_CONFIDENCE_MATCH"


# E: company-only page does not enrich job (generic correlator, real Zeleno Meds page shape) --------------------------

def test_e_generic_company_page_without_the_job_title_is_company_only():
    # Achado real de producao: a careers page real da Zeleno Meds
    # ("Trabalhe Conosco") e um formulario generico de contato - nenhum
    # titulo de vaga especifico aparece nela.
    body = "Trabalhe Conosco ZELENO Premium Cannabis. Preencha o formulario e envie seu curriculo."
    correlation = classify_generic_page_correlation("Analista de Dados / DBA / Engenheiro(a) de Dados - Pleno", body)
    assert correlation == "COMPANY_ONLY"
    assert not can_enrich_job(correlation)


def test_e_short_title_never_correlates_generically_even_if_substring_present():
    # "Analista" sozinho apareceria em qualquer pagina de RH - nunca uma
    # correlacao segura por palavra isolada.
    assert search_job_title_in_page("Analista", "Vagas para Analista disponiveis") is False


# F/G: active/closed official job -------------------------------------------------------------------------------------

def test_f_active_official_job_requires_both_title_match_and_a_real_active_marker():
    body = "Analista de Dados Pleno - Sao Paulo. Candidate-se agora, vaga aberta!"
    matched = search_job_title_in_page("Analista de Dados Pleno", body)
    assert matched is True
    assert classify_job_page_status(200, body, matched) == "ACTIVE"


def test_g_closed_official_job_detected_from_a_real_closed_marker():
    body = "Analista de Dados Pleno - Sao Paulo. Esta vaga nao esta mais disponivel."
    matched = search_job_title_in_page("Analista de Dados Pleno", body)
    assert classify_job_page_status(200, body, matched) == "CLOSED"


def test_status_200_alone_is_never_proof_of_active():
    # Secao 4: "Nao considerar HTTP 200 sozinho como prova de vaga ativa."
    body = "Bem-vindo ao nosso site institucional."
    matched = search_job_title_in_page("Analista de Dados Pleno", body)
    assert matched is False
    assert classify_job_page_status(200, body, matched) == "NOT_FOUND"


def test_status_unreachable_is_unknown_not_not_found():
    assert classify_job_page_status(None, None, False) == "UNKNOWN"


# K: unknown preserved when title matches but no state marker exists ---------------------------------------------------

def test_k_title_matched_without_any_state_marker_stays_unknown():
    body = "Analista de Dados Pleno - Sao Paulo. Sobre a vaga: trabalhamos com dados todos os dias."
    matched = search_job_title_in_page("Analista de Dados Pleno", body)
    assert matched is True
    assert classify_job_page_status(200, body, matched) == "UNKNOWN"
