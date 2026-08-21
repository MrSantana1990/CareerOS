from pathlib import Path


def test_external_application_switches_to_the_new_browser_tab() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "src" / "main.py"
    ).read_text(encoding="utf-8")

    assert "pages_before_action = set(browser.pages)" in source
    assert "page = opened_pages[-1]" in source
    assert source.count('if "gupy.io" in page.url.lower():') >= 2
