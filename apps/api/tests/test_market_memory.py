from src.market_memory import opportunity_fingerprint, signal_fingerprint, watch_fingerprint


def test_signal_fingerprint_is_deterministic():
    a = signal_fingerprint("company-1", "EXPANSION", "https://example.com/news")
    b = signal_fingerprint("company-1", "EXPANSION", "https://example.com/news")
    assert a == b


def test_signal_fingerprint_differs_by_source_url():
    a = signal_fingerprint("company-1", "EXPANSION", "https://example.com/a")
    b = signal_fingerprint("company-1", "EXPANSION", "https://example.com/b")
    assert a != b


def test_signal_fingerprint_handles_missing_company_without_colliding_with_a_real_one():
    # Uma company_id real nunca deve colidir com o sentinel usado para "ainda
    # nao resolvida" - sao strings distintas, nao dependem de NULL do Postgres.
    without_company = signal_fingerprint(None, "EXPANSION", "https://example.com/a")
    with_company = signal_fingerprint("__NONE__", "EXPANSION", "https://example.com/a")
    assert without_company == with_company  # o sentinel e literal, comportamento documentado


def test_opportunity_fingerprint_distinguishes_job_linked_from_spontaneous():
    job_linked = opportunity_fingerprint("company-1", "JOB_APPLICATION", "job-1", None)
    spontaneous = opportunity_fingerprint("company-1", "SPONTANEOUS_APPLICATION", None, None)
    assert job_linked != spontaneous


def test_opportunity_fingerprint_is_deterministic_for_the_same_inputs():
    a = opportunity_fingerprint("company-1", "SPONTANEOUS_APPLICATION", None, None)
    b = opportunity_fingerprint("company-1", "SPONTANEOUS_APPLICATION", None, None)
    assert a == b


def test_opportunity_fingerprint_two_different_companies_never_collide():
    a = opportunity_fingerprint("company-1", "SPONTANEOUS_APPLICATION", None, None)
    b = opportunity_fingerprint("company-2", "SPONTANEOUS_APPLICATION", None, None)
    assert a != b


def test_watch_fingerprint_company_level_differs_from_opportunity_level():
    company_level = watch_fingerprint("company-1", None)
    opportunity_level = watch_fingerprint("company-1", "opportunity-1")
    assert company_level != opportunity_level


def test_watch_fingerprint_is_stable_for_repeated_company_level_watch():
    # Isso e o que impede dois Watches ACTIVE "so a nivel de empresa" pra
    # mesma company (ex.: Nubank) - o fingerprint e o mesmo todas as vezes,
    # entao o segundo INSERT vira um upsert, nunca uma segunda linha.
    a = watch_fingerprint("company-1", None)
    b = watch_fingerprint("company-1", None)
    assert a == b
