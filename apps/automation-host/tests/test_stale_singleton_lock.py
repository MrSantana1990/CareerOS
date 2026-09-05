from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_ensure_browser_clears_stale_singleton_locks_before_launch() -> None:
    source = _source()
    start = source.index("async def ensure_browser(")
    body = source[start : start + 1400]
    assert 'PROFILE.glob("Singleton*")' in body
    assert "stale_lock.unlink(missing_ok=True)" in body
    assert body.index('PROFILE.glob("Singleton*")') < body.index("launch_persistent_context")
