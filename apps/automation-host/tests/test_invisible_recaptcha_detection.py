from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_an_invisible_recaptcha_frame_is_reported_honestly_not_as_generic_unconfirmed() -> None:
    # Causa raiz real do Issue #73, confirmada via diagnostico isolado
    # (perfil clonado, sem risco ao ambiente de producao): o clique em
    # "Candidatar-se no site da empresa" nao produz navegacao porque a
    # propria plataforma aciona um reCAPTCHA Enterprise invisivel
    # (google.com/recaptcha/enterprise/anchor, size=invisible) - sem
    # nenhum texto visivel na pagina, entao INTERVENTION_PATTERNS["CAPTCHA"]
    # (que so olha o texto do body) nunca detectava isso. O clique
    # "funciona" tecnicamente (sem excecao), mas a verificacao anti-bot
    # bloqueia a navegacao real. Isso nao deve ser contornado - so
    # reportado honestamente como CAPTCHA, nao como "sem confirmacao"
    # generico.
    source = _source()
    start = source.index("if can_submit and live_allowed:")
    end = source.index('            else:\n                application["status"] = "READY_FOR_REVIEW"')
    body = source[start:end]
    same_origin_start = body.index("resolved = True")
    recaptcha_check_start = body.index('frame.url.lower()', same_origin_start)
    submission_confirmed_start = body.index("await submission_confirmed(page, before_submit)", same_origin_start)
    assert recaptcha_check_start < submission_confirmed_start
    section = body[same_origin_start:submission_confirmed_start]
    assert 'recaptcha_frame = next(' in section
    assert '"recaptcha" in frame.url.lower()' in section
    assert 'await report_intervention(\n                            application, "CAPTCHA"' in section
    assert "nunca tenta contorná-la" in section
