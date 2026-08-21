from typing import Any, Literal
from uuid import UUID
from pathlib import Path
from datetime import datetime
import hashlib
import json
import os
import urllib.request

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text

from .database import SessionLocal
from .auth import require_admin
from .quality import job_fingerprint, normalize, score_job, transition_allowed
from .preparation import application_strategy, idempotency_key, prepare_email_draft, route_resume
from .communications import correlate_message, notification_priority

router = APIRouter(prefix="/api/v1", tags=["career"])


class CareerRuleInput(BaseModel):
    code: str = Field(min_length=2, max_length=100, pattern=r"^[A-Z0-9_]+$")
    label: str = Field(min_length=3, max_length=200)
    rule_type: Literal["BONUS", "PENALTY", "BLOCK", "REVIEW", "THRESHOLD"]
    configuration: dict[str, Any]
    priority: int = Field(default=100, ge=1, le=1000)
    enabled: bool = True


class DecisionInput(BaseModel):
    decision: Literal["APPROVED", "DISCARDED"]


class ProfileInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=254)
    phone: str = Field(default="", max_length=40)
    city: str = Field(default="", max_length=100)
    state: str = Field(default="", max_length=80)
    linkedin_url: str = Field(default="", max_length=500)
    salary_expectation: str = Field(default="", max_length=120)
    work_models: list[str] = []
    target_roles: list[str] = []
    skills: list[str] = []
    approved_answers: dict[str, str] = {}


class JobInput(BaseModel):
    source: str = Field(min_length=2, max_length=80)
    external_id: str | None = Field(default=None, max_length=255)
    source_url: str = Field(min_length=8, max_length=1000)
    canonical_url: str | None = Field(default=None, max_length=1000)
    company: str = Field(min_length=2, max_length=200)
    title: str = Field(min_length=2, max_length=240)
    description: str = ""
    family: str | None = Field(default=None, max_length=60)
    location: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, max_length=80)
    employment_type: str | None = Field(default=None, max_length=40)
    work_model: str | None = Field(default=None, max_length=30)
    seniority: str | None = Field(default=None, max_length=40)
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, max_length=3)
    salary_period: str | None = Field(default=None, max_length=20)
    language_requirements: list[dict[str, Any]] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    application_channel: str | None = Field(default=None, max_length=40)
    recruiter_name: str | None = Field(default=None, max_length=200)
    recruiter_email: str | None = Field(default=None, max_length=254)


class TransitionInput(BaseModel):
    status: str = Field(min_length=3, max_length=40)
    actor: str = Field(default="SYSTEM", min_length=2, max_length=120)
    automation_mode: Literal["AUTO", "ASSISTED", "MANUAL"] = "ASSISTED"
    reason: str = Field(default="", max_length=2000)
    evidence: dict[str, Any] = Field(default_factory=dict)


class CommunicationInput(BaseModel):
    provider_message_id: str = Field(min_length=1, max_length=255)
    thread_id: str | None = Field(default=None, max_length=255)
    sender: str = Field(min_length=3, max_length=500)
    subject: str = Field(min_length=1, max_length=500)
    category: str = Field(min_length=2, max_length=40, pattern=r"^[A-Z][A-Z_]+$")
    confidence: int = Field(ge=0, le=100)
    received_at: datetime


class CommunicationBatch(BaseModel):
    provider: Literal["GMAIL"] = "GMAIL"
    items: list[CommunicationInput] = Field(max_length=500)


class InterventionInput(BaseModel):
    application_id: UUID | None = None
    executor_id: str = Field(min_length=2, max_length=100)
    reason: Literal["CAPTCHA", "MFA", "LOGIN", "UNKNOWN_FIELD", "SUBMISSION_UNCONFIRMED", "LAYOUT_CHANGED"]
    title: str = Field(min_length=3, max_length=240)
    instructions: str = Field(min_length=3, max_length=2000)
    page_url: str | None = Field(default=None, max_length=1000)
    evidence: dict[str, Any] = Field(default_factory=dict)


class InterventionResolution(BaseModel):
    resolution: Literal["RESOLVED", "SKIPPED", "CANCELLED"]


