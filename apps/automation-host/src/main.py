import asyncio
import json
import logging
import os
import re
import subprocess
import shutil
import uuid
from urllib.error import URLError
from urllib.request import Request, urlopen
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import BrowserContext, Frame, Page, Playwright, async_playwright

from .anti_spam import remaining_daily_quota
from .ats_detection import ATSMatch, detect_ats
from .core_bridge import (CoreSyncRecord, build_job_record, build_prepare_record,
                          build_score_record, build_transition_record, guess_company, is_due,
                          is_eligible_for_prepare, map_local_status_to_core_transition,
                          send_core_sync)
from .email_discovery import detect_email_application
from .evidence_check import is_evidence_grounded
from .hard_blocks import assess_hard_blocks, extract_salary_brl
from .kill_switches import fetch_kill_switches, is_paused
from .url_policy import authenticated_application_url
from pydantic import BaseModel, Field
from pypdf import PdfReader
from .google_career import (connection_status, create_application_email_draft,
                            create_calendar_event, create_reply_draft,
                            mark_questionnaire_complete, scan_recruitment_mail,
                            send_security_code)

runtime_override = os.getenv("CAREER_RUNTIME")
ROOT = Path(__file__).resolve().parents[3] if not runtime_override else Path("/app")
RUNTIME = Path(runtime_override) if runtime_override else ROOT / ".runtime"
PROFILE = RUNTIME / "browser-profiles" / "default"
RESULTS = RUNTIME / "jobs.json"
LOGS = RUNTIME / "automation-events.jsonl"
PROFILE_DATA = RUNTIME / "professional-profile.json"
APPLICATIONS = RUNTIME / "applications.json"
RESUMES = RUNTIME / "resumes"
SCREENSHOTS = RUNTIME / "screenshots"
SETTINGS_DATA = RUNTIME / "automation-settings.json"
LAYOUT_KNOWLEDGE = RUNTIME / "layout-knowledge.json"
SUGGESTED_SOURCES_CACHE = RUNTIME / "suggested-sources.json"
AI_DECISIONS = RUNTIME / "ai-decisions.jsonl"
GOOGLE_TOKEN = RUNTIME / "google" / "google-token.json"
GOOGLE_INBOX = RUNTIME / "google" / "career-mail.json"
GOOGLE_STATUS_CACHE = RUNTIME / "google" / "connection-status.json"
GOOGLE_HEALTH = RUNTIME / "google" / "health.json"
GOOGLE_HEALTH_ALERT_THRESHOLD = 3
CORE_SYNC_OUTBOX = RUNTIME / "core-sync-outbox.jsonl"
CORE_SYNC_DEAD_LETTER = RUNTIME / "core-sync-dead-letter.jsonl"
CORE_SYNC_LINKS = RUNTIME / "core-sync-links.json"
CORE_RESUMES_DIR = RUNTIME / "core-resumes"
LOCAL_AI_URL = os.getenv("LOCAL_AI_URL", "http://127.0.0.1:8080/v1")
RESUME_STORAGE = Path(os.getenv("RESUME_STORAGE_DIR", "/data/resumes")).resolve()
CAREER_API_URL = os.getenv("CAREER_API_URL", "http://api:8000").rstrip("/")
CAREER_ADMIN_TOKEN = os.getenv("ADMIN_API_TOKEN", "")
EXECUTOR_ID = os.getenv("EXECUTOR_ID", "local-browser")
BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "false").lower() in {"1", "true", "yes"}
BROWSER_CHANNEL = os.getenv("BROWSER_CHANNEL", "chrome").strip().lower()

EXTERNAL_APPLY_CTA_PATTERN = (
    r"quero me candidatar|candidatura f[aá]cil|candidatar(?:-se)?|inscrever|"
    r"apply now|apply for this|apply|easy apply|tenho interesse"
)

FINAL_SUBMIT_CTA_PATTERN = (
    r"enviar candidatura|enviar (?:minha |meu )?curr[ií]culo|enviar inscri[cç][aã]o|"
    r"finalizar candidatura|finalizar inscri[cç][aã]o|concluir candidatura|concluir inscri[cç][aã]o|"
    r"confirmar candidatura|candidatar(?:-se)?|submit application|submit your application"
)

NEXT_STEP_CTA_PATTERN = (
    r"pr[oó]xima(?:\s+etapa)?|avan[cç]ar|continuar(?!\s+sem)|revisar candidatura|revisar|"
    r"next(?:\s+step)?|continue|review (?:your )?application|review"
)

MAX_APPLICATION_STEPS = 6

INTERVENTION_PATTERNS = {
    "CAPTCHA": re.compile(r"captcha|recaptcha|não sou um robô", re.IGNORECASE),
    "MFA": re.compile(r"verification code|two-factor|multi-factor|código de verificação|autenticação em duas etapas", re.IGNORECASE),
    "LOGIN": re.compile(r"sign in|log in|entrar na conta|faça login", re.IGNORECASE),
}


async def report_intervention(application: dict[str, object], reason: str, title: str,
                              instructions: str, page_url: str | None = None,
                              evidence: dict[str, object] | None = None) -> None:
    if not CAREER_ADMIN_TOKEN:
        event("INTERVENTION_REPORT_SKIPPED", reason="missing_admin_token")
        return
    legacy_id = str(application.get("id", ""))
    payload = {
        "application_id": None,
        "executor_id": EXECUTOR_ID,
        "reason": reason,
        "title": title,
        "instructions": instructions,
        "page_url": page_url,
        "evidence": {
            "legacy_application_id": legacy_id,
            "job_title": str(application.get("title", ""))[:240],
            "deduplication_key": f"{legacy_id}:{reason}",
            **(evidence or {}),
        },
    }

    def send() -> None:
        request = Request(
            CAREER_API_URL + "/api/v1/interventions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {CAREER_ADMIN_TOKEN}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=20):
            pass

    try:
        await asyncio.to_thread(send)
        event("INTERVENTION_REPORTED", application_id=legacy_id, reason=reason)
    except (URLError, TimeoutError, OSError) as exc:
        event("INTERVENTION_REPORT_FAILED", application_id=legacy_id, reason=reason,
              error=type(exc).__name__)


async def suggest_source_connection(ats_match: ATSMatch) -> None:
    """Sugere ao Core o cadastro de uma fonte estruturada (Greenhouse/Lever/
    Ashby) descoberta via navegador. Sempre com enabled=False — o scheduler
    (apps/worker/src/scheduler.py) só executa fontes com enabled=true, então
    isso nunca ativa nada sozinho; fica pendente de aprovação humana."""
    if not CAREER_ADMIN_TOKEN:
        event("ATS_SOURCE_SUGGESTION_SKIPPED", reason="missing_admin_token")
        return
    already = set(load_json(SUGGESTED_SOURCES_CACHE, []))
    key = f"{ats_match.adapter}:{ats_match.account_key}"
    if key in already:
        return
    payload = {
        "adapter": ats_match.adapter,
        "account_key": ats_match.account_key,
        "company_name": ats_match.account_key,
        "enabled": False,
        "maximum_jobs": 200,
        "cadence_minutes": 360,
    }

    def send() -> dict:
        request = Request(
            CAREER_API_URL + "/api/v1/sources",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {CAREER_ADMIN_TOKEN}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        result = await asyncio.to_thread(send)
        save_json(SUGGESTED_SOURCES_CACHE, sorted(already | {key}))
        event("ATS_SOURCE_SUGGESTED", adapter=ats_match.adapter,
              account_key=ats_match.account_key, source_id=result.get("id"))
    except (URLError, TimeoutError, OSError) as exc:
        event("ATS_SOURCE_SUGGESTION_FAILED", adapter=ats_match.adapter,
              account_key=ats_match.account_key, error=type(exc).__name__)


PLATFORMS = {
    "InfoJobs": "https://www.infojobs.com.br/",
    "Indeed": "https://br.indeed.com/",
    "Catho": "https://www.catho.com.br/vagas/",
    "LinkedIn": "https://www.linkedin.com/jobs/",
}

app = FastAPI(title="CareerOS Automation Host", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"http://(?:192\.168|10|172\.(?:1[6-9]|2\d|3[01]))(?:\.\d{1,3}){2}:3000",
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

playwright: Playwright | None = None
context: BrowserContext | None = None
run_task: asyncio.Task | None = None
state: dict[str, object] = {
    "status": "offline", "platform": None, "role": None, "found": 0,
    "blocked": 0, "message": "Agente ainda não inicializado.", "updated_at": None,
}


class RunRequest(BaseModel):
    roles: list[str] = Field(min_length=1, max_length=20)
    max_roles: int = Field(default=3, ge=1, le=10)


class ProfessionalProfile(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    city: str = "Campinas"
    state: str = "SP"
    linkedin_url: str = ""
    salary_expectation: str = ""
    work_models: list[str] = ["REMOTE", "HYBRID"]
    target_roles: list[str] = [
        "Analista de Sustentação",
        "Analista de Suporte N3",
        "Analista de Sistemas",
    ]
    skills: list[str] = []
    approved_answers: dict[str, str] = {}
    resume_path: str = ""


class AnalyzeRequest(BaseModel):
    minimum_score: int = Field(default=75, ge=0, le=100)
    limit: int = Field(default=250, ge=1, le=1000)


class PrepareRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=50)
    job_urls: list[str] = []


class AutomationSettings(BaseModel):
    auto_apply_enabled: bool = False
    minimum_score: int = Field(default=75, ge=0, le=100)
    daily_target: int = Field(default=20, ge=1, le=50)
    require_complete_profile: bool = True
    preferred_locations: list[str] = ["Campinas e região", "São Paulo - SP", "Portugal"]
    support_salary_campinas: int = Field(default=4000, ge=0)
    support_salary_sao_paulo: int = Field(default=7000, ge=0)
    salary_is_soft_preference: bool = True


class ExecuteRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=50)
    confirm_live_submission: bool = False
    application_ids: list[str] = []
    single_controlled_application_id: str | None = None


class BootstrapRequest(BaseModel):
    resume_path: str


class AIAdviceRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    job_title: str = Field(default="", max_length=500)
    job_description: str = Field(default="", max_length=12000)


class GoogleDraftRequest(BaseModel):
    message_id: str = Field(min_length=5, max_length=200)


class SecurityCodeRequest(BaseModel):
    recipient: str = Field(min_length=5, max_length=254)
    code: str = Field(min_length=6, max_length=12, pattern=r"^[A-Z0-9]+$")


class ApplicationEmailDraftRequest(BaseModel):
    recipient: str = Field(min_length=5, max_length=254)
    subject: str = Field(min_length=3, max_length=300)
    body: str = Field(min_length=10, max_length=10000)
    resume_path: str = Field(min_length=5, max_length=500)


SKILL_CATALOG = [
    "SQL Server", "PostgreSQL", "Oracle", "MySQL", "PL/SQL", "T-SQL",
    "Power BI", "Microsoft Fabric", "Databricks", "Azure", "AWS",
    "Azure Data Factory", "AWS RDS", "AWS Aurora", "Java", "APIs REST",
    "Git", "GitHub", "CI/CD", "Docker", "ETL", "Troubleshooting",
    "Sustentação", "Suporte N2", "Suporte N3", "Suporte N4",
    "Engenharia de Dados", "Modelagem de Dados", "Monitoramento",
]

TARGET_ROLES = [
    "Analista de Sustentação", "Analista de Suporte N3", "Analista de Sistemas",
    "Analista de Banco de Dados", "DBA SQL Server", "DBA Oracle",
    "DBA PostgreSQL", "Analista de Dados", "Analista de BI",
    "Engenheiro de Dados", "Application Support Analyst", "Production Support Analyst",
]


def event(message: str, **metadata: object) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    entry = {"timestamp": datetime.now(UTC).isoformat(), "message": message, **metadata}
    with LOGS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _http_json(url: str, payload: dict | None = None, timeout: int = 8) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    request = Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


async def sync_profile_from_core() -> ProfessionalProfile | None:
    if not CAREER_ADMIN_TOKEN:
        return None

    def fetch() -> dict:
        request = Request(
            CAREER_API_URL + "/api/v1/profile",
            headers={"Authorization": f"Bearer {CAREER_ADMIN_TOKEN}"},
        )
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        profile = ProfessionalProfile.model_validate(await asyncio.to_thread(fetch))
        save_json(PROFILE_DATA, profile.model_dump())
        event("CORE_PROFILE_SYNCED", resume=bool(profile.resume_path), roles=len(profile.target_roles))
        return profile
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        event("CORE_PROFILE_SYNC_FAILED", error=type(exc).__name__)
        return None


async def local_ai_status() -> dict[str, object]:
    try:
        result = await asyncio.to_thread(_http_json, f"{LOCAL_AI_URL}/models", None, 3)
        models = [item.get("id", "") for item in result.get("data", [])]
        return {"available": True, "model": models[0] if models else "local", "privacy": "local-only"}
    except Exception:
        return {"available": False, "model": None, "privacy": "local-only"}


async def local_ai_advice(request: AIAdviceRequest, profile: ProfessionalProfile) -> dict[str, object]:
    system = (
        "Você é o copiloto de candidaturas do CareerOS. Responda SOMENTE JSON válido. "
        "Nunca invente experiência, formação, idioma, salário ou disponibilidade. "
        "Use exclusivamente o perfil fornecido. Se faltar prova, action deve ser ASK_USER. "
        "Formato: {\"action\":\"ANSWER|ASK_USER|SKIP_JOB\",\"answer\":\"\","
        "\"confidence\":0.0,\"evidence\":[\"\"],\"reason\":\"\"}."
    )
    user = {"question": request.question, "job_title": request.job_title,
            "job_description": request.job_description, "profile": profile.model_dump()}
    payload = {"model": "local", "temperature": 0.1, "max_tokens": 500,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": json.dumps(user, ensure_ascii=False)}]}
    result = await asyncio.to_thread(_http_json, f"{LOCAL_AI_URL}/chat/completions", payload, 60)
    content = result["choices"][0]["message"]["content"].strip()
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError("A IA local não retornou JSON válido.")
    decision = json.loads(match.group(0))
    evidence_text = " ".join(str(item) for item in decision.get("evidence") or [])
    grounded = is_evidence_grounded(evidence_text, json.dumps(profile.model_dump(), ensure_ascii=False))
    if decision.get("action") == "ANSWER" and float(decision.get("confidence", 0)) < 0.85:
        decision["action"] = "ASK_USER"
        decision["answer"] = ""
        decision["reason"] = "Confiança abaixo do limite seguro de 85%."
    elif decision.get("action") == "ANSWER" and not grounded:
        decision["action"] = "ASK_USER"
        decision["answer"] = ""
        decision["reason"] = "Evidência citada não foi encontrada no perfil verificado."
    AI_DECISIONS.parent.mkdir(parents=True, exist_ok=True)
    with AI_DECISIONS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": datetime.now(UTC).isoformat(), "input": user, "decision": decision}, ensure_ascii=False) + "\n")
    return decision


def update(**values: object) -> None:
    state.update(values)
    state["updated_at"] = datetime.now(UTC).isoformat()


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def normalized_tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9+#.]{2,}", value.lower())
        if token not in {"para", "com", "uma", "das", "dos", "and", "the"}
    }


def calculate_match(job: dict, profile: ProfessionalProfile) -> tuple[int, list[str], list[str]]:
    title = str(job.get("title", ""))
    role = str(job.get("search_role", ""))
    haystack = normalized_tokens(f"{title} {role}")
    skills = {skill.lower().strip() for skill in profile.skills if skill.strip()}
    matched = sorted(skill for skill in skills if normalized_tokens(skill) & haystack)
    role_tokens = normalized_tokens(role)
    title_tokens = normalized_tokens(title)
    role_overlap = len(role_tokens & title_tokens) / max(1, len(role_tokens))
    technical = min(25, len(matched) * 8)
    title_score = round(role_overlap * 55)
    remote_score = 15 if any(word in title.lower() for word in ("remoto", "remote", "home office")) else 10
    source_score = 12
    geography = title.lower()
    location_score = 18 if "campinas" in geography else 14 if re.search(r"são paulo|\bsp\b", geography) else 12 if re.search(r"portugal|lisboa|porto", geography) else 0
    score = min(100, technical + title_score + remote_score + source_score + location_score)
    positives = [f"Cargo relacionado a {role}."] if role_overlap else []
    positives.extend(f"Competência relacionada: {skill}." for skill in matched[:5])
    risks: list[str] = []
    if not matched:
        risks.append("Descrição resumida ainda não comprova competências técnicas.")
    if "gupy" in str(job.get("url", "")).lower():
        risks.append("Plataforma bloqueada pelo usuário.")
        score = 0
    return score, positives, risks


def resume_text(profile: ProfessionalProfile, limit: int = 18000) -> str:
    source = Path(profile.resume_path)
    if not source.exists() or source.suffix.lower() != ".pdf":
        return ""
    try:
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(source)).pages)[:limit]
    except Exception:
        return ""


