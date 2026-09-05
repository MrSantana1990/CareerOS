from src.career import CompanyIntelInput


def test_company_intel_input_accepts_only_what_was_really_resolved():
    payload = CompanyIntelInput(careers_url="https://acme.com/careers", ats_type="GREENHOUSE")
    assert payload.careers_url == "https://acme.com/careers"
    assert payload.ats_type == "GREENHOUSE"
    assert payload.official_recruiting_email is None
    assert payload.talent_pool_url is None
    assert payload.br_presence is None


def test_company_intel_input_all_fields_optional_never_forces_invention():
    payload = CompanyIntelInput()
    assert payload.model_dump() == {
        "careers_url": None,
        "ats_type": None,
        "official_recruiting_email": None,
        "talent_pool_url": None,
        "br_presence": None,
    }
