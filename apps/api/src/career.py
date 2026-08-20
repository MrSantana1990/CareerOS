from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from .database import SessionLocal
from .auth import require_admin

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


async def organization_id(slug: str) -> UUID:
    async with SessionLocal() as session:
        value = await session.scalar(
            text("SELECT id FROM organizations WHERE slug = :slug AND deleted_at IS NULL"),
            {"slug": slug},
        )
    if not value:
        raise HTTPException(status_code=404, detail="Organização não encontrada.")
    return value


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
