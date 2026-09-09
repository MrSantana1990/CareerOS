from src.channel_discovery import discover_company_channel_candidates, discover_job_channel_candidates

COMPANY_EMPTY = {}
COMPANY_WITH_CAREERS = {"careers_url": "https://empresa.com/carreiras"}
COMPANY_WITH_EMAIL = {"official_recruiting_email": "rh@empresa.com"}


# O: channel from explicit application URL / instruction ------------------------------------

def test_o_explicit_application_email_from_structured_extraction_is_top_priority():
    job = {"canonical_url": "https://boards.greenhouse.io/acme/jobs/1", "source": "greenhouse"}
    structured = {"application_instructions": {"value": {"recruiting_email": "vagas@empresa.com"},
                                                "source_url": "https://empresa.com/vaga"}}
    candidates = discover_job_channel_candidates(job, COMPANY_EMPTY, structured)
    assert candidates[0]["type"] == "OFFICIAL_EMAIL"
    assert candidates[0]["url_or_email"] == "vagas@empresa.com"


def test_official_ats_detected_from_known_source():
    job = {"canonical_url": "https://boards.greenhouse.io/acme/jobs/1", "source": "greenhouse"}
    candidates = discover_job_channel_candidates(job, COMPANY_EMPTY)
    assert candidates[0]["type"] == "OFFICIAL_ATS"
    assert candidates[0]["confidence"] == 95


# P: official email provenance ----------------------------------------------------------------

def test_p_official_email_channel_preserves_provenance_fields():
    job = {"canonical_url": "https://x.com", "source": "linkedin", "recruiter_email": "recruiter@empresa.com"}
    candidates = discover_job_channel_candidates(job, COMPANY_EMPTY)
    email_candidate = next(c for c in candidates if c["type"] == "OFFICIAL_EMAIL")
    assert email_candidate["source"] == "https://x.com"
    assert email_candidate["status"] == "CANDIDATE"
    assert "confidence" in email_candidate


# Q: guessed email rejected (nunca existe funcao que adivinha email - so aceitamos o que ja veio
# explicito do Job/Company/structured_extraction) --------------------------------------------

def test_q_no_email_candidate_when_none_declared_anywhere():
    job = {"canonical_url": "https://linkedin.com/jobs/view/123", "source": "linkedin"}
    candidates = discover_job_channel_candidates(job, COMPANY_EMPTY)
    assert not any(c["type"] == "OFFICIAL_EMAIL" for c in candidates)


# R: generic homepage not treated as application endpoint --------------------------------------

def test_r_company_without_careers_url_produces_no_careers_channel():
    job = {"canonical_url": "https://linkedin.com/jobs/view/123", "source": "linkedin"}
    candidates = discover_job_channel_candidates(job, {"domain": "empresa.com"})
    assert not any(c["type"] == "OFFICIAL_CAREERS" for c in candidates)


def test_r_company_domain_alone_never_becomes_a_channel():
    # domain sozinho (sem careers_url explicito) nunca vira canal - Secao 21.
    candidates = discover_company_channel_candidates({"domain": "empresa.com"})
    assert candidates == []


# Assisted fallback with real, documented auth/captcha patterns --------------------------------

def test_linkedin_job_without_other_evidence_falls_back_to_assisted_with_known_auth_captcha():
    job = {"canonical_url": "https://www.linkedin.com/jobs/view/123", "source": "LinkedIn"}
    candidates = discover_job_channel_candidates(job, COMPANY_EMPTY)
    assert len(candidates) == 1
    assert candidates[0]["type"] == "ASSISTED"
    assert candidates[0]["requires_auth"] is True
    assert candidates[0]["requires_captcha"] is True


def test_linkedin_tracking_params_stripped_to_fit_url_or_email_column():
    # Achado real na validacao do Prompt 6: uma URL real do LinkedIn com
    # parametros de tracking (eBP/refId/trackingId/trk) passou de 900
    # caracteres e quebrou o INSERT (opportunity_channels.url_or_email e
    # VARCHAR(500)) com StringDataRightTruncationError. A query string e
    # ruido analitico, nao faz parte do endereco real da vaga - remover
    # (nunca truncar cego no meio da URL) e a correcao certa.
    long_url = ("https://www.linkedin.com/jobs/view/4362345837/?eBP=" + "x" * 400
                + "&refId=abc&trackingId=def&trk=flagship3_search_srp_jobs")
    assert len(long_url) > 500
    job = {"canonical_url": long_url, "source": "LinkedIn"}
    candidates = discover_job_channel_candidates(job, COMPANY_EMPTY)
    assert len(candidates[0]["url_or_email"]) <= 500
    assert candidates[0]["url_or_email"] == "https://www.linkedin.com/jobs/view/4362345837/"


def test_short_url_is_never_altered():
    job = {"canonical_url": "https://www.linkedin.com/jobs/view/123", "source": "LinkedIn"}
    candidates = discover_job_channel_candidates(job, COMPANY_EMPTY)
    assert candidates[0]["url_or_email"] == "https://www.linkedin.com/jobs/view/123"


def test_infojobs_job_without_other_evidence_falls_back_to_assisted_with_auth_only():
    job = {"canonical_url": "https://www.infojobs.com.br/vaga/123.aspx", "source": "InfoJobs"}
    candidates = discover_job_channel_candidates(job, COMPANY_EMPTY)
    assert candidates[0]["type"] == "ASSISTED"
    assert candidates[0]["requires_auth"] is True
    assert candidates[0]["requires_captcha"] is False


def test_assisted_fallback_never_added_when_a_higher_priority_candidate_exists():
    job = {"canonical_url": "https://www.linkedin.com/jobs/view/123", "source": "linkedin",
           "recruiter_email": "rh@empresa.com"}
    candidates = discover_job_channel_candidates(job, COMPANY_EMPTY)
    assert len(candidates) == 1
    assert candidates[0]["type"] == "OFFICIAL_EMAIL"


# Company/Future Opportunity branch (Secao 22) --------------------------------------------------

def test_company_only_branch_never_invents_spontaneous_application():
    candidates = discover_company_channel_candidates(COMPANY_EMPTY)
    assert candidates == []


def test_company_only_branch_uses_careers_url_when_present():
    candidates = discover_company_channel_candidates(COMPANY_WITH_CAREERS)
    assert candidates[0]["type"] == "OFFICIAL_CAREERS"


def test_company_only_branch_uses_official_email_when_present():
    candidates = discover_company_channel_candidates(COMPANY_WITH_EMAIL)
    assert candidates[0]["type"] == "OFFICIAL_EMAIL"
    assert candidates[0]["url_or_email"] == "rh@empresa.com"
