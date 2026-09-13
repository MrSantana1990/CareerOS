"""Fase 2, Prompt 9.1 - Job Canonicalization & Dedup Repair. Testes A-N da
Secao 17. Caso real usado como benchmark: Zeleno Meds (LinkedIn job id
4459952895), a mesma vaga real raspada 7x com query strings de tracking
diferentes, virando 7 linhas de `jobs` porque o fingerprint por conteudo
(quality.job_fingerprint) hasheava um `description` que mudava a cada
raspagem (UI/sidebar volatil do LinkedIn - contagem de candidaturas, "ha X
dias", vagas similares no rodape)."""

from pathlib import Path

from src.job_identity import (
    canonical_job_fingerprint, classify_duplicate_confidence, extract_provider_job_id,
    group_duplicate_jobs, is_auto_mergeable,
)

_ZELENO_URL_1 = ("https://www.linkedin.com/jobs/view/4459952895/?eBP=CwEAAAGghTEtgSbG3KDupHtj3K9M"
                 "&refId=gEeU8KPUcHRGe2xpw26JLA%3D%3D&trackingId=46NNILfHeU8iWgujUINkLg%3D%3D&trk=flagship3_search_srp_jobs")
_ZELENO_URL_2 = ("https://www.linkedin.com/jobs/view/4459952895/?alternateChannel=search"
                 "&refId=WA7kehgXUhEfXLKU%2Bg2oGA%3D%3D&trackingId=Ymq%2BmwX9SW%2B2thvx13yoGg%3D%3D&trk=d_flagship3_search_srp_jobs")
_ZELENO_DESCRIPTION_1 = ("Analista de Dados vaga real conteudo estavel requisitos sql python. "
                         "candidaturas setenta pessoas visualizacoes recentes semana")
_ZELENO_DESCRIPTION_2 = ("Analista de Dados vaga real conteudo estavel requisitos sql python. "
                         "inscricoes oitenta pessoas acessos recentes quinzena")


# A: LinkedIn same job + different utm -> same Job ----------------------------------------------

def test_a_linkedin_same_job_different_utm_produces_same_fingerprint():
    url_a = "https://www.linkedin.com/jobs/view/4459952895/?utm_source=share&utm_medium=member_desktop"
    url_b = "https://www.linkedin.com/jobs/view/4459952895/?utm_source=email&utm_campaign=weekly"
    fp_a, method_a, id_a = canonical_job_fingerprint(company="Zeleno Meds", title="Analista de Dados",
                                                       location="Sao Paulo", description="qualquer coisa",
                                                       source="linkedin", canonical_url=url_a)
    fp_b, method_b, id_b = canonical_job_fingerprint(company="Zeleno Meds", title="Analista de Dados",
                                                       location="Sao Paulo", description="outra coisa diferente",
                                                       source="linkedin", canonical_url=url_b)
    assert fp_a == fp_b
    assert method_a == method_b == "PROVIDER_ID"
    assert id_a == id_b == "4459952895"


# B: LinkedIn same job + different trk -> same Job (caso real Zeleno Meds) ----------------------

def test_b_real_zeleno_meds_case_different_tracking_params_same_fingerprint():
    fp_1, method_1, id_1 = canonical_job_fingerprint(
        company="Zeleno Meds", title="Analista de Dados / DBA / Engenheiro(a) de Dados - Pleno",
        location="Sao Paulo", description=_ZELENO_DESCRIPTION_1, source="linkedin", canonical_url=_ZELENO_URL_1)
    fp_2, method_2, id_2 = canonical_job_fingerprint(
        company="Zeleno Meds", title="Analista de Dados / DBA / Engenheiro(a) de Dados - Pleno",
        location="Sao Paulo", description=_ZELENO_DESCRIPTION_2, source="linkedin", canonical_url=_ZELENO_URL_2)
    assert fp_1 == fp_2
    assert id_1 == id_2 == "4459952895"
    # Prova direta do bug real: o fingerprint ANTIGO (por conteudo) teria
    # sido diferente aqui, porque as descriptions sao diferentes.
    from src.quality import job_fingerprint
    old_fp_1 = job_fingerprint("Zeleno Meds", "titulo", "Sao Paulo", _ZELENO_DESCRIPTION_1)
    old_fp_2 = job_fingerprint("Zeleno Meds", "titulo", "Sao Paulo", _ZELENO_DESCRIPTION_2)
    assert old_fp_1 != old_fp_2


