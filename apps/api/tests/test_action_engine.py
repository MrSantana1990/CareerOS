from src.action_engine import (assess_language_status, build_application_plan,
                                classify_channel_trust, classify_profile_completeness,
                                classify_sensitive_field, classify_skill_verification,
                                evaluate_action_policy, is_profile_completeness_sufficient,
                                select_channel)

PROFILE_COMPLETE = {
    "city": "Campinas", "state": "SP", "work_models": ["REMOTE"], "target_roles": ["DBA"],
    "language_levels": {"English": "basic"}, "salary_expectation": "8000",
    "approved_answers": {"nome completo": "Rodolfo Santana", "e-mail": "x@x.com"},
}
SKILLS_DECLARED = [{"name": "SQL Server", "verified": False, "evidence_count": 0}]
RESUME_APPROVED = [{"id": "r1", "sha256": "abc", "approved_at": "2026-01-01T00:00:00Z", "active": True}]


def _base_policy(**overrides):
    defaults = dict(brain_decision="ACTIONABLE", resume_available=True,
                    profile_completeness_sufficient=True, channel_trust="VERIFIED_AVAILABLE",
                    product_auto_apply_enabled=False)
    defaults.update(overrides)
    return evaluate_action_policy(**defaults)


# A: Brain ACTIONABLE != automatic submit ------------------------------------------------

def test_a_actionable_without_product_authorization_requires_human_approval():
    result = _base_policy(product_auto_apply_enabled=False)
    assert result.action_decision != "POLICY_ACTION_ALLOWED"
    assert result.action_decision == "HUMAN_APPROVAL_REQUIRED"
    assert "FINAL_APPROVAL" in result.human_requirements


def test_a_actionable_with_all_gates_and_authorization_allows_policy_action():
    result = _base_policy(product_auto_apply_enabled=True)
    assert result.autonomy_class == "POLICY_ACTION"
    assert result.action_decision == "POLICY_ACTION_ALLOWED"


# B: profile incomplete blocks POLICY_ACTION ----------------------------------------------

def test_b_incomplete_profile_blocks_policy_action_even_when_authorized():
    result = _base_policy(product_auto_apply_enabled=True, profile_completeness_sufficient=False)
    assert result.action_decision == "HUMAN_APPROVAL_REQUIRED"
    assert "PROFILE_COMPLETENESS" in result.human_requirements


def test_b_real_profile_language_levels_empty_is_reported_missing():
    report = classify_profile_completeness({"language_levels": {}}, [], [])
    assert report["languages"] == "MISSING"
    assert is_profile_completeness_sufficient(report) is False


# C: explicit language unknown -> Human (covered at Brain layer; Action Engine honors HUMAN_REQUIRED) --

def test_c_brain_human_required_propagates_to_action_engine():
    result = evaluate_action_policy(brain_decision="HUMAN_REQUIRED", unknowns=["language_level_unknown"])
    assert result.autonomy_class == "HUMAN_REQUIRED"
    assert result.action_decision == "HUMAN_APPROVAL_REQUIRED"
    assert "language_level_unknown" in result.human_requirements


# D/E: verified official email accepted / inferred email rejected -------------------------

def test_d_verified_official_channel_is_selected():
    channels = [{"type": "OFFICIAL_EMAIL", "status": "VERIFIED", "requires_auth": False,
                 "requires_captcha": False, "requires_human": False}]
    assert classify_channel_trust(channels[0]) == "VERIFIED_AVAILABLE"
    assert select_channel(channels) is channels[0]


def test_e_unverified_candidate_channel_never_selected():
    # Secao 6: nunca inferir e-mail - um canal ainda CANDIDATE (nao
    # verificado) nao pode ser escolhido como oficial.
    channels = [{"type": "OFFICIAL_EMAIL", "status": "CANDIDATE", "requires_auth": False,
                 "requires_captcha": False, "requires_human": False}]
    assert classify_channel_trust(channels[0]) == "UNVERIFIABLE"
    assert select_channel(channels) is None


# F: duplicate application prevented --------------------------------------------------------

def test_f_duplicate_application_prevented():
    result = _base_policy(duplicate_exists=True)
    assert result.action_decision == "NO_ACTION"
    assert "duplicate_application_prevented" in result.reasons


# G: Deutsche Bank no resend (Brain already returns ACTIONABLE/ALREADY_APPLIED; Action Engine
# must still never allow a duplicate real send for it) --------------------------------------

