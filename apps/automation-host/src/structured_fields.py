"""Job Content Understanding (Fase 2, Prompt 3).

Modulo stdlib puro (mesmo espirito de hard_blocks.py/ats_detection.py/
email_discovery.py), sem dependencia de Playwright/FastAPI.

Reality Check (Prompt 0) provou que hoje uma vaga e lida como um blob de
texto plano (`body.inner_text()`) mais alguns regex - sem distincao entre
requisito obrigatorio e desejavel, sem nivel de idioma exigido separado do
idioma da propria pagina, sem application_instructions estruturado. Este
modulo extrai campos estruturados desse MESMO texto (nao substitui a
extracao existente de hard_blocks.py - reutiliza extract_salary_brl e as
mesmas regras de idioma/regiao) e, quando a vaga vem de um ATS conhecido
(Greenhouse/Lever/Ashby), prefere os dados ja estruturados da API publica
desse ATS (tier 1, sem regex nenhum) em vez de qualquer heuristica.

Cada campo, quando ha evidencia, e um dict:
  {"value": ..., "confidence": int, "evidence_snippet": str, "extraction_method": str}
Ausencia de evidencia = campo ausente do dict. Nunca inventar.
"""

from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ats_detection import ATSMatch
from .email_discovery import detect_email_application
from .hard_blocks import extract_salary_brl

# Mesmas 3 APIs publicas e documentadas ja usadas por
# apps/worker/src/sources.py (GreenhouseAdapter/LeverAdapter/AshbyAdapter) -
# duplicado aqui de proposito (automation-host e worker sao servicos/
# deploys separados, sem import cruzado entre pacotes) so pra checar se o
# board tem vagas de verdade, sem depender de renderizacao de pagina
# nenhuma - o que resolve de raiz o falso-negativo encontrado no Reality
# Check (WebFetch simples via HTTP achava "sem vagas" num board que na
# verdade so precisava de JS pra renderizar; a API JSON nao tem esse
# problema porque nunca dependeu de renderizacao).
_ATS_BOARD_API = {
    "GREENHOUSE": "https://boards-api.greenhouse.io/v1/boards/{account}/jobs",
    "LEVER": "https://api.lever.co/v0/postings/{account}?mode=json",
    "ASHBY": "https://api.ashbyhq.com/posting-api/job-board/{account}",
}

_MANDATORY_MARKERS = re.compile(
    r"\brequired\b|\bmandatory\b|\bmust\b|\bneed(?:s|ed)?\b|\bminimum\b|"
    r"obrigat[oó]ri|requisito",
    re.IGNORECASE,
)
_PREFERRED_MARKERS = re.compile(
    r"preferred|desirable|nice.to.have|\bplus\b|diferencial|desej[aá]vel",
    re.IGNORECASE,
)

_REMOTE = re.compile(r"\bremot[oa]\b|\bremote\b|home.?office", re.IGNORECASE)
_HYBRID = re.compile(r"h[ií]brid[oa]|\bhybrid\b", re.IGNORECASE)
_ONSITE = re.compile(r"presencial|on.?site|in.?office", re.IGNORECASE)
_HYBRID_FREQUENCY = re.compile(
    r"(\d+)\s*(?:dias?|days?)\s*(?:por|per|/|a)\s*(?:semana|week)", re.IGNORECASE,
)

_REGION_PATTERNS = {
    "Campinas": re.compile(r"campinas|hortol[aâ]ndia|sumar[eé]|valinhos|vinhedo|paul[ií]nia|indaiatuba", re.IGNORECASE),
    "São Paulo": re.compile(r"s[aã]o paulo|barueri|osasco|alphaville|guarulhos|abc paulista", re.IGNORECASE),
    "Portugal": re.compile(r"portugal|lisboa|porto", re.IGNORECASE),
}

# Idioma da PAGINA (o texto esta escrito em ingles) != idioma EXIGIDO do
# candidato - so vira language_requirement quando o proprio texto afirma
# um requisito de idioma explicito, nunca por inferencia do idioma da vaga.
_LANGUAGE_REQUIREMENT = re.compile(
    r"(ingl[eê]s|english|espanhol|spanish)\s+(?:fluente|fluent|nativo|native|"
    r"avan[çc]ado|advanced|intermedi[aá]rio|intermediate|b[12]|c[12])|"
    r"(fluente|fluent|nativo|native|avan[çc]ado|advanced|intermedi[aá]rio|"
    r"intermediate|b[12]|c[12])\s+(?:em\s+)?(ingl[eê]s|english|espanhol|spanish)",
    re.IGNORECASE,
)
_LANGUAGE_LEVEL = re.compile(
    r"fluente|fluent|nativo|native|avan[çc]ado|advanced|intermedi[aá]rio|"
    r"intermediate|b[12]|c[12]|b[áa]sico|basic",
    re.IGNORECASE,
)
_LANGUAGE_NAME = re.compile(r"ingl[eê]s|english|espanhol|spanish", re.IGNORECASE)

_SALARY_USD = re.compile(
    r"(?:USD|US\$)\s*([\d,.]+k?)\s*-?\s*([\d,.]+k?)?", re.IGNORECASE,
)


