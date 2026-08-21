import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.main import authenticated_application_url  # noqa: E402


def test_linkedin_regional_url_uses_authenticated_host() -> None:
    original = "https://br.linkedin.com/jobs/view/example-123?trackingId=abc"

    assert authenticated_application_url(original) == (
        "https://www.linkedin.com/jobs/view/example-123?trackingId=abc"
    )


def test_external_ats_url_is_unchanged() -> None:
    original = "https://jobs.example.com/application/123"

    assert authenticated_application_url(original) == original
