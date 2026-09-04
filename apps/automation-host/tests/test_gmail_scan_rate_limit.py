from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "google_career.py").read_text(encoding="utf-8")


def test_already_classified_non_questionnaire_messages_are_not_refetched() -> None:
    # Achado real em produção: cada rodada (a cada 10 minutos) buscava o
    # corpo completo de TODAS as ~350 mensagens do período de 90 dias,
    # mesmo as já classificadas em rodadas anteriores - isso estourava a
    # cota "Units per minute per user" do Gmail (HttpError 403
    # rateLimitExceeded), derrubando o scan inteiro por 13 dias seguidos
    # sem nenhuma resposta de recrutador sendo detectada. Mensagens
    # QUESTIONNAIRE continuam sendo revalidadas (têm lógica própria de
    # expiração), as demais reaproveitam o item já classificado.
    source = _source()
    start = source.index("def scan_recruitment_mail(")
    end = source.index("def create_reply_draft(")
    body = source[start:end]
    assert 'cached = previous.get(reference["id"])' in body
    assert 'cached.get("category") != "QUESTIONNAIRE"' in body
    assert 'by_id[cached["message_id"]] = cached' in body


def test_message_fetch_retries_with_backoff_on_rate_limit() -> None:
    source = _source()
    start = source.index("def _get_message_with_backoff(")
    end = source.index("def scan_recruitment_mail(")
    body = source[start:end]
    assert "exc.resp is not None and exc.resp.status in (403, 429)" in body
    assert "time.sleep(2 ** attempt)" in body
    assert "if not is_rate_limited or attempt == attempts - 1:" in body


def test_scan_recruitment_mail_uses_the_backoff_helper_not_a_raw_get_call() -> None:
    source = _source()
    start = source.index("def scan_recruitment_mail(")
    end = source.index("def create_reply_draft(")
    body = source[start:end]
    assert "message = _get_message_with_backoff(gmail, reference[\"id\"])" in body
