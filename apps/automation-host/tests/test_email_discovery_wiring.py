from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_main_imports_email_discovery() -> None:
    source = _source()
    assert "from .email_discovery import detect_email_application" in source


def test_opportunity_feedback_surfaces_email_application() -> None:
    source = _source()
    start = source.index("def opportunity_feedback(")
    body = source[start : start + 3000]
    assert "email_instruction = detect_email_application(f\"{title} {body}\")" in body
    assert '"email_application":' in body
