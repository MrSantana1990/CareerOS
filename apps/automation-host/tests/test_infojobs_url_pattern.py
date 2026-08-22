from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_looks_like_job_infojobs_pattern_matches_current_real_url_structure() -> None:
    """Achado real em produção: a busca de InfoJobs sempre retornava found=0
    (confirmado nos logs da VPS - SEARCH_COMPLETED com found=0 em toda
    execução), mesmo com a página carregando vagas reais. O padrão antigo
    ("/vaga-de-emprego-", "/vagas-de-emprego/") não bate com a estrutura
    atual de URL do site (confirmado navegando na página real):
    "/vaga-de-analista-suporte-n3-ti-1428-em-sao-paulo__11852782.aspx"."""
    source = _source()
    assert '"InfoJobs": ("/vaga-de-",)' in source
    assert '"/vaga-de-emprego-"' not in source


def test_infojobs_pattern_still_excludes_the_search_page_itself() -> None:
    """A própria página de busca usa "vagas-de-emprego-" (plural) - o padrão
    novo, singular "/vaga-de-", não deve confundir a busca com uma vaga."""
    source = _source()
    start = source.index('def search_url(')
    body = source[start : start + 600]
    assert '"https://www.infojobs.com.br/vagas-de-emprego-{slug}.aspx"' in body
