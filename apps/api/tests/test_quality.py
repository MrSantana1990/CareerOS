from src.quality import job_fingerprint, match_radars, score_job, transition_allowed


def test_fingerprint_normalizes_accents_and_case():
    assert job_fingerprint("Empresa Ágil", "DBA Sênior", "Campinas", "SQL Server AWS") == job_fingerprint("empresa agil", "dba senior", "campinas", "AWS; SQL Server")


def test_hard_block_precedes_high_score():
    result = score_job({"title": "DBA Senior", "source": "GUPY", "required_skills": ["SQL Server"], "work_model": "REMOTE", "application_channel": "EMAIL"}, {"verified_skills": ["SQL Server"], "target_roles": ["DBA Senior"], "work_models": ["REMOTE"]})
    assert result.recommendation == "BLOCK"
    assert "GUPY_BLOCK" in result.blocking_rules


def test_score_is_explainable_and_qualified():
    result = score_job({"title": "Application Support", "source": "GREENHOUSE", "required_skills": ["SQL Server", "AWS"], "work_model": "REMOTE", "seniority": "SENIOR", "application_channel": "GREENHOUSE"}, {"verified_skills": ["SQL Server", "AWS"], "target_roles": ["Application Support"], "work_models": ["REMOTE"]})
    assert result.total >= 80
    assert result.recommendation == "APPLY_HIGH"
    assert result.dimensions["technology"] == 30


def test_state_machine_rejects_unsafe_jump():
    assert transition_allowed("DISCOVERED", "VALIDATING")
    assert not transition_allowed("DISCOVERED", "CONFIRMED")


def test_match_radars_ignores_disabled_radars():
    job = {"title": "Analista de Suporte N3", "description": "Sustentação de sistemas críticos"}
    radars = [{"code": "RADAR_SUPPORT", "enabled": False, "roles": ["Analista de Suporte N3"], "keywords": []}]
    assert match_radars(job, radars) == []


def test_match_radars_finds_role_overlap_when_enabled():
    job = {"title": "Analista de Suporte N3", "description": "Sustentação de sistemas críticos"}
    radars = [{"code": "RADAR_SUPPORT", "enabled": True, "roles": ["Analista de Suporte N3"], "keywords": []}]
    assert match_radars(job, radars) == ["RADAR_SUPPORT"]


def test_match_radars_finds_keyword_overlap_in_description():
    job = {"title": "DBA Pleno", "description": "Vaga remota trabalhando com BigQuery e Power BI"}
    radars = [{"code": "RADAR_DATA", "enabled": True, "roles": [], "keywords": ["bigquery"]}]
    assert match_radars(job, radars) == ["RADAR_DATA"]


def test_match_radars_returns_multiple_matches_in_order():
    job = {"title": "Suporte e Dados - DBA SQL Server", "description": ""}
    radars = [
        {"code": "RADAR_SUPPORT", "enabled": True, "roles": [], "keywords": ["suporte"]},
        {"code": "RADAR_DATA", "enabled": True, "roles": ["DBA SQL Server"], "keywords": []},
    ]
    assert match_radars(job, radars) == ["RADAR_SUPPORT", "RADAR_DATA"]


def test_match_radars_no_overlap_returns_empty():
    job = {"title": "Vendedor Externo", "description": "Vendas de produtos de beleza"}
    radars = [{"code": "RADAR_SUPPORT", "enabled": True, "roles": ["Analista de Suporte"], "keywords": ["suporte"]}]
    assert match_radars(job, radars) == []
