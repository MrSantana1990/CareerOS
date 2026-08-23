from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_dismiss_overlays_recognizes_the_infojobs_cookie_banner() -> None:
    # Achado real em produção: o banner de cookies do InfoJobs usa os
    # botões "Aceitar"/"Disagree and close", nenhum dos quais batia no
    # padrão existente (ok entendi/entendi/continuar sem/agora não). O
    # banner ficava coberto a página e nunca era dispensado, fazendo o
    # clique final no CTA real expirar (Locator.click timeout) em vez de
    # completar - um caso real de "candidatura externa" era na verdade
    # esse overlay nunca dispensado.
    source = _source()
    start = source.index("async def dismiss_overlays(page: Page) -> list[str]:")
    end = source.index("\nasync def search_roots(")
    body = source[start:end]
    assert "aceitar" in body.lower()
    assert "disagree and close" in body.lower()
