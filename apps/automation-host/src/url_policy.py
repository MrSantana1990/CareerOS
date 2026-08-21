from urllib.parse import urlparse


def authenticated_application_url(value: str) -> str:
    """Use the LinkedIn host covered by the authenticated session cookie."""
    parsed = urlparse(value)
    if parsed.netloc.lower() in {"br.linkedin.com", "linkedin.com"}:
        return parsed._replace(netloc="www.linkedin.com").geturl()
    return value
