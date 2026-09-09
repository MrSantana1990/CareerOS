from typing import Any, Literal
from uuid import UUID
from pathlib import Path
from datetime import UTC, datetime
import hashlib
import json
import os
import urllib.request

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text

from .database import SessionLocal
from .auth import require_admin
from .quality import MINIMUM_ACCEPTABLE_SALARY_BRL, job_fingerprint, match_radars, normalize, score_job, transition_allowed
from .action_engine import (assess_language_status, build_application_plan, classify_channel_trust,
                             classify_profile_completeness, evaluate_action_policy,
                             is_profile_completeness_sufficient, select_channel)
from .preparation import application_strategy, idempotency_key, prepare_email_draft, route_resume
from .communications import notification_priority
from .tracking import (aggregate_by_dimension, aggregate_gap_intelligence, calculate_conversion_funnel,
                        classify_correlation, group_interventions_by_root_cause, recommendation_confidence)
from .channel_discovery import discover_company_channel_candidates, discover_job_channel_candidates
from .profile_intelligence import extract_docx_text, extract_profile_evidence
from .market_memory import opportunity_fingerprint, signal_fingerprint, watch_fingerprint
from .opportunity_brain import (BRAIN_VERSION, BrainDecision, evaluate_job_opportunity,
                                 evaluate_signal_opportunity, evaluate_watch_recheck,
                                 opportunity_type_for_signal)

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


class RadarInput(BaseModel):
    code: str = Field(min_length=2, max_length=60, pattern=r"^[A-Z0-9_]+$")
    label: str = Field(min_length=3, max_length=160)
    enabled: bool = False
    autonomy_mode: Literal["MANUAL", "ASSISTED", "AUTONOMOUS"] = "MANUAL"
    schedule_expression: str | None = Field(default=None, max_length=120)
    daily_limit: int | None = Field(default=None, ge=1, le=500)
    score_threshold: int | None = Field(default=None, ge=0, le=100)
    locations: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    salary_floor: float | None = Field(default=None, ge=0)
    work_model: str | None = Field(default=None, max_length=30)
    languages: dict[str, str] = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)


class RadarRuleInput(BaseModel):
    code: str = Field(min_length=2, max_length=100, pattern=r"^[A-Z0-9_]+$")
    label: str = Field(min_length=3, max_length=200)
    rule_type: Literal["BLOCK", "REVIEW", "BOOST", "PENALTY"]
    configuration: dict[str, Any]
    priority: int = Field(default=100, ge=1, le=1000)
    enabled: bool = True


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


class CompanyInput(BaseModel):
    name: str = Field(min_length=2, max_length=200)


SIGNAL_TYPES = Literal["EXPANSION", "INVESTMENT", "NEW_OFFICE", "NEW_OPERATION", "NEW_PROJECT",
                       "HIRING_ANNOUNCEMENT", "RECRUITER_SIGNAL", "CAREERS_CHANGE", "JOB_DISCOVERED",
                       "OTHER_VERIFIED_SIGNAL"]
OPPORTUNITY_TYPES = Literal["JOB_APPLICATION", "SPONTANEOUS_APPLICATION", "TALENT_POOL",
                            "DIRECT_OUTREACH", "RECRUITER_OPPORTUNITY", "FUTURE_HIRING", "WATCH_ONLY"]
OPPORTUNITY_STATUSES = Literal["DISCOVERED", "EVALUATING", "WATCH", "RECHECK", "ACTIONABLE", "PREPARED",
                               "HUMAN_REQUIRED", "BLOCKED", "DROPPED", "APPLIED", "CLOSED"]
CHANNEL_TYPES = Literal["OFFICIAL_ATS", "OFFICIAL_CAREERS", "OFFICIAL_EMAIL", "TALENT_POOL",
                        "SPONTANEOUS_APPLICATION", "RECRUITER_INSTRUCTION", "ASSISTED", "WATCH"]
CHANNEL_STATUSES = Literal["CANDIDATE", "VERIFIED", "REJECTED", "USED"]
WATCH_STATUSES = Literal["ACTIVE", "PROMOTED", "EXPIRED"]


class SignalInput(BaseModel):
    type: SIGNAL_TYPES
    company_id: UUID | None = None
    source_url: str | None = Field(default=None, max_length=1000)
    source_type: str | None = Field(default=None, max_length=40)
    headline: str = Field(min_length=2, max_length=300)
    summary: str | None = Field(default=None, max_length=5000)
    observed_at: datetime | None = None
    published_at: datetime | None = None
    confidence: int | None = Field(default=None, ge=0, le=100)
    evidence: dict[str, Any] = Field(default_factory=dict)


class OpportunityInput(BaseModel):
    company_id: UUID
    job_id: UUID | None = None
    signal_id: UUID | None = None
    type: OPPORTUNITY_TYPES
    status: OPPORTUNITY_STATUSES = "DISCOVERED"
    discovery_source: str | None = Field(default=None, max_length=60)
    evidence: dict[str, Any] = Field(default_factory=dict)


class OpportunityStatusInput(BaseModel):
    status: OPPORTUNITY_STATUSES
    evidence: dict[str, Any] = Field(default_factory=dict)


class OpportunityChannelInput(BaseModel):
    type: CHANNEL_TYPES
    url_or_email: str = Field(min_length=3, max_length=500)
    source: str | None = Field(default=None, max_length=1000)
    verified_at: datetime | None = None
    confidence: int | None = Field(default=None, ge=0, le=100)
    requires_auth: bool = False
    requires_captcha: bool = False
    requires_human: bool = False
    status: CHANNEL_STATUSES = "CANDIDATE"
    evidence: dict[str, Any] = Field(default_factory=dict)


class WatchInput(BaseModel):
    company_id: UUID
    opportunity_id: UUID | None = None
    reason: str = Field(min_length=3, max_length=2000)
    next_check_at: datetime | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class WatchUpdateInput(BaseModel):
    status: WATCH_STATUSES | None = None
    last_checked_at: datetime | None = None
    next_check_at: datetime | None = None
    check_count: int | None = Field(default=None, ge=0)
    evidence: dict[str, Any] | None = None


class CompanyIntelInput(BaseModel):
    careers_url: str | None = Field(default=None, max_length=500)
    ats_type: str | None = Field(default=None, max_length=40)
    official_recruiting_email: str | None = Field(default=None, max_length=254)
    talent_pool_url: str | None = Field(default=None, max_length=500)
    br_presence: bool | None = None


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
    structured_extraction: dict[str, Any] | None = None


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
    opportunity_id: UUID | None = None
    executor_id: str = Field(min_length=2, max_length=100)
    reason: Literal["CAPTCHA", "MFA", "LOGIN", "UNKNOWN_FIELD", "SUBMISSION_UNCONFIRMED", "LAYOUT_CHANGED",
                    "AUTH_REQUIRED", "MISSING_PROFILE_DATA", "SENSITIVE_FIELD_REQUIRED",
                    "MATERIAL_UNKNOWN", "FINAL_APPROVAL"]
    title: str = Field(min_length=3, max_length=240)
    instructions: str = Field(min_length=3, max_length=2000)
    page_url: str | None = Field(default=None, max_length=1000)
    evidence: dict[str, Any] = Field(default_factory=dict)


class InterventionResolution(BaseModel):
    resolution: Literal["RESOLVED", "SKIPPED", "CANCELLED"]


class CareerGoalInput(BaseModel):
    weekly_applications: int = Field(default=20, ge=1, le=500)
    weekly_responses: int = Field(default=3, ge=0, le=500)
    minimum_response_percent: float = Field(default=10, ge=0, le=100)


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


async def record_audit(
    session, actor: str, entity: str, entity_id: UUID | None, action: str, metadata: dict[str, Any] | None = None
) -> None:
    """Grava um evento em audit_logs na MESMA sessão/transação da mudança que o originou,
    para que auditoria e mudança sempre committem juntas ou nenhuma das duas commita.

    audit_logs não tem organization_id (o schema é global desde a migration 0001) - este
    sistema é single-tenant hoje, então isso não perde informação na prática.
    """
    await session.execute(
        text(
            """
            INSERT INTO audit_logs (id, actor, entity, entity_id, action, metadata, correlation_id)
            VALUES (gen_random_uuid(), :actor, :entity, :entity_id, :action, CAST(:metadata AS jsonb), gen_random_uuid())
            """
        ),
        {"actor": actor, "entity": entity, "entity_id": entity_id, "action": action, "metadata": json.dumps(metadata or {})},
    )


