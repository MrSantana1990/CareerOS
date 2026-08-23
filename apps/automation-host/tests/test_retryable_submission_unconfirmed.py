from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_manual_required_from_an_unconfirmed_submission_is_retryable() -> None:
    # Uma tentativa de envio sem confirmação da plataforma é um caso
    # legítimo de retry - especialmente relevante depois de corrigir a
    # classificação interna/externa: um caso que falhou por classificação
    # errada antes agora tem uma chance real de completar de verdade.
    source = _source()
    start = source.index("def retryable(application: dict) -> bool:")
    end = source.index("\n    pending = sorted(")
    body = source[start:end]
    assert '"sem confirmação da plataforma" in application.get("reason", "")' in body


def test_form_filled_awaiting_a_live_submission_is_retryable() -> None:
    # Achado real em produção: uma sonda segura (confirm_live_submission=false)
    # preenche o formulário de verdade e deixa READY_FOR_REVIEW com motivo
    # "autoenvio desligado" - sem essa condição, uma candidatura real
    # controlada e autorizada explicitamente nunca consegue avançar até o
    # clique final, porque o filtro de elegibilidade a exclui da fila mesmo
    # com application_ids/single_controlled_application_id apontando pra ela.
    source = _source()
    start = source.index("def retryable(application: dict) -> bool:")
    end = source.index("\n    pending = sorted(")
    body = source[start:end]
    assert '"autoenvio desligado" in application.get("reason", "")' in body


def test_unresolved_external_apply_is_retryable_bounded_by_the_attempts_cap() -> None:
    # Achado real: uma candidatura que caiu no motivo genérico "candidatura
    # é externa a esta plataforma..." (ex: o clique falhou tecnicamente, não
    # uma navegação externa de verdade - ver LIVE_CLICK_FAILED) precisa
    # poder ser reexaminada pra diagnóstico, sem contornar o cap de
    # segurança: attempts >= 3 continua bloqueando antes desta condição,
    # então isso não reabre o caso Agibank (attempts já em 3).
    source = _source()
    start = source.index("def retryable(application: dict) -> bool:")
    end = source.index("\n    pending = sorted(")
    body = source[start:end]
    assert '"candidatura é externa a esta plataforma" in application.get("reason", "")' in body
    attempts_cap_index = body.index("if attempts >= 3:")
    new_condition_index = body.index('"candidatura é externa a esta plataforma"')
    assert attempts_cap_index < new_condition_index


def test_any_failed_status_is_retryable_bounded_by_the_attempts_cap() -> None:
    # Achado real: uma candidatura FAILED com motivo genérico ("Falha na
    # preparação: Error.") não era retryable, mesmo depois de instrumentar
    # a exceção real pra diagnóstico (application["prepare_error"]) - sem
    # isso, corrigir a causa raiz e tentar de novo exigiria contornar o
    # cap manualmente. A condição antiga só cobria "TimeoutError"; qualquer
    # FAILED agora é elegível, sempre bounded pelo cap attempts >= 3.
    source = _source()
    start = source.index("def retryable(application: dict) -> bool:")
    end = source.index("\n    pending = sorted(")
    body = source[start:end]
    assert 'if application.get("status") == "FAILED":' in body
    attempts_cap_index = body.index("if attempts >= 3:")
    failed_condition_index = body.index('if application.get("status") == "FAILED":')
    assert attempts_cap_index < failed_condition_index
