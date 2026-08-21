from src.quality import job_fingerprint, score_job, transition_allowed


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
