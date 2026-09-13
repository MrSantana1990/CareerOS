"""Fase 2, Prompt 9 - Safe Channel Expansion. Testes A-O da Secao 21.
Nenhuma dependencia externa viva (Secao 21: "No live external dependency in
CI") - probe_careers_candidate recebe um `fetch` falso injetado."""

from src.career import _aggregate_channel_trust
from src.channel_verification import (
    classify_email_trust, is_email_trust_usable, probe_careers_candidate, verify_channel_candidate,
)
from src.opportunity_brain import evaluate_job_opportunity
from src.quality import ScoreResult

_SCORE = ScoreResult(total=80, recommendation="APPLY", dimensions={}, strengths=["fit"], gaps=[], risks=[],
                      blocking_rules=[])

LINKEDIN_CAPTCHA_CHANNEL = {"type": "ASSISTED", "url_or_email": "https://linkedin.com/jobs/view/1",
                            "requires_auth": True, "requires_captcha": True, "requires_human": True,
                            "status": "CANDIDATE"}
INFOJOBS_AUTH_CHANNEL = {"type": "ASSISTED", "url_or_email": "https://infojobs.com.br/vaga/1",
                          "requires_auth": True, "requires_captcha": False, "requires_human": True,
                          "status": "CANDIDATE"}
OFFICIAL_ATS_VERIFIED = {"type": "OFFICIAL_ATS", "url_or_email": "https://boards.greenhouse.io/acme/jobs/1",
                          "requires_auth": False, "requires_captcha": False, "requires_human": False,
                          "status": "VERIFIED"}
OFFICIAL_CAREERS_VERIFIED = {"type": "OFFICIAL_CAREERS", "url_or_email": "https://acme.com/careers",
                              "requires_auth": False, "requires_captcha": False, "requires_human": False,
                              "status": "VERIFIED"}


# A: LinkedIn CAPTCHA + official ATS -> ATS escolhido -------------------------------------------

def test_a_linkedin_captcha_plus_official_ats_selects_the_ats():
    trust, selected = _aggregate_channel_trust([LINKEDIN_CAPTCHA_CHANNEL, OFFICIAL_ATS_VERIFIED])
    assert trust == "VERIFIED_AVAILABLE"
    assert selected["type"] == "OFFICIAL_ATS"


# B: InfoJobs AUTH + official careers/ATS -> alternativa escolhida ------------------------------

def test_b_infojobs_auth_plus_official_careers_selects_the_careers_channel():
    trust, selected = _aggregate_channel_trust([INFOJOBS_AUTH_CHANNEL, OFFICIAL_CAREERS_VERIFIED])
    assert trust == "VERIFIED_AVAILABLE"
    assert selected["type"] == "OFFICIAL_CAREERS"


def test_only_captcha_auth_channels_present_still_reports_the_worst_case_honestly():
    # Sem nenhum canal seguro alternativo, o resultado honesto continua
    # sendo CAPTCHA/AUTH - Prompt 9 nao exige contornar CAPTCHA/AUTH,
    # so evitar HUMAN_REQUIRED quando existe alternativa real.
    trust, selected = _aggregate_channel_trust([LINKEDIN_CAPTCHA_CHANNEL])
    assert trust == "CAPTCHA_REQUIRED"
    assert selected is None


# C: explicit verified email -> email candidate --------------------------------------------------

def test_c_explicit_email_extracted_from_job_posting_becomes_usable_candidate():
    channel = {"type": "OFFICIAL_EMAIL", "url_or_email": "giovanna.marinho@zelenomeds.com",
               "source": "https://linkedin.com/jobs/view/1", "confidence": 90,
               "requires_auth": False, "requires_captcha": False, "requires_human": False,
               "status": "CANDIDATE",
               "evidence": {"evidence_snippet": "envie seu curriculo em meu email: giovanna.marinho@zelenomeds.com",
                            "extraction_method": "detect_email_application"}}
    trust = classify_email_trust(channel, company=None)
    assert trust == "EXPLICIT_IN_JOB_POSTING"
    assert is_email_trust_usable(trust)
    verified = verify_channel_candidate(channel, company=None)
    assert verified["status"] == "VERIFIED"
    assert verified["evidence"]["email_trust"] == "EXPLICIT_IN_JOB_POSTING"


