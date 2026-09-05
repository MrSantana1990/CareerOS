import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "catho_killer_questions_sample.json"


def _load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_preserves_all_thirteen_real_captured_questions() -> None:
    data = _load()
    assert len(data["questions"]) == 13
    assert all(q["text"] and q["classification"] for q in data["questions"])


def test_fixture_classifications_use_only_known_categories() -> None:
    data = _load()
    allowed = {"AUTO_ANSWERABLE", "USER_REQUIRED", "BLOCKING"}
    assert all(q["classification"] in allowed for q in data["questions"])


def test_fixture_never_marks_sensitive_pii_as_auto_answerable() -> None:
    # CPF nunca deve ser AUTO_ANSWERABLE, mesmo que o dado exista em algum
    # lugar - e PII sensivel, decisao sempre humana.
    data = _load()
    cpf_questions = [q for q in data["questions"] if "cpf" in q["text"].lower()]
    assert cpf_questions
    assert all(q["classification"] == "USER_REQUIRED" for q in cpf_questions)
