import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.email_discovery import detect_email_application  # noqa: E402


def test_detects_clear_email_application_instruction() -> None:
    text = "Interessados devem enviar o currículo para vagas@empresa.com.br com urgência."
    result = detect_email_application(text)
    assert result is not None
    assert result.email == "vagas@empresa.com.br"


def test_extracts_instructed_subject() -> None:
    text = (
        'Envie seu currículo para rh@empresa.com com o assunto: "Vaga Analista de Suporte N3"'
    )
    result = detect_email_application(text)
    assert result is not None
    assert result.subject == "Vaga Analista de Suporte N3"


def test_english_instruction_is_also_detected() -> None:
    text = "Please email your resume to jobs@company.com to apply."
    result = detect_email_application(text)
    assert result is not None
    assert result.email == "jobs@company.com"


def test_no_email_present_returns_none() -> None:
    assert detect_email_application("Envie seu currículo pelo formulário do site.") is None


def test_email_without_apply_instruction_is_ignored() -> None:
    text = "Dúvidas sobre a vaga? Fale com nosso time em contato@empresa.com."
    assert detect_email_application(text) is None


def test_no_reply_email_is_rejected() -> None:
    text = "Envie seu currículo para noreply@empresa.com para participar do processo."
    assert detect_email_application(text) is None


def test_picks_email_closest_to_the_instruction_when_multiple_exist() -> None:
    text = (
        "Sobre a empresa, contato geral: institucional@empresa.com. "
        "Para se candidatar, envie seu currículo para vagas@empresa.com agora."
    )
    result = detect_email_application(text)
    assert result is not None
    assert result.email == "vagas@empresa.com"


def test_empty_text_returns_none() -> None:
    assert detect_email_application("") is None


def test_context_captures_surrounding_text() -> None:
    text = "Para essa oportunidade, envie seu currículo para vagas@empresa.com o quanto antes."
    result = detect_email_application(text)
    assert result is not None
    assert "envie seu currículo" in result.context.lower()
