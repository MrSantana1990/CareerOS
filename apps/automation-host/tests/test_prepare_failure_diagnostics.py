from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_a_prepare_failure_records_the_real_exception_instead_of_just_its_type() -> None:
    # Achado real em produção: uma candidatura terminou FAILED com o motivo
    # genérico "Falha na preparação: Error." - sem mensagem, sem traceback,
    # sem evento em automation-events.jsonl. Mesma classe de lacuna já
    # corrigida pro clique final (LIVE_CLICK_FAILED), agora no bloco except
    # que envolve toda a etapa de preparo/preenchimento.
    source = _source()
    start = source.index("        except Exception as exc:\n            application[\"status\"] = \"FAILED\"")
    end = source.index("\n        finally:")
    body = source[start:end]
    assert 'application["prepare_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"' in body
    assert 'event("APPLICATION_PREPARE_FAILED", application_id=application["id"],' in body
