from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_find_first_visible_is_shared_between_click_and_lookup() -> None:
    source = _source()
    assert "async def find_first_visible(root: Page | Frame, pattern: str)" in source
    start = source.index("async def click_first_visible(")
    body = source[start : start + 400]
    assert "item = await find_first_visible(root, pattern)" in body


def test_cta_patterns_cover_final_submit_and_next_step() -> None:
    source = _source()
    assert "FINAL_SUBMIT_CTA_PATTERN = (" in source
    assert "enviar candidatura" in source
    assert "NEXT_STEP_CTA_PATTERN = (" in source
    assert r"pr[oó]xima" in source
    assert "MAX_APPLICATION_STEPS = 6" in source


def test_execute_application_queue_advances_through_multiple_steps() -> None:
    source = _source()
    start = source.index("async def execute_application_queue(")
    body = source[start : start + 14000]
    assert "async def fill_current_step()" in body
    assert "while not unknown and visible_submit is None and steps_advanced < MAX_APPLICATION_STEPS:" in body
    assert "if not await click_first_visible(page, NEXT_STEP_CTA_PATTERN):" in body
    assert "steps_advanced += 1" in body


def test_unknown_required_field_stops_advancing_even_mid_flow() -> None:
    """Nunca avança pra próxima etapa (ou clica em nada) por cima de um campo
    obrigatório sem resposta comprovada - a checagem de seguranca do
    UNKNOWN_FIELD continua valendo em qualquer etapa, não só na primeira."""
    source = _source()
    start = source.index("async def execute_application_queue(")
    body = source[start : start + 14000]
    assert "while not unknown and visible_submit is None" in body
    assert 'application["status"] = "MANUAL_REQUIRED"' in body


def test_steps_advanced_is_audited() -> None:
    source = _source()
    assert 'event("APPLICATION_STEPS_ADVANCED", application_id=application["id"], steps=steps_advanced)' in source
