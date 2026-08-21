from src.communications import correlate_message, email_domain, notification_priority


def test_extracts_sender_domain():
    assert email_domain("Recruiter <ana@example.com>") == "example.com"


def test_correlates_by_company_domain():
    application_id, evidence = correlate_message(
        {"sender": "rh@acme.com", "subject": "Entrevista"},
        [{"id": "a1", "company": "Acme", "company_domain": "acme.com", "title": "DBA"}],
    )
    assert application_id == "a1"
    assert "sender_domain" in evidence


def test_ambiguous_match_requires_review():
    application_id, evidence = correlate_message(
        {"sender": "rh@jobs.com", "subject": "Processo"},
        [{"id": "a1", "company_domain": "jobs.com"}, {"id": "a2", "company_domain": "jobs.com"}],
    )
    assert application_id is None
    assert evidence == ["ambiguous"]


def test_interview_is_urgent():
    assert notification_priority("INTERVIEW") == "URGENT"