# C: LinkedIn different job ID -> distinct Jobs --------------------------------------------------

def test_c_linkedin_different_job_id_produces_distinct_fingerprints():
    fp_a, _, _ = canonical_job_fingerprint(company="Acme", title="Analista", location="SP",
                                             description="d", source="linkedin",
                                             canonical_url="https://www.linkedin.com/jobs/view/1111111111/")
    fp_b, _, _ = canonical_job_fingerprint(company="Acme", title="Analista", location="SP",
                                             description="d", source="linkedin",
                                             canonical_url="https://www.linkedin.com/jobs/view/2222222222/")
    assert fp_a != fp_b


def test_c_extract_provider_job_id_infojobs_and_catho():
    assert extract_provider_job_id("InfoJobs",
        "https://www.infojobs.com.br/vaga-de-analista-bi-em-pernambuco__11759345.aspx") == "11759345"
    assert extract_provider_job_id("Catho",
        "https://www.catho.com.br/vagas/analista-de-suporte-informatica-sao-paulo-sp/38017389") == "38017389"
    assert extract_provider_job_id("linkedin", "https://www.linkedin.com/jobs/view/4459952895/") == "4459952895"


def test_unknown_source_never_extracts_an_id():
    assert extract_provider_job_id("gupy", "https://portal.gupy.io/job/123") is None
    assert extract_provider_job_id(None, "https://www.linkedin.com/jobs/view/123/") is None
    assert extract_provider_job_id("linkedin", None) is None


# D: same company/title different location -> distinct when appropriate -------------------------

def test_d_same_company_and_title_different_location_is_ambiguous_never_auto_merged():
    # Secao 5: "Analista de Dados" na mesma empresa em duas cidades pode
    # ser duas vagas reais - nunca DISTINCT com certeza (ha sinal parcial
    # de duplicidade), mas tambem nunca auto-mergeavel (Secao 16).
    job_a = {"id": "a", "source": "linkedin", "company_id": "acme", "title": "Analista de Dados",
             "location": "Sao Paulo", "canonical_url": "https://x.com/a", "discovered_at": "2026-01-01"}
    job_b = {"id": "b", "source": "linkedin", "company_id": "acme", "title": "Analista de Dados",
             "location": "Recife", "canonical_url": "https://x.com/b", "discovered_at": "2026-01-02"}
    confidence = classify_duplicate_confidence(job_a, job_b)
    assert confidence == "AMBIGUOUS"
    assert not is_auto_mergeable(confidence)


def test_d_same_company_and_title_same_location_is_high_confidence_semantic():
    job_a = {"id": "a", "source": "linkedin", "company_id": "acme", "title": "Analista de Dados",
             "location": "Sao Paulo", "canonical_url": "https://x.com/a", "discovered_at": "2026-01-01"}
    job_b = {"id": "b", "source": "linkedin", "company_id": "acme", "title": "Analista de Dados",
             "location": "Sao Paulo", "canonical_url": "https://x.com/b", "discovered_at": "2026-01-02"}
    assert classify_duplicate_confidence(job_a, job_b) == "HIGH_CONFIDENCE_SEMANTIC"
    assert not is_auto_mergeable("HIGH_CONFIDENCE_SEMANTIC")


# E: same title different company -> distinct --------------------------------------------------

def test_e_same_title_different_company_is_distinct():
    job_a = {"id": "a", "source": "linkedin", "company_id": "acme", "title": "Analista de Dados",
             "location": "Sao Paulo", "canonical_url": "https://x.com/a", "discovered_at": "2026-01-01"}
    job_b = {"id": "b", "source": "linkedin", "company_id": "outra-empresa", "title": "Analista de Dados",
             "location": "Sao Paulo", "canonical_url": "https://x.com/b", "discovered_at": "2026-01-02"}
    assert classify_duplicate_confidence(job_a, job_b) == "DISTINCT"


