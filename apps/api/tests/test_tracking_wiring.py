from pathlib import Path


def _career_source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "career.py").read_text(encoding="utf-8")


def _route_body(source: str, method: str, path: str) -> str:
    start = source.index(f'@router.{method}("{path}")')
    end = source.index("\n@router.", start + 1)
    return source[start:end]


def test_communications_sync_includes_opportunity_only_applications():
    # Achado real (Prompt 6): o INNER JOIN em jobs excluia Deutsche Bank
    # (SPONTANEOUS_APPLICATION sem Job) do pool de correlacao.
    body = _route_body(_career_source(), "post", "/communications/sync")
    assert "LEFT JOIN opportunities o ON o.id=a.opportunity_id" in body
    assert "classify_correlation(" in body


def test_extract_evidence_route_only_processes_docx_never_silently_drops_pdf():
    body = _route_body(_career_source(), "post", "/profile/extract-evidence")
    assert 'storage_path.suffix.lower() != ".docx"' in body
    assert "skipped_pdf.append(" in body


def test_extract_evidence_route_only_populates_language_when_currently_empty():
    body = _route_body(_career_source(), "post", "/profile/extract-evidence")
    assert "if not current_language_levels and merged_language_levels:" in body


def test_extract_evidence_route_resolves_language_intervention_when_populated():
    body = _route_body(_career_source(), "post", "/profile/extract-evidence")
    assert "profile:language_declaration" in body
    assert "status='RESOLVED'" in body


def test_extract_evidence_route_never_marks_skill_verified_from_resume_mention():
    body = _route_body(_career_source(), "post", "/profile/extract-evidence")
    assert "'RESUME', :title" in body
    assert "verified=true" not in body.lower()


def test_extract_evidence_route_skill_evidence_is_idempotent_via_source_check():
    body = _route_body(_career_source(), "post", "/profile/extract-evidence")
    assert "SELECT 1 FROM skill_evidence" in body
    assert "if exists:" in body


def test_funnel_route_reuses_application_events_never_a_new_event_table():
    body = _route_body(_career_source(), "get", "/analytics/funnel")
    assert "FROM application_events ae JOIN applications a" in body
    assert "CREATE TABLE" not in body


def test_gaps_route_reuses_opportunity_brain_evidence():
    body = _route_body(_career_source(), "get", "/analytics/gaps")
    assert "aggregate_gap_intelligence(" in body
    assert "SELECT id, fit_score, evidence FROM opportunities" in body


def test_channel_discovery_route_never_creates_spontaneous_application_channel_type():
    body = _route_body(_career_source(), "post", "/opportunities/{opportunity_id}/channels/discover")
    assert "SPONTANEOUS_APPLICATION" not in body
    assert "discover_job_channel_candidates(" in body
    assert "discover_company_channel_candidates(" in body


def test_channel_discovery_route_is_idempotent_via_existing_unique_constraint():
    body = _route_body(_career_source(), "post", "/opportunities/{opportunity_id}/channels/discover")
    assert "ON CONFLICT (opportunity_id, type, url_or_email) DO UPDATE" in body


def test_grouped_interventions_route_never_deletes_individual_rows():
    body = _route_body(_career_source(), "get", "/interventions/grouped")
    assert "DELETE" not in body.upper()
    assert "group_interventions_by_root_cause(" in body
