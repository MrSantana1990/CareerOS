"""Google Sign-In allowlist (fail-closed) - achado real: sem uma
allowlist explicita, QUALQUER conta Google com e-mail verificado ganhava
acesso automatico ao mesmo painel/dados compartilhados (nao ha
isolamento por usuario ainda). google_login_allowlist deve ser vazia por
padrao (nega tudo), nunca aceitar tudo por padrao."""

from src.config import Settings


def test_allowlist_is_empty_by_default_fail_closed():
    settings = Settings(google_login_allowed_emails="")
    assert settings.google_login_allowlist == set()


def test_allowlist_parses_comma_separated_emails_case_insensitively():
    settings = Settings(google_login_allowed_emails="Rodolfo@Example.com, outra@pessoa.com")
    assert settings.google_login_allowlist == {"rodolfo@example.com", "outra@pessoa.com"}


def test_allowlist_ignores_blank_entries_and_surrounding_whitespace():
    settings = Settings(google_login_allowed_emails=" a@b.com ,, ,c@d.com,")
    assert settings.google_login_allowlist == {"a@b.com", "c@d.com"}