def geography_priority(item: dict) -> int:
    text = f"{item.get('title', '')} {item.get('job_url', item.get('url', ''))}".lower()
    if "campinas" in text:
        return 0
    if re.search(r"são paulo|sao-paulo|\bsp\b", text):
        return 1
    if re.search(r"portugal|lisboa|porto", text):
        return 2
    if re.search(r"remoto|remote", text):
        return 3
    return 4


def opportunity_feedback(title: str, body: str, settings: AutomationSettings) -> dict[str, object]:
    text = f"{title} {body}".lower()
    salary = extract_salary_brl(body)
    is_support = bool(re.search(r"suporte|sustenta[cç][aã]o|service desk|help.?desk|n[1234]", text))
    region = "Campinas" if re.search(r"campinas|hortol[aâ]ndia|sumar[eé]|valinhos|vinhedo|paul[ií]nia|indaiatuba", text) else "São Paulo" if re.search(r"s[aã]o paulo|barueri|osasco|alphaville|guarulhos|abc paulista", text) else "Portugal" if re.search(r"portugal|lisboa|porto", text) else "Outra"
    target = settings.support_salary_campinas if region == "Campinas" else settings.support_salary_sao_paulo if region == "São Paulo" else None
    if is_support and target and salary:
        if salary >= target:
            recommendation = "PRIORITY"
            reason = f"Suporte em {region} com salário publicado de aproximadamente R$ {salary:,.0f}, alinhado à preferência flexível."
        else:
            recommendation = "REVIEW"
            reason = f"Salário publicado de aproximadamente R$ {salary:,.0f}, abaixo da referência flexível de R$ {target:,.0f}; avaliar benefícios, modalidade e aderência."
    elif is_support and target:
        recommendation = "REVIEW"
        reason = f"Vaga de suporte em {region} sem salário publicado; manter para análise, sem rejeição automática."
    else:
        recommendation = "STANDARD"
        reason = "Avaliar aderência técnica, modalidade, benefícios e remuneração em conjunto."
    hard_block_result = assess_hard_blocks(text, salary)
    if hard_block_result.risks:
        reason += f" Atenção: {', '.join(hard_block_result.risks)}."
    email_instruction = detect_email_application(f"{title} {body}")
    return {
        "region": region,
        "salary_brl": salary,
        "recommendation": recommendation,
        "feedback": reason,
        "blocks": hard_block_result.blocks,
        "risks": hard_block_result.risks,
        "email_application": (
            {"email": email_instruction.email, "subject": email_instruction.subject, "context": email_instruction.context}
            if email_instruction
            else None
        ),
    }


def environment_auto_apply_enabled() -> bool:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().upper() == "AUTO_APPLY_ENABLED=TRUE":
                return True
    return os.getenv("AUTO_APPLY_ENABLED", "false").lower() == "true"


def dry_run_enabled() -> bool:
    """Gate independente de AUTO_APPLY_ENABLED - permite religar o autoenvio
    para testar o pipeline de ponta a ponta (Plano Mestre, Fase 28) sem que
    nenhum clique de envio real aconteça."""
    return os.getenv("DRY_RUN_ENABLED", "false").lower() == "true"


def extract_resume_profile(source: Path) -> ProfessionalProfile:
    if source.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="A importação automática atual exige currículo PDF.")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(source)).pages)
    compact = re.sub(r"[ \t]+", " ", text)
    email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", compact)
    phone_match = re.search(r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?9?\d{4}[-\s]?\d{4}", compact)
    linkedin_match = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w%./-]+", compact, re.I)
    name = ""
    for line in text.splitlines():
        candidate = line.strip()
        if 2 <= len(candidate.split()) <= 6 and "rodolfo" in candidate.lower() and "santana" in candidate.lower():
            name = candidate
            break
    lower = compact.lower()
    skills = [skill for skill in SKILL_CATALOG if skill.lower() in lower]
    city = "Campinas" if "campinas" in lower else ""
    state = "SP" if re.search(r"\bsp\b|são paulo", lower) else ""
    return ProfessionalProfile(
        full_name=name or "Rodolfo Santana",
        email=email_match.group(0) if email_match else "",
        phone=phone_match.group(0) if phone_match else "",
        city=city,
        state=state,
        linkedin_url=(
            linkedin_match.group(0)
            if linkedin_match and linkedin_match.group(0).startswith("http")
            else f"https://{linkedin_match.group(0)}" if linkedin_match else ""
        ),
        work_models=["REMOTE", "HYBRID"],
        target_roles=TARGET_ROLES,
        skills=skills,
        approved_answers={},
    )


async def ensure_browser() -> BrowserContext:
    global playwright, context
    if context:
        return context
    PROFILE.mkdir(parents=True, exist_ok=True)
    for stale_lock in PROFILE.glob("Singleton*"):
        stale_lock.unlink(missing_ok=True)
    playwright = await async_playwright().start()
    launch_options: dict[str, object] = {
        "user_data_dir": str(PROFILE),
        "headless": BROWSER_HEADLESS,
        "viewport": {"width": 1440, "height": 900},
        "locale": "pt-BR",
        "args": [
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-background-networking",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--metrics-recording-only",
            "--mute-audio",
            "--renderer-process-limit=2",
            "--js-flags=--max-old-space-size=256",
        ],
    }
    if BROWSER_CHANNEL and BROWSER_CHANNEL != "chromium":
        launch_options["channel"] = BROWSER_CHANNEL
    context = await playwright.chromium.launch_persistent_context(**launch_options)
    mode = "na VPS" if BROWSER_HEADLESS else "neste computador"
    update(status="ready", message=f"Executor do navegador pronto {mode}.")
    event("BROWSER_STARTED")
    return context


def search_url(platform: str, role: str, location: str = "") -> str:
    query = quote_plus(role)
    if platform == "InfoJobs":
        slug = re.sub(r"[^a-z0-9]+", "-", role.lower()).strip("-")
        return f"https://www.infojobs.com.br/vagas-de-emprego-{slug}.aspx"
    if platform == "Indeed":
        return f"https://br.indeed.com/jobs?q={query}&l={quote_plus(location or 'Brasil')}"
    if platform == "Catho":
        return f"https://www.catho.com.br/vagas/?q={query}"
    return f"https://www.linkedin.com/jobs/search/?keywords={query}&location={quote_plus(location or 'Brasil')}"


def looks_like_job(platform: str, url: str, text: str) -> bool:
    value = f"{url} {text}".lower()
    if "gupy.io" in value or "gupy" in urlparse(url).netloc.lower():
        return False
    patterns = {
        "InfoJobs": ("/vaga-de-",),
        "Indeed": ("/viewjob", "jk="),
        "Catho": ("/vaga/", "/vagas/"),
        "LinkedIn": ("/jobs/view/",),
    }
    return len(text.strip()) >= 5 and any(part in url.lower() for part in patterns[platform])


