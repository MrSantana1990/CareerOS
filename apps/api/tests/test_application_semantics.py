"""Fase 2, Prompt 9.2 - Application Conflict Forensics & Safe Reconciliation.
Testes A-O da Secao 14. APPLICATION ROW != REAL APPLICATION (Secao 3):
uma linha PREPARING/READY/ERROR nunca chegou a acao externa comprovada."""

from pathlib import Path

from src.application_semantics import (
    AUTO_RECONCILABLE_GROUP_CLASSES, classify_application_reality, classify_group_application_conflict,
    select_canonical_application,
)


def _artifact(status: str, **overrides) -> dict:
    base = {"id": f"app-{status.lower()}", "status": status, "provider_message_id": None,
            "external_reference": None, "confirmation_evidence": {}, "applied_at": None,
            "created_at": "2026-01-01T00:00:00Z"}
    base.update(overrides)
    return base


# A: two READY artifacts same canonical job -> one intent -----------------------------------------

def test_a_two_ready_artifacts_classify_as_multiple_technical_artifacts():
    app_1 = _artifact("READY", id="a1")
    app_2 = _artifact("READY", id="a2")
    reality_1 = classify_application_reality(app_1)
    reality_2 = classify_application_reality(app_2)
    assert reality_1 == reality_2 == "NON_EXTERNAL_ARTIFACT"
    group = classify_group_application_conflict([reality_1, reality_2])
    assert group == "MULTIPLE_TECHNICAL_ARTIFACTS"
    assert group in AUTO_RECONCILABLE_GROUP_CLASSES


# B: READY + ERROR -> no real external application -------------------------------------------------

def test_b_ready_plus_error_is_no_real_external_application():
    realities = [classify_application_reality(_artifact("READY")), classify_application_reality(_artifact("ERROR"))]
    assert realities == ["NON_EXTERNAL_ARTIFACT", "NON_EXTERNAL_ARTIFACT"]
    assert classify_group_application_conflict(realities) == "MULTIPLE_TECHNICAL_ARTIFACTS"


# C: CONFIRMED + READY -> confirmed preserved --------------------------------------------------------

def test_c_confirmed_plus_ready_preserves_confirmed_as_canonical():
    confirmed = _artifact("CONFIRMED", id="confirmed-1", created_at="2026-01-01T00:00:00Z")
    ready = _artifact("READY", id="ready-1", created_at="2026-01-02T00:00:00Z")
    realities = [classify_application_reality(confirmed), classify_application_reality(ready)]
    assert realities == ["EXTERNAL_CONFIRMED", "NON_EXTERNAL_ARTIFACT"]
    group = classify_group_application_conflict(realities)
    assert group == "ONE_CONFIRMED_PLUS_ARTIFACTS"
    assert group in AUTO_RECONCILABLE_GROUP_CLASSES
    canonical = select_canonical_application([(confirmed, "EXTERNAL_CONFIRMED"), (ready, "NON_EXTERNAL_ARTIFACT")])
    assert canonical["id"] == "confirmed-1"


# D: CONFIRMED + ERROR -> confirmed preserved --------------------------------------------------------

def test_d_confirmed_plus_error_preserves_confirmed_as_canonical():
    confirmed = _artifact("CONFIRMED", id="confirmed-1")
    error = _artifact("ERROR", id="error-1")
    canonical = select_canonical_application([(error, "NON_EXTERNAL_ARTIFACT"), (confirmed, "EXTERNAL_CONFIRMED")])
    assert canonical["id"] == "confirmed-1"
    assert classify_group_application_conflict(["EXTERNAL_CONFIRMED", "NON_EXTERNAL_ARTIFACT"]) == \
        "ONE_CONFIRMED_PLUS_ARTIFACTS"


# E: two independent CONFIRMED -> never auto-merge -----------------------------------------------------

def test_e_two_independent_confirmed_is_multiple_real_applications_never_auto_merged():
    realities = [classify_application_reality(_artifact("CONFIRMED")),
                 classify_application_reality(_artifact("SENT"))]
    assert all(item == "EXTERNAL_CONFIRMED" for item in realities)
    group = classify_group_application_conflict(realities)
    assert group == "MULTIPLE_REAL_APPLICATIONS"
    assert group not in AUTO_RECONCILABLE_GROUP_CLASSES


# F: ambiguous historical statuses -> no unsafe merge --------------------------------------------------

def test_f_closed_without_evidence_or_event_history_is_historical_unknown():
    closed = _artifact("CLOSED")
    reality = classify_application_reality(closed, event_history=None)
    assert reality == "HISTORICAL_UNKNOWN"
    assert classify_group_application_conflict([reality, "NON_EXTERNAL_ARTIFACT"]) == "AMBIGUOUS_HISTORY"


def test_f_closed_with_checked_event_history_and_no_confirmation_is_a_real_artifact_not_unknown():
    # Secao 2: usar evidencia, nao so o nome do status - se o historico de
    # eventos JA foi consultado e nao mostra nenhuma transicao pos-SENT/
    # CONFIRMED, isso e prova (nao ausencia de prova) de que nunca houve
    # acao externa.
    closed = _artifact("CLOSED")
    reality = classify_application_reality(closed, event_history=[{"to_status": "DISCARDED"}])
    assert reality == "NON_EXTERNAL_ARTIFACT"


def test_f_closed_with_a_confirmed_event_in_history_is_external_confirmed():
    closed = _artifact("CLOSED")
    reality = classify_application_reality(
        closed, event_history=[{"to_status": "SENT"}, {"to_status": "CONFIRMED"}, {"to_status": "CLOSED"}])
    assert reality == "EXTERNAL_CONFIRMED"