def test_g_already_applied_opportunity_never_gets_policy_action_allowed_via_duplicate_check():
    result = _base_policy(product_auto_apply_enabled=True, duplicate_exists=True)
    assert result.action_decision != "POLICY_ACTION_ALLOWED"
    assert result.action_decision == "NO_ACTION"


# H: CAPTCHA -> Human -------------------------------------------------------------------------

def test_h_captcha_required_channel_forces_human_execution():
    channel = {"status": "VERIFIED", "requires_captcha": True}
    assert classify_channel_trust(channel) == "CAPTCHA_REQUIRED"
    result = _base_policy(channel_trust="CAPTCHA_REQUIRED")
    assert result.action_decision == "HUMAN_EXECUTION_REQUIRED"
    assert "CAPTCHA" in result.human_requirements


# I: MFA -> Human (modeled as AUTH_REQUIRED channel trust, same family as LinkedIn/InfoJobs) ---

def test_i_auth_required_channel_forces_human_execution():
    channel = {"status": "VERIFIED", "requires_auth": True}
    assert classify_channel_trust(channel) == "AUTH_REQUIRED"
    result = _base_policy(channel_trust="AUTH_REQUIRED")
    assert result.action_decision == "HUMAN_EXECUTION_REQUIRED"
    assert "AUTH_REQUIRED" in result.human_requirements


# J: attempt cap respected ---------------------------------------------------------------------

def test_j_attempt_cap_reached_blocks_before_channel_check():
    result = _base_policy(attempt_cap_reached=True)
    assert result.action_decision == "BLOCKED"
    assert "ATTEMPT_CAP" in result.blocked_gates


# K: sensitive missing field -> Human ------------------------------------------------------------

def test_k_missing_sensitive_field_requires_human():
    assert classify_sensitive_field("cpf", None) == "MISSING_USER_REQUIRED"
    result = _base_policy(sensitive_missing=["cpf"])
    assert result.action_decision == "HUMAN_APPROVAL_REQUIRED"
    assert "cpf" in result.human_requirements


def test_k_present_sensitive_field_is_known_sensitive_not_autofilled_by_default():
    assert classify_sensitive_field("cpf", "123.456.789-00") == "KNOWN_SENSITIVE"


def test_k_present_safe_field_is_known_safe():
    assert classify_sensitive_field("full_name", "Rodolfo Santana") == "KNOWN_SAFE"


# L: salary below floor -> Block -----------------------------------------------------------------

def test_l_salary_below_floor_blocks():
    result = _base_policy(salary_known=True, salary_below_floor=True)
    assert result.action_decision == "BLOCKED"
    assert "salary_below_floor" in result.blocked_gates


# M: salary unknown not fabricated ----------------------------------------------------------------

def test_m_salary_unknown_never_fabricated_into_a_block():
    result = _base_policy(salary_known=False, salary_below_floor=True, product_auto_apply_enabled=True)
    # salary_known=False significa que nao ha piso real conhecido - nunca inventamos um bloqueio.
    assert "salary_below_floor" not in result.blocked_gates


# N: resume unavailable -> Human/Prepare -----------------------------------------------------------

def test_n_resume_unavailable_actionable_requires_human():
    result = _base_policy(resume_available=False)
    assert result.action_decision == "HUMAN_APPROVAL_REQUIRED"
    assert "RESUME_SELECTION" in result.human_requirements


def test_n_resume_unavailable_prepare_stays_prepare_only():
    result = _base_policy(brain_decision="PREPARE", resume_available=False)
    assert result.action_decision == "PREPARE_ONLY"


# O: correct resume hash persisted (Application Plan carries it through) --------------------------

def test_o_application_plan_carries_resume_hash():
    policy = _base_policy(product_auto_apply_enabled=True)
    resume = {"id": "r1", "sha256": "deadbeef"}
    plan = build_application_plan(opportunity_id="op1", job_id="job1", channel=None,
                                   resume=resume, policy_result=policy)
    assert plan["resume_hash"] == "deadbeef"
    assert plan["resume_version_id"] == "r1"


