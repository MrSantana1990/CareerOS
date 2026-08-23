from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_execute_request_defaults_the_scoped_field_to_none() -> None:
    source = _source()
    start = source.index("class ExecuteRequest(BaseModel):")
    body = source[start : start + 250]
    assert "single_controlled_application_id: str | None = None" in body


def test_scoped_submission_never_depends_on_the_global_auto_apply_flag() -> None:
    source = _source()
    start = source.index("single_controlled_match = (")
    end = source.index("\n            quota_available = remaining_quota > 0")
    body = source[start:end]
    assert 'request.single_controlled_application_id is not None' in body
    assert 'application["id"] == request.single_controlled_application_id' in body
    assert "environment_auto_apply_enabled() or single_controlled_match" in body


def test_daily_pipeline_never_sets_the_scoped_override() -> None:
    # O agendador (8h/12h/18h) so pode herdar esse campo se alguem passar a
    # setar explicitamente na chamada - hoje nao seta, entao o campo sempre
    # vem None nesse caminho e nunca autoriza envio fora do AUTO_APPLY_ENABLED
    # global.
    source = _source()
    start = source.index("async def full_daily_pipeline(")
    end = source.index("\nasync def daily_scheduler(")
    body = source[start:end]
    assert "single_controlled_application_id" not in body


def test_scoped_authorization_is_audited() -> None:
    assert 'event("SINGLE_CONTROLLED_SUBMISSION_AUTHORIZED", application_id=application["id"])' in _source()
