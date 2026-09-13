from src.career import CompanyIntelInput


def test_company_intel_input_accepts_only_what_was_really_resolved():
    payload = CompanyIntelInput(careers_url="https://acme.com/careers", ats_type="GREENHOUSE")
    assert payload.careers_url == "https://acme.com/careers"
    assert payload.ats_type == "GREENHOUSE"
    assert payload.domain is None
    assert payload.official_recruiting_email is None
    assert payload.talent_pool_url is None
    assert payload.br_presence is None
    assert payload.evidence == {}


def test_company_intel_input_all_fields_optional_never_forces_invention():
    payload = CompanyIntelInput()
    assert payload.model_dump() == {
        "domain": None,
        "careers_url": None,
        "ats_type": None,
        "official_recruiting_email": None,
        "talent_pool_url": None,
        "br_presence": None,
        "evidence": {},
    }


def test_company_intel_input_accepts_domain_and_evidence():
    payload = CompanyIntelInput(domain="zelenomeds.com",
                                 evidence={"domain": {"confidence": 70, "source": "official_recruiting_email"}})
    assert payload.domain == "zelenomeds.com"
    assert payload.evidence["domain"]["confidence"] == 70
