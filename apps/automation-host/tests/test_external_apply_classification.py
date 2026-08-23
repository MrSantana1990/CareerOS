from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_classify_application_cta_exists_and_checks_cross_origin_links() -> None:
    source = _source()
    start = source.index("async def classify_application_cta(")
    end = source.index("\nasync def follow_external_apply(")
    body = source[start:end]
    assert 'if tag_name != "a":' in body
    assert "return \"INTERNAL_APPLY\"" in body
    assert 'urlparse(target).netloc != urlparse(current_page_url).netloc' in body
    assert 'return "EXTERNAL_APPLY"' in body


def test_follow_external_apply_never_treats_the_click_as_a_form_submission() -> None:
    source = _source()
    start = source.index("async def follow_external_apply(")
    end = source.index("\ndef remember_layout(")
    body = source[start:end]
    assert "opened_pages = [candidate for candidate in browser.pages if candidate not in pages_before]" in body
    assert "await page.goto(urljoin(page.url, href)" in body


def test_final_submit_search_classifies_before_treating_a_match_as_submit() -> None:
    # Achado real em produção: um <a href> pra outro domínio (candidatura
    # externa do LinkedIn) foi tratado como SUBMIT_ACTION só por bater no
    # padrão de texto ("Candidatar-se"), clicado, e não confirmado -
    # MANUAL_REQUIRED honesto, mas pela classificação errada. Corrigido:
    # a busca do botão final classifica antes de decidir o que fazer.
    source = _source()
    start = source.index("visible_submit = None")
    end = source.index("if external_apply_hops:")
    body = source[start:end]
    assert 'await classify_application_cta(candidate, page.url) == "EXTERNAL_APPLY"' in body
    assert "page = await follow_external_apply(page, browser, candidate)" in body
    assert "visible_submit = candidate" in body
    # visible_submit só é atribuído no ramo que já excluiu EXTERNAL_APPLY -
    # nunca a partir de um link de outro domínio.
    external_branch_end = body.index("continue", body.index("EXTERNAL_APPLY"))
    assert "visible_submit = candidate" not in body[: external_branch_end]


def test_external_hops_are_recorded_not_silently_dropped() -> None:
    source = _source()
    start = source.index("visible_submit = None")
    end = source.index("if external_apply_hops:")
    body = source[start:end]
    assert "external_apply_hops.append(hop)" in body
    assert '"target_domain": urlparse(urljoin(page.url, href or ""))' in body
    assert 'event("EXTERNAL_APPLY_LINK_FOLLOWED"' in body


def test_external_hops_still_count_toward_the_max_steps_safety_bound() -> None:
    # Sem isso, uma cadeia de redirecionamentos externos poderia rodar
    # indefinidamente em vez de eventualmente cair no caminho honesto de
    # "botão final não localizado"/MANUAL_REQUIRED.
    source = _source()
    start = source.index("visible_submit = None")
    end = source.index("if external_apply_hops:")
    body = source[start:end]
    external_section = body[body.index("EXTERNAL_APPLY"):body.index("visible_submit = candidate")]
    assert "steps_advanced += 1" in external_section