def test_o_application_plan_is_json_serializable_with_real_uuid_resume_id():
    # Bug real encontrado em producao (Prompt 5): resume["id"] vem do
    # Postgres como um objeto uuid.UUID de verdade (nao uma string) via
    # asyncpg/SQLAlchemy - json.dumps(plan) quebrava com "Object of type
    # UUID is not JSON serializable" para toda Opportunity com Job (as 10
    # JOB_APPLICATION reais na amostra de validacao).
    import json
    import uuid

    policy = _base_policy(product_auto_apply_enabled=True)
    resume = {"id": uuid.uuid4(), "sha256": "deadbeef"}
    plan = build_application_plan(opportunity_id="op1", job_id="job1", channel=None,
                                   resume=resume, policy_result=policy)
    assert isinstance(plan["resume_version_id"], str)
    json.dumps(plan)  # nao pode levantar TypeError


# P: Application Plan idempotent -------------------------------------------------------------------

def test_p_application_plan_idempotency_key_is_stable_for_same_inputs():
    policy = _base_policy()
    channel = {"type": "OFFICIAL_EMAIL", "url_or_email": "rh@empresa.com"}
    plan1 = build_application_plan(opportunity_id="op1", job_id=None, channel=channel,
                                    resume=None, policy_result=policy)
    plan2 = build_application_plan(opportunity_id="op1", job_id=None, channel=channel,
                                    resume=None, policy_result=policy)
    assert plan1["idempotency_key"] == plan2["idempotency_key"]


# Q: confirmed requires evidence (channel staleness / trust as a proxy for "no unverified claim") --

def test_q_stale_verified_channel_is_not_treated_as_currently_available():
    from datetime import UTC, datetime, timedelta
    old = datetime.now(UTC) - timedelta(days=200)
    channel = {"status": "VERIFIED", "verified_at": old}
    assert classify_channel_trust(channel) == "STALE"


# R: Watch scheduler recheck no automatic application (Brain WATCH/RECHECK -> AUTO_SAFE only) ------

def test_r_watch_and_recheck_are_auto_safe_never_policy_action():
    for decision in ("WATCH", "RECHECK", "DROP"):
        result = evaluate_action_policy(brain_decision=decision)
        assert result.autonomy_class == "AUTO_SAFE"
        assert result.action_decision != "POLICY_ACTION_ALLOWED"


# S: InfoJobs AUTH regression -----------------------------------------------------------------------

def test_s_infojobs_style_auth_required_channel_never_auto_bypassed():
    channel = {"status": "VERIFIED", "requires_auth": True, "requires_captcha": False}
    assert classify_channel_trust(channel) == "AUTH_REQUIRED"
    assert select_channel([channel]) is None


# T: LinkedIn CAPTCHA regression -----------------------------------------------------------------------

def test_t_linkedin_style_captcha_channel_never_auto_bypassed():
    channel = {"status": "VERIFIED", "requires_captcha": True}
    assert classify_channel_trust(channel) == "CAPTCHA_REQUIRED"
    assert select_channel([channel]) is None


# --- extras: profile completeness / language / skill verification --------------------------------

def test_language_status_flags_intervention_when_missing():
    status = assess_language_status({"language_levels": {}})
    assert status["needs_intervention"] is True
    assert status["intervention_reason"] == "MISSING_PROFILE_DATA"


def test_language_status_no_intervention_when_declared():
    status = assess_language_status({"language_levels": {"English": "advanced"}})
    assert status["needs_intervention"] is False


def test_skill_verification_declared_when_no_evidence_no_verified_flag():
    assert classify_skill_verification({"name": "SQL Server", "verified": False}, evidence_count=0) == "DECLARED"


def test_skill_verification_evidence_backed_when_evidence_exists():
    assert classify_skill_verification({"name": "AWS", "verified": False}, evidence_count=2) == "EVIDENCE_BACKED"


def test_skill_verification_verified_when_flag_true():
    assert classify_skill_verification({"name": "AWS", "verified": True}, evidence_count=0) == "VERIFIED"


def test_profile_completeness_sufficient_when_all_material_dimensions_present():
    report = classify_profile_completeness(PROFILE_COMPLETE, SKILLS_DECLARED, RESUME_APPROVED)
    assert is_profile_completeness_sufficient(report) is True


def test_profile_completeness_resume_inventory_missing_when_no_approved_resume():
    report = classify_profile_completeness(PROFILE_COMPLETE, SKILLS_DECLARED, [])
    assert report["resume_inventory"] == "MISSING"
    assert is_profile_completeness_sufficient(report) is False


def test_profile_completeness_never_invents_experience_education_certifications():
    report = classify_profile_completeness(PROFILE_COMPLETE, SKILLS_DECLARED, RESUME_APPROVED)
    assert report["experience"] == "MISSING"
    assert report["education"] == "MISSING"
    assert report["certifications"] == "MISSING"
