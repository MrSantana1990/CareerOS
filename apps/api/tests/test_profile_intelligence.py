from src.profile_intelligence import (extract_certifications, extract_docx_text, extract_education,
                                       extract_employment_history, extract_language_levels,
                                       extract_profile_evidence, find_skill_mentions)

# Trecho real do curriculo GENERAL aprovado em producao (extraido via
# docx->texto na validacao do Prompt 6) - usado aqui como fixture porque e
# a evidencia real que o extractor precisa reconhecer corretamente.
REAL_RESUME_EXCERPT = (
    "RODOLFO SANTANA DE JESUS DATA & DATABASE | SQL | PRODUCTION SUPPORT | CLOUD "
    "Campinas, SP, Brazil | +55 11 94002-5492 | helpsystempro@gmail.com "
    "PROFESSIONAL SUMMARY IT professional with approximately 15 years of experience. "
    "CORE TECHNICAL SKILLS Databases: SQL Server, PostgreSQL, Oracle, Firebird, MySQL | "
    "Cloud & Observability: AWS CloudWatch, Azure, Datadog, Grafana, PRTG "
    "PROFESSIONAL EXPERIENCE "
    "N4 Backend Production Support Analyst | Mobato Tecnologia | Campinas, SP | Jul 2024 - Present "
    "Provide N4 technical support for more than six corporate systems. "
    "Junior Database Administrator (DBA) | Vertical Tecnologia e Sistemas Ltda. | Salvador, BA | Nov 2020 - Jan 2022 "
    "Administered data infrastructure and database performance. "
    "EDUCATION Systems Analysis and Development | UniAmerica | 2022-2024 "
    "TRAINING Azure Specialist Training | AZ-900, AZ-103 and AZ-305 | Azure Academy "
    "LANGUAGES Portuguese: Native | English: Technical reading and writing; spoken communication developing | Spanish: Basic "
    "ADDITIONAL INFORMATION Open to remote and international opportunities."
)


# L: resume evidence extraction --------------------------------------------------------------------

def test_l_employment_history_extracted_with_explicit_format_only():
    entries = extract_employment_history(REAL_RESUME_EXCERPT)
    assert len(entries) == 2
    assert entries[0]["role"] == "N4 Backend Production Support Analyst"
    assert entries[0]["company"] == "Mobato Tecnologia"
    assert "Jul 2024" in entries[0]["period"]
    assert entries[1]["company"] == "Vertical Tecnologia e Sistemas Ltda."


def test_l_education_extracted_from_explicit_section():
    entries = extract_education(REAL_RESUME_EXCERPT)
    assert any("UniAmerica" in entry["value"] or "Systems Analysis" in entry["value"] for entry in entries)


def test_l_certifications_extracted_from_training_section():
    entries = extract_certifications(REAL_RESUME_EXCERPT)
    assert any("AZ-900" in entry["value"] for entry in entries)


def test_l_every_extracted_fact_preserves_evidence_and_confidence():
    entries = extract_employment_history(REAL_RESUME_EXCERPT)
    for entry in entries:
        assert entry["evidence_snippet"]
        assert entry["confidence"] > 0
        assert entry["extraction_method"] == "docx_resume_evidence"


# M: no inferred language --------------------------------------------------------------------------

def test_m_language_level_captured_verbatim_never_simplified():
    levels = extract_language_levels(REAL_RESUME_EXCERPT)
    assert levels["Portuguese"]["value"] == "Native"
    assert levels["Spanish"]["value"] == "Basic"
    # Frase nuancada do ingles preservada verbatim - nunca colapsada para
    # "advanced"/"fluent" so porque o CV inteiro esta em ingles.
    assert "developing" in levels["English"]["value"].lower()
    assert "fluent" not in levels["English"]["value"].lower()
    assert "advanced" not in levels["English"]["value"].lower()


def test_m_no_language_section_returns_empty_never_fabricated():
    assert extract_language_levels("Um curriculo qualquer sem secao de idiomas.") == {}


def test_m_docx_text_extraction_is_pure_stdlib_zipfile():
    import io
    import zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<w:document><w:t>Hello World</w:t></w:document>")
    text = extract_docx_text(buffer.getvalue())
    assert "Hello World" in text


# N: skill evidence idempotency (a extracao em si e determinista - a idempotencia real de
# persistencia em skill_evidence e garantida pela rota via ON CONFLICT, testada em wiring) --------

def test_n_skill_mention_found_with_evidence_snippet():
    mentions = find_skill_mentions(REAL_RESUME_EXCERPT, ["SQL Server", "PostgreSQL", "Kubernetes"])
    names = {m["skill_name"] for m in mentions}
    assert "SQL Server" in names
    assert "PostgreSQL" in names
    assert "Kubernetes" not in names  # nao mencionado no curriculo - nunca fabricado


def test_n_skill_mention_is_deterministic_for_identical_input():
    first = find_skill_mentions(REAL_RESUME_EXCERPT, ["SQL Server"])
    second = find_skill_mentions(REAL_RESUME_EXCERPT, ["SQL Server"])
    assert first == second


def test_extract_profile_evidence_aggregates_all_dimensions():
    evidence = extract_profile_evidence(REAL_RESUME_EXCERPT, ["SQL Server", "Azure"])
    assert evidence["language_levels"]["Portuguese"]["value"] == "Native"
    assert len(evidence["employment"]) == 2
    assert evidence["education"]
    assert evidence["certifications"]
    assert {m["skill_name"] for m in evidence["skill_mentions"]} == {"SQL Server", "Azure"}
    assert evidence["extracted_at"]
