from pathlib import Path

import pytest
from pydantic import ValidationError

from src.career import InterventionInput, InterventionResolution


def test_intervention_requires_known_safe_reason():
    intervention = InterventionInput(
        executor_id="local-browser",
        reason="CAPTCHA",
        title="Verificação humana necessária",
        instructions="Resolva manualmente e retome o fluxo.",
        evidence={"deduplication_key": "application-1:CAPTCHA"},
    )
    assert intervention.application_id is None
    assert intervention.reason == "CAPTCHA"


def test_intervention_rejects_unknown_automation_bypass():
    with pytest.raises(ValidationError):
        InterventionInput(
            executor_id="local-browser",
            reason="BYPASS_CAPTCHA",
            title="Não permitido",
            instructions="Não permitido.",
        )


def test_resolution_is_auditable():
    assert InterventionResolution(resolution="RESOLVED").resolution == "RESOLVED"
    assert InterventionResolution(resolution="SKIPPED").resolution == "SKIPPED"


def test_list_interventions_supports_exact_dedup_key_filter():
    """Recuperacao operacional do Gmail - achado real em producao: a
    listagem padrao (100 linhas mais recentes) enterra uma intervencao
    antiga e conhecida (o dedup_key da reautorizacao do Gmail) atras de
    mais de 100 outras mais novas, tornando-a impossivel de localizar so
    por paginacao. dedup_key filtra exato no servidor, sem depender de
    quantas linhas mais recentes existem."""
    source = (Path(__file__).resolve().parents[1] / "src" / "career.py").read_text(encoding="utf-8")
    start = source.index('@router.get("/interventions")')
    end = source.index("\n@router.get", start + 1)
    body = source[start:end]
    assert "dedup_key: str | None = Query" in body
    assert "evidence->>'deduplication_key' = :dedup_key" in body
    assert '"dedup_key": dedup_key' in body
