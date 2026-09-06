from datetime import UTC, datetime, timedelta

from src.google_career import _reply_classification, follow_up_status


def test_auto_submitted_header_is_never_a_recruiter_response() -> None:
    # RFC 3834: o jeito confiavel de identificar resposta automatica,
    # melhor que adivinhar por assunto.
    state, confidence, _ = _reply_classification(
        "no-reply@empresa.com", "Re: Candidatura", "corpo qualquer", "auto-replied"
    )
    assert state == "AUTO_REPLY"
    assert confidence >= 90


def test_mailer_daemon_sender_is_delivery_failure_not_recruiter_response() -> None:
    state, _, _ = _reply_classification(
        "Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
        "Delivery Status Notification (Failure)", "corpo", ""
    )
    assert state == "DELIVERY_FAILURE"


def test_undelivered_mail_subject_is_delivery_failure() -> None:
    state, _, _ = _reply_classification(
        "postmaster@empresa.com", "Undelivered Mail Returned to Sender", "corpo", ""
    )
    assert state == "DELIVERY_FAILURE"


def test_out_of_office_subject_is_auto_reply_not_recruiter_response() -> None:
    state, _, _ = _reply_classification(
        "recrutador@empresa.com", "Out of Office", "Estarei ausente até dia 10.", ""
    )
    assert state == "AUTO_REPLY"


def test_genuine_interview_invite_is_interview_request() -> None:
    state, _, _ = _reply_classification(
        "recrutador@empresa.com", "Convite para entrevista", "Gostaríamos de agendar uma entrevista.", ""
    )
    assert state == "INTERVIEW_REQUEST"


def test_genuine_recruiter_contact_is_recruiter_response() -> None:
    state, _, _ = _reply_classification(
        "recrutador@empresa.com", "Contato sobre uma vaga", "Vi seu perfil e temos uma oportunidade.", ""
    )
    assert state == "RECRUITER_RESPONSE"


def test_genuine_rejection_is_rejection_not_recruiter_response() -> None:
    state, _, _ = _reply_classification(
        "recrutador@empresa.com", "Retorno sobre sua candidatura", "Não seguiremos com o processo.", ""
    )
    assert state == "REJECTION"


def test_follow_up_not_eligible_before_minimum_days() -> None:
    sent_at = datetime(2026, 9, 6, 8, 58, 46, tzinfo=UTC)
    now = sent_at + timedelta(days=1)
    result = follow_up_status(sent_at, now)
    assert result["eligible"] is False
    assert result["days_remaining"] >= 5


def test_follow_up_eligible_after_minimum_days() -> None:
    sent_at = datetime(2026, 9, 6, 8, 58, 46, tzinfo=UTC)
    now = sent_at + timedelta(days=7)
    result = follow_up_status(sent_at, now)
    assert result["eligible"] is True
    assert result["days_remaining"] == 0
