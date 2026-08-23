from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_a_javascript_void_href_never_reaches_page_goto() -> None:
    # Achado real em produção: o botão "Candidatar-me" de uma vaga real do
    # InfoJobs tem href="javascript:void(0)" (placeholder de botão
    # JS-driven, não um link de verdade). O código tratava qualquer href
    # não-vazio como navegável e chamava page.goto(action_href) sem
    # proteção - Playwright rejeita com net::ERR_ABORTED, terminando a
    # candidatura inteira em FAILED. Um href "javascript:" precisa ser
    # tratado como ausente, não como um destino real.
    source = _source()
    start = source.index("action_href = await candidate_link.get_attribute(\"href\")")
    end = source.index("action_clicked = await click_first_visible(page, EXTERNAL_APPLY_CTA_PATTERN)")
    body = source[start:end]
    assert 'action_href.strip().lower().startswith("javascript:")' in body
    assert "action_href = None" in body
