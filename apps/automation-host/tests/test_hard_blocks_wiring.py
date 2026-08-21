from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_opportunity_feedback_uses_shared_hard_blocks_module() -> None:
    source = _source()
    assert "from .hard_blocks import assess_hard_blocks, extract_salary_brl" in source
    assert "def extract_salary_brl(" not in source  # nao deve mais existir cópia local
    assert "hard_block_result = assess_hard_blocks(text, salary)" in source
    assert '"blocks": hard_block_result.blocks,' in source
    assert '"risks": hard_block_result.risks,' in source


def test_inspection_blocks_applications_before_looking_for_cta() -> None:
    source = _source()
    assert 'elif application.get("blocks"):' in source


def test_execution_blocks_applications_before_filling_the_form() -> None:
    source = _source()
    assert 'if application.get("blocks"):' in source
    assert source.count('application["status"] = "BLOCKED"') >= 3