async def collect_page(page: Page, platform: str, role: str, location: str = "") -> tuple[list[dict], int]:
    url = search_url(platform, role, location)
    await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(3500)
    anchors = await page.locator("a[href]").evaluate_all(
        "els => els.map(a => ({href: a.href, text: (a.innerText || a.textContent || '').trim()}))"
    )
    jobs: list[dict] = []
    blocked = 0
    for anchor in anchors:
        href = urljoin(url, anchor.get("href", ""))
        text = re.sub(r"\s+", " ", anchor.get("text", "")).strip()[:300]
        if "gupy.io" in href.lower():
            blocked += 1
            continue
        if looks_like_job(platform, href, text):
            jobs.append({
                "source": platform, "title": text, "url": href, "search_role": role,
                "location_search": location, "collected_at": datetime.now(UTC).isoformat(), "status": "DISCOVERED",
            })
    return jobs, blocked


async def automation_run(request: RunRequest) -> None:
    try:
        browser = await ensure_browser()
        existing: list[dict] = []
        if RESULTS.exists():
            existing = json.loads(RESULTS.read_text(encoding="utf-8"))
        indexed = {job["url"]: job for job in existing}
        total_blocked = 0
        update(status="running", found=len(indexed), blocked=0, message="Busca automática iniciada.")
        event("AUTOMATION_STARTED", roles=request.roles[: request.max_roles])
        page = browser.pages[0] if browser.pages else await browser.new_page()
        settings = AutomationSettings.model_validate(load_json(SETTINGS_DATA, {}))
        locations = settings.preferred_locations or ["Brasil"]
        for role_index, role in enumerate(request.roles[: request.max_roles]):
            # Distribui as regiões entre cargos para manter a busca diária ágil.
            location = locations[role_index % len(locations)]
            for platform in PLATFORMS:
                if asyncio.current_task() and asyncio.current_task().cancelling():
                    raise asyncio.CancelledError
                update(platform=platform, role=role, message=f"Pesquisando {role} em {platform}.")
                try:
                    jobs, blocked = await collect_page(page, platform, role, location)
                    total_blocked += blocked
                    for job in jobs:
                        previous = indexed.get(job["url"])
                        job["first_seen_at"] = (
                            previous.get("first_seen_at") or previous.get("collected_at")
                            if previous else job["collected_at"]
                        )
                        job["last_seen_at"] = job["collected_at"]
                        if previous:
                            for key in ("score", "match_reasons", "risks", "decision"):
                                if key in previous:
                                    job[key] = previous[key]
                        indexed[job["url"]] = job
                    RESULTS.parent.mkdir(parents=True, exist_ok=True)
                    RESULTS.write_text(json.dumps(list(indexed.values()), ensure_ascii=False, indent=2), encoding="utf-8")
                    update(found=len(indexed), blocked=total_blocked)
                    event("SEARCH_COMPLETED", platform=platform, role=role, found=len(jobs), blocked=blocked)
                except Exception as exc:
                    logging.exception("search_failed")
                    event("SEARCH_FAILED", platform=platform, role=role, error=type(exc).__name__)
                await page.wait_for_timeout(1800)
        update(status="completed", platform=None, role=None, found=len(indexed), blocked=total_blocked, message="Busca concluída. Resultados disponíveis no painel.")
        event("AUTOMATION_COMPLETED", found=len(indexed), blocked=total_blocked)
    except asyncio.CancelledError:
        update(status="stopped", platform=None, role=None, message="Automação interrompida pelo usuário.")
        event("AUTOMATION_STOPPED")
        raise


async def resolve_resume_for_application(application: dict) -> tuple[str, str | None]:
    """Devolve (caminho_local, resume_version_id) do currículo que o
    Resume Router do Core escolheu pra esta candidatura (família + idioma,
    só aprovado), quando o Core já preparou essa vaga. Nunca bloqueia se o
    Core estiver fora do ar ou a vaga ainda não foi preparada lá - nesse
    caso devolve ("", None) e o chamador cai pro currículo local
    configurado (profile.resume_path), sem fingir que usou o certo."""
    if not CAREER_ADMIN_TOKEN:
        return "", None
    entry = _load_core_sync_links().get(application["id"], {})
    version_id = entry.get("resume_version_id")
    if not version_id:
        return "", None
    cached = list(CORE_RESUMES_DIR.glob(f"{version_id}.*")) if CORE_RESUMES_DIR.exists() else []
    if cached:
        return str(cached[0]), version_id

    def fetch() -> tuple[bytes, str]:
        request = Request(
            CAREER_API_URL + f"/api/v1/resumes/{version_id}/file",
            headers={"Authorization": f"Bearer {CAREER_ADMIN_TOKEN}"},
        )
        with urlopen(request, timeout=30) as response:
            filename = response.headers.get("X-Resume-Filename", "") or f"{version_id}.pdf"
            return response.read(), filename

    try:
        content, filename = await asyncio.to_thread(fetch)
    except (URLError, TimeoutError, OSError) as exc:
        event("CORE_RESUME_DOWNLOAD_FAILED", application_id=application["id"],
              resume_version_id=version_id, error=type(exc).__name__)
        return "", None
    suffix = Path(filename).suffix or ".pdf"
    target = CORE_RESUMES_DIR / f"{version_id}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    event("CORE_RESUME_DOWNLOADED", application_id=application["id"], resume_version_id=version_id)
    return str(target), version_id


async def sync_job_to_core(page: Page, job: dict, application: dict, body: str) -> None:
    """Encaminha a vaga para o Core assim que existe dado real o bastante -
    a descoberta inicial (automation_run) so tem titulo bruto do link e
    URL, sem nome de empresa; isso so aparece depois de abrir a pagina de
    verdade, aqui. Extracao de empresa e heuristica (guess_company em
    core_bridge.py: URL do LinkedIn quando disponivel, titulo da pagina
    caso contrario, descartando texto padrao de agregador) - nao e uma
    garantia por plataforma, revisao humana continua necessaria ate
    refinarmos por site. Nunca bloqueia o fluxo local: qualquer falha
    aqui vira so um evento de log."""
    if not CAREER_ADMIN_TOKEN:
        return
    try:
        page_title = (await page.title()) or ""
    except Exception:
        page_title = ""
    company = guess_company(source=str(job.get("source", "")), source_url=str(job.get("url", "")),
                             page_title=page_title)
    if not company:
        event("CORE_SYNC_SKIPPED_NO_COMPANY", job_url=job.get("url", ""))
        return
    record = build_job_record(
        source=str(job.get("source", "")),
        source_url=str(job.get("url", "")),
        company=company[:200],
        title=str(application.get("title", ""))[:240],
        description=body[:12000],
        location=str(job.get("location_search", ""))[:200],
        correlation_id=application["id"],
    )
    enqueue_core_sync(record)
    event("CORE_SYNC_ENQUEUED", kind="JOB", correlation_id=application["id"],
          idempotency_key=record.idempotency_key)


