from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_remote_debug_port_defaults_to_disabled() -> None:
    source = _source()
    assert 'BROWSER_REMOTE_DEBUG_PORT = os.getenv("BROWSER_REMOTE_DEBUG_PORT", "").strip()' in source


def test_remote_debug_port_only_binds_to_loopback_when_opted_in() -> None:
    source = _source()
    start = source.index("async def ensure_browser(")
    end = source.index("\nasync def", start + 1)
    body = source[start:end]
    assert "if BROWSER_REMOTE_DEBUG_PORT:" in body
    assert '"--remote-debugging-address=127.0.0.1"' in body
