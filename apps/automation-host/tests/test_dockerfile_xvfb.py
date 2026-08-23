from pathlib import Path


def _dockerfile() -> str:
    return (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")


def test_dockerfile_installs_xvfb() -> None:
    """Achado real: o Catho bloqueia especificamente Chrome headless (403
    Forbidden), mesmo com sessão autenticada válida - confirmado navegando
    no site real com e sem headless usando o mesmo perfil. A VPS não tem
    display fisico, entao precisa de um display virtual (Xvfb) pra rodar
    o Chrome em modo "headed" de verdade, nao o --headless nativo do
    Chrome (que tem diferencas de fingerprint que o Catho detecta)."""
    dockerfile = _dockerfile()
    assert "xvfb" in dockerfile.lower()


def test_dockerfile_starts_xvfb_before_uvicorn() -> None:
    dockerfile = _dockerfile()
    assert "Xvfb :99" in dockerfile
    assert "DISPLAY=:99" in dockerfile
    assert "uvicorn src.main:app" in dockerfile