def _snippet(text: str, start: int, end: int, pad: int = 60) -> str:
    return text[max(0, start - pad):end + pad].strip()


def extract_mandatory_vs_preferred(text: str) -> dict:
    """Nao extrai uma skill isolada - captura a SENTENCA como evidencia,
    honesto dado que nao ha NER real aqui (secao 16/18 do Prompt 3: nao
    exigir perfeicao, nunca converter tecnologia citada em contexto/nice-
    to-have em requisito obrigatorio sem evidencia)."""
    sentences = re.split(r"(?<=[.!?;\n])\s+", text)
    mandatory: list[dict] = []
    preferred: list[dict] = []
    for sentence in sentences:
        stripped = sentence.strip()
        if not stripped:
            continue
        if _MANDATORY_MARKERS.search(stripped):
            mandatory.append({"evidence_snippet": stripped[:300], "confidence": 70})
        elif _PREFERRED_MARKERS.search(stripped):
            preferred.append({"evidence_snippet": stripped[:300], "confidence": 70})
    result = {}
    if mandatory:
        result["mandatory_requirements"] = {"value": [item["evidence_snippet"] for item in mandatory],
                                             "confidence": 70, "evidence_snippet": mandatory[0]["evidence_snippet"],
                                             "extraction_method": "sentence_marker_regex"}
    if preferred:
        result["preferred_requirements"] = {"value": [item["evidence_snippet"] for item in preferred],
                                             "confidence": 70, "evidence_snippet": preferred[0]["evidence_snippet"],
                                             "extraction_method": "sentence_marker_regex"}
    return result


def extract_language_requirements(text: str) -> dict | None:
    """Idioma da pagina != idioma exigido do candidato. So retorna algo
    quando o proprio texto afirma um requisito explicito (ex.: 'ingles
    fluente'), nunca so porque a vaga esta escrita em ingles."""
    match = _LANGUAGE_REQUIREMENT.search(text)
    if not match:
        return None
    snippet = _snippet(text, match.start(), match.end())
    language_match = _LANGUAGE_NAME.search(match.group(0))
    level_match = _LANGUAGE_LEVEL.search(match.group(0))
    language = language_match.group(0) if language_match else None
    level = level_match.group(0) if level_match else None
    return {"value": {"language": language, "level": level}, "confidence": 80,
            "evidence_snippet": snippet, "extraction_method": "regex_proximity"}


def extract_work_model(text: str) -> dict:
    if _HYBRID.search(text):
        match = _HYBRID.search(text)
        value: dict[str, object] = {"work_model": "HYBRID"}
        frequency = _HYBRID_FREQUENCY.search(text)
        if frequency:
            value["frequency_days_per_week"] = int(frequency.group(1))
        return {"value": value, "confidence": 85,
                "evidence_snippet": _snippet(text, match.start(), match.end()),
                "extraction_method": "keyword_regex"}
    if _REMOTE.search(text):
        match = _REMOTE.search(text)
        return {"value": {"work_model": "REMOTE"}, "confidence": 80,
                "evidence_snippet": _snippet(text, match.start(), match.end()),
                "extraction_method": "keyword_regex"}
    if _ONSITE.search(text):
        match = _ONSITE.search(text)
        return {"value": {"work_model": "ONSITE"}, "confidence": 70,
                "evidence_snippet": _snippet(text, match.start(), match.end()),
                "extraction_method": "keyword_regex"}
    # Nunca inferir remote pela ausencia de endereco (secao 20) - UNKNOWN
    # explicito, sem confidence/snippet (nao ha evidencia nenhuma).
    return {"value": {"work_model": "UNKNOWN"}, "confidence": 0,
            "evidence_snippet": None, "extraction_method": "no_evidence"}


def extract_location(text: str) -> dict | None:
    for region, pattern in _REGION_PATTERNS.items():
        match = pattern.search(text)
        if match:
            return {"value": {"region": region}, "confidence": 75,
                    "evidence_snippet": _snippet(text, match.start(), match.end()),
                    "extraction_method": "keyword_regex"}
    return None


def extract_salary(text: str) -> dict | None:
    brl = extract_salary_brl(text)
    if brl is not None:
        match = re.search(r"R\$\s*([\d.]+)(?:,\d{2})?", text, re.IGNORECASE)
        return {"value": {"salary_min": brl, "salary_currency": "BRL"}, "confidence": 85,
                "evidence_snippet": _snippet(text, match.start(), match.end()) if match else None,
                "extraction_method": "regex_brl"}
    usd_match = _SALARY_USD.search(text)
    if usd_match:
        def parse_amount(raw: str) -> float | None:
            has_k = raw.lower().endswith("k")
            digits_only = raw[:-1] if has_k else raw
            cleaned = digits_only.replace(",", "").replace(".", "")
            if not cleaned.isdigit():
                return None
            amount = float(cleaned)
            return amount * 1000 if has_k else amount
        low = parse_amount(usd_match.group(1))
        high = parse_amount(usd_match.group(2)) if usd_match.group(2) else None
        if low is not None:
            return {"value": {"salary_min": low, "salary_max": high, "salary_currency": "USD"},
                    "confidence": 75, "evidence_snippet": _snippet(text, usd_match.start(), usd_match.end()),
                    "extraction_method": "regex_usd"}
    return None


