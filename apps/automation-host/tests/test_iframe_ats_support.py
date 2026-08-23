from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_search_roots_checks_each_frame_not_just_the_top_page() -> None:
    source = _source()
    assert "async def search_roots(page: Page)" in source
    # a pagina principal pode NAO estar no dominio do ATS quando a empresa
    # embute o board num iframe do proprio site — por isso a checagem tem
    # que olhar a URL de cada frame, nao so page.url.
    assert "detect_ats(page.url)" in source
    assert "detect_ats(frame.url)" in source
    assert "page.frames[1:]" in source


def test_cta_and_submit_lookup_use_search_roots() -> None:
    source = _source()
    # click_first_visible e a inspeção prévia percorrem as raízes (page + iframes de ATS conhecido).
    assert "for root in await search_roots(page):" in source
    assert source.count("root.get_by_role(") >= 3
    # botão final de envio também percorre as raízes antes de decidir can_submit,
    # via find_first_visible (mesma busca robusta usada pelo CTA inicial).
    assert "visible_submit = await find_first_visible(root, FINAL_SUBMIT_CTA_PATTERN)" in source


def test_form_filling_functions_operate_on_a_root_not_just_the_top_page() -> None:
    source = _source()
    assert "async def fill_known_fields(root: Page | Frame, profile: ProfessionalProfile)" in source
    assert "async def ai_fill_simple_questions(root: Page | Frame, profile: ProfessionalProfile, application: dict)" in source
    assert "async def required_unknown_fields(root: Page | Frame)" in source
    # o preenchimento agrega resultados de todas as raízes antes de decidir o próximo passo,
    # em cada etapa do formulário (fill_current_step busca raízes frescas a cada chamada,
    # porque clicar em "próxima etapa" pode mudar os frames disponíveis).
    assert "roots = await search_roots(page)" in source
    assert "for root in await search_roots(page):\n                    filled.extend(await fill_known_fields(root, effective_profile))" in source


def test_detected_ats_checks_every_root_not_just_the_top_url() -> None:
    source = _source()
    # a mesma logica de "olhar cada frame" vale para a deteccao/observabilidade,
    # senao o caso mais comum (ATS embutido em iframe do site da empresa) nunca seria marcado.
    assert "next((match for root in roots if (match := detect_ats(root.url))), None)" in source
    assert 'application["detected_ats"] = ats_match.adapter if ats_match else None' in source
    assert 'application["detected_ats_account"] = ats_match.account_key if ats_match else None' in source
    assert "await suggest_source_connection(ats_match)" in source


def test_source_suggestion_always_starts_disabled() -> None:
    source = _source()
    assert '"enabled": False,' in source
    assert "async def suggest_source_connection(ats_match: ATSMatch)" in source
    assert 'CAREER_API_URL + "/api/v1/sources"' in source