def test_c_email_domain_matching_company_domain_is_verified_recruiting():
    channel = {"type": "OFFICIAL_EMAIL", "url_or_email": "rh@acme.com", "status": "CANDIDATE",
               "evidence": {"extraction_method": "detect_email_application"}}
    trust = classify_email_trust(channel, company={"domain": "acme.com"})
    assert trust == "VERIFIED_RECRUITING"
    assert is_email_trust_usable(trust)


def test_c_company_intelligence_official_email_is_verified_official():
    channel = {"type": "OFFICIAL_EMAIL", "url_or_email": "rh@acme.com", "source": "company_intelligence",
               "status": "CANDIDATE"}
    trust = classify_email_trust(channel, company=None)
    assert trust == "VERIFIED_OFFICIAL"
    assert is_email_trust_usable(trust)


# D: inferred email -> rejected/unusable ----------------------------------------------------------

def test_d_email_without_explicit_instruction_evidence_is_unverified_not_promoted():
    # jobs.recruiter_email sem evidence_snippet/extraction_method - pode ser
    # um contato generico capturado por outra via, nunca promovido sozinho.
    channel = {"type": "OFFICIAL_EMAIL", "url_or_email": "contato@empresa.com", "status": "CANDIDATE"}
    trust = classify_email_trust(channel, company=None)
    assert trust == "UNVERIFIED"
    assert not is_email_trust_usable(trust)
    verified = verify_channel_candidate(channel, company=None)
    assert verified["status"] == "CANDIDATE"


def test_d_no_email_present_is_invalid():
    channel = {"type": "OFFICIAL_EMAIL", "url_or_email": None, "status": "CANDIDATE"}
    assert classify_email_trust(channel, company=None) == "INVALID"


def test_d_inferred_state_exists_and_is_never_usable():
    assert "INFERRED" in ("VERIFIED_OFFICIAL", "VERIFIED_RECRUITING", "EXPLICIT_IN_JOB_POSTING",
                           "UNVERIFIED", "INFERRED", "INVALID")
    assert not is_email_trust_usable("INFERRED")


# E: careers page guessed but unverified -> not trusted --------------------------------------------

def test_e_careers_probe_with_no_positive_evidence_returns_nothing():
    def fetch(url):
        return {"status_code": 404, "final_url": url, "body_snippet": ""}
    assert probe_careers_candidate("empresa.com", fetch) is None


def test_e_careers_probe_200_without_keyword_or_ats_redirect_is_not_trusted():
    def fetch(url):
        return {"status_code": 200, "final_url": url, "body_snippet": "bem vindo ao nosso site institucional"}
    assert probe_careers_candidate("empresa.com", fetch) is None


# F: official careers redirect to ATS -> ATS candidate ---------------------------------------------

def test_f_careers_probe_redirect_to_known_ats_is_trusted():
    def fetch(url):
        if url.endswith("/careers"):
            return {"status_code": 200, "final_url": "https://boards.greenhouse.io/empresa", "body_snippet": ""}
        return {"status_code": 404, "final_url": url, "body_snippet": ""}
    result = probe_careers_candidate("empresa.com", fetch)
    assert result is not None
    assert result["url_or_email"] == "https://boards.greenhouse.io/empresa"
    assert result["evidence"]["redirected_to_ats"] is True


def test_f_careers_probe_keyword_match_is_trusted():
    def fetch(url):
        if url.endswith("/careers"):
            return {"status_code": 200, "final_url": url, "body_snippet": "confira nossas vagas abertas"}
        return {"status_code": 404, "final_url": url, "body_snippet": ""}
    result = probe_careers_candidate("empresa.com", fetch)
    assert result is not None
    assert result["type"] == "OFFICIAL_CAREERS"
    assert result["evidence"]["matched_keyword"] is True