@router.get("/audit-logs")
async def list_audit_logs(limit: int = Query(default=100, ge=1, le=500), slug: str = Depends(require_admin)) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, timestamp, actor, entity, entity_id, action, metadata, correlation_id
                    FROM audit_logs
                    ORDER BY timestamp DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
        ).mappings()
    return [dict(row) for row in rows]


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
        await record_audit(session, slug, "source_connections", row["id"], "SOURCE_CHANGED",
                            {"adapter": row["adapter"], "account_key": row["account_key"], "enabled": row["enabled"]})
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
                    jsonb_build_object('strategy', CAST(:strategy AS text), 'resume_hash', CAST(:resume_hash AS text)))
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
                   "preferred_skills": json.dumps(payload.preferred_skills),
                   "structured_extraction": json.dumps(payload.structured_extraction)
                                            if payload.structured_extraction is not None else None})
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
              required_skills, preferred_skills, application_channel, recruiter_name, recruiter_email,
              structured_extraction, fingerprint)
            VALUES (gen_random_uuid(), :organization_id, :company_id, :external_id, :source, :source_url, :canonical_url,
              :title, :description, :family, :location, :country, :employment_type, :work_model, :seniority,
              :salary_min, :salary_max, :salary_currency, :salary_period, CAST(:language_requirements AS jsonb),
              CAST(:required_skills AS jsonb), CAST(:preferred_skills AS jsonb), :application_channel,
              :recruiter_name, :recruiter_email, CAST(:structured_extraction AS jsonb), :fingerprint) RETURNING id
        """), values)
        await session.execute(text("""
            INSERT INTO job_sources (id, organization_id, job_id, source, external_id, source_url)
            VALUES (gen_random_uuid(), :organization_id, :job_id, :source, :external_id, :source_url)
            ON CONFLICT (organization_id, source, source_url) DO UPDATE SET last_seen_at=now()
        """), {**values, "job_id": job_id})
        if created:
            # JOB_DISCOVERED provenance (Secao 22, Prompt 4): o gap deixado
            # pelo Prompt 3 (build_job_discovered_signal_payload implementado
            # mas nao conectado) e resolvido aqui, cirurgicamente, sem tocar
            # o outbox do automation-host - company_id e job_id ja estao
            # resolvidos neste mesmo ponto de ingest_job, entao criar o
            # Signal aqui e uma linha a mais na MESMA transacao, nao uma
            # nova integracao de rede. So para o evento NOVO (created=True),
            # nunca em massa para o historico (Secao 12/22). Provenance
            # pura: so source_url/headline/evidence com a fingerprint, nunca
            # uma copia da descricao/requisitos (Job continua o registro
            # canonico).
            signal_fp = signal_fingerprint(str(company_id), "JOB_DISCOVERED", payload.source_url)
            await session.execute(text("""
                INSERT INTO signals (id, organization_id, company_id, type, source_url, source_type,
                  headline, confidence, evidence, dedup_fingerprint)
                VALUES (gen_random_uuid(), :organization_id, :company_id, 'JOB_DISCOVERED', :source_url,
                  'JOB_BOARD', :headline, 90, CAST(:evidence AS jsonb), :dedup_fingerprint)
                ON CONFLICT (organization_id, dedup_fingerprint) DO NOTHING
            """), {"organization_id": org_id, "company_id": company_id, "source_url": payload.source_url,
                   "headline": payload.title[:300], "evidence": json.dumps({"job_fingerprint": fingerprint}),
                   "dedup_fingerprint": signal_fp})
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


@router.get("/companies")
async def list_companies(limit: int = 100, slug: str = Depends(require_admin)) -> list[dict[str, Any]]:
    org_id = await organization_id(slug)
    query = text("""
        SELECT id, name, domain, careers_url, ats_type, official_recruiting_email,
               talent_pool_url, br_presence, last_checked_at
        FROM companies WHERE organization_id=:organization_id AND deleted_at IS NULL
        ORDER BY name LIMIT :limit
    """)
    async with SessionLocal() as session:
        rows = (await session.execute(query, {"organization_id": org_id, "limit": min(max(limit, 1), 500)})).mappings()
    return [dict(row) for row in rows]


@router.patch("/companies/{company_id}")
async def update_company_intelligence(company_id: UUID, payload: CompanyIntelInput,
                                       slug: str = Depends(require_admin)) -> dict[str, Any]:
    """Company Intelligence (Cycle 009): registra o que foi resolvido de
    verdade sobre uma empresa (careers/ATS/talent pool/e-mail oficial) -
    nunca inventa o que nao foi encontrado; campos nao informados aqui
    preservam o valor ja salvo (COALESCE), nunca voltam a null."""
    org_id = await organization_id(slug)
    values = payload.model_dump()
    values.update({"organization_id": org_id, "company_id": company_id})
    async with SessionLocal() as session:
        updated_id = await session.scalar(text("""
            UPDATE companies SET
              careers_url = COALESCE(:careers_url, careers_url),
              ats_type = COALESCE(:ats_type, ats_type),
              official_recruiting_email = COALESCE(:official_recruiting_email, official_recruiting_email),
              talent_pool_url = COALESCE(:talent_pool_url, talent_pool_url),
              br_presence = COALESCE(:br_presence, br_presence),
              last_checked_at = now()
            WHERE id=:company_id AND organization_id=:organization_id AND deleted_at IS NULL
            RETURNING id
        """), values)
        if not updated_id:
            raise HTTPException(status_code=404, detail="Empresa não encontrada.")
        await session.commit()
    return {"id": updated_id, "updated": True}


@router.post("/companies")
async def create_company(payload: CompanyInput, slug: str = Depends(require_admin)) -> dict[str, Any]:
    """Find-or-create por nome - mesma logica ja usada dentro de ingest_job
    (career.py), so exposta como rota propria porque Market Memory (Fase 2)
    precisa resolver uma Company sem depender de uma Job existir primeiro."""
    org_id = await organization_id(slug)
    values = {"organization_id": org_id, "company": payload.name}
    async with SessionLocal() as session:
        company_id = await session.scalar(text(
            "SELECT id FROM companies WHERE organization_id=:organization_id "
            "AND lower(name)=lower(:company) AND deleted_at IS NULL LIMIT 1"
        ), values)
        created = company_id is None
        if not company_id:
            company_id = await session.scalar(text(
                "INSERT INTO companies (id, organization_id, name) "
                "VALUES (gen_random_uuid(), :organization_id, :company) RETURNING id"
            ), values)
        await session.commit()
    return {"id": company_id, "created": created}


@router.post("/signals")
async def create_signal(payload: SignalInput, slug: str = Depends(require_admin)) -> dict[str, Any]:
    """Upsert por dedup_fingerprint - reenviar o mesmo sinal (mesma empresa,
    tipo e source_url) nunca cria uma segunda linha."""
    org_id = await organization_id(slug)
    fingerprint = signal_fingerprint(str(payload.company_id) if payload.company_id else None,
                                      payload.type, payload.source_url or "")
    values = payload.model_dump()
    values.update({"organization_id": org_id, "dedup_fingerprint": fingerprint,
                   "evidence": json.dumps(payload.evidence)})
    async with SessionLocal() as session:
        row = (await session.execute(text("""
            INSERT INTO signals (id, organization_id, company_id, type, source_url, source_type,
              headline, summary, observed_at, published_at, confidence, evidence, dedup_fingerprint)
            VALUES (gen_random_uuid(), :organization_id, :company_id, :type, :source_url, :source_type,
              :headline, :summary, COALESCE(:observed_at, now()), :published_at, :confidence,
              CAST(:evidence AS jsonb), :dedup_fingerprint)
            ON CONFLICT (organization_id, dedup_fingerprint) DO UPDATE SET
              confidence=EXCLUDED.confidence, evidence=EXCLUDED.evidence, updated_at=now()
            RETURNING id, (xmax = 0) AS created
        """), values)).mappings().one()
        await session.commit()
    return {"id": row["id"], "created": row["created"], "dedup_fingerprint": fingerprint}


@router.get("/signals")
async def list_signals(status: str | None = None, company_id: UUID | None = None,
                        limit: int = 100, slug: str = Depends(require_admin)) -> list[dict[str, Any]]:
    org_id = await organization_id(slug)
    query = text("""
        SELECT id, company_id, type, source_url, source_type, headline, summary, observed_at,
               published_at, confidence, evidence, status, created_at
        FROM signals
        WHERE organization_id=:organization_id
          AND (CAST(:status AS varchar) IS NULL OR status=CAST(:status AS varchar))
          AND (CAST(:company_id AS uuid) IS NULL OR company_id=CAST(:company_id AS uuid))
        ORDER BY observed_at DESC LIMIT :limit
    """)
    async with SessionLocal() as session:
        rows = (await session.execute(query, {
            "organization_id": org_id, "status": status, "company_id": company_id,
            "limit": min(max(limit, 1), 500),
        })).mappings()
    return [dict(row) for row in rows]


@router.post("/opportunities")
async def create_opportunity(payload: OpportunityInput, slug: str = Depends(require_admin)) -> dict[str, Any]:
    """Upsert por dedup_fingerprint (company+type+job+signal) - nunca cria
    uma segunda Opportunity para a mesma combinacao real."""
    org_id = await organization_id(slug)
    fingerprint = opportunity_fingerprint(
        str(payload.company_id), payload.type,
        str(payload.job_id) if payload.job_id else None,
        str(payload.signal_id) if payload.signal_id else None,
    )
    values = payload.model_dump()
    values.update({"organization_id": org_id, "dedup_fingerprint": fingerprint,
                   "evidence": json.dumps(payload.evidence)})
    async with SessionLocal() as session:
        row = (await session.execute(text("""
            INSERT INTO opportunities (id, organization_id, company_id, job_id, signal_id, type,
              status, discovery_source, dedup_fingerprint, evidence)
            VALUES (gen_random_uuid(), :organization_id, :company_id, :job_id, :signal_id, :type,
              :status, :discovery_source, :dedup_fingerprint, CAST(:evidence AS jsonb))
            ON CONFLICT (organization_id, dedup_fingerprint) DO UPDATE SET
              evidence=EXCLUDED.evidence, updated_at=now()
            RETURNING id, status, (xmax = 0) AS created
        """), values)).mappings().one()
        await session.commit()
    return {"id": row["id"], "status": row["status"], "created": row["created"],
            "dedup_fingerprint": fingerprint}


@router.get("/opportunities")
async def list_opportunities(status: str | None = None, company_id: UUID | None = None,
                              limit: int = 100, slug: str = Depends(require_admin)) -> list[dict[str, Any]]:
    org_id = await organization_id(slug)
    query = text("""
        SELECT o.id, o.company_id, c.name AS company, o.job_id, o.signal_id, o.type, o.status,
               o.discovery_source, o.evidence, o.created_at, o.updated_at
        FROM opportunities o JOIN companies c ON c.id=o.company_id
        WHERE o.organization_id=:organization_id
          AND (CAST(:status AS varchar) IS NULL OR o.status=CAST(:status AS varchar))
          AND (CAST(:company_id AS uuid) IS NULL OR o.company_id=CAST(:company_id AS uuid))
        ORDER BY o.updated_at DESC LIMIT :limit
    """)
    async with SessionLocal() as session:
        rows = (await session.execute(query, {
            "organization_id": org_id, "status": status, "company_id": company_id,
            "limit": min(max(limit, 1), 500),
        })).mappings()
    return [dict(row) for row in rows]


@router.patch("/opportunities/{opportunity_id}")
async def update_opportunity_status(opportunity_id: UUID, payload: OpportunityStatusInput,
                                     slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    values = {"organization_id": org_id, "opportunity_id": opportunity_id,
              "status": payload.status, "evidence": json.dumps(payload.evidence)}
    async with SessionLocal() as session:
        updated_id = await session.scalar(text("""
            UPDATE opportunities SET status=:status,
              evidence = evidence || CAST(:evidence AS jsonb), updated_at=now()
            WHERE id=:opportunity_id AND organization_id=:organization_id
            RETURNING id
        """), values)
        if not updated_id:
            raise HTTPException(status_code=404, detail="Opportunity não encontrada.")
        await session.commit()
    return {"id": updated_id, "status": payload.status}


@router.post("/opportunities/{opportunity_id}/channels")
async def create_opportunity_channel(opportunity_id: UUID, payload: OpportunityChannelInput,
                                      slug: str = Depends(require_admin)) -> dict[str, Any]:
    """OFFICIAL_EMAIL so pode existir aqui com source preenchido - nunca um
    e-mail inferido/adivinhado (regra permanente do produto)."""
    org_id = await organization_id(slug)
    if payload.type == "OFFICIAL_EMAIL" and not payload.source:
        raise HTTPException(status_code=422,
                             detail="OFFICIAL_EMAIL exige source (evidência de publicação oficial).")
    values = payload.model_dump()
    values.update({"organization_id": org_id, "opportunity_id": opportunity_id,
                   "evidence": json.dumps(payload.evidence)})
    async with SessionLocal() as session:
        exists = await session.scalar(text(
            "SELECT id FROM opportunities WHERE id=:opportunity_id AND organization_id=:organization_id"
        ), values)
        if not exists:
            raise HTTPException(status_code=404, detail="Opportunity não encontrada.")
        row = (await session.execute(text("""
            INSERT INTO opportunity_channels (id, organization_id, opportunity_id, type, url_or_email,
              source, verified_at, confidence, requires_auth, requires_captcha, requires_human,
              status, evidence)
            VALUES (gen_random_uuid(), :organization_id, :opportunity_id, :type, :url_or_email,
              :source, :verified_at, :confidence, :requires_auth, :requires_captcha, :requires_human,
              :status, CAST(:evidence AS jsonb))
            ON CONFLICT (opportunity_id, type, url_or_email) DO UPDATE SET
              verified_at=EXCLUDED.verified_at, confidence=EXCLUDED.confidence,
              status=EXCLUDED.status, evidence=EXCLUDED.evidence, updated_at=now()
            RETURNING id, (xmax = 0) AS created
        """), values)).mappings().one()
        await session.commit()
    return {"id": row["id"], "created": row["created"]}


@router.get("/opportunities/{opportunity_id}/channels")
async def list_opportunity_channels(opportunity_id: UUID,
                                     slug: str = Depends(require_admin)) -> list[dict[str, Any]]:
    org_id = await organization_id(slug)
    query = text("""
        SELECT id, type, url_or_email, source, verified_at, confidence, requires_auth,
               requires_captcha, requires_human, status, evidence, created_at
        FROM opportunity_channels
        WHERE organization_id=:organization_id AND opportunity_id=:opportunity_id
        ORDER BY created_at
    """)
    async with SessionLocal() as session:
        rows = (await session.execute(query, {
            "organization_id": org_id, "opportunity_id": opportunity_id,
        })).mappings()
    return [dict(row) for row in rows]


@router.post("/watches")
async def create_watch(payload: WatchInput, slug: str = Depends(require_admin)) -> dict[str, Any]:
    """Upsert por dedup_fingerprint (company+opportunity) - so um Watch
    ACTIVE por combinacao real, mesmo quando opportunity_id e NULL (Watch
    so a nivel de empresa, ex.: Nubank sem oportunidade acionavel hoje)."""
    org_id = await organization_id(slug)
    fingerprint = watch_fingerprint(str(payload.company_id),
                                     str(payload.opportunity_id) if payload.opportunity_id else None)
    values = payload.model_dump()
    values.update({"organization_id": org_id, "dedup_fingerprint": fingerprint,
                   "evidence": json.dumps(payload.evidence)})
    async with SessionLocal() as session:
        row = (await session.execute(text("""
            INSERT INTO watches (id, organization_id, company_id, opportunity_id, reason,
              next_check_at, dedup_fingerprint, evidence)
            VALUES (gen_random_uuid(), :organization_id, :company_id, :opportunity_id, :reason,
              :next_check_at, :dedup_fingerprint, CAST(:evidence AS jsonb))
            ON CONFLICT (organization_id, dedup_fingerprint) DO UPDATE SET
              reason=EXCLUDED.reason, next_check_at=EXCLUDED.next_check_at,
              evidence=EXCLUDED.evidence, updated_at=now()
            RETURNING id, status, (xmax = 0) AS created
        """), values)).mappings().one()
        await session.commit()
    return {"id": row["id"], "status": row["status"], "created": row["created"],
            "dedup_fingerprint": fingerprint}


@router.get("/watches")
async def list_watches(due: bool = False, status: str | None = None,
                        limit: int = 100, slug: str = Depends(require_admin)) -> list[dict[str, Any]]:
    org_id = await organization_id(slug)
    query = text("""
        SELECT id, company_id, opportunity_id, reason, status, last_checked_at, next_check_at,
               check_count, evidence, created_at
        FROM watches
        WHERE organization_id=:organization_id
          AND (CAST(:status AS varchar) IS NULL OR status=CAST(:status AS varchar))
          AND (NOT :due OR (status='ACTIVE' AND next_check_at <= now()))
        ORDER BY next_check_at NULLS LAST LIMIT :limit
    """)
    async with SessionLocal() as session:
        rows = (await session.execute(query, {
            "organization_id": org_id, "status": status, "due": due,
            "limit": min(max(limit, 1), 500),
        })).mappings()
    return [dict(row) for row in rows]


@router.patch("/watches/{watch_id}")
async def update_watch(watch_id: UUID, payload: WatchUpdateInput,
                        slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    values = payload.model_dump()
    values.update({"organization_id": org_id, "watch_id": watch_id,
                   "evidence": json.dumps(payload.evidence) if payload.evidence is not None else None})
    async with SessionLocal() as session:
        updated_id = await session.scalar(text("""
            UPDATE watches SET
              status=COALESCE(:status, status),
              last_checked_at=COALESCE(:last_checked_at, last_checked_at),
              next_check_at=COALESCE(:next_check_at, next_check_at),
              check_count=COALESCE(:check_count, check_count),
              evidence=COALESCE(CAST(:evidence AS jsonb), evidence),
              updated_at=now()
            WHERE id=:watch_id AND organization_id=:organization_id
            RETURNING id
        """), values)
        if not updated_id:
            raise HTTPException(status_code=404, detail="Watch não encontrado.")
        await session.commit()
    return {"id": updated_id, "updated": True}


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
        radars = [
            dict(row)
            for row in (
                await session.execute(
                    text("SELECT code, enabled, roles, keywords FROM radars WHERE organization_id=:organization_id"),
                    {"organization_id": org_id},
                )
            ).mappings()
        ]
        profile_data = dict(profile)
        profile_data["verified_skills"] = verified
        salary_text = str(profile_data.get("salary_expectation") or "")
        salary_number = "".join(character for character in salary_text if character.isdigit() or character in ".,")
        try:
            profile_data["salary_expectation_numeric"] = float(salary_number.replace(".", "").replace(",", "."))
        except ValueError:
            profile_data["salary_expectation_numeric"] = 0
        result = score_job(dict(job), profile_data, codes)
        matched_radars = match_radars(dict(job), radars)
        reasons = result.strengths + result.risks + result.blocking_rules + [f"Radar: {code}" for code in matched_radars]
        await session.execute(text("""
            INSERT INTO job_scores (id, organization_id, job_id, total, decision, dimensions, reasons, gaps, model_version)
            VALUES (gen_random_uuid(), :organization_id, :job_id, :total, :decision, CAST(:dimensions AS jsonb), CAST(:reasons AS jsonb), CAST(:gaps AS jsonb), 'V2.0')
            ON CONFLICT (job_id, model_version) DO UPDATE SET total=EXCLUDED.total, decision=EXCLUDED.decision,
              dimensions=EXCLUDED.dimensions, reasons=EXCLUDED.reasons, gaps=EXCLUDED.gaps, updated_at=now()
        """), {"organization_id": org_id, "job_id": job_id, "total": result.total, "decision": result.recommendation,
               "dimensions": json.dumps(result.dimensions), "reasons": json.dumps(reasons), "gaps": json.dumps(result.gaps)})
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


_DECISION_TO_OPPORTUNITY_STATUS = {
    "DROP": "DROPPED", "BLOCK": "BLOCKED", "WATCH": "WATCH", "RECHECK": "RECHECK",
    "PREPARE": "PREPARED", "ACTIONABLE": "ACTIONABLE", "HUMAN_REQUIRED": "HUMAN_REQUIRED",
}
_TERMINAL_OPPORTUNITY_STATUSES = {"APPLIED", "CLOSED"}


async def _has_prior_interaction(session, org_id: UUID, company_id: UUID) -> bool:
    """Secao 3: interacao historica real (Application/Opportunity ja
    aplicada) e evidencia forte de relevancia de Company."""
    row = await session.scalar(text("""
        SELECT 1 FROM opportunities
        WHERE organization_id=:organization_id AND company_id=:company_id
          AND status IN ('APPLIED','CLOSED') LIMIT 1
    """), {"organization_id": org_id, "company_id": company_id})
    return bool(row)


@router.post("/jobs/{job_id}/evaluate")
async def evaluate_job(job_id: UUID, slug: str = Depends(require_admin)) -> dict[str, Any]:
    """Opportunity Brain (Fase 2, Prompt 4) - Job -> Opportunity (Secao 21).
    Reusa Score V2 (score_job) como fonte de eligibility/fit tecnico -
    nao recria um segundo score redundante (Secao 16, decisao A). Idempotente
    via dedup_fingerprint (company+JOB_APPLICATION+job); Opportunity ja
    APPLIED/CLOSED nunca e reprocessada (Secao 29 - regressao Deutsche Bank)."""
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        job = (await session.execute(text(
            "SELECT * FROM jobs WHERE id=:id AND organization_id=:organization_id AND deleted_at IS NULL"
        ), {"id": job_id, "organization_id": org_id})).mappings().first()
        if not job:
            raise HTTPException(status_code=404, detail="Vaga não encontrada.")
        if not job["company_id"]:
            decision = BrainDecision(decision="HUMAN_REQUIRED", eligibility="COMPANY_UNRESOLVED",
                                      fit_score=None, confidence=50, reasons=["job_has_no_company_id"])
            return {**decision.as_dict(), "opportunity_id": None, "created": False}

        profile = (await session.execute(text(
            "SELECT city, work_models, target_roles, salary_expectation, language_levels "
            "FROM candidate_profiles WHERE organization_id=:organization_id AND deleted_at IS NULL LIMIT 1"
        ), {"organization_id": org_id})).mappings().first() or {}
        skills = [dict(row) for row in (await session.execute(text(
            "SELECT name, level, verified, years_experience FROM skills "
            "WHERE organization_id=:organization_id AND deleted_at IS NULL"
        ), {"organization_id": org_id})).mappings()]
        codes = set((await session.scalars(text(
            "SELECT code FROM career_rules WHERE organization_id=:organization_id AND enabled=true AND deleted_at IS NULL"
        ), {"organization_id": org_id})).all())

        profile_data = dict(profile)
        profile_data["verified_skills"] = [item["name"] for item in skills if item.get("verified")]
        salary_text = str(profile_data.get("salary_expectation") or "")
        salary_number = "".join(character for character in salary_text if character.isdigit() or character in ".,")
        try:
            profile_data["salary_expectation_numeric"] = float(salary_number.replace(".", "").replace(",", "."))
        except ValueError:
            profile_data["salary_expectation_numeric"] = 0

        # job_scores (persistido por /jobs/{id}/score) guarda reasons como uma
        # lista ja achatada (strengths+risks+blocking_rules+radars) - nao da
        # para desmontar de volta com seguranca. score_job e puro/determinista
        # e barato (sem I/O), entao recalcular aqui com os mesmos inputs e
        # mais confiavel que tentar reconstruir o ScoreResult a partir do
        # jsonb persistido (Secao 16: Brain usa os componentes do Score V2).
        score_result = score_job(dict(job), profile_data, codes)

        fingerprint = opportunity_fingerprint(str(job["company_id"]), "JOB_APPLICATION", str(job_id), None)
        existing = (await session.execute(text(
            "SELECT id, status FROM opportunities WHERE organization_id=:organization_id AND dedup_fingerprint=:fingerprint"
        ), {"organization_id": org_id, "fingerprint": fingerprint})).mappings().first()
        already_terminal = bool(existing and existing["status"] in _TERMINAL_OPPORTUNITY_STATUSES)

        channels = []
        if existing:
            channels = [dict(row) for row in (await session.execute(text(
                "SELECT status, requires_auth, requires_captcha, requires_human FROM opportunity_channels "
                "WHERE organization_id=:organization_id AND opportunity_id=:opportunity_id"
            ), {"organization_id": org_id, "opportunity_id": existing["id"]})).mappings()]

        decision = evaluate_job_opportunity(
            job=dict(job), profile=profile_data, candidate_skills=skills, score_result=score_result,
            structured_extraction=dict(job["structured_extraction"]) if job["structured_extraction"] else None,
            channels=channels, already_terminal=already_terminal,
        )

        if already_terminal:
            return {**decision.as_dict(), "opportunity_id": existing["id"], "created": False}

        status = _DECISION_TO_OPPORTUNITY_STATUS[decision.decision]
        row = (await session.execute(text("""
            INSERT INTO opportunities (id, organization_id, company_id, job_id, type, status,
              discovery_source, dedup_fingerprint, evidence, fit_score, brain_confidence,
              evaluated_at, brain_version)
            VALUES (gen_random_uuid(), :organization_id, :company_id, :job_id, 'JOB_APPLICATION', :status,
              'OPPORTUNITY_BRAIN', :fingerprint, CAST(:evidence AS jsonb), :fit_score, :confidence,
              now(), :brain_version)
            ON CONFLICT (organization_id, dedup_fingerprint) DO UPDATE SET
              status=EXCLUDED.status, evidence=opportunities.evidence || EXCLUDED.evidence,
              fit_score=EXCLUDED.fit_score, brain_confidence=EXCLUDED.brain_confidence,
              evaluated_at=now(), brain_version=EXCLUDED.brain_version, updated_at=now()
            RETURNING id, (xmax = 0) AS created
        """), {"organization_id": org_id, "company_id": job["company_id"], "job_id": job_id,
               "status": status, "fingerprint": fingerprint, "evidence": json.dumps({"brain": decision.as_dict()}),
               "fit_score": decision.fit_score, "confidence": decision.confidence,
               "brain_version": BRAIN_VERSION})).mappings().one()
        await session.commit()
    return {**decision.as_dict(), "opportunity_id": row["id"], "created": row["created"]}


@router.post("/signals/{signal_id}/evaluate")
async def evaluate_signal(signal_id: UUID, slug: str = Depends(require_admin)) -> dict[str, Any]:
    """Opportunity Brain - Signal -> Opportunity (Secao 20). So promove
    Signals TRUSTED_RESOLVED e relevantes; nunca fabrica candidatura
    espontanea automatica a partir de um Signal (Secao 30, regressao Nubank)."""
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        signal = (await session.execute(text(
            "SELECT * FROM signals WHERE id=:id AND organization_id=:organization_id"
        ), {"id": signal_id, "organization_id": org_id})).mappings().first()
        if not signal:
            raise HTTPException(status_code=404, detail="Signal não encontrado.")

        company = None
        related_signals: list[dict] = []
        has_prior = False
        if signal["company_id"]:
            company = (await session.execute(text(
                "SELECT br_presence, careers_url, ats_type FROM companies WHERE id=:id"
            ), {"id": signal["company_id"]})).mappings().first()
            related_signals = [dict(row) for row in (await session.execute(text(
                "SELECT type, confidence FROM signals WHERE organization_id=:organization_id "
                "AND company_id=:company_id AND id != :signal_id"
            ), {"organization_id": org_id, "company_id": signal["company_id"], "signal_id": signal_id})).mappings()]
            has_prior = await _has_prior_interaction(session, org_id, signal["company_id"])

        decision = evaluate_signal_opportunity(signal=dict(signal), company=dict(company) if company else None,
                                                related_signals=related_signals, has_prior_interaction=has_prior)

        if decision.decision != "WATCH":
            new_signal_status = "DISCARDED" if decision.eligibility == "SIGNAL_QUALITY_GATE" else signal["status"]
            if new_signal_status != signal["status"]:
                await session.execute(text("UPDATE signals SET status=:status, updated_at=now() WHERE id=:id"),
                                       {"status": new_signal_status, "id": signal_id})
                await session.commit()
            return {**decision.as_dict(), "opportunity_id": None}

        opportunity_type = opportunity_type_for_signal(signal["type"])
        fingerprint = opportunity_fingerprint(str(signal["company_id"]), opportunity_type, None, str(signal_id))
        opp_row = (await session.execute(text("""
            INSERT INTO opportunities (id, organization_id, company_id, signal_id, type, status,
              discovery_source, dedup_fingerprint, evidence, fit_score, brain_confidence,
              evaluated_at, brain_version)
            VALUES (gen_random_uuid(), :organization_id, :company_id, :signal_id, :type, 'WATCH',
              'OPPORTUNITY_BRAIN', :fingerprint, CAST(:evidence AS jsonb), NULL, :confidence,
              now(), :brain_version)
            ON CONFLICT (organization_id, dedup_fingerprint) DO UPDATE SET
              evidence=opportunities.evidence || EXCLUDED.evidence, brain_confidence=EXCLUDED.brain_confidence,
              evaluated_at=now(), brain_version=EXCLUDED.brain_version, updated_at=now()
            RETURNING id, (xmax = 0) AS created
        """), {"organization_id": org_id, "company_id": signal["company_id"], "signal_id": signal_id,
               "type": opportunity_type, "fingerprint": fingerprint,
               "evidence": json.dumps({"brain": decision.as_dict()}), "confidence": decision.confidence,
               "brain_version": BRAIN_VERSION})).mappings().one()

        watch_fp = watch_fingerprint(str(signal["company_id"]), str(opp_row["id"]))
        await session.execute(text("""
            INSERT INTO watches (id, organization_id, company_id, opportunity_id, reason,
              next_check_at, dedup_fingerprint, evidence)
            VALUES (gen_random_uuid(), :organization_id, :company_id, :opportunity_id, :reason,
              now() + interval '30 days', :fingerprint, CAST(:evidence AS jsonb))
            ON CONFLICT (organization_id, dedup_fingerprint) DO UPDATE SET
              reason=EXCLUDED.reason, evidence=watches.evidence || EXCLUDED.evidence, updated_at=now()
        """), {"organization_id": org_id, "company_id": signal["company_id"], "opportunity_id": opp_row["id"],
               "reason": "; ".join(decision.reasons) or "Opportunity Brain: sinal relevante sem ação concreta hoje.",
               "fingerprint": watch_fp, "evidence": json.dumps({"brain": decision.as_dict()})})
        await session.execute(text("UPDATE signals SET status='PROMOTED', updated_at=now() WHERE id=:id"),
                               {"id": signal_id})
        await session.commit()
    return {**decision.as_dict(), "opportunity_id": opp_row["id"], "created": opp_row["created"]}


@router.post("/watches/{watch_id}/recheck")
async def recheck_watch(watch_id: UUID, slug: str = Depends(require_admin)) -> dict[str, Any]:
    """Opportunity Brain - Recheck (Secao 24). Nao inicia scheduler novo
    (gap conhecido, Secao 23) - reavaliacao e sob demanda nesta entrega."""
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        watch = (await session.execute(text(
            "SELECT * FROM watches WHERE id=:id AND organization_id=:organization_id"
        ), {"id": watch_id, "organization_id": org_id})).mappings().first()
        if not watch:
            raise HTTPException(status_code=404, detail="Watch não encontrado.")

        company = (await session.execute(text(
            "SELECT br_presence, careers_url, ats_type FROM companies WHERE id=:id"
        ), {"id": watch["company_id"]})).mappings().first()
        since = watch["last_checked_at"]
        query = "SELECT type, confidence FROM signals WHERE organization_id=:organization_id AND company_id=:company_id"
        params = {"organization_id": org_id, "company_id": watch["company_id"]}
        if since:
            query += " AND observed_at > :since"
            params["since"] = since
        new_signals = [dict(row) for row in (await session.execute(text(query), params)).mappings()]
        has_prior = await _has_prior_interaction(session, org_id, watch["company_id"])

        decision = evaluate_watch_recheck(new_signals=new_signals, company=dict(company) if company else None,
                                           has_prior_interaction=has_prior)

        next_check_days = 7 if decision.decision == "RECHECK" else 30
        await session.execute(text("""
            UPDATE watches SET last_checked_at=now(), check_count=check_count+1,
              next_check_at=now() + make_interval(days => :days),
              evidence=evidence || CAST(:evidence AS jsonb), updated_at=now()
            WHERE id=:id
        """), {"id": watch_id, "days": next_check_days, "evidence": json.dumps({"brain": decision.as_dict()})})

        if decision.decision == "RECHECK" and watch["opportunity_id"]:
            await session.execute(text("""
                UPDATE opportunities SET status='RECHECK',
                  evidence=evidence || CAST(:evidence AS jsonb), brain_confidence=:confidence,
                  evaluated_at=now(), brain_version=:brain_version, updated_at=now()
                WHERE id=:opportunity_id AND organization_id=:organization_id
            """), {"opportunity_id": watch["opportunity_id"], "organization_id": org_id,
                   "evidence": json.dumps({"brain": decision.as_dict()}),
                   "confidence": decision.confidence, "brain_version": BRAIN_VERSION})
        await session.commit()
    return {**decision.as_dict(), "watch_id": watch_id, "next_check_days": next_check_days}


def environment_auto_apply_enabled_for_api() -> bool:
    """Secao 10: gate de produto explicito, separado de policy eligible -
    lido diretamente do ambiente do container api (mesmo nome de variavel
    ja usado pelo automation-host), nunca de um valor 'esquecido' em codigo."""
    return os.getenv("AUTO_APPLY_ENABLED", "false").strip().lower() == "true"


def _aggregate_channel_trust(channels: list[dict]) -> tuple[str | None, dict | None]:
    """Prioriza o pior caso material (CAPTCHA/AUTH) sobre um canal
    VERIFIED_AVAILABLE que porventura tambem exista, e so devolve um canal
    selecionado quando ha um VERIFIED_AVAILABLE de verdade (Secao 6/7)."""
    if not channels:
        return None, None
    trusts = [(item, classify_channel_trust(item)) for item in channels]
    if any(trust == "CAPTCHA_REQUIRED" for _, trust in trusts):
        return "CAPTCHA_REQUIRED", None
    if any(trust == "AUTH_REQUIRED" for _, trust in trusts):
        return "AUTH_REQUIRED", None
    selected = select_channel(channels)
    if selected:
        return "VERIFIED_AVAILABLE", selected
    for _, trust in trusts:
        if trust in {"BOT_GATED", "STALE", "UNVERIFIABLE", "UNAVAILABLE"}:
            return trust, None
    return "UNVERIFIABLE", None


@router.post("/opportunities/{opportunity_id}/action-plan")
async def create_action_plan(opportunity_id: UUID, slug: str = Depends(require_admin)) -> dict[str, Any]:
    """Action Engine (Fase 2, Prompt 5) - camada de DECISAO de acao, nunca
    de execucao. Sempre DRY RUN: nenhuma linha aqui envia e-mail, clica em
    formulario ou muda estado externo - so calcula e persiste um Application
    Plan auditavel, e cria Human Intervention quando necessario. A execucao
    real (send_application_email / automacao de browser existentes)
    continua inteiramente fora deste endpoint, atras de AUTO_APPLY_ENABLED
    e de uma acao humana explicita e pontual."""
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        opportunity = (await session.execute(text(
            "SELECT * FROM opportunities WHERE id=:id AND organization_id=:organization_id"
        ), {"id": opportunity_id, "organization_id": org_id})).mappings().first()
        if not opportunity:
            raise HTTPException(status_code=404, detail="Opportunity não encontrada.")

        brain = dict(opportunity["evidence"] or {}).get("brain") or {}
        brain_decision = brain.get("decision", opportunity["status"])
        hard_blocks = list(brain.get("hard_blocks") or [])
        unknowns = list(brain.get("unknowns") or [])

        job = None
        if opportunity["job_id"]:
            job = (await session.execute(text(
                "SELECT * FROM jobs WHERE id=:id AND organization_id=:organization_id"
            ), {"id": opportunity["job_id"], "organization_id": org_id})).mappings().first()

        salary_known = bool(job and job["salary_min"] is not None)
        salary_below_floor = bool(job and job["salary_min"] is not None
                                   and float(job["salary_min"]) < MINIMUM_ACCEPTABLE_SALARY_BRL)
        location_work_model_blocked = any(item in hard_blocks for item in
                                           ("RELOCATION_REQUIRED_IMPLICIT", "RELOCATION_REQUIRED"))
        language_incompatible = "LANGUAGE_GAP" in hard_blocks

        channels = [dict(row) for row in (await session.execute(text(
            "SELECT * FROM opportunity_channels WHERE organization_id=:organization_id AND opportunity_id=:opportunity_id"
        ), {"organization_id": org_id, "opportunity_id": opportunity_id})).mappings()]
        channel_trust, selected_channel = _aggregate_channel_trust(channels)

        profile = dict((await session.execute(text(
            "SELECT city, state, work_models, target_roles, salary_expectation, language_levels, "
            "headline, linkedin_url, approved_answers FROM candidate_profiles "
            "WHERE organization_id=:organization_id AND deleted_at IS NULL LIMIT 1"
        ), {"organization_id": org_id})).mappings().first() or {})
        skills = [dict(row) for row in (await session.execute(text("""
            SELECT s.name, s.verified,
                   (SELECT count(*) FROM skill_evidence e WHERE e.skill_id=s.id AND e.deleted_at IS NULL) AS evidence_count
            FROM skills s WHERE s.organization_id=:organization_id AND s.deleted_at IS NULL
        """), {"organization_id": org_id})).mappings()]
        resumes = [dict(row) for row in (await session.execute(text("""
            SELECT rv.id, rv.sha256, rv.approved_at, r.family, r.language, r.active
            FROM resume_versions rv JOIN resumes r ON r.id=rv.resume_id
            WHERE rv.organization_id=:organization_id AND r.deleted_at IS NULL
        """), {"organization_id": org_id})).mappings()]

        resume: dict | None = None
        if job:
            resume = route_resume(dict(job), resumes)
        completeness = classify_profile_completeness(profile, skills, resumes)
        completeness_ok = is_profile_completeness_sufficient(completeness)

        language_status = assess_language_status(profile)
        if language_status["needs_intervention"]:
            # Secao 2: intervencao de PERFIL (nao de uma Opportunity especifica) -
            # a mesma deduplication_key para toda avaliacao garante uma unica
            # linha persistente ate o usuario declarar o nivel real.
            await _create_or_reuse_intervention(session, org_id, InterventionInput(
                executor_id="action-engine", reason="MISSING_PROFILE_DATA",
                title=language_status["intervention_title"],
                instructions=language_status["intervention_instructions"],
                evidence={"deduplication_key": "profile:language_declaration"},
            ))

        duplicate_exists = bool((await session.scalar(text("""
            SELECT 1 FROM applications
            WHERE organization_id=:organization_id
              AND ((job_id=:job_id AND :job_id IS NOT NULL) OR opportunity_id=:opportunity_id)
              AND status IN ('SENT','CONFIRMED','RECRUITER_RESPONSE','INTERVIEW','TECHNICAL_TEST',
                              'FINAL_STAGE','OFFER')
            LIMIT 1
        """), {"organization_id": org_id, "job_id": opportunity["job_id"], "opportunity_id": opportunity_id})))
        attempt_cap_reached = bool((await session.scalar(text("""
            SELECT count(*) FROM applications
            WHERE organization_id=:organization_id
              AND ((job_id=:job_id AND :job_id IS NOT NULL) OR opportunity_id=:opportunity_id)
              AND status IN ('SUBMITTING','ERROR')
        """), {"organization_id": org_id, "job_id": opportunity["job_id"],
               "opportunity_id": opportunity_id})) or 0) >= 1

        policy = evaluate_action_policy(
            brain_decision=brain_decision, hard_blocks=hard_blocks, unknowns=unknowns,
            salary_known=salary_known, salary_below_floor=salary_below_floor,
            location_work_model_blocked=location_work_model_blocked,
            language_incompatible=language_incompatible, channel_trust=channel_trust,
            resume_available=bool(resume) if job else True, duplicate_exists=duplicate_exists,
            sensitive_missing=[], attempt_cap_reached=attempt_cap_reached,
            profile_completeness_sufficient=completeness_ok,
            product_auto_apply_enabled=environment_auto_apply_enabled_for_api(),
        )
        plan = build_application_plan(
            opportunity_id=str(opportunity_id), job_id=str(opportunity["job_id"]) if opportunity["job_id"] else None,
            channel=selected_channel, resume=resume, policy_result=policy,
            evidence={"profile_completeness": completeness, "channel_trust": channel_trust},
        )

        await session.execute(text("""
            UPDATE opportunities SET evidence=evidence || CAST(:evidence AS jsonb), updated_at=now()
            WHERE id=:id AND organization_id=:organization_id
        """), {"id": opportunity_id, "organization_id": org_id, "evidence": json.dumps({"action_plan": plan})})

        intervention = None
        if policy.human_requirements:
            requirements = set(policy.human_requirements)
            # Prioridade explicita, sem heuristica sobre o formato da string
            # (Secao 22 - cada item carrega contexto suficiente para
            # resolver uma vez): CAPTCHA/AUTH sao sempre o motivo mais
            # concreto quando presentes; PROFILE_COMPLETENESS/RESUME_SELECTION/
            # language_level_unknown sao dados de perfil faltando; o resto
            # (requisito material incerto da propria vaga) vira MATERIAL_UNKNOWN.
            if "CAPTCHA" in requirements:
                reason = "CAPTCHA"
            elif "AUTH_REQUIRED" in requirements:
                reason = "AUTH_REQUIRED"
            elif "FINAL_APPROVAL" in requirements:
                reason = "FINAL_APPROVAL"
            elif requirements & {"PROFILE_COMPLETENESS", "RESUME_SELECTION", "language_level_unknown"}:
                reason = "MISSING_PROFILE_DATA"
            else:
                reason = "MATERIAL_UNKNOWN"
            intervention_payload = InterventionInput(
                opportunity_id=opportunity_id, executor_id="action-engine",
                reason=reason, title=f"Ação requer decisão humana — {reason}",
                instructions="; ".join(policy.human_requirements) or "Revisão manual necessária.",
                evidence={"deduplication_key": f"action-plan:{opportunity_id}:{reason}",
                          "policy_result": policy.as_dict()},
            )
            intervention = await _create_or_reuse_intervention(session, org_id, intervention_payload)
        await session.commit()
    return {"plan": plan, "intervention": intervention}


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
               COALESCE(p.approved_answers, '{}'::jsonb) || COALESCE((
                 SELECT jsonb_object_agg(q.normalized_question, q.approved_answer)
                 FROM application_questions q
                 WHERE q.organization_id=:organization_id AND q.verified=true
                   AND q.approved_answer IS NOT NULL
               ), '{}'::jsonb) AS approved_answers,
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


@router.get("/resumes/{version_id}/file")
async def download_resume_file(version_id: UUID, slug: str = Depends(require_admin)) -> Response:
    """Devolve os bytes do currículo aprovado que o Resume Router
    escolheu (resume_version_id retornado por POST /jobs/{id}/prepare) -
    necessário porque quem prepara a candidatura (Core) e quem preenche o
    formulário de verdade (automation-host) são serviços/volumes
    separados; sem isso não há como o Resume Router influenciar uma
    candidatura real."""
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        row = (await session.execute(text("""
            SELECT rv.storage_key, r.name AS resume_name
            FROM resume_versions rv JOIN resumes r ON r.id = rv.resume_id
            WHERE rv.id = :version_id AND rv.organization_id = :organization_id
        """), {"version_id": version_id, "organization_id": org_id})).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Versão de currículo não encontrada.")
    storage_path = Path(row["storage_key"])
    if not storage_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo do currículo não encontrado no armazenamento.")
    filename = row["resume_name"] or storage_path.name
    return Response(content=storage_path.read_bytes(), media_type="application/octet-stream",
                     headers={"X-Resume-Filename": filename})


@router.post("/profile/extract-evidence")
async def extract_profile_evidence_route(slug: str = Depends(require_admin)) -> dict[str, Any]:
    """Profile Intelligence (Fase 2, Prompt 6, Secoes 15-19) - extrai fatos
    EXPLICITOS do curriculo aprovado e persistido (nunca infere, nunca usa
    memoria de conversa). So DOCX e suportado nesta entrega (stdlib puro,
    sem nova dependencia) - resumes em PDF sao pulados e reportados como
    gap, nunca silenciosamente ignorados."""
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        resumes = [dict(row) for row in (await session.execute(text("""
            SELECT rv.id, rv.storage_key, rv.sha256, r.code
            FROM resume_versions rv JOIN resumes r ON r.id=rv.resume_id
            WHERE rv.organization_id=:organization_id AND r.deleted_at IS NULL
              AND rv.approved_at IS NOT NULL AND r.active=true
        """), {"organization_id": org_id})).mappings()]
        skill_rows = [dict(row) for row in (await session.execute(text(
            "SELECT id, name FROM skills WHERE organization_id=:organization_id AND deleted_at IS NULL"
        ), {"organization_id": org_id})).mappings()]

        processed, skipped_pdf, evidence_by_resume = [], [], {}
        for resume in resumes:
            storage_path = Path(resume["storage_key"])
            if storage_path.suffix.lower() != ".docx":
                skipped_pdf.append({"resume_code": resume["code"], "reason": "unsupported_format",
                                     "extension": storage_path.suffix})
                continue
            if not storage_path.exists():
                continue
            text_content = extract_docx_text(storage_path.read_bytes())
            evidence = extract_profile_evidence(text_content, [item["name"] for item in skill_rows])
            evidence_by_resume[resume["code"]] = {**evidence, "resume_version_id": str(resume["id"]),
                                                    "resume_sha256": resume["sha256"]}
            processed.append(resume["code"])

        if not evidence_by_resume:
            return {"processed": [], "skipped": skipped_pdf, "language_populated": False,
                    "skill_evidence_created": 0}

        merged_language_levels = {}
        merged_skill_mentions: list[dict] = []
        for evidence in evidence_by_resume.values():
            merged_language_levels.update(evidence.get("language_levels") or {})
            merged_skill_mentions.extend(evidence.get("skill_mentions") or [])

        await session.execute(text("""
            UPDATE candidate_profiles SET resume_evidence=CAST(:evidence AS jsonb), updated_at=now()
            WHERE organization_id=:organization_id
        """), {"organization_id": org_id, "evidence": json.dumps(evidence_by_resume)})

        current_language_levels = await session.scalar(text(
            "SELECT language_levels FROM candidate_profiles WHERE organization_id=:organization_id LIMIT 1"
        ), {"organization_id": org_id})
        language_populated = False
        if not current_language_levels and merged_language_levels:
            flat_levels = {language: fact["value"] for language, fact in merged_language_levels.items()}
            await session.execute(text("""
                UPDATE candidate_profiles SET language_levels=CAST(:levels AS jsonb), updated_at=now()
                WHERE organization_id=:organization_id
            """), {"organization_id": org_id, "levels": json.dumps(flat_levels)})
            language_populated = True
            await session.execute(text("""
                UPDATE human_interventions SET status='RESOLVED', resolution='RESOLVED', resolved_at=now(),
                  updated_at=now()
                WHERE organization_id=:organization_id AND status='PENDING'
                  AND evidence->>'deduplication_key'='profile:language_declaration'
            """), {"organization_id": org_id})

        skill_evidence_created = 0
        name_to_id = {item["name"]: item["id"] for item in skill_rows}
        for mention in merged_skill_mentions:
            skill_id = name_to_id.get(mention["skill_name"])
            if not skill_id:
                continue
            resume_code = next((code for code, ev in evidence_by_resume.items()
                                if mention in (ev.get("skill_mentions") or [])), "GENERAL")
            source_tag = f"resume_version:{evidence_by_resume[resume_code]['resume_version_id']}"
            exists = await session.scalar(text("""
                SELECT 1 FROM skill_evidence WHERE organization_id=:organization_id AND skill_id=:skill_id
                  AND source=:source AND deleted_at IS NULL LIMIT 1
            """), {"organization_id": org_id, "skill_id": skill_id, "source": source_tag})
            if exists:
                continue
            await session.execute(text("""
                INSERT INTO skill_evidence (id, organization_id, skill_id, evidence_type, title,
                  description, source, approved)
                VALUES (gen_random_uuid(), :organization_id, :skill_id, 'RESUME', :title,
                  :description, :source, false)
            """), {"organization_id": org_id, "skill_id": skill_id,
                    "title": f"Mencionado no currículo aprovado ({resume_code})",
                    "description": mention["evidence_snippet"], "source": source_tag})
            skill_evidence_created += 1
        await session.commit()
    return {"processed": processed, "skipped": skipped_pdf, "language_populated": language_populated,
            "skill_evidence_created": skill_evidence_created}


@router.get("/analytics/funnel")
async def get_conversion_funnel(slug: str = Depends(require_admin)) -> dict[str, Any]:
    """Secao 10/11 - reusa jobs/job_scores/opportunities/applications/
    application_events ja existentes (nunca duplica o modelo de evento -
    application_events ja e append-only, com trigger de banco)."""
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        jobs_count = await session.scalar(text(
            "SELECT count(*) FROM jobs WHERE organization_id=:organization_id AND deleted_at IS NULL"
        ), {"organization_id": org_id})
        scored_count = await session.scalar(text(
            "SELECT count(DISTINCT job_id) FROM job_scores WHERE organization_id=:organization_id"
        ), {"organization_id": org_id})
        opportunities_by_status = dict((await session.execute(text(
            "SELECT status, count(*) FROM opportunities WHERE organization_id=:organization_id GROUP BY status"
        ), {"organization_id": org_id})).all())
        applications_by_status = dict((await session.execute(text(
            "SELECT status, count(*) FROM applications WHERE organization_id=:organization_id "
            "AND deleted_at IS NULL GROUP BY status"
        ), {"organization_id": org_id})).all())
        events_by_type = dict((await session.execute(text("""
            SELECT CASE
                     WHEN to_status IN ('RECRUITER_RESPONSE') THEN 'RESPONSE'
                     WHEN to_status IN ('INTERVIEW','TECHNICAL_TEST','FINAL_STAGE') THEN 'INTERVIEW'
                     WHEN to_status = 'OFFER' THEN 'OFFER'
                     ELSE NULL
                   END AS bucket, count(*)
            FROM application_events ae JOIN applications a ON a.id=ae.application_id
            WHERE a.organization_id=:organization_id
            GROUP BY bucket
        """), {"organization_id": org_id})).all())
        events_by_type.pop(None, None)
        funnel = calculate_conversion_funnel(
            jobs_count=jobs_count or 0, scored_count=scored_count or 0,
            opportunities_by_status=opportunities_by_status, applications_by_status=applications_by_status,
            events_by_type=events_by_type,
        )
        applications_rows = [dict(row) for row in (await session.execute(text("""
            SELECT a.status, a.channel AS application_channel, o.type AS opportunity_type
            FROM applications a LEFT JOIN opportunities o ON o.id=a.opportunity_id
            WHERE a.organization_id=:organization_id AND a.deleted_at IS NULL
        """), {"organization_id": org_id})).mappings()]
        dimensional = {
            "application_channel": aggregate_by_dimension(applications_rows, "application_channel"),
            "opportunity_type": aggregate_by_dimension(applications_rows, "opportunity_type"),
        }
        sample_size = sum(applications_by_status.values())
    return {"funnel": funnel, "dimensional": dimensional,
            "recommendation_confidence": recommendation_confidence(sample_size)}


@router.get("/analytics/gaps")
async def get_gap_intelligence(slug: str = Depends(require_admin)) -> dict[str, Any]:
    """Career Gap Intelligence (Secao 14) - agrega hard_blocks/unknowns
    reais ja persistidos pelo Opportunity Brain (Prompt 4), nunca inventa
    uma categoria sem origem real."""
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        opportunities = [dict(row) for row in (await session.execute(text(
            "SELECT id, fit_score, evidence FROM opportunities WHERE organization_id=:organization_id"
        ), {"organization_id": org_id})).mappings()]
    return {"gaps": aggregate_gap_intelligence(opportunities), "opportunities_considered": len(opportunities)}


@router.post("/opportunities/{opportunity_id}/channels/discover")
async def discover_channels(opportunity_id: UUID, slug: str = Depends(require_admin)) -> dict[str, Any]:
    """Channel Population (Fase 2, Prompt 6, Secao 20 - P0). So cria
    OpportunityChannel a partir de evidencia real ja persistida (Job/
    Company/structured_extraction) - nunca adivinha e-mail, nunca
    transforma homepage generica em canal (Secao 21). Nenhuma acao de
    candidatura acontece aqui."""
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        opportunity = (await session.execute(text(
            "SELECT * FROM opportunities WHERE id=:id AND organization_id=:organization_id"
        ), {"id": opportunity_id, "organization_id": org_id})).mappings().first()
        if not opportunity:
            raise HTTPException(status_code=404, detail="Opportunity não encontrada.")
        company = dict((await session.execute(text(
            "SELECT careers_url, official_recruiting_email, talent_pool_url, ats_type "
            "FROM companies WHERE id=:id"
        ), {"id": opportunity["company_id"]})).mappings().first() or {})

        job = None
        if opportunity["job_id"]:
            job = (await session.execute(text(
                "SELECT * FROM jobs WHERE id=:id AND organization_id=:organization_id"
            ), {"id": opportunity["job_id"], "organization_id": org_id})).mappings().first()

        if job:
            candidates = discover_job_channel_candidates(
                dict(job), company,
                dict(job["structured_extraction"]) if job["structured_extraction"] else None,
            )
        else:
            candidates = discover_company_channel_candidates(company)

        created = []
        for candidate in candidates:
            row = (await session.execute(text("""
                INSERT INTO opportunity_channels (id, organization_id, opportunity_id, type, url_or_email,
                  source, confidence, requires_auth, requires_captcha, requires_human, status, evidence)
                VALUES (gen_random_uuid(), :organization_id, :opportunity_id, :type, :url_or_email,
                  :source, :confidence, :requires_auth, :requires_captcha, :requires_human, :status,
                  CAST(:evidence AS jsonb))
                ON CONFLICT (opportunity_id, type, url_or_email) DO UPDATE SET
                  confidence=EXCLUDED.confidence, evidence=EXCLUDED.evidence, updated_at=now()
                RETURNING id, (xmax = 0) AS created
            """), {"organization_id": org_id, "opportunity_id": opportunity_id,
                    "evidence": json.dumps({"discovery": "channel_population_v1"}), **candidate})).mappings().one()
            created.append({**candidate, "id": row["id"], "created": row["created"]})
        await session.commit()
    return {"opportunity_id": opportunity_id, "candidates": created}


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
        await record_audit(session, slug, "career_rules", row["id"], "RULE_CHANGED",
                            {"code": row["code"], "rule_type": row["rule_type"], "enabled": row["enabled"]})
        await session.commit()
    return dict(row)


async def radar_id_by_code(organization_id_value: UUID, code: str) -> UUID:
    async with SessionLocal() as session:
        value = await session.scalar(
            text("SELECT id FROM radars WHERE organization_id = :organization_id AND code = :code"),
            {"organization_id": organization_id_value, "code": code},
        )
    if not value:
        raise HTTPException(status_code=404, detail="Radar não encontrado.")
    return value


@router.get("/radars")
async def list_radars(slug: str = Depends(require_admin)) -> list[dict[str, Any]]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, code, label, enabled, autonomy_mode, schedule_expression,
                           daily_limit, score_threshold, locations, roles, keywords,
                           exclusions, salary_floor, work_model, languages, sources
                    FROM radars
                    WHERE organization_id = :organization_id
                    ORDER BY code
                    """
                ),
                {"organization_id": org_id},
            )
        ).mappings()
    return [dict(row) for row in rows]


