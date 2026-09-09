from datetime import UTC, datetime, timedelta

from src.reply_tracking import assess_follow_up_eligibility, classify_application_thread_reply, follow_up_status


def test_auto_submitted_header_is_never_a_recruiter_response() -> None:
    # RFC 3834: o jeito confiavel de identificar resposta automatica,
    # melhor que adivinhar por assunto.
    state, confidence, _ = classify_application_thread_reply(
        "no-reply@empresa.com", "Re: Candidatura", "corpo qualquer", "auto-replied"
    )
    assert state == "AUTO_REPLY"
    assert confidence >= 90


def test_mailer_daemon_sender_is_delivery_failure_not_recruiter_response() -> None:
    state, _, _ = classify_application_thread_reply(
        "Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
        "Delivery Status Notification (Failure)", "corpo", ""
    )
    assert state == "DELIVERY_FAILURE"


def test_undelivered_mail_subject_is_delivery_failure() -> None:
    state, _, _ = classify_application_thread_reply(
        "postmaster@empresa.com", "Undelivered Mail Returned to Sender", "corpo", ""
    )
    assert state == "DELIVERY_FAILURE"


def test_out_of_office_subject_is_auto_reply_not_recruiter_response() -> None:
    state, _, _ = classify_application_thread_reply(
        "recrutador@empresa.com", "Out of Office", "Estarei ausente até dia 10.", ""
    )
    assert state == "AUTO_REPLY"


def test_genuine_interview_invite_is_interview_request() -> None:
    state, _, _ = classify_application_thread_reply(
        "recrutador@empresa.com", "Convite para entrevista", "Gostaríamos de agendar uma entrevista.", ""
    )
    assert state == "INTERVIEW_REQUEST"


def test_genuine_recruiter_contact_is_recruiter_response() -> None:
    state, _, _ = classify_application_thread_reply(
        "recrutador@empresa.com", "Contato sobre uma vaga", "Vi seu perfil e temos uma oportunidade.", ""
    )
    assert state == "RECRUITER_RESPONSE"


def test_genuine_rejection_is_rejection_not_recruiter_response() -> None:
    state, _, _ = classify_application_thread_reply(
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


# Secao 8 (Prompt 6) / Secao 1-4 (Prompt 6.1) - assess_follow_up_eligibility
# (estados ricos, nunca envia). Regressao A-G da Secao 4 do Prompt 6.1.

def test_a_confirmed_no_reply_before_threshold_is_not_eligible_yet() -> None:
    sent_at = datetime(2026, 9, 6, 8, 58, 46, tzinfo=UTC)
    result = assess_follow_up_eligibility(sent_at=sent_at, application_status="CONFIRMED",
                                           thread_state="AWAITING_RESPONSE",
                                           now=sent_at + timedelta(days=2))
    assert result["status"] == "NOT_ELIGIBLE_YET"


def test_b_confirmed_no_reply_after_threshold_is_eligible() -> None:
    sent_at = datetime(2026, 9, 6, 8, 58, 46, tzinfo=UTC)
    result = assess_follow_up_eligibility(sent_at=sent_at, application_status="CONFIRMED",
                                           thread_state="AWAITING_RESPONSE",
                                           now=sent_at + timedelta(days=8))
    assert result["status"] == "ELIGIBLE"


def test_c_confirmed_with_recruiter_reply_is_response_received() -> None:
    sent_at = datetime(2026, 9, 6, 8, 58, 46, tzinfo=UTC)
    result = assess_follow_up_eligibility(sent_at=sent_at, application_status="CONFIRMED",
                                           thread_state="RECRUITER_RESPONSE",
                                           now=sent_at + timedelta(days=8))
    assert result["status"] == "RESPONSE_RECEIVED"


def test_d_rejected_application_is_terminal() -> None:
    sent_at = datetime(2026, 9, 6, 8, 58, 46, tzinfo=UTC)
    result = assess_follow_up_eligibility(sent_at=sent_at, application_status="REJECTED",
                                           thread_state="AWAITING_RESPONSE",
                                           now=sent_at + timedelta(days=10))
    assert result["status"] == "TERMINAL"


def test_e_offer_is_terminal_never_eligible_for_follow_up() -> None:
    sent_at = datetime(2026, 9, 6, 8, 58, 46, tzinfo=UTC)
    result = assess_follow_up_eligibility(sent_at=sent_at, application_status="OFFER",
                                           thread_state="AWAITING_RESPONSE",
                                           now=sent_at + timedelta(days=10))
    assert result["status"] == "TERMINAL"


def test_e_hired_and_withdrawn_are_terminal_if_they_ever_appear() -> None:
    sent_at = datetime(2026, 9, 6, 8, 58, 46, tzinfo=UTC)
    for status in ("HIRED", "WITHDRAWN"):
        result = assess_follow_up_eligibility(sent_at=sent_at, application_status=status,
                                               now=sent_at + timedelta(days=10))
        assert result["status"] == "TERMINAL"


def test_f_auto_reply_never_counts_as_recruiter_response() -> None:
    # Secao 4.F: AUTO_REPLY cai no mesmo caminho de AWAITING_RESPONSE -
    # decidido so pelo prazo, nunca vira RESPONSE_RECEIVED.
    sent_at = datetime(2026, 9, 6, 8, 58, 46, tzinfo=UTC)
    result = assess_follow_up_eligibility(sent_at=sent_at, application_status="CONFIRMED",
                                           thread_state="AUTO_REPLY",
                                           now=sent_at + timedelta(days=2))
    assert result["status"] == "NOT_ELIGIBLE_YET"
    result_after = assess_follow_up_eligibility(sent_at=sent_at, application_status="CONFIRMED",
                                                 thread_state="AUTO_REPLY",
                                                 now=sent_at + timedelta(days=8))
    assert result_after["status"] == "ELIGIBLE"


def test_g_bounce_never_counts_as_recruiter_response_blocks_instead() -> None:
    sent_at = datetime(2026, 9, 6, 8, 58, 46, tzinfo=UTC)
    result = assess_follow_up_eligibility(sent_at=sent_at, application_status="CONFIRMED",
                                           thread_state="DELIVERY_FAILURE",
                                           now=sent_at + timedelta(days=8))
    assert result["status"] == "BLOCKED"


def test_not_yet_sent_application_is_not_applicable() -> None:
    result = assess_follow_up_eligibility(sent_at=None, application_status="PREPARING")
    assert result["status"] == "NOT_APPLICABLE"


def test_application_status_already_recruiter_response_short_circuits_thread_check() -> None:
    # O proprio status da candidatura ja e evidencia mais forte que uma
    # nova checagem de thread - nao precisa do thread_state confirmar de novo.
    sent_at = datetime(2026, 9, 6, 8, 58, 46, tzinfo=UTC)
    result = assess_follow_up_eligibility(sent_at=sent_at, application_status="INTERVIEW", thread_state=None)
    assert result["status"] == "RESPONSE_RECEIVED"
