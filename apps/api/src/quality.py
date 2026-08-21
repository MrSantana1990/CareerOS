"""Deterministic core-quality rules; no network or database side effects."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import re
import unicodedata
from urllib.parse import urlparse


def normalize(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain.lower()).split())


def job_fingerprint(company: str, title: str, location: str, description: str) -> str:
    meaningful = sorted({token for token in normalize(description).split() if len(token) >= 4})[:80]
    material = "|".join((normalize(company), normalize(title), normalize(location), " ".join(meaningful)))
    return sha256(material.encode()).hexdigest()


ALLOWED_TRANSITIONS = {
    "DISCOVERED": {"VALIDATING", "DISCARDED", "ERROR"},
    "VALIDATING": {"VALIDATED", "CLOSED", "MANUAL_REQUIRED", "ERROR"},
    "VALIDATED": {"QUALIFIED", "DISCARDED", "WAITING_DECISION"},
    "QUALIFIED": {"WAITING_DECISION", "PREPARING", "DISCARDED"},
    "WAITING_DECISION": {"PREPARING", "DISCARDED"},
    "PREPARING": {"READY", "MANUAL_REQUIRED", "ERROR"},
    "READY": {"SUBMITTING", "DISCARDED"},
    "SUBMITTING": {"SENT", "CONFIRMED", "MANUAL_REQUIRED", "ERROR"},
    "SENT": {"CONFIRMED", "ERROR"},
    "CONFIRMED": {"RECRUITER_RESPONSE", "REJECTED", "CLOSED"},
    "RECRUITER_RESPONSE": {"INTERVIEW", "REJECTED", "CLOSED"},
    "INTERVIEW": {"TECHNICAL_TEST", "FINAL_STAGE", "OFFER", "REJECTED"},
    "TECHNICAL_TEST": {"FINAL_STAGE", "OFFER", "REJECTED"},
    "FINAL_STAGE": {"OFFER", "REJECTED"},
}


def transition_allowed(current: str, target: str) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


@dataclass(frozen=True)
class ScoreResult:
    total: int
    recommendation: str
    dimensions: dict[str, int]
    strengths: list[str]
    gaps: list[str]
    risks: list[str]
    blocking_rules: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def _overlap(required: list[str], verified: list[str], weight: int) -> tuple[int, list[str], list[str]]:
    wanted = {normalize(item) for item in required if normalize(item)}
    known = {normalize(item) for item in verified if normalize(item)}
    if not wanted:
        return weight, [], []
    matched = wanted & known
    score = round(weight * len(matched) / len(wanted))
    return score, sorted(matched), sorted(wanted - known)


def score_job(job: dict, profile: dict, enabled_rules: set[str] | None = None) -> ScoreResult:
    enabled = enabled_rules or {"GUPY_BLOCK", "SPANISH_FLUENT_BLOCK", "ENGLISH_C1_REVIEW", "SUPPORT_N1_MINIMUM"}
    text = normalize(" ".join(str(job.get(key) or "") for key in ("title", "description", "location")))
    source = normalize(str(job.get("source") or ""))
    domain = normalize(urlparse(str(job.get("canonical_url") or job.get("source_url") or "")).netloc)
    languages = job.get("language_requirements") or []
    blocks: list[str] = []
    risks: list[str] = []
    if "GUPY_BLOCK" in enabled and (source == "gupy" or "gupy io" in domain):
        blocks.append("GUPY_BLOCK")
    if "SPANISH_FLUENT_BLOCK" in enabled and any(normalize(str(item.get("language"))) in {"es", "spanish", "espanhol"} and item.get("required") and normalize(str(item.get("level"))) in {"fluent", "fluente", "c1", "c2"} for item in languages if isinstance(item, dict)):
        blocks.append("SPANISH_FLUENT_BLOCK")
    if "ENGLISH_C1_REVIEW" in enabled and any(normalize(str(item.get("language"))) in {"en", "english", "ingles"} and item.get("required") and normalize(str(item.get("level"))) in {"fluent", "fluente", "c1", "c2"} for item in languages if isinstance(item, dict)):
        risks.append("ENGLISH_C1_REVIEW")
    if "RELOCATION_REQUIRED" in enabled and "relocation" in text and "required" in text:
        blocks.append("RELOCATION_REQUIRED")

    technical, strengths, gaps = _overlap(job.get("required_skills") or [], profile.get("verified_skills") or [], 30)
    target_roles = [normalize(item) for item in profile.get("target_roles") or []]
    title = normalize(str(job.get("title") or ""))
    experience = 20 if any(role and (role in title or title in role) for role in target_roles) else 8
    seniority = normalize(str(job.get("seniority") or ""))
    seniority_score = 10 if seniority in {"senior", "specialist", "especialista"} else 7 if seniority else 5
    work_model = normalize(str(job.get("work_model") or ""))
    desired_models = {normalize(item) for item in profile.get("work_models") or []}
    work_score = 10 if work_model in desired_models else 6 if not work_model else 0
    salary_min = float(job.get("salary_min") or 0)
    if "SUPPORT_N1_MINIMUM" in enabled and normalize(str(job.get("family") or "")) == "support" and seniority in {"n1", "junior"} and salary_min and salary_min < 4000:
        blocks.append("SUPPORT_N1_MINIMUM")
    expected = float(profile.get("salary_expectation_numeric") or 0)
    compensation = 10 if not salary_min or not expected or salary_min >= expected else max(0, round(10 * salary_min / expected))
    location = normalize(str(job.get("location") or ""))
    city = normalize(str(profile.get("city") or ""))
    location_score = 5 if work_model == "remote" or (city and city in location) else 2 if not location else 0
    language_score = 3 if risks else 5
    channel = normalize(str(job.get("application_channel") or ""))
    channel_score = 5 if channel in {"email", "ats api", "greenhouse", "lever", "ashby"} else 3
    freshness = max(0, min(5, int(job.get("freshness_score", 5))))
    dimensions = {"technology": technical, "experience": experience, "seniority": seniority_score,
                  "work_model": work_score, "compensation": compensation, "location": location_score,
                  "language": language_score, "channel": channel_score, "freshness": freshness}
    total = min(100, sum(dimensions.values()))
    if blocks:
        recommendation = "BLOCK"
    elif risks or 60 <= total < 75:
        recommendation = "REVIEW"
    elif total >= 75:
        recommendation = "APPLY_HIGH" if total >= 80 else "APPLY"
    else:
        recommendation = "DISCARD"
    return ScoreResult(total, recommendation, dimensions, strengths, gaps, risks, blocks)
