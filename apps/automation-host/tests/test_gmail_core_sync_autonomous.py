from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def _function_body(name: str) -> str:
    source = _source()
    start = source.index(f"async def {name}(")
    end = source.index("\nasync def", start + 1)
    return source[start:end]


def test_sync_communications_to_core_never_propagates_an_exception() -> None:
    # Requisito C: Core indisponivel nao pode derrubar o scheduler de
    # Gmail, que so depende da API do Google.
    body = _function_body("sync_communications_to_core")
    assert "try:" in body
    assert "except Exception as sync_error:" in body
    assert 'event("GOOGLE_CORE_SYNC_FAILED"' in body
    assert "return False" in body


def test_sync_communications_to_core_posts_to_the_real_core_endpoint() -> None:
    body = _function_body("sync_communications_to_core")
    assert 'CAREER_API_URL + "/api/v1/communications/sync"' in body
    assert '"provider": "GMAIL"' in body


def test_sync_communications_to_core_skips_silently_without_admin_token_or_items() -> None:
    body = _function_body("sync_communications_to_core")
    assert "if not CAREER_ADMIN_TOKEN or not items:" in body
    assert "return False" in body


def test_autonomous_gmail_scheduler_now_syncs_to_core() -> None:
    # Bug real (auditoria pre-Fase 2): o scheduler autonomo (a cada
    # ~10min) nunca chamava isto - so o endpoint manual /google/scan
    # sincronizava com o Core, deixando recruitment_communications
    # parado por semanas apesar de centenas de scans autonomos.
    body = _function_body("google_mail_scheduler")
    assert "await sync_communications_to_core(result[\"items\"])" in body


def test_core_sync_failure_inside_scheduler_does_not_count_as_a_gmail_health_failure() -> None:
    # sync_communications_to_core nunca levanta excecao (ver teste acima),
    # entao ela nunca cai no except que incrementa consecutive_failures -
    # a saude do Gmail e a do Core sao contadas separadamente.
    body = _function_body("google_mail_scheduler")
    sync_call_index = body.index("await sync_communications_to_core(")
    except_index = body.index("except Exception as exc:")
    assert sync_call_index < except_index


def test_manual_scan_endpoint_reuses_the_same_sync_function_not_a_duplicate() -> None:
    source = _source()
    start = source.index('@app.post("/google/scan")')
    end = source.index("\n@app.post", start + 1)
    body = source[start:end]
    assert "await sync_communications_to_core(result[\"items\"])" in body
    # Nao deve existir uma segunda construcao manual do payload aqui -
    # a logica de sync vive so em sync_communications_to_core.
    assert '"provider": "GMAIL"' not in body