@router.put("/radars/{code}")
async def save_radar(code: str, payload: RadarInput, slug: str = Depends(require_admin)) -> dict[str, Any]:
    if code != payload.code:
        raise HTTPException(status_code=400, detail="O código da rota deve ser igual ao payload.")
    org_id = await organization_id(slug)
    query = text(
        """
        INSERT INTO radars
            (id, organization_id, code, label, enabled, autonomy_mode, schedule_expression,
             daily_limit, score_threshold, locations, roles, keywords, exclusions,
             salary_floor, work_model, languages, sources)
        VALUES
            (gen_random_uuid(), :organization_id, :code, :label, :enabled, :autonomy_mode,
             :schedule_expression, :daily_limit, :score_threshold, CAST(:locations AS jsonb),
             CAST(:roles AS jsonb), CAST(:keywords AS jsonb), CAST(:exclusions AS jsonb),
             :salary_floor, :work_model, CAST(:languages AS jsonb), CAST(:sources AS jsonb))
        ON CONFLICT (organization_id, code)
        DO UPDATE SET label = EXCLUDED.label,
                      enabled = EXCLUDED.enabled,
                      autonomy_mode = EXCLUDED.autonomy_mode,
                      schedule_expression = EXCLUDED.schedule_expression,
                      daily_limit = EXCLUDED.daily_limit,
                      score_threshold = EXCLUDED.score_threshold,
                      locations = EXCLUDED.locations,
                      roles = EXCLUDED.roles,
                      keywords = EXCLUDED.keywords,
                      exclusions = EXCLUDED.exclusions,
                      salary_floor = EXCLUDED.salary_floor,
                      work_model = EXCLUDED.work_model,
                      languages = EXCLUDED.languages,
                      sources = EXCLUDED.sources,
                      updated_at = now()
        RETURNING id, code, label, enabled, autonomy_mode, schedule_expression, daily_limit,
                  score_threshold, locations, roles, keywords, exclusions, salary_floor,
                  work_model, languages, sources
        """
    )
    values = payload.model_dump()
    values["organization_id"] = org_id
    for key in ("locations", "roles", "keywords", "exclusions", "languages", "sources"):
        values[key] = json.dumps(values[key])
    async with SessionLocal() as session:
        row = (await session.execute(query, values)).mappings().one()
        await session.commit()
    return dict(row)