async def inspect_application_queue(request: PrepareRequest) -> None:
    profile = ProfessionalProfile.model_validate(load_json(PROFILE_DATA, {}))
    settings = AutomationSettings.model_validate(load_json(SETTINGS_DATA, {}))
    applications = load_json(APPLICATIONS, [])
    indexed = {item["job_url"]: item for item in applications}
    target_urls = set(request.job_urls)
    if target_urls:
        # Mirar URL(s) especifica(s) substitui o registro existente (se
        # houver) em vez de duplicar - usado pra reprocessar uma vaga
        # pontual com o codigo atual sem criar uma segunda candidatura
        # pra mesma vaga.
        for url in target_urls:
            indexed.pop(url, None)
    jobs = load_json(RESULTS, [])
    candidates = [
        job for job in jobs
        if job.get("decision") == "APPROVED_AUTO" and job.get("url") not in indexed
        and (not target_urls or job.get("url") in target_urls)
    ]
    candidates.sort(key=lambda job: (
        -(datetime.fromisoformat(job.get("first_seen_at") or job.get("collected_at")).timestamp()),
        geography_priority(job),
    ))
    candidates = candidates[: request.limit]
    if not profile.full_name or not profile.email or not profile.resume_path:
        update(
            status="profile_required",
            message="Preencha nome, e-mail e currículo antes de preparar candidaturas.",
        )
        return
    browser = await ensure_browser()
    page = browser.pages[0] if browser.pages else await browser.new_page()
    update(status="preparing", message=f"Inspecionando {len(candidates)} candidaturas qualificadas.")
    for job in candidates:
        url = str(job["url"])
        application = {
            "id": str(uuid.uuid4()),
            "job_url": url,
            "title": job.get("title", ""),
            "source": job.get("source", ""),
            "score": job.get("score", 0),
            "status": "INSPECTING",
            "created_at": datetime.now(UTC).isoformat(),
            "job_first_seen_at": job.get("first_seen_at") or job.get("collected_at"),
            "submitted_at": None,
            "reason": "",
        }
        try:
            await page.goto(authenticated_application_url(url), wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(2500)
            dismissed = await dismiss_overlays(page)
            current_url = page.url.lower()
            body = (await page.locator("body").inner_text(timeout=10_000))[:80_000]
            assessment = opportunity_feedback(application["title"], body, settings)
            application.update(assessment)
            await sync_job_to_core(page, job, application, body)
            if re.search(r"n[aã]o aceita mais candidaturas|vaga (?:foi )?encerrada|processo seletivo encerrado|no longer accepting applications|job is no longer available", body, re.IGNORECASE):
                application["status"] = "CLOSED"
                application["reason"] = "Vaga encerrada: a plataforma não aceita mais candidaturas."
            elif "gupy.io" in current_url or "gupy.io" in body.lower():
                application["status"] = "BLOCKED"
                application["reason"] = "Ignorada: plataforma bloqueada pelo usuário."
            elif application.get("blocks"):
                application["status"] = "BLOCKED"
                application["reason"] = f"Bloqueada: {', '.join(application['blocks'])}."
            elif INTERVENTION_PATTERNS["MFA"].search(body):
                application["status"] = "MANUAL_REQUIRED"
                application["reason"] = "Confirmação em duas etapas necessária."
                await report_intervention(
                    application, "MFA", "Confirme o acesso na plataforma",
                    "Abra a página, conclua a verificação em duas etapas e depois retome a automação.",
                    page.url,
                )
            elif INTERVENTION_PATTERNS["CAPTCHA"].search(body):
                application["status"] = "MANUAL_REQUIRED"
                application["reason"] = "CAPTCHA detectado."
                await report_intervention(
                    application, "CAPTCHA", "Verificação humana necessária",
                    "Abra a página e resolva o CAPTCHA manualmente. O sistema nunca tenta contorná-lo.",
                    page.url,
                )
            else:
                cta_pattern = re.compile(r"candidat|inscrever|apply|tenho interesse", re.IGNORECASE)
                has_button = False
                has_link = False
                for root in await search_roots(page):
                    apply_locator = root.get_by_role("button", name=cta_pattern)
                    apply_links = root.get_by_role("link", name=cta_pattern)
                    has_button = has_button or any([await apply_locator.nth(i).is_visible() for i in range(min(await apply_locator.count(), 8))])
                    has_link = has_link or any([await apply_links.nth(i).is_visible() for i in range(min(await apply_links.count(), 8))])
                application["status"] = "READY_TO_PREPARE" if has_button or has_link else "MANUAL_REQUIRED"
                application["dismissed_overlays"] = dismissed
                application["reason"] = (
                    "Ação de candidatura localizada; aguardando preenchimento seguro."
                    if has_button or has_link
                    else "Botão de candidatura não localizado ou layout desconhecido."
                )
        except Exception as exc:
            application["status"] = "FAILED"
            application["reason"] = f"Falha de inspeção: {type(exc).__name__}."
        indexed[url] = application
        save_json(APPLICATIONS, list(indexed.values()))
        event(
            "APPLICATION_INSPECTED",
            job_url=url,
            status=application["status"],
            score=application["score"],
        )
    update(
        status="completed",
        message="Inspeção concluída. Nenhuma candidatura foi enviada sem autorização de autoenvio.",
    )


async def fill_known_fields(root: Page | Frame, profile: ProfessionalProfile) -> list[str]:
    values = {
        r"nome|name": profile.full_name,
        r"e-?mail": profile.email,
        r"telefone|celular|phone|mobile": profile.phone,
        r"cidade|city": profile.city,
        r"estado|state": profile.state,
        r"linkedin": profile.linkedin_url,
        r"pretens|sal[aá]rio|salary": profile.salary_expectation,
    }
    filled: list[str] = []
    for pattern, value in values.items():
        if not value:
            continue
        locator = root.get_by_label(re.compile(pattern, re.IGNORECASE))
        count = min(await locator.count(), 3)
        for index in range(count):
            field = locator.nth(index)
            try:
                if await field.is_visible() and await field.is_editable():
                    await field.fill(value)
                    filled.append(pattern)
            except Exception:
                continue
    resume = Path(profile.resume_path)
    if resume.exists():
        file_inputs = root.locator('input[type="file"]')
        for index in range(await file_inputs.count()):
            try:
                await file_inputs.nth(index).set_input_files(str(resume))
                filled.append("resume")
            except Exception:
                continue
    return filled


async def ai_fill_simple_questions(root: Page | Frame, profile: ProfessionalProfile, application: dict) -> dict[str, object]:
    questions = await root.locator("input[required], textarea[required], select[required]").evaluate_all(
        """els => els.filter(el => el.getClientRects().length && !el.disabled).map((el, index) => {
          let container = el.closest('fieldset, [role="group"], .form-group, .question, li');
          if (!container && (el.type === 'radio' || el.type === 'checkbox')) {
            let node = el.parentElement;
            while (node && node !== document.body) {
              if (node.querySelectorAll(`input[type="${el.type}"]`).length >= 2 && (node.innerText || '').trim().length > 5) { container = node; break; }
              node = node.parentElement;
            }
          }
          container = container || el.closest('label') || el.parentElement;
          const text = (container?.innerText || el.getAttribute('aria-label') || el.name || '').trim();
          let options = [];
          if (el.type === 'radio' || el.type === 'checkbox') {
            const root = el.closest('fieldset, [role="group"], .form-group, .question') || container;
            options = [...(root?.querySelectorAll('label') || [])].map(x => x.innerText.trim()).filter(Boolean);
          } else if (el.tagName === 'SELECT') {
            options = [...el.options].map(x => x.text.trim()).filter(Boolean);
          }
          return {index, type: el.type || el.tagName.toLowerCase(), name: el.name || el.id || '', question: text.slice(0, 1200), options: [...new Set(options)].slice(0, 20), maxLength: el.maxLength > 0 ? el.maxLength : null, placeholder: el.placeholder || ''};
        }).filter((x, i, arr) => x.question && arr.findIndex(y => y.name === x.name && y.question === x.question) === i)"""
    )
    questions = [q for q in questions if not re.search(r"report|denunci|newsletter|search", f"{q.get('name','')} {q.get('question','')}", re.I)]
    if not questions:
        return {"filled": [], "unresolved": []}
    filled, unresolved = [], []
    remaining = []
    for question in questions:
        question_tokens = normalized_tokens(str(question.get("question", "")))
        best_answer, best_score, best_evidence = "", 0.0, ""
        for saved_question, saved_answer in profile.approved_answers.items():
            saved_tokens = normalized_tokens(saved_question)
            union = question_tokens | saved_tokens
            score = len(question_tokens & saved_tokens) / len(union) if union else 0.0
            if score > best_score:
                best_answer, best_score = str(saved_answer).strip(), score
                best_evidence = f"Memória aprovada: {saved_question}"
        if best_answer and best_score >= 0.55:
            name = str(question.get("name", ""))
            fields = root.locator(f'[name="{name}"]') if name else root.locator("__missing__")
            matched = False
            for index in range(await fields.count()):
                field = fields.nth(index)
                try:
                    field_type = await field.get_attribute("type") or ""
                    if field_type in {"radio", "checkbox"}:
                        field_value = await field.get_attribute("value") or ""
                        field_id = await field.get_attribute("id") or ""
                        label = root.locator(f'label[for="{field_id}"]')
                        label_text = await label.inner_text() if await label.count() else ""
                        if best_answer.lower() in {field_value.lower(), label_text.strip().lower()}:
                            await field.check()
                            matched = True
                    elif await field.is_editable():
                        await field.fill(best_answer[: question.get("maxLength") or 450])
                        matched = True
                except Exception:
                    continue
            if matched:
                filled.append({"name": name, "answer": best_answer, "evidence": best_evidence})
                continue
        remaining.append(question)
    questions = remaining
    if not questions:
        event("APPROVED_MEMORY_USED", application_id=application.get("id"), filled=len(filled))
        return {"filled": filled, "unresolved": []}
    system = (
        "Você é um redator profissional brasileiro preenchendo um formulário de emprego em nome do candidato. "
        "Leia a pergunta inteira, as opções, o cargo, o perfil e o currículo antes de responder. Use SOMENTE fatos comprovados. "
        "Escreva em primeira pessoa, de forma humana, natural, segura e objetiva. Não use linguagem de IA, elogios vazios, clichês, "
        "superlativos ou repetições. Para rádio/select, escolha literalmente uma opção oferecida. Para campo curto, use uma frase. "
        "Para pergunta aberta, use 2 a 4 frases e no máximo 450 caracteres: experiência concreta, relação com a vaga e contribuição. "
        "Respeite maxLength. Não inclua saudação ou despedida. Responda SOMENTE JSON válido no formato "
        "{\"answers\":[{\"name\":\"\",\"answer\":\"\",\"confidence\":0.0,\"evidence\":\"\"}]}. "
        "Evidence deve citar o trecho ou competência do currículo que sustenta a resposta. Se não houver prova, answer deve ser vazio. Não invente."
    )
    payload_data = {"job": application.get("title", ""), "questions": questions,
                    "profile": profile.model_dump(), "resume": resume_text(profile)}
    payload = {"model": "local", "temperature": 0.0, "max_tokens": 1000,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": json.dumps(payload_data, ensure_ascii=False)}]}
    try:
        result = await asyncio.to_thread(_http_json, f"{LOCAL_AI_URL}/chat/completions", payload, 90)
    except (URLError, TimeoutError, OSError, ValueError):
        unresolved.extend(str(question.get("name", "")) for question in questions)
        event("LOCAL_AI_UNAVAILABLE", application_id=application.get("id"), unresolved=len(unresolved))
        return {"filled": filled, "unresolved": unresolved}
    content = result["choices"][0]["message"]["content"]
    parsed = json.loads(re.search(r"\{.*\}", content, re.DOTALL).group(0))
    for answer in parsed.get("answers", []):
        name, value = str(answer.get("name", "")), str(answer.get("answer", "")).strip()
        evidence = str(answer.get("evidence", "")).strip()
        grounded = is_evidence_grounded(evidence, payload_data["resume"], " ".join(profile.skills), " ".join(profile.target_roles))
        if (not value or not evidence or float(answer.get("confidence", 0)) < 0.85 or not grounded
                or re.search(r"como (?:uma )?ia|modelo de linguagem|apaixonad[oa]|sempre sonhei", value, re.I)):
            unresolved.append(name)
            continue
        question_meta = next((q for q in questions if q.get("name") == name), {})
        max_length = question_meta.get("maxLength") or 450
        if len(value) > max_length:
            value = value[:max_length].rsplit(" ", 1)[0].rstrip(" ,;:") + "."
        fields = root.locator(f'[name="{name}"]') if name else root.locator("__missing__")
        matched = False
        for index in range(await fields.count()):
            field = fields.nth(index)
            try:
                field_type = await field.get_attribute("type") or ""
                if field_type in {"radio", "checkbox"}:
                    field_value = await field.get_attribute("value") or ""
                    field_id = await field.get_attribute("id") or ""
                    label = root.locator(f'label[for="{field_id}"]')
                    label_text = await label.inner_text() if await label.count() else ""
                    if value.lower() in {field_value.lower(), label_text.strip().lower()}:
                        await field.check()
                        matched = True
                elif await field.is_editable():
                    await field.fill(value)
                    matched = True
            except Exception:
                continue
        if matched:
            filled.append({"name": name, "answer": value, "evidence": answer.get("evidence", "")})
        else:
            unresolved.append(name)
    event("AI_FORM_FILLED", application_id=application.get("id"), filled=len(filled), unresolved=len(unresolved))
    return {"filled": filled, "unresolved": unresolved}


async def required_unknown_fields(root: Page | Frame) -> list[str]:
    return await root.locator("input[required], textarea[required], select[required]").evaluate_all(
        """els => els.filter(el => {
          if (el.type === 'hidden' || el.type === 'submit') return false;
          if (!el.isConnected || el.disabled || el.getClientRects().length === 0) return false;
          const style = getComputedStyle(el);
          if (style.display === 'none' || style.visibility === 'hidden') return false;
          if (el.closest('[hidden], [aria-hidden="true"], dialog:not([open])')) return false;
          const marker = `${el.name || ''} ${el.id || ''} ${el.getAttribute('aria-label') || ''}`.toLowerCase();
          if (/report|denunci|newsletter|search/.test(marker)) return false;
          if (el.type === 'checkbox' || el.type === 'radio') return !el.checked;
          return !String(el.value || '').trim();
        }).map(el => el.getAttribute('aria-label') || el.name || el.id || el.type || 'campo obrigatório')"""
    )


async def dismiss_overlays(page: Page) -> list[str]:
    dismissed: list[str] = []
    pattern = re.compile(r"ok,? entendi|entendi|continuar sem|agora não", re.IGNORECASE)
    for role in ("button", "link"):
        locator = page.get_by_role(role, name=pattern)
        for index in range(min(await locator.count(), 5)):
            item = locator.nth(index)
            try:
                if await item.is_visible():
                    dismissed.append((await item.inner_text()).strip()[:80])
                    await item.click(timeout=3000)
                    await page.wait_for_timeout(350)
            except Exception:
                continue
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
    return dismissed


async def search_roots(page: Page) -> list[Page | Frame]:
    """Greenhouse/Lever/Ashby tanto podem hospedar a vaga diretamente (o
    dominio da propria pagina ja e o ATS) quanto ficar embutidos num
    <iframe> dentro do site da empresa (a pagina principal continua no
    dominio da empresa, mas um dos iframes aponta para o ATS). Por isso
    verificamos a URL de cada frame, nao so a da pagina principal, antes de
    decidir se vale a pena expandir a busca — em qualquer site sem um frame
    de ATS conhecido, o comportamento fica identico ao atual ([page])."""
    ats_frames = [frame for frame in page.frames[1:] if detect_ats(frame.url)]
    if not detect_ats(page.url) and not ats_frames:
        return [page]
    return [page, *ats_frames]


async def find_first_visible(root: Page | Frame, pattern: str):
    """Mesma busca robusta usada por click_first_visible, mas sem clicar -
    usada tanto pra decidir se um CTA existe (antes de decidir clicar)
    quanto para efetivamente clicar nele depois."""
    matcher = re.compile(pattern, re.IGNORECASE)
    for role in ("button", "link"):
        locator = root.get_by_role(role, name=matcher)
        for index in range(min(await locator.count(), 8)):
            item = locator.nth(index)
            try:
                if await item.is_visible() and await item.is_enabled():
                    return item
            except Exception:
                continue
    # Alguns portais desenham o CTA em div/span sem semântica de botão.
    locator = root.locator("button, a, [role='button'], input[type='button'], input[type='submit']").filter(has_text=matcher)
    for index in range(min(await locator.count(), 12)):
        item = locator.nth(index)
        try:
            if await item.is_visible():
                return item
        except Exception:
            continue
    return None


async def click_first_visible(page: Page, pattern: str) -> bool:
    for root in await search_roots(page):
        item = await find_first_visible(root, pattern)
        if item is not None:
            try:
                await item.click(timeout=8000)
                return True
            except Exception:
                continue
    return False


async def classify_application_cta(item, current_page_url: str) -> str:
    """INTERNAL_APPLY (formulário/candidatura executável na página atual)
    ou EXTERNAL_APPLY (redirecionamento pra outro domínio - ATS/site da
    empresa). O texto do botão nunca revela isso sozinho: "Candidatar-se"
    é usado tanto pra abrir um link externo (ex: LinkedIn) quanto pra
    enviar um formulário interno já preenchido (ex: SevenSys/Abler) -
    achado real em produção que confundia os dois."""
    try:
        tag_name = await item.evaluate("el => el.tagName.toLowerCase()")
    except Exception:
        return "INTERNAL_APPLY"
    if tag_name != "a":
        return "INTERNAL_APPLY"
    try:
        href = await item.get_attribute("href")
    except Exception:
        href = None
    if not href:
        return "INTERNAL_APPLY"
    target = urljoin(current_page_url, href)
    if urlparse(target).netloc and urlparse(target).netloc != urlparse(current_page_url).netloc:
        return "EXTERNAL_APPLY"
    return "INTERNAL_APPLY"


async def follow_external_apply(page: Page, browser: BrowserContext, item) -> Page:
    """Segue um CTA classificado como EXTERNAL_APPLY - clica e acompanha
    a navegação real (nova aba ou goto via href), nunca trata o clique
    em si como um envio de formulário. Candidatura externa é um fluxo
    legítimo a seguir, não um motivo pra desistir."""
    pages_before = set(browser.pages)
    href = None
    try:
        href = await item.get_attribute("href")
    except Exception:
        pass
    try:
        await item.click(timeout=8000)
    except Exception:
        return page
    await page.wait_for_timeout(1800)
    opened_pages = [candidate for candidate in browser.pages if candidate not in pages_before]
    if opened_pages:
        page = opened_pages[-1]
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=35_000)
        except Exception:
            pass
    elif href:
        try:
            await page.goto(urljoin(page.url, href), wait_until="domcontentloaded", timeout=35_000)
        except Exception:
            pass
    await dismiss_overlays(page)
    return page


def remember_layout(application: dict, stage: str, details: dict | None = None) -> None:
    knowledge = load_json(LAYOUT_KNOWLEDGE, {})
    host = urlparse(str(application.get("job_url", ""))).netloc.lower() or "unknown"
    history = knowledge.setdefault(host, [])
    history.append({"at": datetime.now(UTC).isoformat(), "stage": stage,
                    "status": application.get("status"), "reason": application.get("reason", ""),
                    "details": details or {}})
    knowledge[host] = history[-50:]
    save_json(LAYOUT_KNOWLEDGE, knowledge)


async def submission_confirmed(page: Page, previous_url: str) -> bool:
    """CONFIRMED exige evidência positiva real - nunca promove por
    inferência fraca. O texto forte de sucesso já basta sozinho. Mudança
    de URL NUNCA basta sozinha: qualquer etapa intermediária do fluxo
    (revisão, confirmação de dados) também muda a URL e quase sempre tem
    "application" no caminho - isso já foi causa real de falso positivo.
    Só conta como confirmação corroborada por URL quando a página também
    tem alguma palavra de agradecimento/recebimento, mesmo que mais fraca
    que o padrão forte acima."""
    body = (await page.locator("body").inner_text(timeout=10_000))[:40_000]
    success_text = re.search(
        r"candidatura (?:foi )?enviada|candidatura realizada|cv enviado|inscri[cç][aã]o (?:foi )?conclu[ií]da|application submitted|successfully applied|já se candidatou",
        body, re.IGNORECASE,
    )
    if success_text:
        return True
    url_looks_like_success = page.url != previous_url and bool(
        re.search(r"success|confirmation|thank-?you", page.url, re.IGNORECASE)
    )
    if not url_looks_like_success:
        return False
    return bool(re.search(r"obrigado|recebemos|received|thank you", body, re.IGNORECASE))


async def execute_application_queue(request: ExecuteRequest) -> None:
    switches = await asyncio.to_thread(fetch_kill_switches, CAREER_API_URL, CAREER_ADMIN_TOKEN)
    kill_status = is_paused(switches, "PAUSE_ALL", "PAUSE_BROWSER_APPLY", fail_closed=True)
    if kill_status.paused:
        event("EXECUTION_PAUSED", reason=kill_status.reason, reachable=kill_status.reachable)
        update(status="paused", message=f"Execução pausada: {kill_status.reason or 'kill switch ativo'}.")
        return
    settings = AutomationSettings.model_validate(load_json(SETTINGS_DATA, {}))
    profile = ProfessionalProfile.model_validate(load_json(PROFILE_DATA, {}))
    applications = load_json(APPLICATIONS, [])
    remaining_quota = remaining_daily_quota(applications, settings.daily_target, datetime.now(UTC))
    def retryable(application: dict) -> bool:
        if application.get("status") == "READY_TO_PREPARE":
            return True
        attempts = int(application.get("attempts", 0))
        if attempts >= 3:
            return False
        if application.get("status") == "FAILED" and "TimeoutError" in application.get("reason", ""):
            return True
        if application.get("status") == "READY_FOR_REVIEW" and "botão final não localizado" in application.get("reason", ""):
            return True
        if application.get("status") == "MANUAL_REQUIRED" and application.get("unknown_fields"):
            return True
        if application.get("status") == "MANUAL_REQUIRED" and "sem confirmação da plataforma" in application.get("reason", ""):
            return True
        return False

    pending = sorted([
        application for application in applications
        if retryable(application) and (not request.application_ids or application.get("id") in request.application_ids)
    ], key=lambda application: (
        -(datetime.fromisoformat(application.get("job_first_seen_at") or application.get("created_at")).timestamp()),
        geography_priority(application),
    ))[: request.limit]
    browser = await ensure_browser()
    page = browser.pages[0] if browser.pages else await browser.new_page()
    submitted = 0
    total = len(pending)
    update(status="applying", message=f"Preparando {total} candidaturas.")
    for position, application in enumerate(pending, start=1):
        application["attempts"] = int(application.get("attempts", 0)) + 1
        update(status="applying", platform=application.get("source"), role=application.get("title"),
               message=f"Candidatura {position}/{total}: abrindo vaga.")
        try:
            await page.goto(authenticated_application_url(application["job_url"]), wait_until="commit", timeout=35_000)
            await page.wait_for_timeout(2000)
            if "gupy.io" in page.url.lower():
                application["status"] = "BLOCKED"
                application["reason"] = "Ignorada: plataforma bloqueada pelo usuário."
                continue
            body = (await page.locator("body").inner_text())[:100_000]
            application.update(opportunity_feedback(application["title"], body, settings))
            if application.get("blocks"):
                application["status"] = "BLOCKED"
                application["reason"] = f"Bloqueada: {', '.join(application['blocks'])}."
                remember_layout(application, "hard_block", {"blocks": application["blocks"]})
                continue
            if re.search(r"n[aã]o aceita mais candidaturas|vaga (?:foi )?encerrada|processo seletivo encerrado|no longer accepting applications|job is no longer available", body, re.IGNORECASE):
                application["status"] = "CLOSED"
                application["reason"] = "Vaga encerrada: a plataforma não aceita mais candidaturas."
                remember_layout(application, "closed_vacancy")
                continue
            if re.search(r"candidatura realizada(?: hoje)?|cv enviado|já se candidatou|application submitted|successfully applied", body, re.IGNORECASE):
                # A página INDICA candidatura já enviada, mas isso é uma inferência sobre o
                # estado da página, não prova de primeira mão de que este sistema enviou -
                # pode ser candidatura manual anterior, cache da plataforma, ou até engano.
                # Nunca vira APPLIED sozinho; precisa de confirmação humana.
                application["status"] = "MANUAL_REQUIRED"
                application["reason"] = ("A página indica candidatura já enviada para esta vaga, mas o "
                                          "sistema não tem evidência própria do envio - confirme manualmente.")
                event("APPLICATION_ALREADY_SUBMITTED_UNCONFIRMED", application_id=application["id"])
                await report_intervention(
                    application, "SUBMISSION_UNCONFIRMED", "Confirme se a candidatura já foi enviada",
                    "A página mostra uma mensagem de candidatura já realizada, mas o sistema não tem "
                    "evidência própria de ter enviado. Verifique manualmente antes de contar como concluída.",
                    page.url,
                )
                continue
            if INTERVENTION_PATTERNS["MFA"].search(body):
                application["status"] = "MANUAL_REQUIRED"
                application["reason"] = "Confirmação em duas etapas necessária."
                await report_intervention(
                    application, "MFA", "Confirme o acesso na plataforma",
                    "Abra a página, conclua a verificação em duas etapas e depois retome a automação.",
                    page.url,
                )
                continue
            if re.search(r"entre para se candidatar|fa[cç]a login para se candidatar|sign in to apply|join linkedin", body, re.IGNORECASE):
                application["status"] = "MANUAL_REQUIRED"
                application["reason"] = "A plataforma exige login antes da candidatura."
                await report_intervention(
                    application, "LOGIN_REQUIRED", "Entre na plataforma de vagas",
                    "Faça login na plataforma e retome a automação. A senha não é armazenada pelo HelpSystem.",
                    page.url,
                )
                continue
            if INTERVENTION_PATTERNS["CAPTCHA"].search(body):
                application["status"] = "MANUAL_REQUIRED"
                application["reason"] = "CAPTCHA detectado."
                await report_intervention(
                    application, "CAPTCHA", "Verificação humana necessária",
                    "Abra a página e resolva o CAPTCHA manualmente. O sistema nunca tenta contorná-lo.",
                    page.url,
                )
                continue
            dismissed = await dismiss_overlays(page)
            pages_before_action = set(browser.pages)
            action_href = None
            action_links = page.get_by_role(
                "link", name=re.compile(r"candidatar|apply", re.IGNORECASE)
            )
            for link_index in range(min(await action_links.count(), 8)):
                candidate_link = action_links.nth(link_index)
                if await candidate_link.is_visible():
                    action_href = await candidate_link.get_attribute("href")
                    if action_href:
                        break
            action_clicked = await click_first_visible(page, EXTERNAL_APPLY_CTA_PATTERN)
            if action_clicked:
                await page.wait_for_timeout(1800)
                opened_pages = [candidate for candidate in browser.pages if candidate not in pages_before_action]
                if opened_pages:
                    page = opened_pages[-1]
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=35_000)
                    except Exception:
                        pass
                elif action_href:
                    await page.goto(
                        urljoin(page.url, action_href),
                        wait_until="domcontentloaded",
                        timeout=35_000,
                    )
                await dismiss_overlays(page)
            if "gupy.io" in page.url.lower():
                application["status"] = "BLOCKED"
                application["reason"] = "Ignorada: plataforma bloqueada pelo usuÃ¡rio."
                remember_layout(application, "blocked_platform", {"platform": "gupy"})
                continue
            roots = await search_roots(page)
            ats_match = (
                next((match for root in roots if (match := detect_ats(root.url))), None)
                or (detect_ats(action_href) if action_href else None)
            )
            application["detected_ats"] = ats_match.adapter if ats_match else None
            application["detected_ats_account"] = ats_match.account_key if ats_match else None
            if ats_match:
                await suggest_source_connection(ats_match)
            resume_override_path, core_resume_version_id = await resolve_resume_for_application(application)
            application["core_resume_version_id"] = core_resume_version_id
            effective_profile = (
                profile.model_copy(update={"resume_path": resume_override_path})
                if resume_override_path else profile
            )
            filled: list[str] = []
            ai_filled: list[dict[str, object]] = []

            async def fill_current_step() -> list[str]:
                step_unknown: list[str] = []
                for root in await search_roots(page):
                    filled.extend(await fill_known_fields(root, effective_profile))
                    ai_result = await ai_fill_simple_questions(root, effective_profile, application)
                    ai_filled.extend(ai_result.get("filled", []))
                    step_unknown.extend(await required_unknown_fields(root))
                return step_unknown

            visible_submit = None
            steps_advanced = 0
            external_apply_hops: list[dict[str, str]] = []
            unknown = await fill_current_step()
            while not unknown and visible_submit is None and steps_advanced < MAX_APPLICATION_STEPS:
                candidate = None
                for root in await search_roots(page):
                    candidate = await find_first_visible(root, FINAL_SUBMIT_CTA_PATTERN)
                    if candidate is not None:
                        break
                if candidate is not None:
                    # Achado real em produção: um <a href> apontando pra outro domínio
                    # NUNCA é um envio de formulário, mesmo batendo no padrão de texto
                    # final ("Candidatar-se" é usado tanto pra isso quanto pra abrir
                    # link externo). Candidatura externa é um fluxo legítimo a seguir,
                    # não um motivo pra desistir - segue a navegação e continua
                    # procurando o envio de verdade na página de destino, em vez de
                    # clicar no link como se fosse SUBMIT_ACTION.
                    if await classify_application_cta(candidate, page.url) == "EXTERNAL_APPLY":
                        href = None
                        try:
                            href = await candidate.get_attribute("href")
                        except Exception:
                            pass
                        hop = {
                            "at": datetime.now(UTC).isoformat(),
                            "from_url": page.url,
                            "target_domain": urlparse(urljoin(page.url, href or "")).netloc,
                        }
                        event("EXTERNAL_APPLY_LINK_FOLLOWED", application_id=application["id"],
                              target_domain=hop["target_domain"])
                        page = await follow_external_apply(page, browser, candidate)
                        hop["followed_to_url"] = page.url
                        external_apply_hops.append(hop)
                        steps_advanced += 1
                        unknown = await fill_current_step()
                        continue
                    visible_submit = candidate
                    break
                if not await click_first_visible(page, NEXT_STEP_CTA_PATTERN):
                    break
                steps_advanced += 1
                await page.wait_for_timeout(1500)
                await dismiss_overlays(page)
                unknown = await fill_current_step()
            if external_apply_hops:
                application["external_apply_hops"] = external_apply_hops

            SCREENSHOTS.mkdir(parents=True, exist_ok=True)
            evidence = SCREENSHOTS / f"{application['id']}-prepared.png"
            await page.screenshot(path=str(evidence), full_page=True)
            application["evidence"] = str(evidence)
            application["filled_fields"] = filled
            application["ai_answers"] = ai_filled
            application["unknown_fields"] = unknown
            application["dismissed_overlays"] = dismissed
            if steps_advanced:
                event("APPLICATION_STEPS_ADVANCED", application_id=application["id"], steps=steps_advanced)
            if unknown:
                application["status"] = "MANUAL_REQUIRED"
                application["reason"] = f"Resposta ainda não comprovada: {', '.join(unknown[:5])}."
                remember_layout(application, "required_fields", {"fields": unknown})
                await report_intervention(
                    application, "UNKNOWN_FIELD", "Revise respostas obrigatórias",
                    "Existem campos que o sistema não pode responder sem sua confirmação.",
                    page.url, {"fields": unknown[:20]},
                )
                continue
            can_submit = visible_submit is not None
            # Autorização de teste controlado: libera envio ao vivo SÓ para o
            # application_id exato indicado nesta chamada, sem depender do
            # interruptor global AUTO_APPLY_ENABLED (que continua desligado
            # em produção). Nunca é setado por daily_scheduler/full_daily_pipeline
            # - só existe quando alguém monta a chamada explicitamente com esse
            # campo, então o agendador nunca herda isso por acidente.
            single_controlled_match = (
                request.single_controlled_application_id is not None
                and application["id"] == request.single_controlled_application_id
            )
            if single_controlled_match:
                event("SINGLE_CONTROLLED_SUBMISSION_AUTHORIZED", application_id=application["id"])
            would_apply = request.confirm_live_submission and (
                environment_auto_apply_enabled() or single_controlled_match
            )
            quota_available = remaining_quota > 0
            live_allowed = would_apply and not dry_run_enabled() and quota_available
            if can_submit and would_apply and not dry_run_enabled() and not quota_available:
                event("DAILY_LIMIT_REACHED", application_id=application["id"], daily_target=settings.daily_target)
            elif can_submit and would_apply and not live_allowed:
                event("DRY_RUN_SUBMISSION_BLOCKED", application_id=application["id"])
            if can_submit and live_allowed:
                # O texto e até a tag do elemento não bastam pra saber se um clique
                # é um envio de formulário ou um redirecionamento externo - SPAs
                # modernas (ex: LinkedIn) costumam usar <button onClick> disparando
                # window.open()/navegação via JS, não um <a href> simples (achado
                # real: a checagem estática por tag/href não pegou esse caso).
                # Decide observando o que o clique realmente faz: nova aba ou
                # mudança de domínio nunca é um envio - é candidatura externa, um
                # fluxo legítimo a seguir, não motivo pra desistir. Só chama
                # submission_confirmed() quando o clique manteve a mesma origem.
                live_click_attempts = 0
                resolved = False
                while visible_submit is not None and live_click_attempts < MAX_APPLICATION_STEPS:
                    live_click_attempts += 1
                    before_submit = page.url
                    before_pages = set(browser.pages)
                    try:
                        await visible_submit.click(timeout=8000)
                    except Exception:
                        break
                    await page.wait_for_timeout(2200)
                    opened_pages = [candidate for candidate in browser.pages if candidate not in before_pages]
                    navigated_cross_origin = urlparse(page.url).netloc != urlparse(before_submit).netloc
                    if opened_pages or navigated_cross_origin:
                        if opened_pages:
                            page = opened_pages[-1]
                            try:
                                await page.wait_for_load_state("domcontentloaded", timeout=35_000)
                            except Exception:
                                pass
                        await dismiss_overlays(page)
                        hop = {
                            "at": datetime.now(UTC).isoformat(), "from_url": before_submit,
                            "followed_to_url": page.url, "target_domain": urlparse(page.url).netloc,
                        }
                        external_apply_hops.append(hop)
                        event("EXTERNAL_APPLY_LINK_FOLLOWED", application_id=application["id"],
                              target_domain=hop["target_domain"])
                        await fill_current_step()
                        visible_submit = None
                        for root in await search_roots(page):
                            visible_submit = await find_first_visible(root, FINAL_SUBMIT_CTA_PATTERN)
                            if visible_submit is not None:
                                break
                        continue
                    resolved = True
                    if await submission_confirmed(page, before_submit):
                        application["status"] = "APPLIED"
                        application["submitted_at"] = datetime.now(UTC).isoformat()
                        application["reason"] = "Envio confirmado pela plataforma."
                        submitted += 1
                        remaining_quota -= 1
                        event("APPLICATION_SUBMITTED", application_id=application["id"])
                    else:
                        application["status"] = "MANUAL_REQUIRED"
                        application["reason"] = "Envio acionado, mas sem confirmação da plataforma; não contabilizada."
                        remember_layout(application, "submission_unconfirmed")
                        await report_intervention(
                            application, "SUBMISSION_UNCONFIRMED", "Confirme o envio da candidatura",
                            "A plataforma não confirmou o envio. Verifique a página antes de tentar novamente.",
                            page.url,
                        )
                    break
                if external_apply_hops:
                    application["external_apply_hops"] = external_apply_hops
                if not resolved:
                    application["status"] = "MANUAL_REQUIRED"
                    application["reason"] = (
                        "A candidatura é externa a esta plataforma (link/redirecionamento) e não foi "
                        "possível localizar um envio interno de verdade após seguir a navegação - "
                        "conclua manualmente no site de destino."
                    )
                    remember_layout(application, "external_apply_unresolved", {"hops": external_apply_hops})
                    await report_intervention(
                        application, "SUBMISSION_UNCONFIRMED", "Complete a candidatura externa manualmente",
                        "O sistema seguiu um ou mais links de candidatura externa mas não encontrou um "
                        "formulário interno pra completar o envio automaticamente. Finalize a candidatura "
                        "manualmente no site da empresa.",
                        page.url, {"external_apply_hops": external_apply_hops},
                    )
            else:
                application["status"] = "READY_FOR_REVIEW"
                if not can_submit:
                    application["reason"] = "Formulário preparado; botão final não localizado."
                elif would_apply and not quota_available:
                    application["reason"] = f"Formulário preenchido; limite diário de {settings.daily_target} candidaturas já atingido."
                elif dry_run_enabled():
                    application["reason"] = "Formulário preenchido; modo DRY RUN ativo (nenhum envio real é permitido)."
                else:
                    application["reason"] = "Formulário preenchido; autoenvio desligado."
        except Exception as exc:
            application["status"] = "FAILED"
            application["reason"] = f"Falha na preparação: {type(exc).__name__}."
            remember_layout(application, "exception", {"error": type(exc).__name__, "url": page.url[:160]})
        finally:
            save_json(APPLICATIONS, applications)
            await sync_status_to_core(application)
    update(status="completed", message=f"Preparação concluída; {submitted} candidaturas enviadas.")
    event("APPLICATION_RUN_COMPLETED", submitted=submitted, inspected=len(pending))


