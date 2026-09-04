from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_the_recurring_scheduler_uses_a_light_scan_window_not_the_deep_catchup_one() -> None:
    # Achado real em produção: o ciclo agendado (a cada 10 minutos) chamava
    # scan_recruitment_mail com os mesmos parâmetros de um catch-up
    # completo (90 dias, 250 resultados) - o mesmo custo de cota pra
    # sempre, mesmo sem e-mail novo nenhum. Isso estourou a cota "Units
    # per minute" do Gmail e deixou 13 dias sem nenhum scan bem-sucedido,
    # incluindo um convite de entrevista real que ficou sem resposta
    # detectada todo esse tempo.
    source = _source()
    start = source.index("async def google_mail_scheduler() -> None:")
    end = source.index("\n\n\n@app.on_event(\"startup\")")
    body = source[start:end]
    assert "scan_recruitment_mail, GOOGLE_TOKEN, GOOGLE_INBOX, 7, 40" in body
