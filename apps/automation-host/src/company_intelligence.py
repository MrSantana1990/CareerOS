"""Company Intelligence (Fase 2, Prompt 11) - descoberta CONSERVADORA de
domain/careers_url/ATS oficiais, e resolucao de work_model/location com
prioridade de fonte.

Modulo stdlib puro (sem Playwright/FastAPI/rede), no mesmo espirito de
ats_detection.py/email_discovery.py/market_signal_source.py - testavel
isoladamente, sem instalar as dependencias pesadas do pacote. Todo I/O
real (fetch HTTP) e feito pelo caller (main.py) e passado aqui ja como
dict {status_code, final_url, body_snippet} - este modulo nunca abre uma
conexao de rede.

Principio central (achado real do Prompt 10/9): nunca promover uma
inferencia a fato. Um dominio so vira VERIFIED_OFFICIAL_DOMAIN com uma
resposta HTTP real; uma careers page so conta com evidencia real (keyword
ou redirect para ATS conhecido); um Job so e enriquecido quando a
correlacao e EXACT/HIGH_CONFIDENCE - "empresa tem uma pagina de carreiras"
nunca prova que UMA vaga especifica ainda esta ativa la (Secao 6)."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit

# ---------------------------------------------------------------------------
# Secao 3 - DOMAIN DISCOVERY
# ---------------------------------------------------------------------------

# Provedores de e-mail genericos - um endereco nesses dominios nunca e
# evidencia do dominio OFICIAL da empresa (Secao 3: "NAO inferir
# companyname.com sem validacao" - um Gmail pessoal e o oposto de
# evidencia de dominio corporativo).
_GENERIC_EMAIL_DOMAINS = {
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.br",
    "live.com", "icloud.com", "uol.com.br", "bol.com.br", "terra.com.br",
    "protonmail.com", "aol.com", "msn.com",
}


def extract_domain_candidate_from_email(email: str | None) -> str | None:
    """So devolve um candidato quando o dominio do e-mail NAO e um
    provedor generico conhecido - nunca adivinha, so extrai o que ja esta
    literalmente no endereco real (official_recruiting_email da Company
    OU application_instructions.recruiting_email de um Job real dessa
    empresa, Secao 1/3)."""
    if not email or "@" not in email:
        return None
    domain = email.rsplit("@", 1)[-1].strip().lower()
    if not domain or domain in _GENERIC_EMAIL_DOMAINS:
        return None
    return domain


def classify_domain_probe(status_code: int | None, final_url: str | None, requested_domain: str) -> str:
    """VERIFIED_OFFICIAL_DOMAIN so com uma resposta HTTP real (200) e sem
    redirect para um dominio completamente diferente (dominio estacionado/
    revendido aponta para outro host) - Secao 3."""
    if status_code != 200 or not final_url:
        return "UNVERIFIED"
    final_host = urlsplit(final_url).netloc.lower().split(":")[0]
    requested = requested_domain.lower().lstrip("www.")
    final_bare = final_host.lstrip("www.")
    if final_bare == requested or final_bare.endswith(f".{requested}") or requested.endswith(f".{final_bare}"):
        return "VERIFIED_OFFICIAL_DOMAIN"
    return "UNVERIFIED"


# ---------------------------------------------------------------------------
# Secao 4/5 - CAREERS URL DISCOVERY / ATS DETECTION
# ---------------------------------------------------------------------------

CAREERS_PROBE_PATHS = ("/careers", "/jobs", "/trabalhe-conosco", "/vagas", "/carreiras")

_CAREERS_KEYWORDS = ("vaga", "carreira", "career", "job opening", "trabalhe conosco",
                     "join our team", "we're hiring", "oportunidades")


def classify_careers_probe(status_code: int | None, final_url: str | None, body_snippet: str | None) -> dict | None:
    """So retorna um candidato quando o fetch real confirma evidencia (200
    + palavra-chave real no corpo, OU redirect para um host reconhecido
    como ATS) - nunca por status_code sozinho (Secao 4: "nao assumir que
    qualquer URL 200 e careers")."""
    if status_code != 200 or not final_url:
        return None
    body = str(body_snippet or "").lower()
    matched_keyword = any(keyword in body for keyword in _CAREERS_KEYWORDS)
    return {"final_url": final_url, "matched_keyword": matched_keyword}


# ---------------------------------------------------------------------------
# Secao 6 - JOB CORRELATION
# ---------------------------------------------------------------------------

JOB_CORRELATION_LEVELS = ("EXACT_JOB_MATCH", "HIGH_CONFIDENCE_MATCH", "COMPANY_ONLY", "NOT_FOUND")


def _normalize(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain.lower()).split())


