from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_remote_debug_port_defaults_to_disabled() -> None:
    source = _source()
    assert 'BROWSER_REMOTE_DEBUG_PORT = os.getenv("BROWSER_REMOTE_DEBUG_PORT", "").strip()' in source


def test_remote_debug_port_is_gated_by_host_side_publish_not_container_bind() -> None:
    # Docker "-p" nunca alcanca um servico ligado so em 127.0.0.1 de outro
    # namespace de rede - o isolamento real precisa vir do publish
    # loopback-only no host (docker-compose.yml) + do tunel SSH, entao o
    # bind dentro do container e 0.0.0.0 de proposito.
    source = _source()
    start = source.index("async def ensure_browser(")
    end = source.index("\nasync def", start + 1)
    body = source[start:end]
    assert "if BROWSER_REMOTE_DEBUG_PORT:" in body
    assert '"--remote-debugging-address=0.0.0.0"' in body
