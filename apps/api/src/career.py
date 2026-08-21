from typing import Any, Literal
from uuid import UUID
from pathlib import Path
import hashlib
import json
import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text

from .database import SessionLocal
from .auth import require_admin
from .quality import job_fingerprint, score_job, transition_allowed

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


async def organization_id(slug: str) -> UUID:
    async with SessionLocal() as session:
        value = await session.scalar(
            text("SELECT id FROM organizations WHERE slug = :slug AND deleted_at IS NULL"),
            {"slug": slug},
        )
    if not value:
        raise HTTPException(status_code=404, detail="Organização não encontrada.")
    return value


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
async def upload_resume(file: UploadFile = File(...), slug: str = Depends(require_admin)) -> dict[str, str]:
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
            VALUES (gen_random_uuid(), :organization_id, 'CURRENT', :name, 'GENERAL', 'pt-BR', true)
            ON CONFLICT (organization_id, code) DO UPDATE SET name = EXCLUDED.name, updated_at = now()
            RETURNING id
        """), {"organization_id": org_id, "name": file.filename or f"curriculo{suffix}"})
        version = (await session.scalar(text("SELECT COALESCE(max(version), 0) + 1 FROM resume_versions WHERE resume_id = :resume_id"), {"resume_id": resume_id})) or 1
        await session.execute(text("""
            INSERT INTO resume_versions (id, organization_id, resume_id, version, storage_key, sha256, approved_at)
            VALUES (gen_random_uuid(), :organization_id, :resume_id, :version, :storage_key, :sha256, now())
        """), {"organization_id": org_id, "resume_id": resume_id, "version": version, "storage_key": str(target), "sha256": digest})
        await session.commit()
    return {"resume_path": str(target), "resume_name": file.filename or target.name}


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