async def analyze_all_jobs(minimum_score: int) -> dict[str, int]:
    profile = ProfessionalProfile.model_validate(load_json(PROFILE_DATA, {}))
    jobs = load_json(RESULTS, [])
    approved = review = ignored = 0
    for job in jobs:
        score, positives, risks = calculate_match(job, profile)
        job["score"] = score
        job["match_reasons"] = positives
        job["risks"] = risks
        if score >= minimum_score:
            job["decision"] = "APPROVED_AUTO"
            approved += 1
        elif score >= 60:
            job["decision"] = "REQUIRES_REVIEW"
            review += 1
        else:
            job["decision"] = "IGNORED"
            ignored += 1
        job["status"] = "ANALYZED"
    save_json(RESULTS, jobs)
    event("JOBS_ANALYZED", approved=approved, review=review, ignored=ignored)
    return {"analyzed": len(jobs), "approved": approved, "review": review, "ignored": ignored}


async def full_daily_pipeline() -> None:
    switches = await asyncio.to_thread(fetch_kill_switches, CAREER_API_URL, CAREER_ADMIN_TOKEN)
    kill_status = is_paused(switches, "PAUSE_ALL", fail_closed=False)
    if kill_status.paused:
        event("DAILY_PIPELINE_PAUSED", reason=kill_status.reason)
        update(status="paused", message=f"Ciclo diário pausado: {kill_status.reason or 'kill switch ativo'}.")
        return
    profile = await sync_profile_from_core()
    if profile is None:
        profile = ProfessionalProfile.model_validate(load_json(PROFILE_DATA, {}))
    settings = AutomationSettings.model_validate(load_json(SETTINGS_DATA, {}))
    if not profile.full_name or not profile.email or not profile.resume_path:
        update(status="profile_required", message="Currículo ou contatos obrigatórios não foram extraídos.")
        return
    event("DAILY_PIPELINE_STARTED")
    await automation_run(RunRequest(roles=profile.target_roles, max_roles=min(10, len(profile.target_roles))))
    await analyze_all_jobs(settings.minimum_score)
    await inspect_application_queue(PrepareRequest(limit=settings.daily_target))
    await execute_application_queue(ExecuteRequest(limit=settings.daily_target, confirm_live_submission=True))
    event("DAILY_PIPELINE_COMPLETED")


