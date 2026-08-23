import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core_bridge import (  # noqa: E402
    CoreSyncRecord, backoff_seconds, build_job_record, build_prepare_record,
    build_score_record, build_transition_record, guess_company,
    guess_company_from_linkedin_url, is_due, is_eligible_for_prepare,
    job_idempotency_key, looks_like_job_board_boilerplate,
    map_local_status_to_core_transition, send_core_sync,
)


def test_guess_company_from_linkedin_url_extracts_the_at_slug() -> None:
    url = ("https://br.linkedin.com/jobs/view/analista-de-suporte-de-t-i-s%C3%A3o-paulo-sp-"
           "at-hospcom-hospitalar-4443708471?position=9")
    assert guess_company_from_linkedin_url(url) == "Hospcom Hospitalar"


def test_guess_company_from_linkedin_url_empty_when_pattern_absent() -> None:
    assert guess_company_from_linkedin_url("https://br.linkedin.com/jobs/view/no-slug-here") == ""


def test_looks_like_job_board_boilerplate_flags_infojobs_style_titles() -> None:
    assert looks_like_job_board_boilerplate("Vaga de emprego de Engenheiro de Dados em Todo Brasil")


def test_looks_like_job_board_boilerplate_allows_real_company_names() -> None:
    assert not looks_like_job_board_boilerplate("Stefanini Group")


def test_guess_company_prefers_linkedin_url_slug_over_page_title() -> None:
    url = "https://br.linkedin.com/jobs/view/analista-de-dados-at-acme-corp-123456"
    company = guess_company(source="LinkedIn", source_url=url, page_title="Something misleading")
    assert company == "Acme Corp"


def test_guess_company_falls_back_to_page_title_when_no_separator_present() -> None:
    # Heurística fraca fora do LinkedIn: sem separador reconhecível, usa o
    # título inteiro. Não há garantia de formato por plataforma - por isso
    # continua exigindo revisão humana até refinarmos site a site.
    company = guess_company(source="Catho", source_url="https://catho.com/vaga/1",
                             page_title="Acme Ltda")
    assert company == "Acme Ltda"


def test_guess_company_rejects_catho_generic_static_title() -> None:
    # Achado real em produção: o título do Catho é fixo pra qualquer vaga
    # ("Vagas de emprego em todo Brasil | Catho") - nem cargo nem empresa,
    # e sem o filtro de nome de plataforma o "Catho" do fim virava empresa.
    company = guess_company(
        source="Catho", source_url="https://www.catho.com.br/vagas/x/123",
        page_title="Vagas de emprego em todo Brasil | Catho",
    )
    assert company == ""


def test_guess_company_rejects_job_board_boilerplate_instead_of_fabricating() -> None:
    company = guess_company(
        source="InfoJobs", source_url="https://www.infojobs.com.br/vaga-de-x__123.aspx",
        page_title="Vaga de emprego de ENGENHEIRO DE DADOS SR em Todo Brasil",
    )
    assert company == ""


def test_score_record_has_no_body_only_a_path_job_id() -> None:
    record = build_score_record(job_id="job-1", correlation_id="app-1")
    assert record.kind == "SCORE"
    assert record.payload == {"job_id": "job-1"}
    assert record.idempotency_key == "score:job-1"


def test_prepare_record_has_no_body_only_a_path_job_id() -> None:
    record = build_prepare_record(job_id="job-1", correlation_id="app-1")
    assert record.kind == "PREPARE"
    assert record.idempotency_key == "prepare:job-1"


def test_send_core_sync_sends_no_body_for_score_or_prepare() -> None:
    record = build_score_record(job_id="job-1", correlation_id="app-1")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"total": 80, "recommendation": "APPLY_HIGH"}'

    def fake_urlopen(request, timeout=20):
        captured["data"] = request.data
        captured["method"] = request.method
        captured["path"] = request.full_url
        return FakeResponse()

    with patch("src.core_bridge.urlopen", side_effect=fake_urlopen):
        result = send_core_sync("http://api:8000", "token", record)
    assert result.ok is True
    assert captured["data"] is None
    assert captured["method"] == "POST"
    assert captured["path"] == "http://api:8000/api/v1/jobs/job-1/score"


def test_is_eligible_for_prepare_matches_the_cores_own_gate() -> None:
    assert is_eligible_for_prepare(75, "APPLY") is True
    assert is_eligible_for_prepare(100, "APPLY_HIGH") is True
    assert is_eligible_for_prepare(74, "APPLY") is False
    assert is_eligible_for_prepare(90, "BLOCK") is False
    assert is_eligible_for_prepare(90, "DISCARD") is False
    assert is_eligible_for_prepare(65, "REVIEW") is False


