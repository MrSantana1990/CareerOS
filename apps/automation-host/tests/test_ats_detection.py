import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ats_detection import detect_ats  # noqa: E402


def test_detects_greenhouse_board() -> None:
    match = detect_ats("https://boards.greenhouse.io/airbnb/jobs/123456")
    assert match is not None
    assert match.adapter == "GREENHOUSE"
    assert match.account_key == "airbnb"


def test_detects_greenhouse_job_boards_alias_host() -> None:
    match = detect_ats("https://job-boards.greenhouse.io/stripe/jobs/9999")
    assert match is not None
    assert match.adapter == "GREENHOUSE"
    assert match.account_key == "stripe"


def test_detects_lever_board_with_query_string() -> None:
    match = detect_ats("https://jobs.lever.co/stripe/9f1c2b3a?lever-source=LinkedIn")
    assert match is not None
    assert match.adapter == "LEVER"
    assert match.account_key == "stripe"


def test_detects_ashby_board_case_insensitive_host() -> None:
    match = detect_ats("https://Jobs.AshbyHQ.com/notion/9f1c2b3a")
    assert match is not None
    assert match.adapter == "ASHBY"
    assert match.account_key == "notion"


def test_ignores_generic_job_boards() -> None:
    urls = [
        "https://www.linkedin.com/jobs/view/example-123",
        "https://br.indeed.com/viewjob?jk=abcdef",
        "https://www.catho.com.br/vagas/exemplo-de-vaga/",
        "https://www.infojobs.com.br/vaga-exemplo.aspx",
    ]
    for url in urls:
        assert detect_ats(url) is None


def test_ignores_lookalike_host() -> None:
    assert detect_ats("https://notgreenhouse.io/airbnb/jobs/123") is None
    assert detect_ats("https://boards.greenhouse.io.evil.com/airbnb/jobs/123") is None


def test_ignores_missing_or_empty_url() -> None:
    assert detect_ats(None) is None
    assert detect_ats("") is None


def test_ignores_board_without_recoverable_slug() -> None:
    assert detect_ats("https://boards.greenhouse.io/") is None


def test_rejects_slug_with_invalid_characters() -> None:
    assert detect_ats("https://jobs.lever.co/apply%20now/123") is None
