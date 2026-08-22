from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_main_imports_kill_switch_client() -> None:
    source = _source()
    assert "from .kill_switches import fetch_kill_switches, is_paused" in source


def test_execute_application_queue_checks_kill_switch_before_running() -> None:
    source = _source()
    start = source.index("async def execute_application_queue(")
    body = source[start : start + 700]
    assert 'is_paused(switches, "PAUSE_ALL", "PAUSE_BROWSER_APPLY", fail_closed=True)' in body
    assert "if kill_status.paused:" in body
    assert "return" in body


def test_daily_pipeline_checks_kill_switch_before_running() -> None:
    source = _source()
    start = source.index("async def full_daily_pipeline(")
    body = source[start : start + 700]
    assert 'is_paused(switches, "PAUSE_ALL", fail_closed=False)' in body
    assert "if kill_status.paused:" in body
