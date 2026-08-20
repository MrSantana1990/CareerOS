from fastapi import Header, HTTPException

from .config import get_settings

settings = get_settings()


async def require_admin(
    authorization: str | None = Header(default=None),
    organization_slug: str | None = Header(default=None, alias="X-Organization-Slug"),
) -> str:
    if settings.app_env == "production":
        expected = settings.admin_api_token.strip()
        supplied = (authorization or "").removeprefix("Bearer ").strip()
        if not expected or supplied != expected:
            raise HTTPException(status_code=401, detail="Credencial administrativa inválida.")
    return organization_slug or settings.default_organization_slug
