from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_manual_required_from_an_unconfirmed_submission_is_retryable() -> None:
    # Uma tentativa de envio sem confirmação da plataforma é um caso
    # legítimo de retry - especialmente relevante depois de corrigir a
    # classificação interna/externa: um caso que falhou por classificação
    # errada antes agora tem uma chance real de completar de verdade.
    source = _source()
    start = source.index("def retryable(application: dict) -> bool:")
    end = source.index("\n    pending = sorted(")
    body = source[start:end]
    assert '"sem confirmação da plataforma" in application.get("reason", "")' in body