async def daily_scheduler() -> None:
    global run_task
    started = datetime.now().astimezone()
    last_slot = f"{started.date().isoformat()}-{started.hour}" if started.hour in {8, 12, 18} else ""
    while True:
        now = datetime.now().astimezone()
        slot = f"{now.date().isoformat()}-{now.hour}"
        profile = ProfessionalProfile.model_validate(load_json(PROFILE_DATA, {}))
        if now.hour in {8, 12, 18} and slot != last_slot and profile.target_roles:
            last_slot = slot
            if not run_task or run_task.done():
                event("SCHEDULE_TRIGGERED", slot=slot)
                run_task = asyncio.create_task(full_daily_pipeline())
        await asyncio.sleep(60)


def enqueue_core_sync(record: CoreSyncRecord) -> None:
    """Nunca bloqueia o chamador: so acrescenta uma linha ao outbox local.
    A entrega de verdade (com retry/backoff) acontece em core_sync_scheduler."""
    CORE_SYNC_OUTBOX.parent.mkdir(parents=True, exist_ok=True)
    with CORE_SYNC_OUTBOX.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


def _load_core_sync_outbox() -> list[CoreSyncRecord]:
    if not CORE_SYNC_OUTBOX.exists():
        return []
    records = []
    for line in CORE_SYNC_OUTBOX.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(CoreSyncRecord.from_dict(json.loads(line)))
        except (json.JSONDecodeError, TypeError):
            continue
    return records