def extract_application_instructions(text: str) -> dict | None:
    """Reutiliza detect_email_application (email_discovery.py) - nunca
    reimplementado, nunca infere e-mail."""
    instruction = detect_email_application(text)
    if not instruction:
        return None
    return {"value": {"recruiting_email": instruction.email, "subject": instruction.subject},
            "confidence": 85, "evidence_snippet": instruction.context,
            "extraction_method": "detect_email_application"}


def extract_all(text: str, source_url: str | None = None) -> dict:
    """Orquestra os extractors puros de texto plano (tier 4/5 - browser-
    rendered DOM/text + regex deterministico). Para vagas de ATS conhecido,
    ver from_ats_structured_job (tier 1, dados ja estruturados da API
    publica, sem regex nenhum)."""
    fields: dict[str, object] = {}
    salary = extract_salary(text)
    if salary:
        fields["salary"] = salary
    work_model = extract_work_model(text)
    fields["work_model"] = work_model
    location = extract_location(text)
    if location:
        fields["location"] = location
    language = extract_language_requirements(text)
    if language:
        fields["language_requirements"] = language
    application = extract_application_instructions(text)
    if application:
        fields["application_instructions"] = application
    fields.update(extract_mandatory_vs_preferred(text))
    if source_url:
        for field in fields.values():
            if isinstance(field, dict):
                field.setdefault("source_url", source_url)
    return fields


def from_ats_structured_job(normalized: dict, source_url: str | None = None) -> dict:
    """Tier 1 (structured/API): converte um job ja normalizado pela API
    publica de um ATS conhecido (mesma forma de NormalizedJob.as_payload()
    em apps/worker/src/sources.py - GreenhouseAdapter/LeverAdapter/
    AshbyAdapter) para o mesmo formato de evidencia, confidence alta porque
    veio de dado estruturado, nao de regex sobre texto renderizado."""
    fields: dict[str, object] = {}
    if normalized.get("location"):
        fields["location"] = {"value": {"region": normalized["location"]}, "confidence": 95,
                               "evidence_snippet": None, "extraction_method": "ats_api",
                               "source_url": source_url}
    if normalized.get("work_model"):
        fields["work_model"] = {"value": {"work_model": normalized["work_model"]}, "confidence": 95,
                                 "evidence_snippet": None, "extraction_method": "ats_api",
                                 "source_url": source_url}
    if normalized.get("salary_min") is not None:
        fields["salary"] = {"value": {"salary_min": normalized.get("salary_min"),
                                       "salary_max": normalized.get("salary_max"),
                                       "salary_currency": normalized.get("salary_currency"),
                                       "salary_period": normalized.get("salary_period")},
                             "confidence": 95, "evidence_snippet": None,
                             "extraction_method": "ats_api", "source_url": source_url}
    return fields


def classify_board_fetch(status_code: int | None, error_type: str | None, job_count: int | None) -> str:
    """Decisao pura (secao 24): nunca converter 'nao consegui renderizar'
    em CLOSED. Separada da chamada de rede de verdade (fetch_ats_board_
    status) pra ser testavel sem internet no CI."""
    if error_type in {"URLError", "TimeoutError", "OSError"}:
        return "UNVERIFIABLE"
    if status_code == 403:
        return "BOT_GATED"
    if status_code == 401:
        return "AUTH_REQUIRED"
    if status_code is not None and status_code >= 500:
        return "TOOLING_LIMIT"
    if status_code == 200 and job_count is not None:
        return "LIVE" if job_count > 0 else "CLOSED"
    return "UNVERIFIABLE"


def fetch_ats_board_status(ats_match: ATSMatch, timeout: int = 15) -> str:
    """So chamada pra APIs publicas e documentadas (Greenhouse/Lever/Ashby)
    - nunca contorna autenticacao/CAPTCHA/bot protection; um 401/403 real
    dessas APIs vira AUTH_REQUIRED/BOT_GATED honesto, nunca burlado."""
    template = _ATS_BOARD_API.get(ats_match.adapter)
    if not template:
        return "UNVERIFIABLE"
    url = template.format(account=ats_match.account_key)
    status_code: int | None = None
    error_type: str | None = None
    job_count: int | None = None
    try:
        request = Request(url, headers={"Accept": "application/json",
                                         "User-Agent": "CareerOS-MarketScan/1.0"})
        with urlopen(request, timeout=timeout) as response:
            status_code = response.status
            payload = json.loads(response.read().decode("utf-8"))
            jobs = payload.get("jobs", payload) if isinstance(payload, dict) else payload
            job_count = len(jobs) if isinstance(jobs, list) else 0
    except HTTPError as exc:
        status_code = exc.code
    except URLError:
        error_type = "URLError"
    except TimeoutError:
        error_type = "TimeoutError"
    except OSError:
        error_type = "OSError"
    return classify_board_fetch(status_code, error_type, job_count)