# F: repeated ingestion idempotent (fingerprint estavel entre chamadas) --------------------------

def test_f_repeated_computation_is_perfectly_idempotent():
    args = dict(company="Zeleno Meds", title="Analista", location="SP", description=_ZELENO_DESCRIPTION_1,
                source="linkedin", canonical_url=_ZELENO_URL_1)
    first = canonical_job_fingerprint(**args)
    second = canonical_job_fingerprint(**args)
    assert first == second


# G/H: grouping never creates a second canonical - only 1 canonical per group -------------------

def test_g_group_duplicate_jobs_real_zeleno_meds_7_rows_become_1_group():
    jobs = []
    urls = [
        "https://www.linkedin.com/jobs/view/4459952895/?eBP=aaa&trk=1",
        "https://www.linkedin.com/jobs/view/4459952895/?eBP=bbb&trk=2",
        "https://www.linkedin.com/jobs/view/4459952895/?alternateChannel=search&refId=1",
        "https://www.linkedin.com/jobs/view/4459952895/?eBP=ccc&refId=2",
        "https://www.linkedin.com/jobs/view/4459952895/?alternateChannel=search&refId=3",
        "https://www.linkedin.com/jobs/view/4459952895/?eBP=ddd&refId=4",
        "https://www.linkedin.com/jobs/view/4459952895/",
    ]
    for index, url in enumerate(urls):
        jobs.append({"id": f"job-{index}", "source": "linkedin", "source_url": url, "canonical_url": url,
                     "company_id": "zeleno", "title": "Analista de Dados", "location": "Sao Paulo",
                     "discovered_at": f"2026-09-{7 + index:02d}"})
    grouping = group_duplicate_jobs(jobs)
    assert len(grouping["auto_mergeable"]) == 1
    group = grouping["auto_mergeable"][0]
    assert group["confidence"] == "EXACT_PROVIDER_ID"
    assert group["canonical_job_id"] == "job-0"  # mais antigo por discovered_at
    assert set(group["duplicate_job_ids"]) == {f"job-{i}" for i in range(1, 7)}
    assert grouping["semantic_only"] == []


def test_h_group_never_produces_two_canonical_ids_for_the_same_real_job():
    jobs = [
        {"id": "a", "source": "linkedin", "canonical_url": "https://www.linkedin.com/jobs/view/999/?x=1",
         "company_id": "c", "title": "t", "location": "l", "discovered_at": "2026-01-01"},
        {"id": "b", "source": "linkedin", "canonical_url": "https://www.linkedin.com/jobs/view/999/?x=2",
         "company_id": "c", "title": "t", "location": "l", "discovered_at": "2026-01-02"},
    ]
    grouping = group_duplicate_jobs(jobs)
    canonical_ids = {g["canonical_job_id"] for g in grouping["auto_mergeable"]}
    assert len(canonical_ids) == 1


def test_group_duplicate_jobs_url_group_excludes_already_provider_grouped():
    # Um job sem source reconhecida mas com a mesma URL exata (sem query
    # string) de outro ainda cai no grupo EXACT_CANONICAL_URL.
    jobs = [
        {"id": "a", "source": "unknownats", "canonical_url": "https://boards.example.com/jobs/55",
         "company_id": "c", "title": "t", "location": "l", "discovered_at": "2026-01-01"},
        {"id": "b", "source": "unknownats", "canonical_url": "https://boards.example.com/jobs/55?utm=x",
         "company_id": "c", "title": "t", "location": "l", "discovered_at": "2026-01-02"},
    ]
    grouping = group_duplicate_jobs(jobs)
    assert len(grouping["auto_mergeable"]) == 1
    assert grouping["auto_mergeable"][0]["confidence"] == "EXACT_CANONICAL_URL"