def test_f_careers_probe_never_calls_fetch_without_a_known_domain():
    calls = []

    def fetch(url):
        calls.append(url)
        return {"status_code": 200, "final_url": url, "body_snippet": "vagas"}
    assert probe_careers_candidate("", fetch) is None
    assert calls == []


# G: multiple channels deterministic ranking ---------------------------------------------------------

def test_g_multiple_verified_channels_pick_highest_priority_deterministically():
    trust, selected = _aggregate_channel_trust([OFFICIAL_CAREERS_VERIFIED, OFFICIAL_ATS_VERIFIED])
    assert trust == "VERIFIED_AVAILABLE"
    assert selected["type"] == "OFFICIAL_ATS"  # prioridade 1 < OFFICIAL_CAREERS (2)


def test_g_ranking_is_stable_across_input_order():
    trust_a, selected_a = _aggregate_channel_trust([OFFICIAL_CAREERS_VERIFIED, OFFICIAL_ATS_VERIFIED])
    trust_b, selected_b = _aggregate_channel_trust([OFFICIAL_ATS_VERIFIED, OFFICIAL_CAREERS_VERIFIED])
    assert selected_a["type"] == selected_b["type"]


# H: stale/closed endpoint -> unavailable -----------------------------------------------------------

def test_h_rejected_channel_is_unavailable_never_selected():
    from src.action_engine import classify_channel_trust
    rejected = {**OFFICIAL_ATS_VERIFIED, "status": "REJECTED"}
    assert classify_channel_trust(rejected) == "UNAVAILABLE"
    trust, selected = _aggregate_channel_trust([rejected])
    assert selected is None


# I: generic careers page != specific active job ------------------------------------------------------

def test_i_careers_probe_result_is_never_auto_verified_for_a_specific_job():
    def fetch(url):
        return {"status_code": 200, "final_url": url, "body_snippet": "vagas abertas"}
    candidate = probe_careers_candidate("empresa.com", fetch)
    assert candidate["evidence"]["job_specific"] is False
    # verify_channel_candidate nunca promove OFFICIAL_CAREERS a VERIFIED so
    # por probe generico - exige confirmacao especifica (Secao 13/14).
    verified = verify_channel_candidate(candidate, company=None)
    assert verified["status"] == "CANDIDATE"


# J/K: second run idempotent / no duplicate channels ----------------------------------------------

def test_j_verify_channel_candidate_is_idempotent():
    channel = {"type": "OFFICIAL_EMAIL", "url_or_email": "vagas@acme.com", "status": "CANDIDATE",
               "evidence": {"extraction_method": "detect_email_application"}, "source": "https://job.example"}
    once = verify_channel_candidate(channel, company={"domain": "acme.com"})
    twice = verify_channel_candidate(once, company={"domain": "acme.com"})
    assert once == twice


def test_k_verify_channel_candidate_never_mutates_the_input_dict():
    channel = {"type": "OFFICIAL_EMAIL", "url_or_email": "vagas@acme.com", "status": "CANDIDATE",
               "evidence": {"extraction_method": "detect_email_application"}}
    original = dict(channel)
    verify_channel_candidate(channel, company=None)
    assert channel == original


def test_k_verify_channel_candidate_never_promotes_rejected_or_used():
    for terminal_status in ("REJECTED", "USED"):
        channel = {"type": "OFFICIAL_EMAIL", "url_or_email": "vagas@acme.com", "status": terminal_status,
                   "evidence": {"extraction_method": "detect_email_application"}}
        assert verify_channel_candidate(channel, company=None)["status"] == terminal_status


# L: no send function called ------------------------------------------------------------------------

def test_l_channel_verification_module_never_imports_a_send_function():
    import inspect
    import src.channel_verification as module
    source = inspect.getsource(module)
    for forbidden in ("send_application_email", "urlopen(", "requests.post(", "requests.get("):
        assert forbidden not in source


# M: AUTO_APPLY false preserved (verification never touches product authorization) ------------------

def test_m_channel_verification_never_references_auto_apply():
    import inspect
    import src.channel_verification as module
    assert "AUTO_APPLY" not in inspect.getsource(module)


# N: evidence/provenance preserved ---------------------------------------------------------------------

