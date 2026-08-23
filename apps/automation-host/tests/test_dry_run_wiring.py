from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_dry_run_enabled_reads_dedicated_env_var() -> None:
    source = _source()
    start = source.index("def dry_run_enabled(")
    body = source[start : start + 300]
    assert 'os.getenv("DRY_RUN_ENABLED", "false").lower() == "true"' in body


def test_dry_run_is_an_independent_gate_from_auto_apply_enabled() -> None:
    source = _source()
    assert "environment_auto_apply_enabled() or single_controlled_match" in source
    assert "live_allowed = would_apply and not dry_run_enabled()" in source


def test_blocked_dry_run_submissions_are_audited() -> None:
    source = _source()
    assert 'event("DRY_RUN_SUBMISSION_BLOCKED", application_id=application["id"])' in source


def test_dry_run_reason_is_distinguishable_from_auto_apply_off() -> None:
    source = _source()
    assert "Formulário preenchido; modo DRY RUN ativo (nenhum envio real é permitido)." in source