def test_single_job_never_forms_a_group():
    jobs = [{"id": "a", "source": "linkedin", "canonical_url": "https://www.linkedin.com/jobs/view/1/",
             "company_id": "c", "title": "t", "location": "l", "discovered_at": "2026-01-01"}]
    grouping = group_duplicate_jobs(jobs)
    assert grouping["auto_mergeable"] == []
    assert grouping["semantic_only"] == []


# I/J/K/L/M: wiring-level guarantees (career.py route) -------------------------------------------

def _career_source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "career.py").read_text(encoding="utf-8")


def _route_body(source: str, path: str) -> str:
    start = source.index(f'@router.post("{path}")')
    end = source.index("\n@router.", start + 1)
    return source[start:end]


def test_i_reconciliation_route_never_merges_when_multiple_jobs_have_real_applications():
    body = _route_body(_career_source(), "/jobs/reconcile-duplicates")
    assert "MULTIPLE_JOBS_WITH_REAL_APPLICATIONS" in body
    assert "len(jobs_with_applications) > 1" in body


def test_reconciliation_route_defaults_to_dry_run_never_writes_by_accident():
    body = _route_body(_career_source(), "/jobs/reconcile-duplicates")
    assert "dry_run: bool = True" in body


def test_reconciliation_route_never_deletes_a_job_row():
    body = _route_body(_career_source(), "/jobs/reconcile-duplicates")
    assert "DELETE FROM jobs" not in body
    assert "DELETE FROM opportunities" not in body
    assert "DELETE FROM applications" not in body


def test_j_reconciliation_never_repoints_opportunity_channels_or_applications_fk():
    # Canal de e-mail/Action Plan da Opportunity permanecem intocados - so
    # a evidence (jsonb) da Opportunity duplicada ganha uma marca auditavel.
    body = _route_body(_career_source(), "/jobs/reconcile-duplicates")
    assert "UPDATE opportunity_channels" not in body
    assert "UPDATE applications" not in body
    assert 'UPDATE opportunities SET evidence' in body
    assert "job_id" not in body.split("UPDATE opportunities SET evidence")[1].split("WHERE")[0]


def test_k_ingest_job_still_creates_a_job_discovered_signal_per_observation():
    # Multiplas observacoes da mesma vaga real continuam gerando Signals
    # (provenance historica, Secao 9) - o que muda e que agora elas
    # convergem para o MESMO Job canonico via canonical_job_fingerprint,
    # em vez de cada uma criar um Job novo.
    source = _career_source()
    start = source.index("async def ingest_job(")
    end = source.index("\n@router.", start)
    body = source[start:end]
    assert "canonical_job_fingerprint(" in body
    assert "'JOB_DISCOVERED'" in body
    assert "signal_fingerprint(" in body


def test_m_reconciliation_route_never_calls_a_send_or_submit_function():
    body = _route_body(_career_source(), "/jobs/reconcile-duplicates")
    for forbidden in ("send_application_email(", "urlopen(", "requests.post(", "submit"):
        assert forbidden not in body


def test_reconciliation_backfills_the_canonical_jobs_fingerprint_for_forward_idempotency():
    # Achado real na validacao em producao deste prompt (Secao 11): marcar
    # as duplicatas nao basta - se o Job canonico continuar com o
    # fingerprint ANTIGO (por conteudo), uma raspagem futura da MESMA vaga
    # real (tracking param diferente) computaria o novo fingerprint por
    # provider_id e nao bateria com o valor antigo, criando um Job novo em
    # vez de reconhecer o canonico. O UPDATE do fingerprint do canonico
    # fecha esse gap.
    body = _route_body(_career_source(), "/jobs/reconcile-duplicates")
    assert "UPDATE jobs SET fingerprint=:fingerprint" in body
    assert 'if method == "PROVIDER_ID":' in body


def test_pending_evaluation_filter_excludes_duplicate_jobs():
    body = _route_body_get(_career_source(), "/jobs")
    assert "j.dedup_status != 'DUPLICATE'" in body


def _route_body_get(source: str, path: str) -> str:
    start = source.index(f'@router.get("{path}")')
    end = source.index("\n@router.", start + 1)
    return source[start:end]