def test_map_local_status_covers_the_real_apply_time_outcomes() -> None:
    assert map_local_status_to_core_transition("READY_FOR_REVIEW") == "READY"
    assert map_local_status_to_core_transition("APPLIED") == "CONFIRMED"
    assert map_local_status_to_core_transition("MANUAL_REQUIRED") == "MANUAL_REQUIRED"


def test_map_local_status_folds_block_and_closed_into_error_not_a_new_core_state() -> None:
    # BLOCKED/CLOSED não têm alvo direto a partir de PREPARING no schema
    # real do Core (ALLOWED_TRANSITIONS) - mapear pra um estado novo
    # exigiria migration, fora do escopo desta ponte. ERROR é o alvo
    # honesto disponível, com o motivo real preservado em reason.
    assert map_local_status_to_core_transition("BLOCKED") == "ERROR"
    assert map_local_status_to_core_transition("CLOSED") == "ERROR"
    assert map_local_status_to_core_transition("FAILED") == "ERROR"


def test_map_local_status_returns_none_for_pre_application_statuses() -> None:
    assert map_local_status_to_core_transition("INSPECTING") is None
    assert map_local_status_to_core_transition("ANALYZED") is None
    assert map_local_status_to_core_transition("READY_TO_PREPARE") is None


def test_build_transition_record_idempotency_key_is_stable_per_application_and_target() -> None:
    record = build_transition_record(core_application_id="app-1", target_status="READY",
                                      reason="Formulário pronto.", correlation_id="local-1")
    assert record.kind == "TRANSITION"
    assert record.idempotency_key == "transition:app-1:READY"
    assert record.payload == {"application_id": "app-1", "status": "READY", "reason": "Formulário pronto."}


def test_send_core_sync_transition_body_only_has_status_and_reason() -> None:
    record = build_transition_record(core_application_id="app-1", target_status="MANUAL_REQUIRED",
                                      reason="CAPTCHA detectado.", correlation_id="local-1")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"from": "PREPARING", "to": "MANUAL_REQUIRED"}'

    def fake_urlopen(request, timeout=20):
        captured["data"] = json.loads(request.data.decode())
        captured["path"] = request.full_url
        return FakeResponse()

    with patch("src.core_bridge.urlopen", side_effect=fake_urlopen):
        result = send_core_sync("http://api:8000", "token", record)
    assert result.ok is True
    assert captured["path"] == "http://api:8000/api/v1/applications/app-1/transition"
    assert captured["data"] == {"status": "MANUAL_REQUIRED", "reason": "CAPTCHA detectado."}


def test_send_core_sync_transition_409_means_already_applied_not_an_error() -> None:
    record = build_transition_record(core_application_id="app-1", target_status="READY",
                                      reason="", correlation_id="local-1")
    error = HTTPError("http://api:8000/api/v1/applications/app-1/transition", 409, "Conflict", hdrs=None, fp=None)  # type: ignore[arg-type]
    with patch("src.core_bridge.urlopen", side_effect=error):
        result = send_core_sync("http://api:8000", "token", record)
    assert result.ok is True
    assert result.response == {"already_applied": True}


def test_job_idempotency_key_matches_job_sources_unique_constraint_granularity() -> None:
    assert job_idempotency_key("Catho", "https://www.catho.com.br/vagas/123") == \
        "Catho:https://www.catho.com.br/vagas/123"


def test_build_job_record_maps_fields_for_core_job_input() -> None:
    record = build_job_record(
        source="Catho", source_url="https://catho.com/vaga/1", company="Acme",
        title="Analista de Dados", description="Descrição real", location="Campinas",
        correlation_id="app-123",
    )
    assert record.kind == "JOB"
    assert record.payload["company"] == "Acme"
    assert record.payload["source"] == "Catho"
    assert record.idempotency_key == "Catho:https://catho.com/vaga/1"
    assert record.correlation_id == "app-123"
    assert record.schema_version == 1
    assert record.attempts == 0


def test_record_round_trips_through_dict_for_jsonl_outbox() -> None:
    record = build_job_record(
        source="LinkedIn", source_url="https://linkedin.com/jobs/9", company="Acme",
        title="DBA", description="", location=None, correlation_id="app-9",
    )
    restored = CoreSyncRecord.from_dict(record.to_dict())
    assert restored == record


