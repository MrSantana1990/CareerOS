from pathlib import Path


def _main_source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def _google_career_source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "google_career.py").read_text(encoding="utf-8")


def test_send_application_email_uses_messages_send_not_drafts_create() -> None:
    # CONFIRMED por e-mail exige envio real confirmado pelo provedor
    # (message_id de messages().send()), nunca so um draft_id.
    source = _google_career_source()
    start = source.index("def send_application_email(")
    end = source.index("\ndef ", start + 1)
    body = source[start:end]
    assert "gmail.users().messages().send(" in body
    assert '"message_id": sent["id"]' in body
    assert '"thread_id": sent.get("threadId")' in body


def test_application_email_send_endpoint_requires_explicit_confirm_send() -> None:
    # Nunca automatico/em lote - cada envio real exige confirm_send=true
    # explicito nesta chamada especifica.
    source = _main_source()
    assert "confirm_send: bool = False" in source
    start = source.index('@app.post("/google/application-send")')
    body = source[start:start + 1500]
    assert "if not request.confirm_send:" in body
    assert "send_application_email" in body
    assert 'event("APPLICATION_EMAIL_SENT", message_id=result["message_id"])' in body
