from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def _report_intervention_body() -> str:
    source = _source()
    start = source.index("async def report_intervention(")
    end = source.index("\n    def send() -> None:")
    return source[start:end]


def test_intervention_links_to_the_real_core_application_when_known() -> None:
    # Achado real (Cycle 006): application_id sempre ia None pro Core -
    # nenhuma intervencao nunca ficava ligada ao registro real da
    # candidatura, tornando impossivel enriquecer a fila de acao humana
    # (Human Action Queue) com empresa/vaga/score sem abrir cada uma
    # manualmente. A fila real de producao mostrou 6 intervencoes
    # pendentes, todas com application_id vazio.
    body = _report_intervention_body()
    assert 'core_application_id = _load_core_sync_links().get(legacy_id, {}).get("core_application_id")' in body
    assert '"application_id": core_application_id,' in body


def test_intervention_evidence_includes_enough_context_for_a_human_queue() -> None:
    body = _report_intervention_body()
    assert '"source": str(application.get("source", ""))' in body
    assert '"score": application.get("score")' in body
    assert '"region": str(application.get("region", ""))' in body
    assert '"job_url": str(application.get("job_url", ""))[:500]' in body
    assert '"resume_version_id": application.get("core_resume_version_id")' in body
