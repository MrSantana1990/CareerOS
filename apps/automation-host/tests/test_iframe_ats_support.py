from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_search_roots_only_expands_for_known_ats() -> None:
    source = _source()
    assert "async def search_roots(page: Page)" in source
    assert "detect_ats(page.url)" in source
    assert "page.frames[1:]" in source


def test_cta_and_submit_lookup_use_search_roots() -> None:
    source = _source()
    # click_first_visible e a inspeção prévia percorrem as raízes (page + iframes de ATS conhecido).
    assert "for root in await search_roots(page):" in source
    assert source.count("root.get_by_role(") >= 4
    # botão final de envio também percorre as raízes antes de decidir can_submit
    assert "for root in await search_roots(page):\n                submit = root.get_by_role" in source


def test_form_filling_functions_operate_on_a_root_not_just_the_top_page() -> None:
    source = _source()
    assert "async def fill_known_fields(root: Page | Frame, profile: ProfessionalProfile)" in source
    assert "async def ai_fill_simple_questions(root: Page | Frame, profile: ProfessionalProfile, application: dict)" in source
    assert "async def required_unknown_fields(root: Page | Frame)" in source
    # o preenchimento agrega resultados de todas as raízes antes de decidir o próximo passo
    assert "for root in await search_roots(page):\n                filled.extend(await fill_known_fields(root, profile))" in source


def test_detected_ats_is_recorded_and_suggested_before_filling() -> None:
    source = _source()
    assert 'application["detected_ats"] = ats_match.adapter if ats_match else None' in source
    assert 'application["detected_ats_account"] = ats_match.account_key if ats_match else None' in source
    assert "await suggest_source_connection(ats_match)" in source


def test_source_suggestion_always_starts_disabled() -> None:
    source = _source()
    assert '"enabled": False,' in source
    assert "async def suggest_source_connection(ats_match: ATSMatch)" in source
    assert 'CAREER_API_URL + "/api/v1/sources"' in source
