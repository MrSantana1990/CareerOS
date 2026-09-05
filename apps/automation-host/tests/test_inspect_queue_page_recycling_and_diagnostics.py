from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def _inspect_loop_body() -> str:
    source = _source()
    start = source.index('update(status="preparing", message=f"Inspecionando {len(candidates)}')
    end = source.index('async def sync_status_to_core(')
    return source[start:end]


def test_inspect_queue_recycles_the_page_after_every_candidate() -> None:
    # Achado real em produção: exatamente o mesmo bug já corrigido em
    # execute_application_queue (page crash por OOM, ver
    # test_page_recycling_prevents_oom.py) existia também aqui - uma
    # única página do Chrome era reaproveitada para todas as vagas
    # inspecionadas num único lote, sem nunca ser reciclada. 249 das 519
    # candidaturas FAILED reais compartilhavam o motivo genérico "Falha
    # de inspeção: Error." - a mesma classe de causa (OOM/page crash),
    # nunca diagnosticada porque essa função tem seu próprio bloco
    # except, separado do de execute_application_queue.
    body = _inspect_loop_body()
    assert "stale_pages = list(browser.pages)" in body
    assert "page = await browser.new_page()" in body
    assert "await stale.close()" in body


def test_inspect_queue_failure_records_the_real_exception() -> None:
    body = _inspect_loop_body()
    start = body.index("except Exception as exc:")
    end = body.index("indexed[url] = application")
    except_block = body[start:end]
    assert 'application["inspect_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"' in except_block
    assert 'event("APPLICATION_INSPECT_FAILED", application_id=application["id"],' in except_block
