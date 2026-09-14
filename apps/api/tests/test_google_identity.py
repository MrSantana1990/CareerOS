"""Google Sign-In (Adendo de Autenticacao) - GOOGLE LOGIN != GMAIL
INTEGRATION. A rota POST /auth/google so persiste identidade JA
verificada (issuer/audience/assinatura/nonce conferidos em apps/web
antes de chamar aqui) na tabela `users` JA EXISTENTE (migration 0002) -
nunca uma tabela paralela, nunca recebe/guarda id_token ou access_token
do Google."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.career import GoogleIdentityInput


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "career.py").read_text(encoding="utf-8")


def _route_body() -> str:
    source = _source()
    start = source.index('@router.post("/auth/google")')
    end = source.index('\n@router.post("/profile/resume")', start)
    return source[start:end]


def test_google_identity_input_requires_provider_subject():
    with pytest.raises(ValidationError):
        GoogleIdentityInput(provider_subject="", email="a@b.com", email_verified=True)


def test_google_identity_input_accepts_minimal_valid_payload():
    identity = GoogleIdentityInput(provider_subject="1234567890", email="rodolfo@example.com",
                                   email_verified=True, display_name="Rodolfo Santana")
    assert identity.provider_subject == "1234567890"
    assert identity.email_verified is True


def test_google_identity_input_never_carries_any_google_token_field():
    # Contrato explicito (Secao 6/7): esta rota nunca aceita id_token/access_token -
    # somente os campos ja extraidos e verificados pelo chamador.
    fields = set(GoogleIdentityInput.model_fields)
    for forbidden in ("id_token", "access_token", "refresh_token", "code"):
        assert forbidden not in fields


# E: email nao verificado -> reject -------------------------------------------------------------------------

def test_e_unverified_email_is_rejected_before_any_lookup():
    body = _route_body()
    assert "if not payload.email_verified:" in body
    assert "raise HTTPException(status_code=422" in body
    # o reject acontece ANTES de qualquer SELECT/INSERT/UPDATE na tabela users.
    guard_index = body.index("if not payload.email_verified:")
    first_query_index = body.index("SELECT", guard_index + 1)
    assert guard_index < first_query_index


# F: mesmo Google sub -> mesmo usuario (upsert idempotente por provider_subject) -----------------------------

def test_f_same_provider_subject_resolves_to_the_same_user_first():
    body = _route_body()
    assert "auth_provider='GOOGLE'\n              AND provider_subject=:provider_subject" in body
    # essa checagem por provider_subject roda ANTES da checagem por email (linking) e
    # antes da criacao de um usuario novo - garante que o mesmo sub nunca cria duplicata.
    subject_check_index = body.index("existing_by_subject")
    email_check_index = body.index("linkable = await session.scalar")
    insert_index = body.index("INSERT INTO users")
    assert subject_check_index < email_check_index < insert_index


# Secao 5: linking seguro so quando ainda NAO ha provider vinculado (nunca rouba um vinculo existente) --------

def test_linking_only_applies_to_users_without_any_provider_yet():
    body = _route_body()
    assert "provider_subject IS NULL" in body


def test_new_user_creation_never_defaults_email_verified_to_false():
    body = _route_body()
    # A INSERT sempre grava email_verified=true (chegar ate aqui ja implica o guard
    # inicial ter passado) - nunca deixa uma linha nova com email_verified indefinido/falso.
    insert_start = body.index("INSERT INTO users")
    insert_end = body.index("RETURNING", insert_start)
    assert "true, :avatar_url" in body[insert_start:insert_end]


def test_first_user_in_organization_becomes_owner_others_become_member():
    body = _route_body()
    assert '"OWNER" if is_first_user else "MEMBER"' in body


def test_route_never_logs_or_returns_any_secret_field():
    body = _route_body()
    for forbidden in ("id_token", "access_token", "client_secret", "refresh_token"):
        assert forbidden not in body