def classify_job_correlation(candidate: dict | None, target_job: dict) -> str:
    """candidate: o que foi encontrado na careers page/ATS (opcional
    provider_job_id/title/location). target_job: o Job real que estamos
    tentando enriquecer. Somente EXACT/HIGH_CONFIDENCE podem enriquecer o
    Job especifico (Secao 6) - COMPANY_ONLY nunca inventa campo do Job
    atual, so alimenta Company Intelligence/future discovery."""
    if candidate is None:
        return "NOT_FOUND"
    candidate_id = candidate.get("provider_job_id")
    target_id = target_job.get("external_id") or target_job.get("provider_job_id")
    if candidate_id and target_id and str(candidate_id) == str(target_id):
        return "EXACT_JOB_MATCH"
    candidate_title = _normalize(str(candidate.get("title") or ""))
    target_title = _normalize(str(target_job.get("title") or ""))
    candidate_location = _normalize(str(candidate.get("location") or ""))
    target_location = _normalize(str(target_job.get("location") or ""))
    if candidate_title and candidate_title == target_title and (
        not target_location or candidate_location == target_location
    ):
        return "HIGH_CONFIDENCE_MATCH"
    if candidate.get("company_only"):
        return "COMPANY_ONLY"
    return "NOT_FOUND"


_ENRICHABLE_CORRELATION_LEVELS = {"EXACT_JOB_MATCH", "HIGH_CONFIDENCE_MATCH"}


def can_enrich_job(correlation: str) -> bool:
    return correlation in _ENRICHABLE_CORRELATION_LEVELS


# ---------------------------------------------------------------------------
# Secao 7/11 - WORK MODEL RESOLUTION (SOURCE PRIORITY)
# ---------------------------------------------------------------------------

SOURCE_PRIORITY_ORDER = (
    "OFFICIAL_ATS_STRUCTURED", "OFFICIAL_JOB_PAGE", "TRUSTED_STRUCTURED_EXTRACTION", "DISCOVERY_SOURCE_TEXT",
)
_PRIORITY_RANK = {name: index for index, name in enumerate(SOURCE_PRIORITY_ORDER)}


def resolve_work_model_with_priority(candidates: list[dict]) -> dict:
    """candidates: [{"work_model": "REMOTE"|"HYBRID"|"ONSITE", "source_priority": ...,
    "evidence_snippet":..., "confidence":...}, ...] - ja filtrados pelo
    caller para conter so evidencia real (nunca um candidato inferido por
    heuristica proibida como "cidade -> onsite", Secao 7). Devolve o de
    maior prioridade; UNKNOWN se a lista estiver vazia ou nenhum item tiver
    work_model reconhecivel."""
    usable = [item for item in candidates
              if item.get("work_model") in {"REMOTE", "HYBRID", "ONSITE"}
              and item.get("source_priority") in _PRIORITY_RANK]
    if not usable:
        return {"work_model": "UNKNOWN", "source_priority": None, "evidence_snippet": None}
    best = min(usable, key=lambda item: _PRIORITY_RANK[item["source_priority"]])
    return {"work_model": best["work_model"], "source_priority": best["source_priority"],
            "evidence_snippet": best.get("evidence_snippet"), "confidence": best.get("confidence")}
