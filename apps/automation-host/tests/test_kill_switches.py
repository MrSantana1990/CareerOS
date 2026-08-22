import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.kill_switches import is_paused  # noqa: E402


def test_not_paused_when_no_switch_is_set() -> None:
    status = is_paused({"PAUSE_ALL": {"paused": False}}, "PAUSE_ALL", fail_closed=True)
    assert status.paused is False
    assert status.reachable is True


def test_paused_when_first_key_is_active() -> None:
    status = is_paused({"PAUSE_ALL": {"paused": True, "reason": "incidente"}}, "PAUSE_ALL", "PAUSE_BROWSER_APPLY", fail_closed=True)
    assert status.paused is True
    assert status.reason == "incidente"


def test_paused_when_second_key_is_active() -> None:
    switches = {"PAUSE_ALL": {"paused": False}, "PAUSE_BROWSER_APPLY": {"paused": True, "reason": "manutenção"}}
    status = is_paused(switches, "PAUSE_ALL", "PAUSE_BROWSER_APPLY", fail_closed=True)
    assert status.paused is True
    assert status.reason == "manutenção"


def test_missing_key_defaults_to_not_paused() -> None:
    status = is_paused({}, "PAUSE_ALL", fail_closed=True)
    assert status.paused is False


def test_unreachable_core_fails_closed_when_requested() -> None:
    status = is_paused(None, "PAUSE_ALL", "PAUSE_BROWSER_APPLY", fail_closed=True)
    assert status.paused is True
    assert status.reachable is False


def test_unreachable_core_fails_open_when_requested() -> None:
    status = is_paused(None, "PAUSE_ALL", fail_closed=False)
    assert status.paused is False
    assert status.reachable is False


def test_reason_falls_back_to_key_when_missing() -> None:
    status = is_paused({"PAUSE_ALL": {"paused": True}}, "PAUSE_ALL", fail_closed=True)
    assert status.reason == "PAUSE_ALL"