def _rewrite_core_sync_outbox(records: list[CoreSyncRecord]) -> None:
    CORE_SYNC_OUTBOX.parent.mkdir(parents=True, exist_ok=True)
    with CORE_SYNC_OUTBOX.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


def _dead_letter_core_sync(record: CoreSyncRecord) -> None:
    CORE_SYNC_DEAD_LETTER.parent.mkdir(parents=True, exist_ok=True)
    with CORE_SYNC_DEAD_LETTER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


def _load_core_sync_links() -> dict:
    return load_json(CORE_SYNC_LINKS, {})


def _update_core_sync_link(correlation_id: str, **fields: object) -> None:
    links = _load_core_sync_links()
    entry = links.get(correlation_id, {})
    entry.update(fields)
    links[correlation_id] = entry
    save_json(CORE_SYNC_LINKS, links)


def _advance_core_sync_chain(record: CoreSyncRecord, response: dict | None) -> list[CoreSyncRecord]:
    """JOB sincronizado -> pontua; pontuação elegível -> prepara (Resume
    Router de verdade). Cada etapa só avança se a anterior teve sucesso -
    nunca pula direto pra prepare sem o job_id/score reais do Core.

    Retorna os registros novos em vez de enfileirar direto (enqueue_core_sync
    só acrescenta ao outbox): core_sync_scheduler chama isso DENTRO do
    laço que depois reescreve o arquivo inteiro a partir da lista
    `remaining` em memória - um enqueue direto aqui seria apagado pela
    reescrita no fim do mesmo ciclo (bug real encontrado e corrigido:
    a cadeia nunca avançava além de JOB porque o SCORE enfileirado assim
    sumia antes de ser lido de novo)."""
    if response is None or response.get("already_applied"):
        return []
    if record.kind == "JOB":
        job_id = response.get("id")
        if not job_id:
            return []
        _update_core_sync_link(record.correlation_id, job_id=job_id)
        return [build_score_record(job_id=job_id, correlation_id=record.correlation_id)]
    if record.kind == "SCORE":
        job_id = record.payload.get("job_id")
        total = int(response.get("total", 0) or 0)
        recommendation = str(response.get("recommendation", ""))
        _update_core_sync_link(record.correlation_id, last_score=total, last_recommendation=recommendation)
        if is_eligible_for_prepare(total, recommendation):
            return [build_prepare_record(job_id=job_id, correlation_id=record.correlation_id)]
        event("CORE_SYNC_NOT_ELIGIBLE", correlation_id=record.correlation_id,
              total=total, recommendation=recommendation)
        return []
    if record.kind == "PREPARE":
        application = response.get("application") or {}
        _update_core_sync_link(
            record.correlation_id,
            core_application_id=application.get("id"),
            resume_version_id=application.get("resume_version_id"),
            resume_family=response.get("resume_family"),
        )
        event("CORE_APPLICATION_PREPARED", correlation_id=record.correlation_id,
              core_application_id=application.get("id"), resume_version_id=application.get("resume_version_id"))
        return []
    if record.kind == "TRANSITION":
        event("CORE_TRANSITION_APPLIED", correlation_id=record.correlation_id,
              to_status=record.payload.get("status"))
        return []
    return []


async def sync_status_to_core(application: dict) -> None:
    """Reflete o status local como uma transição real no Core - vocabulário
    canônico único (core_bridge.LOCAL_STATUS_TO_CORE_TRANSITION), nunca uma
    segunda máquina de estados independente. Nunca bloqueia o fluxo local:
    se o Core ainda não preparou esta vaga (sem core_application_id) ou
    não há transição aplicável pro status atual, não faz nada."""
    if not CAREER_ADMIN_TOKEN:
        return
    entry = _load_core_sync_links().get(application["id"], {})
    core_application_id = entry.get("core_application_id")
    if not core_application_id:
        return
    target_status = map_local_status_to_core_transition(str(application.get("status", "")))
    if not target_status or entry.get("last_core_transition") == target_status:
        return
    enqueue_core_sync(build_transition_record(
        core_application_id=core_application_id, target_status=target_status,
        reason=str(application.get("reason", "")), correlation_id=application["id"],
    ))
    _update_core_sync_link(application["id"], last_core_transition=target_status)


async def core_sync_scheduler() -> None:
    await asyncio.sleep(15)
    while True:
        records = _load_core_sync_outbox()
        if records:
            now = datetime.now(UTC)
            remaining: list[CoreSyncRecord] = []
            for record in records:
                if not is_due(record, now):
                    remaining.append(record)
                    continue
                result = await asyncio.to_thread(send_core_sync, CAREER_API_URL, CAREER_ADMIN_TOKEN, record)
                if result.ok:
                    event("CORE_SYNC_OK", kind=record.kind, correlation_id=record.correlation_id,
                          idempotency_key=record.idempotency_key, attempts=record.attempts + 1)
                    remaining.extend(_advance_core_sync_chain(record, result.response))
                    continue
                record.attempts += 1
                record.last_error = result.error
                record.last_attempt_at = now.isoformat()
                if not result.retryable or record.attempts >= 5:
                    event("CORE_SYNC_DEAD_LETTERED", kind=record.kind, correlation_id=record.correlation_id,
                          idempotency_key=record.idempotency_key, attempts=record.attempts, error=result.error)
                    _dead_letter_core_sync(record)
                else:
                    event("CORE_SYNC_RETRY_SCHEDULED", kind=record.kind, correlation_id=record.correlation_id,
                          attempts=record.attempts, error=result.error)
                    remaining.append(record)
            _rewrite_core_sync_outbox(remaining)
        await asyncio.sleep(30)


async def google_mail_scheduler() -> None:
    await asyncio.sleep(20)
    while True:
        if GOOGLE_TOKEN.exists():
            health = load_json(GOOGLE_HEALTH, {"consecutive_failures": 0, "last_success_at": None})
            try:
                result = await asyncio.to_thread(scan_recruitment_mail, GOOGLE_TOKEN, GOOGLE_INBOX, 90, 250)
                event("GOOGLE_MAIL_SCANNED", scanned=result["scanned"], discovered=result["discovered"])
                if health.get("consecutive_failures", 0) >= GOOGLE_HEALTH_ALERT_THRESHOLD:
                    event("GOOGLE_MAIL_RECOVERED", after_failures=health["consecutive_failures"])
                save_json(GOOGLE_HEALTH, {
                    "consecutive_failures": 0,
                    "last_success_at": datetime.now(UTC).isoformat(),
                    "last_error": None,
                })
            except Exception as exc:
                consecutive_failures = health.get("consecutive_failures", 0) + 1
                save_json(GOOGLE_HEALTH, {
                    "consecutive_failures": consecutive_failures,
                    "last_success_at": health.get("last_success_at"),
                    "last_error": type(exc).__name__,
                    "last_error_at": datetime.now(UTC).isoformat(),
                })
                event("GOOGLE_MAIL_SCAN_FAILED", error=type(exc).__name__, consecutive_failures=consecutive_failures)
                if consecutive_failures == GOOGLE_HEALTH_ALERT_THRESHOLD:
                    event("GOOGLE_MAIL_AUTH_BROKEN", error=type(exc).__name__, consecutive_failures=consecutive_failures)
        await asyncio.sleep(600)


@app.on_event("startup")
async def startup_scheduler() -> None:
    await sync_profile_from_core()
    update(status="ready", message="Agente pronto. Próximas execuções automáticas: 08:00, 12:00 e 18:00.")
    asyncio.create_task(daily_scheduler())
    asyncio.create_task(google_mail_scheduler())
    asyncio.create_task(core_sync_scheduler())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
async def get_status() -> dict[str, object]:
    return {**state, "service_online": True, "executor_mode": "vps" if BROWSER_HEADLESS else "local"}


@app.get("/metrics")
async def get_metrics() -> dict[str, object]:
    jobs = load_json(RESULTS, [])
    applications = load_json(APPLICATIONS, [])
    event_count = 0
    if LOGS.exists():
        with LOGS.open("r", encoding="utf-8") as handle:
            event_count = sum(1 for line in handle if line.strip())
    decisions: dict[str, int] = {}
    statuses: dict[str, int] = {}
    sources: dict[str, int] = {}
    for job in jobs:
        decision = str(job.get("decision") or "PENDING")
        decisions[decision] = decisions.get(decision, 0) + 1
        source = str(job.get("source") or "UNKNOWN")
        sources[source] = sources.get(source, 0) + 1
    for application in applications:
        status = str(application.get("status") or "UNKNOWN")
        statuses[status] = statuses.get(status, 0) + 1
    google_health = load_json(GOOGLE_HEALTH, {})
    return {
        "service_online": True,
        "executor_mode": "vps" if BROWSER_HEADLESS else "local",
        "status": state.get("status", "unknown"),
        "jobs": len(jobs),
        "applications": len(applications),
        "blocked": int(state.get("blocked", 0) or 0),
        "decisions": decisions,
        "application_statuses": statuses,
        "sources": sources,
        "events": event_count,
        "updated_at": state.get("updated_at"),
        "google_mail_healthy": google_health.get("consecutive_failures", 0) < GOOGLE_HEALTH_ALERT_THRESHOLD,
        "google_mail_consecutive_failures": google_health.get("consecutive_failures", 0),
        "google_mail_last_success_at": google_health.get("last_success_at"),
    }


@app.get("/ai/status")
async def get_ai_status() -> dict[str, object]:
    return await local_ai_status()


@app.get("/core-sync/status")
async def core_sync_status() -> dict:
    outbox = _load_core_sync_outbox()
    dead_letter_count = 0
    if CORE_SYNC_DEAD_LETTER.exists():
        dead_letter_count = sum(1 for line in CORE_SYNC_DEAD_LETTER.read_text(encoding="utf-8").splitlines() if line.strip())
    by_kind: dict[str, int] = {}
    for record in outbox:
        by_kind[record.kind] = by_kind.get(record.kind, 0) + 1
    return {"pending": len(outbox), "pending_by_kind": by_kind, "dead_letter": dead_letter_count}


@app.post("/core-sync/dead-letter/{idempotency_key:path}/requeue")
async def core_sync_requeue(idempotency_key: str) -> dict:
    if not CORE_SYNC_DEAD_LETTER.exists():
        raise HTTPException(status_code=404, detail="Nenhuma entrada na dead-letter.")
    lines = [line for line in CORE_SYNC_DEAD_LETTER.read_text(encoding="utf-8").splitlines() if line.strip()]
    remaining: list[str] = []
    requeued: dict | None = None
    for line in lines:
        data = json.loads(line)
        if requeued is None and data.get("idempotency_key") == idempotency_key:
            requeued = data
            continue
        remaining.append(line)
    if requeued is None:
        raise HTTPException(status_code=404, detail="Chave não encontrada na dead-letter.")
    record = CoreSyncRecord.from_dict(requeued)
    record.attempts = 0
    record.last_error = None
    record.last_attempt_at = None
    enqueue_core_sync(record)
    with CORE_SYNC_DEAD_LETTER.open("w", encoding="utf-8") as handle:
        for line in remaining:
            handle.write(line + "\n")
    event("CORE_SYNC_REQUEUED", idempotency_key=idempotency_key, kind=record.kind)
    return {"requeued": True, "kind": record.kind}


