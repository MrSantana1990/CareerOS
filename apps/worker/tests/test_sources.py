from src.sources import AshbyAdapter, GreenhouseAdapter, LeverAdapter, build_adapter, plain_text


def test_html_is_converted_to_plain_text():
    assert plain_text("<p>SQL &amp; <strong>AWS</strong></p>") == "SQL & AWS"


def test_greenhouse_normalization_preserves_published_facts():
    job = GreenhouseAdapter("example", "Example Inc").normalize({
        "id": 42, "title": "DBA", "absolute_url": "https://example/jobs/42",
        "content": "<p>PostgreSQL</p>", "location": {"name": "Remote"},
    })
    assert job.external_id == "42"
    assert job.description == "PostgreSQL"
    assert job.application_channel == "GREENHOUSE"


def test_lever_normalization_includes_compensation():
    job = LeverAdapter("example", "Example Inc").normalize({
        "id": "abc", "text": "Support Engineer", "hostedUrl": "https://jobs/abc",
        "descriptionPlain": "Support", "categories": {"location": "Brazil"},
        "workplaceType": "remote", "salaryRange": {"min": 5000, "max": 7000,
        "currency": "BRL", "interval": "month"},
    })
    assert job.salary_min == 5000
    assert job.work_model == "remote"


def test_ashby_normalization_never_invents_missing_compensation():
    job = AshbyAdapter("example", "Example Inc").normalize({
        "id": "xyz", "title": "Data Analyst", "jobUrl": "https://jobs/xyz",
        "descriptionHtml": "<p>SQL</p>", "location": "São Paulo", "isRemote": False,
    })
    assert job.salary_min is None
    assert job.description == "SQL"


def test_adapter_factory_rejects_unknown_source_and_unsafe_account():
    try:
        build_adapter("unknown", "example", "Example Inc")
        raise AssertionError("unknown source accepted")
    except ValueError:
        pass
    try:
        build_adapter("lever", "../../unsafe", "Example Inc")
        raise AssertionError("unsafe account accepted")
    except ValueError:
        pass