@router.get("/radars/{code}/rules")
async def list_radar_rules(code: str, slug: str = Depends(require_admin)) -> list[dict[str, Any]]:
    org_id = await organization_id(slug)
    r_id = await radar_id_by_code(org_id, code)
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, code, label, rule_type, configuration, priority, enabled
                    FROM radar_rules
                    WHERE organization_id = :organization_id AND radar_id = :radar_id
                    ORDER BY priority, code
                    """
                ),
                {"organization_id": org_id, "radar_id": r_id},
            )
        ).mappings()
    return [dict(row) for row in rows]


@router.put("/radars/{code}/rules/{rule_code}")
async def save_radar_rule(
    code: str, rule_code: str, payload: RadarRuleInput, slug: str = Depends(require_admin)
) -> dict[str, Any]:
    if rule_code != payload.code:
        raise HTTPException(status_code=400, detail="O código da rota deve ser igual ao payload.")
    org_id = await organization_id(slug)
    r_id = await radar_id_by_code(org_id, code)
    query = text(
        """
        INSERT INTO radar_rules (id, organization_id, radar_id, code, label, rule_type, configuration, priority, enabled)
        VALUES (gen_random_uuid(), :organization_id, :radar_id, :code, :label, :rule_type,
                CAST(:configuration AS jsonb), :priority, :enabled)
        ON CONFLICT (radar_id, code)
        DO UPDATE SET label = EXCLUDED.label,
                      rule_type = EXCLUDED.rule_type,
                      configuration = EXCLUDED.configuration,
                      priority = EXCLUDED.priority,
                      enabled = EXCLUDED.enabled,
                      updated_at = now()
        RETURNING id, code, label, rule_type, configuration, priority, enabled
        """
    )
    values = payload.model_dump()
    values["organization_id"] = org_id
    values["radar_id"] = r_id
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
        if not changed:
            raise HTTPException(status_code=404, detail="Decisão pendente não encontrada.")
        await record_audit(session, slug, "decision_inbox", decision_id, f"DECISION_{payload.decision}")
        await session.commit()
    return {"status": payload.decision}


@router.post("/communications/sync")
async def sync_communications(batch: CommunicationBatch, slug: str = Depends(require_admin)) -> dict[str, int]:
    org_id = await organization_id(slug)
    matched = unmatched = notifications = 0
    async with SessionLocal() as session:
        # Achado real (Prompt 6): o INNER JOIN em jobs excluia toda
        # candidatura ligada so a uma Opportunity (SPONTANEOUS_APPLICATION
        # sem Job - ex.: Deutsche Bank, Prompt 2) do pool de correlacao.
        # LEFT JOIN duplo (via Job OU via Opportunity) inclui os dois casos.
        rows = (await session.execute(text("""
            SELECT a.id, COALESCE(j.title, '') AS title,
                   COALESCE(cj.name, co.name) AS company,
                   COALESCE(cj.domain, co.domain) AS company_domain
            FROM applications a
            LEFT JOIN jobs j ON j.id=a.job_id
            LEFT JOIN companies cj ON cj.id=j.company_id
            LEFT JOIN opportunities o ON o.id=a.opportunity_id
            LEFT JOIN companies co ON co.id=o.company_id
            WHERE a.organization_id=:organization_id AND a.deleted_at IS NULL
              AND a.status NOT IN ('CLOSED', 'WITHDRAWN')
        """), {"organization_id": org_id})).mappings()
        candidates = [dict(item) for item in rows]
        for item_model in batch.items:
            item = item_model.model_dump()
            correlation = classify_correlation(item, candidates)
            application_id, correlation_status = correlation["application_id"], correlation["status"]
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
                    "evidence": json.dumps({"signals": correlation["evidence"]})})
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


@router.get("/analytics")
async def career_analytics(slug: str = Depends(require_admin)) -> dict[str, Any]:
    """Evidence-based operational funnel; empty samples never become recommendations."""
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        application_rows = (await session.execute(text("""
            SELECT status, count(*)::int AS total
            FROM applications WHERE organization_id=:organization_id
            GROUP BY status ORDER BY total DESC, status
        """), {"organization_id": org_id})).mappings().all()
        source_rows = (await session.execute(text("""
            SELECT j.source, count(*)::int AS jobs,
                   count(a.id)::int AS applications,
                   count(a.id) FILTER (WHERE a.status IN ('APPLIED','CONFIRMED','INTERVIEW','OFFER'))::int AS progressed
            FROM jobs j LEFT JOIN applications a ON a.job_id=j.id
            WHERE j.organization_id=:organization_id
            GROUP BY j.source ORDER BY jobs DESC, j.source LIMIT 20
        """), {"organization_id": org_id})).mappings().all()
        communication_rows = (await session.execute(text("""
            SELECT category, count(*)::int AS total
            FROM recruitment_communications WHERE organization_id=:organization_id
            GROUP BY category ORDER BY total DESC, category
        """), {"organization_id": org_id})).mappings().all()
        intervention_row = (await session.execute(text("""
            SELECT count(*)::int AS total,
                   count(*) FILTER (WHERE status='PENDING')::int AS pending,
                   count(*) FILTER (WHERE status='RESOLVED')::int AS resolved
            FROM human_interventions WHERE organization_id=:organization_id
        """), {"organization_id": org_id})).mappings().one()
        timeline_rows = (await session.execute(text("""
            WITH days AS (
              SELECT generate_series(current_date - interval '29 days', current_date, interval '1 day')::date AS day
            ), job_counts AS (
              SELECT created_at::date AS day, count(*)::int AS total FROM jobs
              WHERE organization_id=:organization_id AND created_at >= current_date - interval '29 days'
              GROUP BY created_at::date
            ), application_counts AS (
              SELECT created_at::date AS day, count(*)::int AS total FROM applications
              WHERE organization_id=:organization_id AND created_at >= current_date - interval '29 days'
              GROUP BY created_at::date
            ), response_counts AS (
              SELECT received_at::date AS day, count(*)::int AS total FROM recruitment_communications
              WHERE organization_id=:organization_id AND received_at >= current_date - interval '29 days'
                AND category IN ('INTERVIEW','PROPOSAL','REJECTION','APPLICATION_CONFIRMED')
              GROUP BY received_at::date
            )
            SELECT d.day, COALESCE(j.total,0)::int AS jobs,
                   COALESCE(a.total,0)::int AS applications, COALESCE(r.total,0)::int AS responses
            FROM days d LEFT JOIN job_counts j USING(day)
            LEFT JOIN application_counts a USING(day) LEFT JOIN response_counts r USING(day)
            ORDER BY d.day
        """), {"organization_id": org_id})).mappings().all()
        cohort_rows = (await session.execute(text("""
            SELECT date_trunc('week', a.created_at)::date AS week,
                   count(DISTINCT a.id)::int AS applications,
                   count(DISTINCT a.id) FILTER (WHERE a.status IN ('APPLIED','CONFIRMED','INTERVIEW','OFFER'))::int AS submitted,
                   count(DISTINCT rc.application_id) FILTER (WHERE rc.category IN ('INTERVIEW','PROPOSAL','REJECTION','APPLICATION_CONFIRMED'))::int AS responses
            FROM applications a LEFT JOIN recruitment_communications rc ON rc.application_id=a.id
            WHERE a.organization_id=:organization_id AND a.created_at >= current_date - interval '12 weeks'
            GROUP BY date_trunc('week', a.created_at)::date ORDER BY week
        """), {"organization_id": org_id})).mappings().all()
        goal_row = (await session.execute(text("""
            SELECT weekly_applications, weekly_responses, minimum_response_percent
            FROM career_goals WHERE organization_id=:organization_id
        """), {"organization_id": org_id})).mappings().first()
        current_week_row = (await session.execute(text("""
            SELECT
              (SELECT count(*)::int FROM applications
               WHERE organization_id=:organization_id
                 AND created_at >= date_trunc('week', current_date)) AS applications,
              (SELECT count(DISTINCT application_id)::int FROM recruitment_communications
               WHERE organization_id=:organization_id
                 AND received_at >= date_trunc('week', current_date)
                 AND category IN ('INTERVIEW','PROPOSAL','REJECTION','APPLICATION_CONFIRMED')) AS responses
        """), {"organization_id": org_id})).mappings().one()
    statuses = {row["status"]: row["total"] for row in application_rows}
    applications = sum(statuses.values())
    submitted = sum(statuses.get(status, 0) for status in ("APPLIED", "CONFIRMED", "INTERVIEW", "OFFER"))
    responses = sum(row["total"] for row in communication_rows
                    if row["category"] in {"INTERVIEW", "PROPOSAL", "REJECTION", "APPLICATION_CONFIRMED"})
    warnings = []
    if applications < 10:
        warnings.append("Amostra de candidaturas insuficiente para recomendações confiáveis (mínimo: 10).")
    if submitted == 0:
        warnings.append("Ainda não há candidatura enviada e confirmada no Core.")
    goals = dict(goal_row) if goal_row else {
        "weekly_applications": 20, "weekly_responses": 3, "minimum_response_percent": 10.0,
    }
    current_week = dict(current_week_row)
    return {
        "sample": {"applications": applications, "submitted": submitted,
                   "communications": sum(row["total"] for row in communication_rows)},
        "funnel": [{"status": row["status"], "total": row["total"]} for row in application_rows],
        "sources": [dict(row) for row in source_rows],
        "communications": [dict(row) for row in communication_rows],
        "interventions": dict(intervention_row),
        "timeline": [dict(row) for row in timeline_rows],
        "cohorts": [dict(row) for row in cohort_rows],
        "goals": goals,
        "goal_progress": {
            "applications": current_week.get("applications", 0),
            "responses": current_week.get("responses", 0),
            "applications_percent": round(current_week.get("applications", 0) * 100 / goals["weekly_applications"], 1),
            "responses_percent": round(current_week.get("responses", 0) * 100 / goals["weekly_responses"], 1) if goals["weekly_responses"] else None,
        },
        "rates": {
            "submission_percent": round(submitted * 100 / applications, 1) if applications else None,
            "response_percent": round(responses * 100 / submitted, 1) if submitted else None,
        },
        "warnings": warnings,
        "recommendations_enabled": applications >= 10 and submitted > 0,
        "generated_at": datetime.now(UTC),
    }


@router.put("/analytics/goals")
async def update_analytics_goals(payload: CareerGoalInput,
                                 slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        row = (await session.execute(text("""
            INSERT INTO career_goals
              (id, organization_id, weekly_applications, weekly_responses, minimum_response_percent)
            VALUES (gen_random_uuid(), :organization_id, :weekly_applications, :weekly_responses, :minimum_response_percent)
            ON CONFLICT (organization_id) DO UPDATE SET
              weekly_applications=EXCLUDED.weekly_applications,
              weekly_responses=EXCLUDED.weekly_responses,
              minimum_response_percent=EXCLUDED.minimum_response_percent,
              updated_at=now()
            RETURNING weekly_applications, weekly_responses, minimum_response_percent, updated_at
        """), {"organization_id": org_id, **payload.model_dump()})).mappings().one()
        await session.commit()
    return dict(row)


async def _create_or_reuse_intervention(session, org_id: UUID, payload: InterventionInput) -> dict:
    """Compartilhado entre a rota HTTP /interventions e o Action Engine
    (Prompt 5) - mesma logica de dedup (evidence.deduplication_key) e
    notificacao, nunca duplicada."""
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
          (id, organization_id, application_id, opportunity_id, executor_id, reason, title,
           instructions, page_url, evidence)
        VALUES (gen_random_uuid(), :organization_id, :application_id, :opportunity_id, :executor_id,
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
    return dict(row)


@router.post("/interventions")
async def create_intervention(payload: InterventionInput,
                              slug: str = Depends(require_admin)) -> dict[str, Any]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        row = await _create_or_reuse_intervention(session, org_id, payload)
        await session.commit()
    return row


@router.get("/interventions")
async def list_interventions(status: str = Query(default="PENDING"),
                             slug: str = Depends(require_admin)) -> list[dict[str, Any]]:
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        rows = (await session.execute(text("""
            SELECT id, application_id, opportunity_id, executor_id, reason, status, title,
                   instructions, page_url, evidence, created_at, resolved_at, resolution
            FROM human_interventions
            WHERE organization_id=:organization_id AND (:status='ALL' OR status=:status)
            ORDER BY CASE status WHEN 'PENDING' THEN 1 ELSE 2 END, created_at DESC LIMIT 100
        """), {"organization_id": org_id, "status": status})).mappings()
    return [dict(row) for row in rows]


@router.get("/interventions/grouped")
async def list_interventions_grouped(status: str = Query(default="PENDING"),
                                     slug: str = Depends(require_admin)) -> list[dict[str, Any]]:
    """Secao 25 - agrupa por causa raiz (mesmo reason + mesmos
    human_requirements) para o usuario nao virar operador: 10
    Opportunities bloqueadas pelo mesmo motivo viram 1 grupo, nunca 10
    decisoes identicas. Nenhum historico e apagado - so a apresentacao
    agrupa (ver /interventions para a lista individual completa)."""
    org_id = await organization_id(slug)
    async with SessionLocal() as session:
        rows = [dict(row) for row in (await session.execute(text("""
            SELECT id, opportunity_id, reason, evidence
            FROM human_interventions
            WHERE organization_id=:organization_id AND (:status='ALL' OR status=:status)
        """), {"organization_id": org_id, "status": status})).mappings()]
    return group_interventions_by_root_cause(rows)


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
