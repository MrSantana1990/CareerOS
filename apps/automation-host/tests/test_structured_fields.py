from src.structured_fields import (classify_board_fetch, extract_all,
                                    extract_application_instructions,
                                    extract_language_requirements, extract_location,
                                    extract_mandatory_vs_preferred, extract_salary,
                                    extract_work_model, from_ats_structured_job)


def test_mandatory_requirement_captured_with_evidence() -> None:
    text = "You must have 5 years of experience with SQL Server. Kubernetes is a plus."
    result = extract_mandatory_vs_preferred(text)
    assert "mandatory_requirements" in result
    assert "SQL Server" in result["mandatory_requirements"]["evidence_snippet"]


def test_preferred_requirement_captured_separately_from_mandatory() -> None:
    text = "Required: SQL. Experience with Kubernetes is a nice to have."
    result = extract_mandatory_vs_preferred(text)
    assert "preferred_requirements" in result
    assert "Kubernetes" in result["preferred_requirements"]["evidence_snippet"]


def test_preferred_skill_never_promoted_to_mandatory() -> None:
    # Secao 18: "experience with Kubernetes is a plus" nao pode virar
    # mandatory Kubernetes.
    text = "Experience with Kubernetes is a plus."
    result = extract_mandatory_vs_preferred(text)
    assert "mandatory_requirements" not in result
    assert "preferred_requirements" in result


def test_explicit_language_requirement_captured() -> None:
    result = extract_language_requirements("Necessário inglês avançado para reuniões internacionais.")
    assert result is not None
    assert result["value"]["level"] is not None


def test_english_page_without_explicit_requirement_returns_none() -> None:
    # Secao 17: pagina escrita em ingles != requisito de ingles do
    # candidato. So convertermos "job description written in English" em
    # requisito seria uma inferencia proibida.
    text = "We are looking for a Senior Data Engineer to join our growing team in Brazil."
    assert extract_language_requirements(text) is None


def test_salary_brl_extraction() -> None:
    result = extract_salary("Salário de R$ 8.000,00 por mês, benefícios inclusos.")
    assert result is not None
    assert result["value"]["salary_currency"] == "BRL"
    assert result["value"]["salary_min"] == 8000
    assert result["value"]["salary_max"] is None


def test_salary_brl_range_extraction() -> None:
    # Achado real na validacao do Prompt 3 (InfoJobs): "R$ 4.330,00 a
    # R$ 4.331,00" e uma faixa, nao um unico valor - salary_max precisa
    # ser reportado quando o texto descreve uma faixa.
    result = extract_salary("Salário de R$ 4.330,00 a R$ 4.331,00, CLT integral.")
    assert result is not None
    assert result["value"]["salary_min"] == 4330
    assert result["value"]["salary_max"] == 4331


def test_salary_usd_extraction() -> None:
    result = extract_salary("Compensation: USD 6k-7k per month, fully remote.")
    assert result is not None
    assert result["value"]["salary_currency"] == "USD"
    assert result["value"]["salary_min"] == 6000
    assert result["value"]["salary_max"] == 7000


def test_no_salary_evidence_returns_none() -> None:
    assert extract_salary("Competitive salary, to be discussed.") is None


def test_hybrid_work_model_with_frequency() -> None:
    result = extract_work_model("This is a hybrid model, 2 days per week in office.")
    assert result["value"]["work_model"] == "HYBRID"
    assert result["value"]["frequency_days_per_week"] == 2


def test_remote_work_model() -> None:
    result = extract_work_model("100% remoto, sem necessidade de deslocamento.")
    assert result["value"]["work_model"] == "REMOTE"


def test_work_model_unknown_never_inferred_from_absence() -> None:
    # Secao 20: nao inferir remote pela ausencia de endereco.
    result = extract_work_model("Vaga para atuar no time de dados da empresa.")
    assert result["value"]["work_model"] == "UNKNOWN"
    assert result["confidence"] == 0


def test_location_extraction_campinas() -> None:
    result = extract_location("Vaga presencial em Campinas, região metropolitana.")
    assert result["value"]["region"] == "Campinas"


def test_recruiting_email_with_evidence() -> None:
    result = extract_application_instructions(
        "Envie seu currículo para rh@empresa.com com o assunto: Vaga Analista."
    )
    assert result is not None
    assert result["value"]["recruiting_email"] == "rh@empresa.com"
    assert "envie" in result["evidence_snippet"].lower()


def test_no_email_inferred_without_apply_instruction() -> None:
    # Secao 21/L: um e-mail generico de contato no rodape, sem instrucao
    # explicita de candidatura, nao conta.
    result = extract_application_instructions("Dúvidas? Contate contato@empresa.com.")
    assert result is None


def test_extract_all_falls_back_to_flat_text_regex() -> None:
    text = "Vaga híbrida em Campinas, salário R$ 6.000, inglês avançado necessário."
    fields = extract_all(text, source_url="https://example.com/vaga")
    assert fields["work_model"]["value"]["work_model"] == "HYBRID"
    assert fields["location"]["value"]["region"] == "Campinas"
    assert fields["salary"]["value"]["salary_min"] == 6000
    assert fields["language_requirements"]["value"]["level"] is not None
    assert fields["work_model"]["source_url"] == "https://example.com/vaga"


def test_from_ats_structured_job_uses_high_confidence_no_regex() -> None:
    normalized = {"location": "Remote - Brazil", "work_model": "REMOTE",
                  "salary_min": 6000, "salary_max": 7000, "salary_currency": "USD",
                  "salary_period": "MONTHLY"}
    fields = from_ats_structured_job(normalized, source_url="https://boards.greenhouse.io/acme/jobs/1")
    assert fields["work_model"]["extraction_method"] == "ats_api"
    assert fields["work_model"]["confidence"] == 95
    assert fields["salary"]["value"]["salary_currency"] == "USD"


def test_classify_board_fetch_live_when_jobs_present() -> None:
    assert classify_board_fetch(200, None, job_count=5) == "LIVE"


def test_classify_board_fetch_closed_is_a_real_signal_not_a_guess() -> None:
    # Um board vazio via API estruturada e um sinal real (nao um
    # falso-negativo de renderizacao, como no Reality Check).
    assert classify_board_fetch(200, None, job_count=0) == "CLOSED"


def test_classify_board_fetch_never_converts_render_failure_into_closed() -> None:
    assert classify_board_fetch(None, "URLError", job_count=None) == "UNVERIFIABLE"


def test_classify_board_fetch_bot_gated_on_403() -> None:
    assert classify_board_fetch(403, None, job_count=None) == "BOT_GATED"


def test_classify_board_fetch_auth_required_on_401() -> None:
    assert classify_board_fetch(401, None, job_count=None) == "AUTH_REQUIRED"


def test_classify_board_fetch_tooling_limit_on_server_error() -> None:
    assert classify_board_fetch(503, None, job_count=None) == "TOOLING_LIMIT"