def test_from_dict_ignores_unknown_future_fields_for_forward_compatibility() -> None:
    data = {
        "kind": "JOB", "payload": {}, "idempotency_key": "k", "correlation_id": "c",
        "schema_version": 1, "attempts": 0, "created_at": "2026-01-01T00:00:00+00:00",
        "last_error": None, "last_attempt_at": None, "some_future_field": "ignored",
    }
    record = CoreSyncRecord.from_dict(data)
    assert record.kind == "JOB"


def test_backoff_grows_then_caps_at_the_last_configured_step() -> None:
    assert backoff_seconds(0) == 5
    assert backoff_seconds(1) == 20
    assert backoff_seconds(4) == 300
    assert backoff_seconds(99) == 300


def test_is_due_true_for_a_record_never_attempted() -> None:
    record = build_job_record(source="Catho", source_url="u", company="A", title="T",
                               description="", location="", correlation_id="c")
    assert is_due(record, datetime.now(UTC)) is True


def test_is_due_false_before_backoff_window_elapses() -> None:
    now = datetime(2026, 8, 23, 12, 0, 0, tzinfo=UTC)
    record = build_job_record(source="Catho", source_url="u", company="A", title="T",
                               description="", location="", correlation_id="c")
    record.attempts = 1
    record.last_attempt_at = now.isoformat()
    from datetime import timedelta
    almost_due = now + timedelta(seconds=10)
    assert is_due(record, almost_due) is False


def test_is_due_true_once_backoff_window_elapses() -> None:
    now = datetime(2026, 8, 23, 12, 0, 0, tzinfo=UTC)
    record = build_job_record(source="Catho", source_url="u", company="A", title="T",
                               description="", location="", correlation_id="c")
    record.attempts = 1
    record.last_attempt_at = now.isoformat()
    from datetime import timedelta
    past_due = now + timedelta(seconds=21)
    assert is_due(record, past_due) is True


def test_send_core_sync_without_admin_token_is_non_retryable() -> None:
    record = build_job_record(source="Catho", source_url="u", company="A", title="T",
                               description="", location="", correlation_id="c")
    result = send_core_sync("http://api:8000", "", record)
    assert result.ok is False
    assert result.retryable is False
    assert result.error == "missing_admin_token"


def test_send_core_sync_treats_409_as_success_not_error() -> None:
    record = build_job_record(source="Catho", source_url="u", company="A", title="T",
                               description="", location="", correlation_id="c")
    error = HTTPError("http://api:8000/api/v1/jobs", 409, "Conflict", hdrs=None, fp=None)  # type: ignore[arg-type]
    with patch("src.core_bridge.urlopen", side_effect=error):
        result = send_core_sync("http://api:8000", "token", record)
    assert result.ok is True
    assert result.response == {"already_applied": True}


def test_send_core_sync_marks_client_errors_as_non_retryable() -> None:
    record = build_job_record(source="Catho", source_url="u", company="A", title="T",
                               description="", location="", correlation_id="c")
    error = HTTPError("http://api:8000/api/v1/jobs", 422, "Unprocessable", hdrs=None, fp=None)  # type: ignore[arg-type]
    with patch("src.core_bridge.urlopen", side_effect=error):
        result = send_core_sync("http://api:8000", "token", record)
    assert result.ok is False
    assert result.retryable is False


def test_send_core_sync_marks_server_errors_as_retryable() -> None:
    record = build_job_record(source="Catho", source_url="u", company="A", title="T",
                               description="", location="", correlation_id="c")
    error = HTTPError("http://api:8000/api/v1/jobs", 503, "Unavailable", hdrs=None, fp=None)  # type: ignore[arg-type]
    with patch("src.core_bridge.urlopen", side_effect=error):
        result = send_core_sync("http://api:8000", "token", record)
    assert result.ok is False
    assert result.retryable is True


def test_send_core_sync_marks_network_errors_as_retryable() -> None:
    record = build_job_record(source="Catho", source_url="u", company="A", title="T",
                               description="", location="", correlation_id="c")
    with patch("src.core_bridge.urlopen", side_effect=URLError("timed out")):
        result = send_core_sync("http://api:8000", "token", record)
    assert result.ok is False
    assert result.retryable is True


def test_send_core_sync_sends_correlation_id_header() -> None:
    record = build_job_record(source="Catho", source_url="u", company="A", title="T",
                               description="", location="", correlation_id="app-42")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"id": "job-1", "created": true, "deduplicated": false}'

    def fake_urlopen(request, timeout=20):
        captured["headers"] = dict(request.headers)
        return FakeResponse()

    with patch("src.core_bridge.urlopen", side_effect=fake_urlopen):
        result = send_core_sync("http://api:8000", "token", record)
    assert result.ok is True
    assert captured["headers"].get("X-correlation-id") == "app-42"
