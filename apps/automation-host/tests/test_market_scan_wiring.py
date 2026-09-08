from pathlib import Path


def _main_source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def _core_bridge_source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "core_bridge.py").read_text(encoding="utf-8")


def _function_body(source: str, name: str) -> str:
    start = source.index(f"async def {name}(")
    end = source.index("\nasync def", start + 1)
    return source[start:end]


def test_market_scan_scheduler_is_registered_on_startup() -> None:
    source = _main_source()
    start = source.index("async def startup_scheduler(")
    body = source[start:start + 600]
    assert "asyncio.create_task(market_scan_scheduler())" in body


def test_market_scan_scheduler_never_lets_a_failure_propagate() -> None:
    # Requisito D: falha da fonte nao pode derrubar outros schedulers.
    body = _function_body(_main_source(), "market_scan_scheduler")
    assert "try:" in body
    assert "await market_scan()" in body
    assert 'event("MARKET_SCAN_FAILED"' in body


def test_market_scan_scheduler_runs_once_per_day_not_every_tick() -> None:
    body = _function_body(_main_source(), "market_scan_scheduler")
    assert "now.hour == 6" in body
    assert "slot != last_slot" in body


def test_market_scan_never_raises_when_admin_token_missing() -> None:
    body = _function_body(_main_source(), "market_scan")
    assert "if not CAREER_ADMIN_TOKEN:" in body
    assert 'event("MARKET_SCAN_SKIPPED"' in body


def test_market_scan_emits_required_observability_events() -> None:
    body = _function_body(_main_source(), "market_scan")
    for required_event in ("MARKET_SCAN_STARTED", "MARKET_SCAN_COMPLETED", "MARKET_SCAN_FAILED",
                            "SIGNAL_DISCOVERED", "SIGNAL_DUPLICATE", "SIGNAL_PERSISTED"):
        assert f'"{required_event}"' in body, f"missing event {required_event}"


def test_market_scan_tracks_required_metrics() -> None:
    body = _function_body(_main_source(), "market_scan")
    for metric in ("items_seen", "items_normalized", "signals_created", "duplicates",
                   "unresolved_company", "errors"):
        assert f'"{metric}"' in body, f"missing metric {metric}"


def test_market_scan_a_single_query_failure_does_not_abort_remaining_queries() -> None:
    body = _function_body(_main_source(), "market_scan")
    start = body.index("for query in DEFAULT_QUERIES:")
    loop_body = body[start:start + 700]
    assert "except Exception as fetch_error:" in loop_body
    assert "continue" in loop_body


def test_structured_fields_extraction_wired_into_sync_job_to_core() -> None:
    body = _function_body(_main_source(), "sync_job_to_core")
    assert "structured = extract_structured_fields(body, source_url=page.url)" in body
    assert "structured_extraction=structured or None" in body


def test_build_job_record_forwards_structured_extraction_when_present() -> None:
    source = _core_bridge_source()
    start = source.index("def build_job_record(")
    body = source[start:start + 1600]
    assert "structured_extraction: dict | None = None" in body
    assert 'payload["structured_extraction"] = structured_extraction' in body
