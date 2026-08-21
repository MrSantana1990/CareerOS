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
