import re
from typing import Any


def email_domain(sender: str) -> str:
    match = re.search(r"[\w.+-]+@([\w.-]+)", sender.lower())
    return match.group(1).removeprefix("www.") if match else ""


def correlate_message(message: dict[str, Any], applications: list[dict[str, Any]]) -> tuple[str | None, list[str]]:
    sender_domain = email_domain(str(message.get("sender", "")))
    subject = str(message.get("subject", "")).lower()
    ranked: list[tuple[int, str, list[str]]] = []
    for application in applications:
        score, evidence = 0, []
        company = str(application.get("company", "")).strip().lower()
        company_domain = str(application.get("company_domain", "")).strip().lower().removeprefix("www.")
        title = str(application.get("title", "")).strip().lower()
        if company_domain and sender_domain == company_domain:
            score += 70
            evidence.append("sender_domain")
        if company and len(company) >= 3 and company in subject:
            score += 35
            evidence.append("company_subject")
        if title and len(title) >= 5 and title in subject:
            score += 25
            evidence.append("job_title_subject")
        if score:
            ranked.append((score, str(application["id"]), evidence))
    ranked.sort(reverse=True)
    if not ranked or ranked[0][0] < 35:
        return None, []
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None, ["ambiguous"]
    return ranked[0][1], ranked[0][2]


def notification_priority(category: str) -> str:
    if category in {"INTERVIEW", "OFFER"}:
        return "URGENT"
    if category in {"RECRUITER", "QUESTIONNAIRE"}:
        return "HIGH"
    return "NORMAL"
