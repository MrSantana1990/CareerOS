import pytest
from pydantic import ValidationError

from src.career import RadarInput, RadarRuleInput


def test_radar_defaults_are_safe():
    radar = RadarInput(code="RADAR_SUPPORT", label="Suporte / Sustentação")
    assert radar.enabled is False
    assert radar.autonomy_mode == "MANUAL"
    assert radar.roles == []
    assert radar.languages == {}


def test_radar_rejects_unknown_autonomy_mode():
    with pytest.raises(ValidationError):
        RadarInput(code="RADAR_SUPPORT", label="Suporte", autonomy_mode="FULL_AUTO")


def test_radar_rejects_lowercase_code():
    with pytest.raises(ValidationError):
        RadarInput(code="radar_support", label="Suporte")


def test_radar_score_threshold_is_bounded():
    with pytest.raises(ValidationError):
        RadarInput(code="RADAR_SUPPORT", label="Suporte", score_threshold=150)


def test_radar_rule_requires_known_type():
    rule = RadarRuleInput(code="SUPPORT_N1_MINIMUM", label="Suporte N1 mínimo", rule_type="BLOCK", configuration={})
    assert rule.priority == 100
    assert rule.enabled is True


def test_radar_rule_rejects_unknown_type():
    with pytest.raises(ValidationError):
        RadarRuleInput(code="X", label="Regra inválida aqui", rule_type="INVALIDO", configuration={})
