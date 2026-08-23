from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_prepare_request_accepts_a_job_urls_filter() -> None:
    source = _source()
    start = source.index("class PrepareRequest(BaseModel):")
    body = source[start : start + 150]
    assert "job_urls: list[str] = []" in body


def test_targeting_a_url_supersedes_any_existing_application_instead_of_duplicating() -> None:
    source = _source()
    start = source.index("async def inspect_application_queue(")
    body = source[start : start + 1200]
    assert "target_urls = set(request.job_urls)" in body
    assert "indexed.pop(url, None)" in body
    assert 'and (not target_urls or job.get("url") in target_urls)' in body
