from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_main_imports_evidence_check() -> None:
    source = _source()
    assert "from .evidence_check import is_evidence_grounded" in source


def test_ai_form_fill_rejects_ungrounded_answers() -> None:
    source = _source()
    start = source.index("async def ai_fill_simple_questions(")
    body = source[start : start + 8000]
    assert "grounded = is_evidence_grounded(evidence, payload_data[\"resume\"]" in body
    assert "or not grounded" in body


def test_ai_advice_rejects_ungrounded_answers() -> None:
    source = _source()
    start = source.index("async def local_ai_advice(")
    body = source[start : start + 2000]
    assert "grounded = is_evidence_grounded(evidence_text" in body
    assert 'decision["reason"] = "Evidência citada não foi encontrada no perfil verificado."' in body
