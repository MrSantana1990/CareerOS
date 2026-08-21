"""Pure application preparation rules; facts are never generated or embellished."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .quality import normalize


FAMILY_MAP = {
    "SUPPORT": ["PT_SUPPORT_SENIOR", "EN_SUPPORT_DATABASE"],
    "DBA": ["PT_DBA_SQL", "EN_SUPPORT_DATABASE"],
    "SQL": ["PT_DBA_SQL", "EN_SUPPORT_DATABASE"],
    "DATA": ["PT_DATA", "EN_DATA_DATABASE", "EN_DATA_ENGINEERING"],
}


def route_resume(job: dict, resumes: list[dict]) -> dict | None:
    language = normalize(str(job.get("language") or "pt"))
    preferred_language = "en" if language.startswith("en") else "pt"
    families = FAMILY_MAP.get(str(job.get("family") or "").upper(), [])
    candidates = [item for item in resumes if item.get("approved_at") and item.get("active")]
    candidates.sort(key=lambda item: (
        item.get("family") not in families,
        not str(item.get("language") or "").lower().startswith(preferred_language),
        item.get("family") != "GENERAL",
        -int(item.get("version") or 0),
    ))
    return candidates[0] if candidates else None


def application_strategy(job: dict) -> str:
    if job.get("recruiter_email"):
        return "EMAIL"
    channel = normalize(str(job.get("application_channel") or ""))
    if channel in {"greenhouse", "lever", "ashby", "ats api"}:
        return "ATS_API"
    return "MANUAL"


def idempotency_key(organization_id: str, job_id: str) -> str:
    return sha256(f"{organization_id}:{job_id}".encode()).hexdigest()


@dataclass(frozen=True)
class EmailDraft:
    recipient: str
    subject: str
    body: str


def prepare_email_draft(job: dict, profile: dict) -> EmailDraft:
    recipient = str(job.get("recruiter_email") or "").strip()
    if "@" not in recipient:
        raise ValueError("A vaga não possui e-mail legítimo para candidatura.")
    full_name = str(profile.get("full_name") or "").strip()
    if not full_name:
        raise ValueError("Perfil aprovado incompleto.")
    title = str(job.get("title") or "oportunidade").strip()
    company = str(job.get("company") or "empresa").strip()
    subject = f"Candidatura — {title} — {full_name}"
    body = (f"Olá,\n\nTenho interesse na oportunidade de {title} na {company}. "
            "Encaminho meu currículo aprovado para avaliação.\n\n"
            f"Atenciosamente,\n{full_name}")
    return EmailDraft(recipient, subject, body)
