"""Fase 2, Prompt 13 - wiring/observabilidade do Content Perception
(main.py). Complementa os testes puros de classificacao/extracao/QR em
test_multimodal_perception.py (as funcoes puras moram em
multimodal_perception.py, sem I/O proprio - so decode_qr_from_image_bytes
tem import tardio opcional de Pillow/pyzbar)."""

from pathlib import Path


def _main_source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def _function_body(source: str, name: str) -> str:
    start = source.index(f"async def {name}(")
    candidates = []
    for marker in ("\nasync def ", "\ndef ", "\n@app."):
        index = source.find(marker, start + 1)
        if index != -1:
            candidates.append(index)
    end = min(candidates) if candidates else len(source)
    return source[start:end]


def test_content_perceive_endpoint_is_registered() -> None:
    source = _main_source()
    assert '@app.post("/content/perceive")' in source


def test_perceive_multimodal_content_never_sends_external_actions() -> None:
    body = _function_body(_main_source(), "perceive_multimodal_content")
    for forbidden in ("send_application_email(", "send_security_code(", "smtplib", "twilio"):
        assert forbidden not in body


def test_perceive_multimodal_content_rejects_non_vacancy_without_ingestion() -> None:
    body = _function_body(_main_source(), "perceive_multimodal_content")
    assert '"NON_VACANCY"' in body
    assert "VACANCY_VISUAL_REJECTED" in body


def test_perceive_multimodal_content_never_invents_company_for_job_ingestion() -> None:
    # So cria Job (build_job_record) quando payload.company foi
    # explicitamente fornecido pelo chamador - caso contrario vira Signal
    # (nunca inventa o nome da empresa, Secao 5/18).
    body = _function_body(_main_source(), "perceive_multimodal_content")
    assert 'classification["classification"] == "VACANCY_CANDIDATE" and payload.company' in body
    assert "_post_signal(" in body


def test_perceive_multimodal_content_reuses_existing_job_ingestion_mechanism() -> None:
    # Secao 18 - nunca um pipeline paralelo: mesmo build_job_record +
    # enqueue_core_sync ja usados por sync_job_to_core (Prompt 8/11/12).
    body = _function_body(_main_source(), "perceive_multimodal_content")
    assert "build_job_record(" in body
    assert "enqueue_core_sync(record)" in body


def test_perceive_multimodal_content_emits_required_observability_events() -> None:
    body = _function_body(_main_source(), "perceive_multimodal_content")
    for required_event in (
        "CONTENT_PERCEPTION_STARTED", "VACANCY_VISUAL_DETECTED", "VACANCY_VISUAL_REJECTED",
        "DIRECT_EMAIL_DETECTED", "DIRECT_WHATSAPP_DETECTED", "MULTIMODAL_JOB_INGESTED",
        "MULTIMODAL_SIGNAL_CREATED", "CONTENT_PERCEPTION_COMPLETED",
    ):
        assert required_event in body


def test_resolve_qr_evidence_never_resolves_unsafe_scheme() -> None:
    body = _function_body(_main_source(), "_resolve_qr_evidence")
    assert "QR_REJECTED_UNSAFE" in body
    assert 'normalized["scheme_classification"] != "SAFE"' in body
    assert 'return {"qr_status": "QR_DECODED", "qr_destination": "UNKNOWN"' in body


def test_resolve_qr_evidence_only_fetches_http_https_schemes() -> None:
    body = _function_body(_main_source(), "_resolve_qr_evidence")
    assert 'normalized["scheme"] in {"http", "https"}' in body
    assert "_fetch_public_page" in body


def test_resolve_qr_evidence_returns_none_without_image() -> None:
    body = _function_body(_main_source(), "_resolve_qr_evidence")
    assert "if not payload.image_base64:" in body
    assert "return None" in body


def test_content_perceive_endpoint_never_bypasses_perception_failures_silently() -> None:
    source = _main_source()
    start = source.index('@app.post("/content/perceive")')
    end = source.index("\n@app.", start + 1) if "\n@app." in source[start + 1:] else len(source)
    body = source[start:end]
    assert "CONTENT_PERCEPTION_FAILED" in body
    assert "raise HTTPException" in body