@app.get("/google/status")
async def google_status() -> dict:
    items = load_json(GOOGLE_INBOX, [])
    if not GOOGLE_TOKEN.exists():
        return {"connected": False, "email": None, "calendar": False, "alerts": 0, "last_items": items[:20]}
    cached = load_json(GOOGLE_STATUS_CACHE, {})
    checked_at = cached.get("checked_at")
    if checked_at:
        try:
            age = datetime.now(UTC) - datetime.fromisoformat(checked_at)
            if age.total_seconds() < 600:
                cached["alerts"] = len([item for item in items if item.get("status") == "NEW"])
                cached["last_items"] = items[:20]
                return cached
        except (TypeError, ValueError):
            pass
    try:
        status = await asyncio.to_thread(connection_status, GOOGLE_TOKEN)
        status["checked_at"] = datetime.now(UTC).isoformat()
        save_json(GOOGLE_STATUS_CACHE, status)
        status["alerts"] = len([item for item in items if item.get("status") == "NEW"])
        status["last_items"] = items[:20]
        return status
    except Exception as exc:
        # A checagem ao vivo falhou agora - nunca reportar connected=true com base em
        # cache antigo, mesmo que a última checagem bem-sucedida tenha sido recente.
        health = load_json(GOOGLE_HEALTH, {})
        return {
            "connected": False,
            "email": cached.get("email"),
            "calendar": False,
            "error": type(exc).__name__,
            "last_success_at": health.get("last_success_at") or cached.get("checked_at"),
            "consecutive_failures": health.get("consecutive_failures", 0),
            "alerts": len([item for item in items if item.get("status") == "NEW"]),
            "last_items": items[:20],
        }


@app.post("/google/scan")
async def google_scan() -> dict:
    if not GOOGLE_TOKEN.exists():
        raise HTTPException(status_code=401, detail="Google ainda não autorizado.")
    try:
        result = await asyncio.to_thread(scan_recruitment_mail, GOOGLE_TOKEN, GOOGLE_INBOX, 90, 250)
        if CAREER_ADMIN_TOKEN:
            payload = {"provider": "GMAIL", "items": [{
                "provider_message_id": item["message_id"],
                "thread_id": item.get("thread_id"),
                "sender": item.get("sender", ""),
                "subject": item.get("subject", "(sem assunto)"),
                "category": item.get("category", "OTHER"),
                "confidence": item.get("confidence", 0),
                "received_at": item["received_at"],
            } for item in result["items"]]}
            try:
                request = Request(
                    CAREER_API_URL + "/api/v1/communications/sync",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Authorization": f"Bearer {CAREER_ADMIN_TOKEN}",
                             "Content-Type": "application/json"},
                    method="POST",
                )
                await asyncio.to_thread(urlopen, request, timeout=20)
            except Exception as sync_error:
                event("GOOGLE_CORE_SYNC_FAILED", error=type(sync_error).__name__)
        event("GOOGLE_MAIL_SCANNED", scanned=result["scanned"], discovered=result["discovered"])
        return result
    except Exception as exc:
        event("GOOGLE_MAIL_SCAN_FAILED", error=type(exc).__name__)
        raise HTTPException(status_code=502, detail=f"Falha ao consultar Gmail: {type(exc).__name__}") from exc


@app.post("/google/security-code")
async def google_security_code(request: SecurityCodeRequest,
                               authorization: str = Header(default="")) -> dict[str, bool]:
    if not CAREER_ADMIN_TOKEN or authorization != f"Bearer {CAREER_ADMIN_TOKEN}":
        raise HTTPException(status_code=401, detail="Não autorizado.")
    try:
        await asyncio.to_thread(send_security_code, GOOGLE_TOKEN, request.recipient, request.code)
        event("SECURITY_CODE_SENT")
        return {"sent": True}
    except Exception as exc:
        event("SECURITY_CODE_FAILED", error=type(exc).__name__)
        raise HTTPException(status_code=503, detail="Não foi possível entregar o código.") from exc
@app.post("/google/draft")
async def google_draft(request: GoogleDraftRequest) -> dict:
    try:
        result = await asyncio.to_thread(create_reply_draft, GOOGLE_TOKEN, GOOGLE_INBOX, request.message_id)
        event("GOOGLE_REPLY_DRAFT_CREATED", subject=result.get("subject"))
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao criar rascunho: {type(exc).__name__}") from exc


@app.post("/google/application-draft")
async def google_application_draft(request: ApplicationEmailDraftRequest) -> dict:
    source = Path(request.resume_path).resolve()
    if not source.is_relative_to(RESUME_STORAGE) or not source.is_file():
        raise HTTPException(status_code=400, detail="Currículo aprovado não localizado.")
    try:
        result = await asyncio.to_thread(create_application_email_draft, GOOGLE_TOKEN,
                                         request.recipient, request.subject, request.body, source)
        event("APPLICATION_EMAIL_DRAFT_CREATED", draft_id=result["draft_id"])
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao criar rascunho: {type(exc).__name__}") from exc


@app.post("/google/calendar")
async def google_calendar(request: GoogleDraftRequest) -> dict:
    try:
        result = await asyncio.to_thread(create_calendar_event, GOOGLE_TOKEN, GOOGLE_INBOX, request.message_id)
        event("GOOGLE_CALENDAR_EVENT_CREATED", subject=result.get("subject"))
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao criar compromisso: {type(exc).__name__}") from exc


@app.post("/google/questionnaire/complete")
async def google_questionnaire_complete(request: GoogleDraftRequest) -> dict:
    try:
        result = await asyncio.to_thread(mark_questionnaire_complete, GOOGLE_INBOX, request.message_id)
        event("GOOGLE_QUESTIONNAIRE_MARKED_COMPLETE", subject=result.get("subject"))
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/ai/advice")
async def get_ai_advice(request: AIAdviceRequest) -> dict[str, object]:
    profile = ProfessionalProfile.model_validate(load_json(PROFILE_DATA, {}))
    try:
        decision = await local_ai_advice(request, profile)
        event("LOCAL_AI_DECISION", action=decision.get("action"), confidence=decision.get("confidence"))
        return decision
    except (URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=f"IA local indisponível: {type(exc).__name__}") from exc


@app.get("/jobs")
async def get_jobs() -> list[dict]:
    if not RESULTS.exists():
        return []
    return json.loads(RESULTS.read_text(encoding="utf-8"))


@app.get("/profile")
async def get_profile() -> dict:
    return ProfessionalProfile.model_validate(load_json(PROFILE_DATA, {})).model_dump()


@app.get("/settings")
async def get_settings() -> dict:
    return AutomationSettings.model_validate(load_json(SETTINGS_DATA, {})).model_dump()


@app.put("/settings")
async def put_settings(settings: AutomationSettings) -> dict:
    save_json(SETTINGS_DATA, settings.model_dump())
    event("AUTOMATION_SETTINGS_UPDATED", auto_apply_enabled=settings.auto_apply_enabled)
    return settings.model_dump()


@app.put("/profile")
async def put_profile(profile: ProfessionalProfile) -> dict:
    save_json(PROFILE_DATA, profile.model_dump())
    event("PROFILE_UPDATED")
    return profile.model_dump()


@app.post("/profile/resume")
async def upload_resume(file: UploadFile = File(...)) -> dict[str, str]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise HTTPException(status_code=400, detail="Envie um arquivo PDF ou DOCX.")
    RESUMES.mkdir(parents=True, exist_ok=True)
    target = RESUMES / f"resume-{uuid.uuid4().hex}{suffix}"
    with target.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)
    if target.stat().st_size > 10 * 1024 * 1024:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Currículo maior que 10 MB.")
    profile = ProfessionalProfile.model_validate(load_json(PROFILE_DATA, {}))
    profile.resume_path = str(target)
    save_json(PROFILE_DATA, profile.model_dump())
    event("RESUME_IMPORTED", filename=target.name)
    return {"resume_path": str(target), "filename": file.filename or target.name}


@app.post("/bootstrap")
async def bootstrap_from_resume(request: BootstrapRequest) -> dict:
    source = Path(request.resume_path).resolve()
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=404, detail="Currículo não encontrado.")
    if source.stat().st_size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Currículo maior que 10 MB.")
    RESUMES.mkdir(parents=True, exist_ok=True)
    target = RESUMES / f"resume-current{source.suffix.lower()}"
    shutil.copy2(source, target)
    profile = extract_resume_profile(target)
    profile.resume_path = str(target)
    save_json(PROFILE_DATA, profile.model_dump())
    settings = AutomationSettings(
        auto_apply_enabled=True,
        minimum_score=75,
        daily_target=20,
        require_complete_profile=True,
    )
    save_json(SETTINGS_DATA, settings.model_dump())
    event("SYSTEM_BOOTSTRAPPED_FROM_RESUME", skills=len(profile.skills))
    return {"profile": profile.model_dump(), "settings": settings.model_dump()}


@app.post("/analyze")
async def analyze_jobs(request: AnalyzeRequest) -> dict[str, int]:
    return await analyze_all_jobs(request.minimum_score)


@app.get("/applications")
async def get_applications() -> list[dict]:
    return load_json(APPLICATIONS, [])


@app.post("/applications/prepare")
async def prepare_applications(request: PrepareRequest) -> dict[str, bool]:
    global run_task
    if run_task and not run_task.done():
        raise HTTPException(status_code=409, detail="Já existe uma execução em andamento.")
    run_task = asyncio.create_task(inspect_application_queue(request))
    return {"accepted": True}


@app.post("/applications/execute")
async def execute_applications(request: ExecuteRequest) -> dict[str, bool]:
    global run_task
    if run_task and not run_task.done():
        raise HTTPException(status_code=409, detail="Já existe uma execução em andamento.")
    run_task = asyncio.create_task(execute_application_queue(request))
    return {"accepted": True}


@app.post("/play")
async def play_daily_pipeline() -> dict[str, bool]:
    global run_task
    if run_task and not run_task.done():
        raise HTTPException(status_code=409, detail="Já existe uma execução em andamento.")
    run_task = asyncio.create_task(full_daily_pipeline())
    return {"accepted": True}


@app.post("/browser/start")
async def browser_start() -> dict[str, object]:
    await ensure_browser()
    return state


@app.post("/browser/login")
async def browser_login() -> dict[str, object]:
    browser = await ensure_browser()
    for name, url in PLATFORMS.items():
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        event("LOGIN_PAGE_OPENED", platform=name)
    update(status="login_required", message="Faça login nas quatro abas e volte ao painel.")
    return state


@app.post("/browser/manual-login")
async def browser_manual_login() -> dict[str, object]:
    """Release Playwright and open the same profile in ordinary Chrome for OAuth login."""
    global playwright, context
    if run_task and not run_task.done():
        raise HTTPException(status_code=409, detail="Interrompa a busca antes do login manual.")
    if context:
        await context.close()
        context = None
    if playwright:
        await playwright.stop()
        playwright = None
    chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    if not chrome.exists():
        chrome = Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe")
    if not chrome.exists():
        raise HTTPException(status_code=500, detail="Google Chrome não encontrado.")
    command = [str(chrome), f"--user-data-dir={PROFILE}", *PLATFORMS.values()]
    subprocess.Popen(command, close_fds=True)
    update(status="manual_login", message="Chrome normal aberto. Entre pelo Google e feche a janela antes de retomar a automação.")
    event("MANUAL_LOGIN_BROWSER_STARTED")
    return state


@app.post("/run")
async def start_run(request: RunRequest) -> dict[str, object]:
    global run_task
    if run_task and not run_task.done():
        raise HTTPException(status_code=409, detail="Já existe uma busca em andamento.")
    run_task = asyncio.create_task(automation_run(request))
    return {"accepted": True}


@app.post("/stop")
async def stop_run() -> dict[str, object]:
    global run_task
    if run_task and not run_task.done():
        run_task.cancel()
        try:
            await run_task
        except asyncio.CancelledError:
            pass
    run_task = None
    update(status="stopped", message="Parada solicitada pelo usuário.")
    return state