def test_f_ambiguous_status_with_direct_evidence_never_needs_event_history():
    closed_with_evidence = _artifact("CLOSED", provider_message_id="gmail-msg-123")
    assert classify_application_reality(closed_with_evidence) == "EXTERNAL_CONFIRMED"


def test_f_one_confirmed_plus_one_unconfirmed_attempt_is_ambiguous_not_auto_merged():
    realities = ["EXTERNAL_CONFIRMED", "EXTERNAL_ATTEMPT_UNCONFIRMED"]
    group = classify_group_application_conflict(realities)
    assert group == "AMBIGUOUS_HISTORY"
    assert group not in AUTO_RECONCILABLE_GROUP_CLASSES


# G: provider message id evidence preserved -------------------------------------------------------------

def test_g_provider_message_id_alone_is_sufficient_external_evidence():
    app = _artifact("PREPARING", provider_message_id="1a075f10df38136e")
    assert classify_application_reality(app) == "EXTERNAL_ATTEMPT_UNCONFIRMED"


def test_g_confirmation_evidence_with_real_content_counts_as_evidence():
    app = _artifact("READY", confirmation_evidence={"success_page_text": "Candidatura enviada"})
    assert classify_application_reality(app) == "EXTERNAL_ATTEMPT_UNCONFIRMED"


def test_g_empty_confirmation_evidence_dict_is_not_evidence():
    app = _artifact("READY", confirmation_evidence={"success_page_text": None, "screenshot": None})
    assert classify_application_reality(app) == "NON_EXTERNAL_ARTIFACT"


# Base cases: single application groups -------------------------------------------------------------

def test_zero_applications_is_safe_no_real_application():
    assert classify_group_application_conflict([]) == "SAFE_NO_REAL_APPLICATION"
    assert "SAFE_NO_REAL_APPLICATION" in AUTO_RECONCILABLE_GROUP_CLASSES


def test_single_application_of_any_kind_is_safe_single_real_application():
    for status in ("PREPARING", "READY", "ERROR", "CONFIRMED", "SUBMITTING"):
        reality = classify_application_reality(_artifact(status))
        assert classify_group_application_conflict([reality]) == "SAFE_SINGLE_REAL_APPLICATION"


def test_select_canonical_application_with_no_applications_returns_none():
    assert select_canonical_application([]) is None


# Wiring: career.py routes ---------------------------------------------------------------------------

def _career_source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "career.py").read_text(encoding="utf-8")


def _route_body(source: str, path: str) -> str:
    start = source.index(f'@router.post("{path}")')
    end = source.index("\n@router.", start + 1)
    return source[start:end]


# H/I/J: events, communications, human interventions preserved (never modified/deleted by reconciliation)

def test_h_reconciliation_route_never_touches_application_events():
    body = _route_body(_career_source(), "/jobs/reconcile-duplicates")
    assert "UPDATE application_events" not in body
    assert "DELETE FROM application_events" not in body
    assert "INSERT INTO application_events" not in body


def test_i_reconciliation_route_never_touches_recruitment_communications():
    body = _route_body(_career_source(), "/jobs/reconcile-duplicates")
    assert "UPDATE recruitment_communications" not in body
    assert "DELETE FROM recruitment_communications" not in body


def test_j_reconciliation_route_never_deletes_a_human_intervention():
    body = _route_body(_career_source(), "/jobs/reconcile-duplicates")
    assert "DELETE FROM human_interventions" not in body


# K: future duplicate Job cannot create duplicate Application intent -----------------------------------

def test_k_prepare_application_resolves_canonical_job_before_creating_an_application():
    body = _route_body(_career_source(), "/jobs/{job_id}/prepare")
    assert 'job["dedup_status"] == "DUPLICATE"' in body
    assert 'job["canonical_job_id"]' in body
    resolve_index = body.index('job["dedup_status"] == "DUPLICATE"')
    insert_index = body.index("INSERT INTO applications")
    assert resolve_index < insert_index


# M: rerun idempotent (reconciliation only touches still-CANONICAL rows) --------------------------------

def test_m_reconciliation_only_considers_still_canonical_jobs():
    body = _route_body(_career_source(), "/jobs/reconcile-duplicates")
    assert "dedup_status='CANONICAL'" in body


# N: no send/submit -----------------------------------------------------------------------------------

def test_n_reconciliation_route_never_calls_a_send_or_submit_function():
    body = _route_body(_career_source(), "/jobs/reconcile-duplicates")
    for forbidden in ("send_application_email(", "urlopen(", "requests.post(", "submit"):
        assert forbidden not in body


def test_n_application_semantics_module_never_imports_a_send_function():
    import inspect

    import src.application_semantics as module
    source = inspect.getsource(module)
    for forbidden in ("send_application_email", "urlopen(", "requests.post("):
        assert forbidden not in source


# Section 7: multiple real applications register a finding, never 25 blind interventions ---------------

def test_multiple_real_applications_creates_exactly_one_deduplicated_intervention_per_group():
    body = _route_body(_career_source(), "/jobs/reconcile-duplicates")
    assert "DUPLICATE_EXTERNAL_APPLICATION" in body
    assert 'f"duplicate-external-application:{group[\'canonical_job_id\']}"' in body


def test_reconciliation_never_deletes_an_application_row():
    body = _route_body(_career_source(), "/jobs/reconcile-duplicates")
    assert "DELETE FROM applications" not in body