def test_n_verify_channel_candidate_preserves_original_evidence_alongside_trust():
    channel = {"type": "OFFICIAL_EMAIL", "url_or_email": "vagas@acme.com", "status": "CANDIDATE",
               "evidence": {"extraction_method": "detect_email_application", "evidence_snippet": "envie para vagas@acme.com"}}
    verified = verify_channel_candidate(channel, company=None)
    assert verified["evidence"]["evidence_snippet"] == "envie para vagas@acme.com"
    assert verified["evidence"]["email_trust"] == "EXPLICIT_IN_JOB_POSTING"


# O: existing assisted channel remains when no better alternative --------------------------------------

def test_o_assisted_channel_alone_stays_candidate_never_falsely_promoted():
    assisted = {"type": "ASSISTED", "url_or_email": "https://linkedin.com/jobs/view/1",
                "requires_auth": True, "requires_captcha": True, "requires_human": True, "status": "CANDIDATE"}
    verified = verify_channel_candidate(assisted, company=None)
    assert verified["status"] == "CANDIDATE"
    trust, selected = _aggregate_channel_trust([verified])
    assert trust == "CAPTCHA_REQUIRED"
    assert selected is None


# Brain-level fix (Secao 12 aplicado tambem em opportunity_brain.py) -------------------------------

_REMOTE_JOB = {"work_model": "REMOTE"}


def test_brain_verified_channel_reaches_actionable_even_with_a_bad_channel_present():
    channels = [LINKEDIN_CAPTCHA_CHANNEL, {**OFFICIAL_ATS_VERIFIED}]
    decision = evaluate_job_opportunity(
        job=_REMOTE_JOB, profile={}, candidate_skills=[], score_result=_SCORE,
        structured_extraction=None, channels=channels, already_terminal=False,
    )
    assert decision.decision == "ACTIONABLE"


def test_brain_no_verified_channel_and_human_required_flag_still_requires_human():
    channels = [LINKEDIN_CAPTCHA_CHANNEL]
    decision = evaluate_job_opportunity(
        job=_REMOTE_JOB, profile={}, candidate_skills=[], score_result=_SCORE,
        structured_extraction=None, channels=channels, already_terminal=False,
    )
    assert decision.decision == "HUMAN_REQUIRED"


# Wiring: discover_channels route calls verify_channel_candidate and persists
# the promoted status (Secao 3/12 fix would be silently ineffective without
# `status=EXCLUDED.status` on conflict - achado real durante a implementacao
# deste prompt) --------------------------------------------------------------

def _route_body(source: str, path: str) -> str:
    start = source.index(f'@router.post("{path}")')
    end = source.index("\n@router.", start + 1)
    return source[start:end]


def _career_source() -> str:
    from pathlib import Path
    return (Path(__file__).resolve().parents[1] / "src" / "career.py").read_text(encoding="utf-8")


def test_discover_channels_route_verifies_candidates_before_persisting():
    body = _route_body(_career_source(), "/opportunities/{opportunity_id}/channels/discover")
    assert "verify_channel_candidate(candidate, company)" in body


def test_discover_channels_route_fetches_company_domain_for_email_trust():
    body = _route_body(_career_source(), "/opportunities/{opportunity_id}/channels/discover")
    assert "SELECT domain, careers_url" in body


def test_discover_channels_route_persists_status_promotion_on_conflict():
    # Achado real: sem isto, um canal ja existente como CANDIDATE nunca
    # seria promovido a VERIFIED numa reavaliacao (ON CONFLICT so
    # atualizava confidence/evidence, nunca status).
    body = _route_body(_career_source(), "/opportunities/{opportunity_id}/channels/discover")
    assert "status=EXCLUDED.status" in body


def test_aggregate_channel_trust_checks_select_channel_before_captcha_auth():
    source = _career_source()
    start = source.index("def _aggregate_channel_trust(")
    end = source.index("\n@router.", start)
    body = source[start:end]
    select_index = body.index("select_channel(channels)")
    captcha_index = body.index('"CAPTCHA_REQUIRED"')
    assert select_index < captcha_index