class SourceConnectionInput(BaseModel):
    adapter: Literal["GREENHOUSE", "LEVER", "ASHBY"]
    account_key: str = Field(min_length=2, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    company_name: str = Field(min_length=2, max_length=200)
    enabled: bool = False
    maximum_jobs: int = Field(default=200, ge=1, le=500)
    cadence_minutes: int = Field(default=360, ge=30, le=1440)


class DiscoveryRunInput(BaseModel):
    run_id: UUID | None = None
    status: Literal["RUNNING", "COMPLETED", "FAILED"]
    found_count: int = Field(default=0, ge=0)
    created_count: int = Field(default=0, ge=0)
    deduplicated_count: int = Field(default=0, ge=0)
    error_message: str | None = Field(default=None, max_length=2000)


class ApprovedAnswerInput(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    category: Literal["salary", "availability", "remote_work", "implementation", "requirements",
                      "stakeholders", "database", "cloud", "support", "data", "languages",
                      "management", "travel", "on_call"]
    approved_answer: str | None = Field(default=None, max_length=4000)
    language: str = Field(default="pt-BR", min_length=2, max_length=10)
    verified: bool = False


async def organization_id(slug: str) -> UUID:
    async with SessionLocal() as session:
        value = await session.scalar(
            text("SELECT id FROM organizations WHERE slug = :slug AND deleted_at IS NULL"),
            {"slug": slug},
        )
    if not value:
        raise HTTPException(status_code=404, detail="Organização não encontrada.")
    return value


@router.get("/sources")
async def list_sources(enabled: bool | None = None, slug: str = Depends(require_admin)) -> list[dict[str, Any]]:
    org_id = await organization_id(slug)
    condition = "AND enabled=:enabled" if enabled is not None else ""
    query = text(f"""
        SELECT id, adapter, account_key, company_name, enabled, maximum_jobs, cadence_minutes,
               last_started_at, last_completed_at, last_error
        FROM source_connections
        WHERE organization_id=:organization_id {condition}
        ORDER BY company_name, adapter
    """)
    parameters = {"organization_id": org_id, "enabled": enabled}
    async with SessionLocal() as session:
        rows = (await session.execute(query, parameters)).mappings()
    return [dict(row) for row in rows]


@router.post("/sources")
async def save_source(payload: SourceConnectionInput, slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    values = {**payload.model_dump(), "organization_id": org_id}
    query = text("""
        INSERT INTO source_connections
          (id, organization_id, adapter, account_key, company_name, enabled, maximum_jobs, cadence_minutes)
        VALUES (gen_random_uuid(), :organization_id, :adapter, :account_key, :company_name,
                :enabled, :maximum_jobs, :cadence_minutes)
        ON CONFLICT (organization_id, adapter, account_key) DO UPDATE SET
          company_name=EXCLUDED.company_name, enabled=EXCLUDED.enabled,
          maximum_jobs=EXCLUDED.maximum_jobs, cadence_minutes=EXCLUDED.cadence_minutes,
          updated_at=now()
        RETURNING id, adapter, account_key, company_name, enabled, maximum_jobs, cadence_minutes
    """)
    async with SessionLocal() as session:
        row = (await session.execute(query, values)).mappings().one()
        await session.commit()
    return dict(row)


@router.post("/sources/{connection_id}/runs")
async def report_discovery_run(connection_id: UUID, payload: DiscoveryRunInput,
                               slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        exists = await session.scalar(text("""
            SELECT id FROM source_connections
            WHERE id=:id AND organization_id=:organization_id
        """), {"id": connection_id, "organization_id": org_id})
        if not exists:
            raise HTTPException(status_code=404, detail="Fonte não encontrada.")
        if payload.status == "RUNNING":
            run_id = await session.scalar(text("""
                INSERT INTO discovery_runs (id, organization_id, source_connection_id, status)
                VALUES (gen_random_uuid(), :organization_id, :connection_id, 'RUNNING') RETURNING id
            """), {"organization_id": org_id, "connection_id": connection_id})
            await session.execute(text("""
                UPDATE source_connections SET last_started_at=now(), last_error=NULL, updated_at=now()
                WHERE id=:connection_id
            """), {"connection_id": connection_id})
        else:
            if not payload.run_id:
                raise HTTPException(status_code=422, detail="run_id é obrigatório para finalizar.")
            run_id = payload.run_id
            updated = await session.execute(text("""
                UPDATE discovery_runs SET status=:status, found_count=:found_count,
                  created_count=:created_count, deduplicated_count=:deduplicated_count,
                  error_message=:error_message, completed_at=now()
                WHERE id=:run_id AND source_connection_id=:connection_id
            """), {**payload.model_dump(), "connection_id": connection_id})
            if updated.rowcount != 1:
                raise HTTPException(status_code=404, detail="Execução não encontrada.")
            await session.execute(text("""
                UPDATE source_connections SET last_completed_at=now(), last_error=:error_message,
                  updated_at=now() WHERE id=:connection_id
            """), {"connection_id": connection_id, "error_message": payload.error_message})
        await session.commit()
    return {"run_id": run_id, "status": payload.status}


@router.get("/answers")
async def list_answers(slug: str = Depends(require_admin)) -> list[dict[str, Any]]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        rows = (await session.execute(text("""
            SELECT id, normalized_question, category, approved_answer, language, verified,
                   usage_count, last_reviewed_at
            FROM application_questions WHERE organization_id=:organization_id
            ORDER BY category, normalized_question
        """), {"organization_id": org_id})).mappings()
    return [dict(row) for row in rows]


@router.put("/answers")
async def save_answer(payload: ApprovedAnswerInput, slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    if payload.verified and not payload.approved_answer:
        raise HTTPException(status_code=422, detail="Resposta verificada não pode ficar vazia.")
    values = {**payload.model_dump(), "organization_id": org_id,
              "normalized_question": normalize(payload.question)}
    async with SessionLocal() as session:
        row = (await session.execute(text("""
            INSERT INTO application_questions
              (id, organization_id, normalized_question, category, approved_answer, language,
               verified, last_reviewed_at)
            VALUES (gen_random_uuid(), :organization_id, :normalized_question, :category,
                    :approved_answer, :language, :verified,
                    CASE WHEN :verified THEN now() ELSE NULL END)
            ON CONFLICT (organization_id, normalized_question, language) DO UPDATE SET
              category=EXCLUDED.category, approved_answer=EXCLUDED.approved_answer,
              verified=EXCLUDED.verified,
              last_reviewed_at=CASE WHEN EXCLUDED.verified THEN now() ELSE application_questions.last_reviewed_at END,
              updated_at=now()
            RETURNING id, normalized_question, category, approved_answer, language, verified,
                      usage_count, last_reviewed_at
        """), values)).mappings().one()
        await session.commit()
    return dict(row)


@router.get("/answers/match")
async def match_answer(question: str = Query(min_length=3, max_length=500), language: str = "pt-BR",
                       slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        row = (await session.execute(text("""
            UPDATE application_questions SET usage_count=usage_count+1, updated_at=now()
            WHERE organization_id=:organization_id AND normalized_question=:question
              AND language=:language AND verified=true AND approved_answer IS NOT NULL
            RETURNING id, category, approved_answer, language, verified, usage_count
        """), {"organization_id": org_id, "question": normalize(question),
                "language": language})).mappings().first()
        if row:
            await session.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Resposta aprovada não encontrada; revisão humana necessária.")
    return dict(row)


@router.post("/jobs/{job_id}/prepare")
async def prepare_application(job_id: UUID, slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        job = (await session.execute(text("""
            SELECT j.*, c.name AS company, s.total AS score, s.decision
            FROM jobs j JOIN companies c ON c.id=j.company_id
            LEFT JOIN LATERAL (
              SELECT total, decision FROM job_scores WHERE job_id=j.id ORDER BY created_at DESC LIMIT 1
            ) s ON true
            WHERE j.id=:job_id AND j.organization_id=:organization_id AND j.deleted_at IS NULL
        """), {"job_id": job_id, "organization_id": org_id})).mappings().first()
        if not job:
            raise HTTPException(status_code=404, detail="Vaga não encontrada.")
        if job["validation_status"] != "OPEN" or not job["score"] or job["score"] < 75 or job["decision"] in {"BLOCK", "DISCARD"}:
            raise HTTPException(status_code=409, detail="Vaga não está qualificada para preparação.")
        resumes = list((await session.execute(text("""
            SELECT rv.id, rv.version, rv.sha256, rv.storage_key, rv.approved_at,
                   r.family, r.language, r.active
            FROM resume_versions rv JOIN resumes r ON r.id=rv.resume_id
            WHERE rv.organization_id=:organization_id AND r.deleted_at IS NULL
        """), {"organization_id": org_id})).mappings())
        selected = route_resume(dict(job), [dict(item) for item in resumes])
        if not selected:
            raise HTTPException(status_code=409, detail="Nenhum currículo aprovado e ativo disponível.")
        strategy = application_strategy(dict(job))
        key = idempotency_key(str(org_id), str(job_id))
        existing = (await session.execute(text("""
            SELECT a.id, a.status, a.strategy, a.resume_version_id, a.resume_hash,
                   d.id AS draft_id, d.recipient, d.subject, d.body, d.status AS draft_status
            FROM applications a LEFT JOIN application_drafts d ON d.application_id=a.id
            WHERE a.organization_id=:organization_id AND a.job_id=:job_id
        """), {"organization_id": org_id, "job_id": job_id})).mappings().first()
        if existing:
            draft = None if not existing["draft_id"] else {
                "id": existing["draft_id"], "recipient": existing["recipient"],
                "subject": existing["subject"], "body": existing["body"],
                "status": existing["draft_status"],
            }
            return {"application": {key: existing[key] for key in
                    ("id", "status", "strategy", "resume_version_id", "resume_hash")},
                    "resume_family": selected["family"], "draft": draft, "sent": False,
                    "idempotent_replay": True}
        application = (await session.execute(text("""
            INSERT INTO applications
              (id, organization_id, job_id, resume_version_id, resume_hash, status, channel,
               strategy, idempotency_key, automation_mode, prepared_at)
            VALUES (gen_random_uuid(), :organization_id, :job_id, :resume_version_id, :resume_hash,
                    'PREPARING', :strategy, :strategy, :idempotency_key, 'ASSISTED', now())
            RETURNING id, status, strategy, resume_version_id, resume_hash
        """), {"organization_id": org_id, "job_id": job_id,
                "resume_version_id": selected["id"], "resume_hash": selected["sha256"],
                "strategy": strategy, "idempotency_key": key})).mappings().one()
        draft = None
        if strategy == "EMAIL":
            profile = (await session.execute(text("""
                SELECT u.full_name FROM users u
                WHERE u.organization_id=:organization_id AND u.status='ACTIVE' LIMIT 1
            """), {"organization_id": org_id})).mappings().first() or {}
            email = prepare_email_draft(dict(job), dict(profile))
            draft = (await session.execute(text("""
                INSERT INTO application_drafts
                  (id, organization_id, application_id, recipient, subject, body, status)
                VALUES (gen_random_uuid(), :organization_id, :application_id, :recipient,
                        :subject, :body, 'REVIEW_REQUIRED')
                ON CONFLICT (application_id) DO UPDATE SET recipient=EXCLUDED.recipient,
                  subject=EXCLUDED.subject, body=EXCLUDED.body, status='REVIEW_REQUIRED',
                  approved_at=NULL, updated_at=now()
                RETURNING id, recipient, subject, body, status
            """), {"organization_id": org_id, "application_id": application["id"],
                    "recipient": email.recipient, "subject": email.subject, "body": email.body})).mappings().one()
        await session.execute(text("""
            INSERT INTO application_events
              (id, organization_id, application_id, event_type, to_status, actor,
               automation_mode, reason, evidence)
            VALUES (gen_random_uuid(), :organization_id, :application_id, 'APPLICATION_PREPARED',
                    'PREPARING', 'SYSTEM', 'ASSISTED', 'Preparação sem envio',
                    jsonb_build_object('strategy', :strategy, 'resume_hash', :resume_hash))
        """), {"organization_id": org_id, "application_id": application["id"],
                "strategy": strategy, "resume_hash": selected["sha256"]})
        await session.commit()
    return {"application": dict(application), "resume_family": selected["family"],
            "draft": dict(draft) if draft else None, "sent": False}


@router.post("/applications/{application_id}/draft/approve")
async def approve_application_draft(application_id: UUID,
                                    slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        draft = (await session.execute(text("""
            UPDATE application_drafts SET status='APPROVED', approved_at=now(), updated_at=now()
            WHERE application_id=:application_id AND organization_id=:organization_id
              AND status='REVIEW_REQUIRED'
            RETURNING id, recipient, subject, body, status, approved_at
        """), {"application_id": application_id, "organization_id": org_id})).mappings().first()
        if not draft:
            raise HTTPException(status_code=404, detail="Rascunho pendente não encontrado.")
        await session.execute(text("""
            INSERT INTO application_events
              (id, organization_id, application_id, event_type, from_status, to_status,
               actor, automation_mode, reason, evidence)
            VALUES (gen_random_uuid(), :organization_id, :application_id, 'DRAFT_APPROVED',
                    'PREPARING', 'READY', 'USER', 'ASSISTED', 'Rascunho aprovado manualmente', '{}')
        """), {"organization_id": org_id, "application_id": application_id})
        await session.execute(text("""
            UPDATE applications SET status='READY', updated_at=now() WHERE id=:application_id
        """), {"application_id": application_id})
        await session.commit()
    return {**dict(draft), "sent": False}


@router.post("/applications/{application_id}/draft/materialize")
async def materialize_application_draft(application_id: UUID,
                                        slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        row = (await session.execute(text("""
            SELECT d.id, d.recipient, d.subject, d.body, d.status, d.provider_draft_id,
                   rv.storage_key
            FROM application_drafts d JOIN applications a ON a.id=d.application_id
            JOIN resume_versions rv ON rv.id=a.resume_version_id
            WHERE d.application_id=:application_id AND d.organization_id=:organization_id
        """), {"application_id": application_id,
                "organization_id": org_id})).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Rascunho não encontrado.")
        if row["provider_draft_id"]:
            return {"draft_id": row["provider_draft_id"], "status": "MATERIALIZED",
                    "sent": False, "idempotent_replay": True}
        if row["status"] != "APPROVED":
            raise HTTPException(status_code=409, detail="O rascunho exige aprovação humana.")
        request = urllib.request.Request(
            os.getenv("INTEGRATIONS_URL", "http://integrations:8765") + "/google/application-draft",
            data=json.dumps({"recipient": row["recipient"], "subject": row["subject"],
                             "body": row["body"], "resume_path": row["storage_key"]}).encode(),
            method="POST", headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                provider = json.loads(response.read().decode())
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Gmail não criou o rascunho.") from exc
        await session.execute(text("""
            UPDATE application_drafts SET status='MATERIALIZED', provider_draft_id=:provider_id,
              updated_at=now() WHERE id=:id
        """), {"provider_id": provider["draft_id"], "id": row["id"]})
        await session.commit()
    return {"draft_id": provider["draft_id"], "status": "MATERIALIZED", "sent": False}


@router.post("/jobs")
async def ingest_job(payload: JobInput, slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    fingerprint = job_fingerprint(payload.company, payload.title, payload.location or "", payload.description)
    values = payload.model_dump()
    values.update({"organization_id": org_id, "fingerprint": fingerprint,
                   "canonical_url": payload.canonical_url or payload.source_url,
                   "language_requirements": json.dumps(payload.language_requirements),
                   "required_skills": json.dumps(payload.required_skills),
                   "preferred_skills": json.dumps(payload.preferred_skills)})
    async with SessionLocal() as session:
        company_id = await session.scalar(text("SELECT id FROM companies WHERE organization_id=:organization_id AND lower(name)=lower(:company) AND deleted_at IS NULL LIMIT 1"), values)
        if not company_id:
            company_id = await session.scalar(text("INSERT INTO companies (id, organization_id, name) VALUES (gen_random_uuid(), :organization_id, :company) RETURNING id"), values)
        values["company_id"] = company_id
        existing = await session.scalar(text("SELECT id FROM jobs WHERE organization_id=:organization_id AND fingerprint=:fingerprint"), values)
        created = existing is None
        job_id = existing or await session.scalar(text("""
            INSERT INTO jobs (id, organization_id, company_id, external_id, source, source_url, canonical_url,
              title, description, family, location, country, employment_type, work_model, seniority,
              salary_min, salary_max, salary_currency, salary_period, language_requirements,
              required_skills, preferred_skills, application_channel, recruiter_name, recruiter_email, fingerprint)
            VALUES (gen_random_uuid(), :organization_id, :company_id, :external_id, :source, :source_url, :canonical_url,
              :title, :description, :family, :location, :country, :employment_type, :work_model, :seniority,
              :salary_min, :salary_max, :salary_currency, :salary_period, CAST(:language_requirements AS jsonb),
              CAST(:required_skills AS jsonb), CAST(:preferred_skills AS jsonb), :application_channel,
              :recruiter_name, :recruiter_email, :fingerprint) RETURNING id
        """), values)
        await session.execute(text("""
            INSERT INTO job_sources (id, organization_id, job_id, source, external_id, source_url)
            VALUES (gen_random_uuid(), :organization_id, :job_id, :source, :external_id, :source_url)
            ON CONFLICT (organization_id, source, source_url) DO UPDATE SET last_seen_at=now()
        """), {**values, "job_id": job_id})
        await session.commit()
    return {"id": job_id, "fingerprint": fingerprint, "created": created, "deduplicated": not created}


@router.get("/jobs")
async def list_jobs(limit: int = 100, slug: str = Depends(require_admin)) -> list[dict[str, Any]]:
    org_id = await organization_id(slug)
    query = text("""
        SELECT j.id, j.title, c.name AS company, j.canonical_url, j.location, j.country,
               j.work_model, j.seniority, j.validation_status AS status, j.discovered_at,
               s.total AS score, s.decision AS recommendation
        FROM jobs j JOIN companies c ON c.id=j.company_id
        LEFT JOIN LATERAL (SELECT total, decision FROM job_scores WHERE job_id=j.id ORDER BY created_at DESC LIMIT 1) s ON true
        WHERE j.organization_id=:organization_id AND j.deleted_at IS NULL
        ORDER BY j.discovered_at DESC LIMIT :limit
    """)
    async with SessionLocal() as session:
        rows = (await session.execute(query, {"organization_id": org_id, "limit": min(max(limit, 1), 500)})).mappings()
    return [dict(row) for row in rows]


@router.post("/jobs/{job_id}/score")
async def calculate_job_score(job_id: UUID, slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        job = (await session.execute(text("SELECT * FROM jobs WHERE id=:id AND organization_id=:organization_id AND deleted_at IS NULL"), {"id": job_id, "organization_id": org_id})).mappings().first()
        if not job:
            raise HTTPException(status_code=404, detail="Vaga não encontrada.")
        profile = (await session.execute(text("SELECT city, work_models, target_roles, salary_expectation FROM candidate_profiles WHERE organization_id=:organization_id AND deleted_at IS NULL LIMIT 1"), {"organization_id": org_id})).mappings().first() or {}
        verified = list((await session.scalars(text("SELECT name FROM skills WHERE organization_id=:organization_id AND verified=true AND deleted_at IS NULL"), {"organization_id": org_id})).all())
        codes = set((await session.scalars(text("SELECT code FROM career_rules WHERE organization_id=:organization_id AND enabled=true AND deleted_at IS NULL"), {"organization_id": org_id})).all())
        profile_data = dict(profile)
        profile_data["verified_skills"] = verified
        salary_text = str(profile_data.get("salary_expectation") or "")
        salary_number = "".join(character for character in salary_text if character.isdigit() or character in ".,")
        try:
            profile_data["salary_expectation_numeric"] = float(salary_number.replace(".", "").replace(",", "."))
        except ValueError:
            profile_data["salary_expectation_numeric"] = 0
        result = score_job(dict(job), profile_data, codes)
        await session.execute(text("""
            INSERT INTO job_scores (id, organization_id, job_id, total, decision, dimensions, reasons, gaps, model_version)
            VALUES (gen_random_uuid(), :organization_id, :job_id, :total, :decision, CAST(:dimensions AS jsonb), CAST(:reasons AS jsonb), CAST(:gaps AS jsonb), 'V2.0')
            ON CONFLICT (job_id, model_version) DO UPDATE SET total=EXCLUDED.total, decision=EXCLUDED.decision,
              dimensions=EXCLUDED.dimensions, reasons=EXCLUDED.reasons, gaps=EXCLUDED.gaps, updated_at=now()
        """), {"organization_id": org_id, "job_id": job_id, "total": result.total, "decision": result.recommendation,
               "dimensions": json.dumps(result.dimensions), "reasons": json.dumps(result.strengths + result.risks + result.blocking_rules), "gaps": json.dumps(result.gaps)})
        new_status = "BLOCKED" if result.blocking_rules else "OPEN"
        await session.execute(text("UPDATE jobs SET validation_status=:status, validated_at=now(), updated_at=now() WHERE id=:id"), {"status": new_status, "id": job_id})
        if result.recommendation == "REVIEW":
            await session.execute(text("""
                INSERT INTO decision_inbox (id, organization_id, job_id, recommendation, status, summary)
                VALUES (gen_random_uuid(), :organization_id, :job_id, 'REVIEW', 'PENDING', CAST(:summary AS jsonb))
                ON CONFLICT (organization_id, job_id) DO UPDATE SET recommendation='REVIEW', status='PENDING', summary=EXCLUDED.summary, updated_at=now()
            """), {"organization_id": org_id, "job_id": job_id, "summary": json.dumps(result.as_dict())})
        await session.commit()
    return result.as_dict()


@router.post("/applications/{application_id}/transition")
async def transition_application(application_id: UUID, payload: TransitionInput, slug: str = Depends(require_admin)) -> dict[str, str]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        current = await session.scalar(text("SELECT status FROM applications WHERE id=:id AND organization_id=:organization_id"), {"id": application_id, "organization_id": org_id})
        if not current:
            raise HTTPException(status_code=404, detail="Candidatura não encontrada.")
        if not transition_allowed(current, payload.status):
            raise HTTPException(status_code=409, detail=f"Transição inválida: {current} → {payload.status}.")
        await session.execute(text("UPDATE applications SET status=:status, automation_mode=:mode, updated_at=now() WHERE id=:id"), {"status": payload.status, "mode": payload.automation_mode, "id": application_id})
        await session.execute(text("""
            INSERT INTO application_events (id, organization_id, application_id, event_type, from_status, to_status, actor, automation_mode, reason, evidence)
            VALUES (gen_random_uuid(), :organization_id, :application_id, 'PIPELINE_CHANGED', :from_status, :to_status, :actor, :mode, :reason, CAST(:evidence AS jsonb))
        """), {"organization_id": org_id, "application_id": application_id, "from_status": current, "to_status": payload.status,
               "actor": payload.actor, "mode": payload.automation_mode, "reason": payload.reason, "evidence": json.dumps(payload.evidence)})
        await session.commit()
    return {"from": current, "to": payload.status}


@router.get("/profile")
async def get_profile(slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    query = text("""
        SELECT u.full_name, u.email, COALESCE(u.phone, '') AS phone,
               COALESCE(p.city, '') AS city, COALESCE(p.state, '') AS state,
               COALESCE(p.linkedin_url, '') AS linkedin_url,
               COALESCE(p.salary_expectation, '') AS salary_expectation,
               COALESCE(p.work_models, '[]'::jsonb) AS work_models,
               COALESCE(p.target_roles, '[]'::jsonb) AS target_roles,
               COALESCE(p.approved_answers, '{}'::jsonb) AS approved_answers,
               COALESCE((SELECT jsonb_agg(s.name ORDER BY s.name) FROM skills s
                         WHERE s.organization_id = :organization_id AND s.deleted_at IS NULL), '[]'::jsonb) AS skills,
               rv.storage_key AS resume_path, r.name AS resume_name
        FROM users u
        LEFT JOIN candidate_profiles p ON p.user_id = u.id AND p.deleted_at IS NULL
        LEFT JOIN LATERAL (
            SELECT rv.storage_key, rv.resume_id FROM resume_versions rv
            WHERE rv.organization_id = :organization_id ORDER BY rv.created_at DESC LIMIT 1
        ) rv ON true
        LEFT JOIN resumes r ON r.id = rv.resume_id
        WHERE u.organization_id = :organization_id AND u.role = 'OWNER' AND u.deleted_at IS NULL
        ORDER BY u.created_at LIMIT 1
    """)
    async with SessionLocal() as session:
        row = (await session.execute(query, {"organization_id": org_id})).mappings().first()
    if not row:
        return {"full_name": "", "email": "", "phone": "", "city": "", "state": "", "linkedin_url": "", "salary_expectation": "", "work_models": [], "target_roles": [], "skills": [], "approved_answers": {}, "resume_path": "", "resume_name": ""}
    return dict(row)


@router.put("/profile")
async def save_profile(payload: ProfileInput, slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        user_id = await session.scalar(text("""
            INSERT INTO users (id, organization_id, email, full_name, phone, role, status)
            VALUES (gen_random_uuid(), :organization_id, :email, :full_name, :phone, 'OWNER', 'ACTIVE')
            ON CONFLICT (organization_id, email) DO UPDATE
            SET full_name = EXCLUDED.full_name, phone = EXCLUDED.phone, updated_at = now()
            RETURNING id
        """), {"organization_id": org_id, "email": payload.email, "full_name": payload.full_name, "phone": payload.phone})
        await session.execute(text("""
            INSERT INTO candidate_profiles
                (id, organization_id, user_id, city, state, linkedin_url, salary_expectation,
                 work_models, target_roles, approved_answers)
            VALUES (gen_random_uuid(), :organization_id, :user_id, :city, :state, :linkedin_url,
                    :salary_expectation, CAST(:work_models AS jsonb), CAST(:target_roles AS jsonb),
                    CAST(:approved_answers AS jsonb))
            ON CONFLICT (organization_id, user_id) DO UPDATE SET
                city = EXCLUDED.city, state = EXCLUDED.state, linkedin_url = EXCLUDED.linkedin_url,
                salary_expectation = EXCLUDED.salary_expectation, work_models = EXCLUDED.work_models,
                target_roles = EXCLUDED.target_roles, approved_answers = EXCLUDED.approved_answers,
                updated_at = now(), deleted_at = NULL
        """), {"organization_id": org_id, "user_id": user_id, "city": payload.city, "state": payload.state,
               "linkedin_url": payload.linkedin_url, "salary_expectation": payload.salary_expectation,
               "work_models": json.dumps(payload.work_models), "target_roles": json.dumps(payload.target_roles),
               "approved_answers": json.dumps(payload.approved_answers)})
        for skill in {item.strip() for item in payload.skills if item.strip()}:
            await session.execute(text("""
                INSERT INTO skills (id, organization_id, name, level, verified)
                VALUES (gen_random_uuid(), :organization_id, :name, 'INFORMED', false)
                ON CONFLICT (organization_id, name) DO UPDATE SET deleted_at = NULL, updated_at = now()
            """), {"organization_id": org_id, "name": skill})
        await session.commit()
    return await get_profile(slug)


@router.post("/profile/resume")
async def upload_resume(
    file: UploadFile = File(...),
    family: Literal["GENERAL", "PT_SUPPORT_SENIOR", "PT_DBA_SQL", "PT_DATA",
                    "EN_SUPPORT_DATABASE", "EN_DATA_DATABASE", "EN_DATA_ENGINEERING"] = "GENERAL",
    language: Literal["pt-BR", "en"] = "pt-BR",
    slug: str = Depends(require_admin),
) -> dict[str, str]:
    org_id = await organization_id(slug)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise HTTPException(status_code=400, detail="Use um arquivo PDF ou DOCX.")
    content = await file.read(10 * 1024 * 1024 + 1)
    if not content or len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="O currículo deve ter até 10 MB.")
    digest = hashlib.sha256(content).hexdigest()
    storage_dir = Path(os.getenv("RESUME_STORAGE_DIR", "/tmp/careeros-resumes"))
    storage_dir.mkdir(parents=True, exist_ok=True)
    target = storage_dir / f"{org_id}-{digest[:16]}{suffix}"
    target.write_bytes(content)
    async with SessionLocal() as session:
        resume_id = await session.scalar(text("""
            INSERT INTO resumes (id, organization_id, code, name, family, language, active)
            VALUES (gen_random_uuid(), :organization_id, :family, :name, :family, :language, true)
            ON CONFLICT (organization_id, code) DO UPDATE SET name = EXCLUDED.name,
              family=EXCLUDED.family, language=EXCLUDED.language, active=true, updated_at=now()
            RETURNING id
        """), {"organization_id": org_id, "name": file.filename or f"curriculo{suffix}",
                "family": family, "language": language})
        version = (await session.scalar(text("SELECT COALESCE(max(version), 0) + 1 FROM resume_versions WHERE resume_id = :resume_id"), {"resume_id": resume_id})) or 1
        await session.execute(text("""
            INSERT INTO resume_versions (id, organization_id, resume_id, version, storage_key, sha256, approved_at)
            VALUES (gen_random_uuid(), :organization_id, :resume_id, :version, :storage_key, :sha256, now())
        """), {"organization_id": org_id, "resume_id": resume_id, "version": version, "storage_key": str(target), "sha256": digest})
        await session.commit()
    return {"resume_path": str(target), "resume_name": file.filename or target.name,
            "family": family, "language": language}


@router.get("/career-rules")
async def list_rules(slug: str = Depends(require_admin)) -> list[dict[str, Any]]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, code, label, rule_type, configuration, priority, enabled
                    FROM career_rules
                    WHERE organization_id = :organization_id AND deleted_at IS NULL
                    ORDER BY priority, code
                    """
                ),
                {"organization_id": org_id},
            )
        ).mappings()
    return [dict(row) for row in rows]


@router.put("/career-rules/{code}")
async def save_rule(
    code: str,
    payload: CareerRuleInput,
    slug: str = Depends(require_admin),
) -> dict[str, Any]:
    if code != payload.code:
        raise HTTPException(status_code=400, detail="O código da rota deve ser igual ao payload.")
    org_id = await organization_id(slug)
    query = text(
        """
        INSERT INTO career_rules
            (id, organization_id, code, label, rule_type, configuration, priority, enabled)
        VALUES
            (gen_random_uuid(), :organization_id, :code, :label, :rule_type,
             CAST(:configuration AS jsonb), :priority, :enabled)
        ON CONFLICT (organization_id, code)
        DO UPDATE SET label = EXCLUDED.label,
                      rule_type = EXCLUDED.rule_type,
                      configuration = EXCLUDED.configuration,
                      priority = EXCLUDED.priority,
                      enabled = EXCLUDED.enabled,
                      updated_at = now(),
                      deleted_at = NULL
        RETURNING id, code, label, rule_type, configuration, priority, enabled
        """
    )
    import json

    values = payload.model_dump()
    values["organization_id"] = org_id
    values["configuration"] = json.dumps(payload.configuration)
    async with SessionLocal() as session:
        row = (await session.execute(query, values)).mappings().one()
        await session.commit()
    return dict(row)


@router.get("/decisions")
async def list_decisions(
    status: str = "PENDING",
    slug: str = Depends(require_admin),
) -> list[dict[str, Any]]:
    org_id = await organization_id(slug)
    query = text(
        """
        SELECT d.id, d.recommendation, d.status, d.summary, d.expires_at,
               j.title, j.location, j.work_model, j.source_url,
               c.name AS company,
               s.total AS fit
        FROM decision_inbox d
        JOIN jobs j ON j.id = d.job_id
        LEFT JOIN companies c ON c.id = j.company_id
        LEFT JOIN LATERAL (
            SELECT total FROM job_scores
            WHERE job_id = j.id
            ORDER BY created_at DESC LIMIT 1
        ) s ON true
        WHERE d.organization_id = :organization_id AND d.status = :status
        ORDER BY s.total DESC NULLS LAST, d.created_at DESC
        """
    )
    async with SessionLocal() as session:
        rows = (await session.execute(query, {"organization_id": org_id, "status": status})).mappings()
    return [dict(row) for row in rows]


@router.post("/decisions/{decision_id}")
async def decide(
    decision_id: UUID,
    payload: DecisionInput,
    slug: str = Depends(require_admin),
) -> dict[str, str]:
    org_id = await organization_id(slug)
    query = text(
        """
        UPDATE decision_inbox
        SET status = :status, decided_at = now(), updated_at = now()
        WHERE id = :id AND organization_id = :organization_id AND status = 'PENDING'
        RETURNING id
        """
    )
    async with SessionLocal() as session:
        changed = await session.scalar(
            query,
            {"id": decision_id, "organization_id": org_id, "status": payload.decision},
        )
        await session.commit()
    if not changed:
        raise HTTPException(status_code=404, detail="Decisão pendente não encontrada.")
    return {"status": payload.decision}


@router.post("/communications/sync")
async def sync_communications(batch: CommunicationBatch, slug: str = Depends(require_admin)) -> dict[str, int]:
    org_id = await organization_id(slug)
    matched = unmatched = notifications = 0
    async with SessionLocal() as session:
        rows = (await session.execute(text("""
            SELECT a.id, j.title, c.name AS company, c.domain AS company_domain
            FROM applications a JOIN jobs j ON j.id=a.job_id
            LEFT JOIN companies c ON c.id=j.company_id
            WHERE a.organization_id=:organization_id AND a.deleted_at IS NULL
              AND a.status NOT IN ('CLOSED', 'WITHDRAWN')
        """), {"organization_id": org_id})).mappings()
        candidates = [dict(item) for item in rows]
        for item_model in batch.items:
            item = item_model.model_dump()
            application_id, evidence = correlate_message(item, candidates)
            correlation_status = "MATCHED" if application_id else "REVIEW" if evidence == ["ambiguous"] else "UNMATCHED"
            matched += int(bool(application_id))
            unmatched += int(not application_id)
            await session.execute(text("""
                INSERT INTO recruitment_communications
                  (id, organization_id, application_id, provider, provider_message_id,
                   thread_id, sender, subject, category, confidence, received_at,
                   correlation_status, evidence)
                VALUES (gen_random_uuid(), :organization_id, :application_id, :provider,
                        :provider_message_id, :thread_id, :sender, :subject, :category,
                        :confidence, :received_at, :correlation_status,
                        CAST(:evidence AS jsonb))
                ON CONFLICT (organization_id, provider, provider_message_id) DO UPDATE SET
                  application_id=EXCLUDED.application_id, category=EXCLUDED.category,
                  confidence=EXCLUDED.confidence, correlation_status=EXCLUDED.correlation_status,
                  evidence=EXCLUDED.evidence, updated_at=now()
            """), {**item, "organization_id": org_id, "application_id": application_id,
                    "provider": batch.provider, "correlation_status": correlation_status,
                    "evidence": json.dumps({"signals": evidence})})
            if item["category"] != "OTHER":
                result = await session.execute(text("""
                    INSERT INTO career_notifications
                      (id, organization_id, application_id, kind, title, body, priority, deduplication_key)
                    VALUES (gen_random_uuid(), :organization_id, :application_id, :kind,
                            :title, :body, :priority, :deduplication_key)
                    ON CONFLICT (organization_id, deduplication_key) DO NOTHING RETURNING id
                """), {"organization_id": org_id, "application_id": application_id,
                        "kind": item["category"], "title": f"Atualização: {item['category'].title()}",
                        "body": "Há uma nova comunicação de recrutamento para revisar no portal.",
                        "priority": notification_priority(item["category"]),
                        "deduplication_key": f"gmail:{item['provider_message_id']}"})
                notifications += int(result.first() is not None)
        await session.commit()
    return {"processed": len(batch.items), "matched": matched, "unmatched": unmatched, "notifications": notifications}


@router.get("/notifications")
async def list_notifications(unread_only: bool = Query(default=False), slug: str = Depends(require_admin)) -> list[dict[str, Any]]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        rows = (await session.execute(text("""
            SELECT id, application_id, kind, title, body, priority, read_at, created_at
            FROM career_notifications WHERE organization_id=:organization_id
              AND (:unread_only=false OR read_at IS NULL)
            ORDER BY read_at NULLS FIRST, CASE priority WHEN 'URGENT' THEN 1 WHEN 'HIGH' THEN 2 ELSE 3 END,
              created_at DESC LIMIT 100
        """), {"organization_id": org_id, "unread_only": unread_only})).mappings()
    return [dict(row) for row in rows]


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: UUID, slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        row = (await session.execute(text("""
            UPDATE career_notifications SET read_at=COALESCE(read_at, now())
            WHERE id=:id AND organization_id=:organization_id RETURNING id, read_at
        """), {"id": notification_id, "organization_id": org_id})).mappings().first()
        await session.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Notificação não encontrada.")
    return dict(row)


@router.post("/followups/evaluate")
async def evaluate_followups(slug: str = Depends(require_admin)) -> dict[str, int]:
    """Creates review reminders only; it never sends a follow-up."""
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        due = list((await session.execute(text("""
            SELECT a.id, j.title FROM applications a JOIN jobs j ON j.id=a.job_id
            WHERE a.organization_id=:organization_id AND a.applied_at IS NOT NULL
              AND a.applied_at <= now() - interval '7 days'
              AND a.status NOT IN ('CLOSED', 'WITHDRAWN', 'OFFER')
              AND NOT EXISTS (SELECT 1 FROM recruitment_communications rc
                              WHERE rc.application_id=a.id AND rc.received_at >= a.applied_at)
        """), {"organization_id": org_id})).mappings())
        created = 0
        for item in due:
            result = await session.execute(text("""
                INSERT INTO career_notifications
                  (id, organization_id, application_id, kind, title, body, priority, deduplication_key)
                VALUES (gen_random_uuid(), :organization_id, :application_id, 'FOLLOWUP_DUE',
                        'Follow-up disponível para revisão', :body, 'NORMAL', :key)
                ON CONFLICT (organization_id, deduplication_key) DO NOTHING RETURNING id
            """), {"organization_id": org_id, "application_id": item["id"],
                    "body": f"A candidatura para {item['title']} está sem resposta há pelo menos 7 dias.",
                    "key": f"followup:{item['id']}:7d"})
            created += int(result.first() is not None)
        await session.commit()
    return {"eligible": len(due), "notifications": created, "sent": 0}


@router.post("/interventions")
async def create_intervention(payload: InterventionInput,
                              slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        existing = (await session.execute(text("""
            SELECT id, reason, status, title, instructions, page_url, created_at
            FROM human_interventions
            WHERE organization_id=:organization_id AND executor_id=:executor_id
              AND reason=:reason AND status='PENDING'
              AND evidence->>'deduplication_key'=:deduplication_key
            ORDER BY created_at DESC LIMIT 1
        """), {"organization_id": org_id, "executor_id": payload.executor_id,
                "reason": payload.reason,
                "deduplication_key": str(payload.evidence.get("deduplication_key", ""))})).mappings().first()
        if existing and payload.evidence.get("deduplication_key"):
            return dict(existing)
        row = (await session.execute(text("""
            INSERT INTO human_interventions
              (id, organization_id, application_id, executor_id, reason, title,
               instructions, page_url, evidence)
            VALUES (gen_random_uuid(), :organization_id, :application_id, :executor_id,
                    :reason, :title, :instructions, :page_url, CAST(:evidence AS jsonb))
            RETURNING id, reason, status, title, instructions, page_url, created_at
        """), {**payload.model_dump(exclude={"evidence"}), "organization_id": org_id,
                "evidence": json.dumps(payload.evidence)})).mappings().one()
        await session.execute(text("""
            INSERT INTO career_notifications
              (id, organization_id, application_id, kind, title, body, priority,
               deduplication_key)
            VALUES (gen_random_uuid(), :organization_id, :application_id,
                    'HUMAN_INTERVENTION', :title, :body, 'URGENT', :key)
            ON CONFLICT (organization_id, deduplication_key) DO NOTHING
        """), {"organization_id": org_id, "application_id": payload.application_id,
                "title": payload.title, "body": payload.instructions,
                "key": f"intervention:{row['id']}"})
        await session.commit()
    return dict(row)


@router.get("/interventions")
async def list_interventions(status: str = Query(default="PENDING"),
                             slug: str = Depends(require_admin)) -> list[dict[str, Any]]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        rows = (await session.execute(text("""
            SELECT id, application_id, executor_id, reason, status, title,
                   instructions, page_url, evidence, created_at, resolved_at, resolution
            FROM human_interventions
            WHERE organization_id=:organization_id AND (:status='ALL' OR status=:status)
            ORDER BY CASE status WHEN 'PENDING' THEN 1 ELSE 2 END, created_at DESC LIMIT 100
        """), {"organization_id": org_id, "status": status})).mappings()
    return [dict(row) for row in rows]


@router.post("/interventions/{intervention_id}/resolve")
async def resolve_intervention(intervention_id: UUID, payload: InterventionResolution,
                               slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        row = (await session.execute(text("""
            UPDATE human_interventions SET status=:status, resolution=:resolution,
              resolved_at=now(), updated_at=now()
            WHERE id=:id AND organization_id=:organization_id AND status='PENDING'
            RETURNING id, status, resolution, resolved_at
        """), {"id": intervention_id, "organization_id": org_id,
                "status": payload.resolution,
                "resolution": payload.resolution})).mappings().first()
        await session.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Intervenção pendente não encontrada.")
    return dict(row)
