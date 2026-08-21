from src.preparation import application_strategy, idempotency_key, prepare_email_draft, route_resume


def test_resume_router_uses_approved_matching_family():
    resumes = [
        {"family": "GENERAL", "language": "pt-BR", "version": 3, "approved_at": "now", "active": True},
        {"family": "PT_DBA_SQL", "language": "pt-BR", "version": 1, "approved_at": "now", "active": True},
    ]
    assert route_resume({"family": "DBA", "language": "pt-BR"}, resumes)["family"] == "PT_DBA_SQL"


def test_resume_router_rejects_unapproved_files():
    assert route_resume({"family": "DATA"}, [{"family": "PT_DATA", "approved_at": None, "active": True}]) is None


def test_email_is_only_selected_for_published_recipient():
    assert application_strategy({"recruiter_email": "jobs@example.com"}) == "EMAIL"
    assert application_strategy({"application_channel": "GREENHOUSE"}) == "ATS_API"


def test_email_draft_contains_only_grounded_identity_and_job():
    draft = prepare_email_draft(
        {"recruiter_email": "jobs@example.com", "title": "DBA", "company": "Example"},
        {"full_name": "Rodolfo Santana"},
    )
    assert draft.recipient == "jobs@example.com"
    assert "DBA" in draft.subject
    assert "anos" not in draft.body


def test_application_key_is_deterministic():
    assert idempotency_key("org", "job") == idempotency_key("org", "job")
