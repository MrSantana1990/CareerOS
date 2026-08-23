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


def test_live_click_observes_navigation_before_trusting_it_as_a_real_submit() -> None:
    # Achado real: o botão "Candidatar-se" do LinkedIn não é um <a href>
    # simples - é um <button> cujo clique dispara navegação via JS
    # (window.open ou equivalente). classify_application_cta (inspeção
    # estática, antes do clique) não pega esse caso. A rede de segurança
    # de verdade tem que observar o que o clique realmente fez.
    source = _source()
    start = source.index("if can_submit and live_allowed:")
    end = source.index('            else:\n                application["status"] = "READY_FOR_REVIEW"')
    body = source[start:end]
    assert "opened_pages = [candidate for candidate in browser.pages if candidate not in before_pages]" in body
    assert "navigated_cross_origin = urlparse(page.url).netloc != urlparse(before_submit).netloc" in body
    assert "if opened_pages or navigated_cross_origin:" in body


def test_external_navigation_from_a_live_click_never_calls_submission_confirmed() -> None:
    source = _source()
    start = source.index("if can_submit and live_allowed:")
    end = source.index('            else:\n                application["status"] = "READY_FOR_REVIEW"')
    body = source[start:end]
    external_branch_start = body.index("if opened_pages or navigated_cross_origin:")
    external_branch_end = body.index("continue", external_branch_start)
    external_branch = body[external_branch_start:external_branch_end]
    assert "submission_confirmed(" not in external_branch
    assert "APPLIED" not in external_branch


def test_live_click_keeps_trying_after_an_external_hop_instead_of_giving_up() -> None:
    source = _source()
    start = source.index("if can_submit and live_allowed:")
    end = source.index('            else:\n                application["status"] = "READY_FOR_REVIEW"')
    body = source[start:end]
    assert "await fill_current_step()" in body
    assert 'visible_submit = await find_first_visible(root, FINAL_SUBMIT_CTA_PATTERN)' in body
    assert "live_click_attempts < MAX_APPLICATION_STEPS" in body


def test_unresolved_external_apply_ends_in_manual_required_with_an_honest_reason() -> None:
    source = _source()
    start = source.index("if can_submit and live_allowed:")
    end = source.index('            else:\n                application["status"] = "READY_FOR_REVIEW"')
    body = source[start:end]
    assert "if not resolved:" in body
    assert 'application["status"] = "MANUAL_REQUIRED"' in body
    assert "conclua manualmente no site de destino" in body


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
