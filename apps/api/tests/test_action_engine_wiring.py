from pathlib import Path


def _career_source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "career.py").read_text(encoding="utf-8")


def _route_body(source: str, path: str) -> str:
    start = source.index(f'@router.post("{path}")')
    end = source.index("\n@router.", start + 1)
    return source[start:end]


def test_action_plan_route_never_calls_a_real_send_or_submit_function():
    # Secao 26/38: sempre DRY RUN - nenhuma CHAMADA (nao so mencao em texto/
    # docstring) a send_application_email, Gmail, ou automacao de browser
    # pode existir neste endpoint.
    body = _route_body(_career_source(), "/opportunities/{opportunity_id}/action-plan")
    forbidden_calls = ("send_application_email(", "gmail.users(", "requests.post(",
                       "urlopen(", "playwright.")
    lowered = body.lower()
    for term in forbidden_calls:
        assert term.lower() not in lowered, f"achou chamada proibida de execucao real: {term}"


def test_action_plan_route_uses_action_policy_and_persists_plan_on_opportunity():
    body = _route_body(_career_source(), "/opportunities/{opportunity_id}/action-plan")
    assert "evaluate_action_policy(" in body
    assert "build_application_plan(" in body
    assert '"action_plan": plan' in body


def test_action_plan_route_reuses_score_v2_resume_router_never_reimplements():
    body = _route_body(_career_source(), "/opportunities/{opportunity_id}/action-plan")
    assert "route_resume(dict(job), resumes)" in body


def test_action_plan_route_checks_duplicate_before_policy():
    body = _route_body(_career_source(), "/opportunities/{opportunity_id}/action-plan")
    duplicate_idx = body.index("duplicate_exists")
    policy_idx = body.index("policy = evaluate_action_policy(")
    assert duplicate_idx < policy_idx


def test_action_plan_route_reads_product_authorization_from_environment():
    body = _route_body(_career_source(), "/opportunities/{opportunity_id}/action-plan")
    assert "environment_auto_apply_enabled_for_api()" in body


def test_environment_auto_apply_enabled_for_api_defaults_safe():
    source = _career_source()
    start = source.index("def environment_auto_apply_enabled_for_api()")
    end = source.index("\n\n", start)
    body = source[start:end]
    assert 'os.getenv("AUTO_APPLY_ENABLED", "false")' in body


def test_action_plan_route_creates_profile_language_intervention_when_missing():
    body = _route_body(_career_source(), "/opportunities/{opportunity_id}/action-plan")
    assert "assess_language_status(profile)" in body
    assert '"deduplication_key": "profile:language_declaration"' in body


def test_intervention_input_accepts_opportunity_without_application():
    from src.career import InterventionInput
    payload = InterventionInput(executor_id="action-engine", reason="MATERIAL_UNKNOWN",
                                 title="x" * 5, instructions="y" * 5)
    assert payload.application_id is None
    assert payload.opportunity_id is None


def test_intervention_input_accepts_new_action_engine_reasons():
    from src.career import InterventionInput
    for reason in ("AUTH_REQUIRED", "MISSING_PROFILE_DATA", "SENSITIVE_FIELD_REQUIRED",
                   "MATERIAL_UNKNOWN", "FINAL_APPROVAL"):
        InterventionInput(executor_id="action-engine", reason=reason, title="x" * 5, instructions="y" * 5)
