from src.market_signal_source import (build_job_discovered_signal_payload, build_rss_url,
                                       classify_signal_type, parse_rss_items, resolve_company)

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Test feed</title>
<item>
  <title>Nubank investe R$2,5 bilhões e inaugura escritório em Campinas</title>
  <link>https://example.com/nubank-campinas</link>
  <pubDate>Tue, 08 Sep 2026 12:00:00 GMT</pubDate>
  <source url="https://forbes.com.br">Forbes Brasil</source>
</item>
<item>
  <title>Empresa X anuncia contratação de nova equipe de dados</title>
  <link>https://example.com/empresa-x</link>
  <pubDate>Mon, 07 Sep 2026 09:00:00 GMT</pubDate>
  <source>G1</source>
</item>
<item>
  <title></title>
  <link>https://example.com/no-title</link>
</item>
</channel>
</rss>
"""


def test_parse_rss_items_extracts_title_link_source_and_pubdate() -> None:
    items = parse_rss_items(SAMPLE_RSS)
    assert len(items) == 2  # o item sem title/link e descartado
    first = items[0]
    assert first.title == "Nubank investe R$2,5 bilhões e inaugura escritório em Campinas"
    assert first.link == "https://example.com/nubank-campinas"
    assert first.source == "Forbes Brasil"
    assert first.published_at == "Tue, 08 Sep 2026 12:00:00 GMT"


def test_parse_rss_items_skips_entries_without_title_or_link() -> None:
    items = parse_rss_items(SAMPLE_RSS)
    assert all(item.title and item.link for item in items)


def test_build_rss_url_encodes_query_and_sets_brazil_locale() -> None:
    url = build_rss_url("empresa expansão Campinas")
    assert url.startswith("https://news.google.com/rss/search?q=")
    assert "hl=pt-BR" in url
    assert "gl=BR" in url


def test_classify_signal_type_new_office() -> None:
    assert classify_signal_type("Nubank inaugura novo escritório em Campinas") == "NEW_OFFICE"


def test_classify_signal_type_expansion() -> None:
    assert classify_signal_type("Empresa anuncia expansão no interior de SP") == "EXPANSION"


def test_classify_signal_type_investment() -> None:
    assert classify_signal_type("Empresa recebe investimento de R$500 milhões") == "INVESTMENT"


def test_classify_signal_type_hiring() -> None:
    assert classify_signal_type("Empresa abre contratação para nova equipe") == "HIRING_ANNOUNCEMENT"


def test_classify_signal_type_uncertain_falls_back_to_other_verified() -> None:
    # Nao exige classificacao perfeita (secao 4) - quando incerto,
    # OTHER_VERIFIED_SIGNAL em vez de arriscar uma classificacao especifica.
    assert classify_signal_type("Empresa reforça presença no mercado brasileiro") == "OTHER_VERIFIED_SIGNAL"


def test_resolve_company_matches_known_company_case_insensitively() -> None:
    result = resolve_company("nubank investe em Campinas", ["Nubank", "Deutsche Bank Brasil"])
    assert result == "Nubank"


def test_resolve_company_returns_none_when_no_known_company_matches() -> None:
    # Nunca inventa/adivinha Company nova a partir de uma manchete (secao 5).
    result = resolve_company("Empresa Desconhecida investe em Campinas", ["Nubank", "Deutsche Bank Brasil"])
    assert result is None


def test_resolve_company_prefers_the_longer_more_specific_match() -> None:
    result = resolve_company("Deutsche Bank Brasil expande operação", ["Deutsche Bank Brasil", "Deutsche Bank"])
    assert result == "Deutsche Bank Brasil"


def test_build_job_discovered_signal_payload_never_duplicates_job_content() -> None:
    payload = build_job_discovered_signal_payload(
        company_id="company-1", source_url="https://boards.greenhouse.io/acme/jobs/1",
        headline="Senior Data Engineer", job_fingerprint="abc123",
    )
    assert payload["type"] == "JOB_DISCOVERED"
    assert payload["headline"] == "Senior Data Engineer"
    assert "description" not in payload
    assert "requirements" not in payload
    assert payload["evidence"] == {"job_fingerprint": "abc123"}
