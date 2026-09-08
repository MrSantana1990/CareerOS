"""Fase 2 (Prompt 2) - Market Memory: Signal, Opportunity, OpportunityChannel, Watch.

Additive only. No existing table is renamed or dropped. applications.job_id
becomes nullable (was NOT NULL) so a SPONTANEOUS_APPLICATION Opportunity can
produce a real Application without a fabricated Job - the exact gap that
left the first real CONFIRMED (Deutsche Bank Brasil, Cycle 009) as Gmail
evidence only, with no Core record. A CHECK constraint keeps every
application anchored to at least a job or an opportunity, so the
traditional Job -> Application path (job_id NOT NULL in practice, still
enforced by the check + the pre-existing unique constraint) is unaffected.

Dedup uses a deterministic dedup_fingerprint string column (see
market_memory.py) on every new table instead of relying on Postgres NULL
semantics for uniqueness - deliberate choice, not an oversight (see Prompt 2
report, section 9).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014_market_memory"
down_revision = "0013_company_intelligence"

UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB()


def upgrade() -> None:
    op.create_table(
        "signals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("company_id", UUID),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("source_type", sa.String(40)),
        sa.Column("headline", sa.String(300), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("confidence", sa.Integer()),
        sa.Column("evidence", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("dedup_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="NEW"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "dedup_fingerprint"),
        sa.CheckConstraint(
            "type IN ('EXPANSION','INVESTMENT','NEW_OFFICE','NEW_OPERATION','NEW_PROJECT',"
            "'HIRING_ANNOUNCEMENT','RECRUITER_SIGNAL','CAREERS_CHANGE','JOB_DISCOVERED',"
            "'OTHER_VERIFIED_SIGNAL')",
            name="ck_signals_type",
        ),
        sa.CheckConstraint(
            "status IN ('NEW','COMPANY_RESOLVED','PROMOTED','WATCH','DISCARDED')",
            name="ck_signals_status",
        ),
        sa.CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 100", name="ck_signals_confidence"),
    )
    op.create_index("ix_signals_organization", "signals", ["organization_id"])
    op.create_index("ix_signals_company", "signals", ["organization_id", "company_id"])
    op.create_index("ix_signals_status", "signals", ["organization_id", "status"])

    op.create_table(
        "opportunities",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("job_id", UUID),
        sa.Column("signal_id", UUID),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DISCOVERED"),
        sa.Column("discovery_source", sa.String(60)),
        sa.Column("dedup_fingerprint", sa.String(64), nullable=False),
        sa.Column("evidence", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "dedup_fingerprint"),
        sa.CheckConstraint(
            "type IN ('JOB_APPLICATION','SPONTANEOUS_APPLICATION','TALENT_POOL','DIRECT_OUTREACH',"
            "'RECRUITER_OPPORTUNITY','FUTURE_HIRING','WATCH_ONLY')",
            name="ck_opportunities_type",
        ),
        sa.CheckConstraint(
            "status IN ('DISCOVERED','EVALUATING','WATCH','RECHECK','ACTIONABLE','PREPARED',"
            "'HUMAN_REQUIRED','BLOCKED','DROPPED','APPLIED','CLOSED')",
            name="ck_opportunities_status",
        ),
    )
    op.create_index("ix_opportunities_organization", "opportunities", ["organization_id"])
    op.create_index("ix_opportunities_company", "opportunities", ["organization_id", "company_id"])
    op.create_index("ix_opportunities_status", "opportunities", ["organization_id", "status"])

    op.create_table(
        "opportunity_channels",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("opportunity_id", UUID, nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("url_or_email", sa.String(500), nullable=False),
        sa.Column("source", sa.String(1000)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("confidence", sa.Integer()),
        sa.Column("requires_auth", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requires_captcha", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requires_human", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="CANDIDATE"),
        sa.Column("evidence", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("opportunity_id", "type", "url_or_email"),
        sa.CheckConstraint(
            "type IN ('OFFICIAL_ATS','OFFICIAL_CAREERS','OFFICIAL_EMAIL','TALENT_POOL',"
            "'SPONTANEOUS_APPLICATION','RECRUITER_INSTRUCTION','ASSISTED','WATCH')",
            name="ck_opportunity_channels_type",
        ),
        sa.CheckConstraint(
            "status IN ('CANDIDATE','VERIFIED','REJECTED','USED')",
            name="ck_opportunity_channels_status",
        ),
        sa.CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 100",
                            name="ck_opportunity_channels_confidence"),
    )
    op.create_index("ix_opportunity_channels_opportunity", "opportunity_channels", ["opportunity_id"])

    op.create_table(
        "watches",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("opportunity_id", UUID),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("next_check_at", sa.DateTime(timezone=True)),
        sa.Column("check_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dedup_fingerprint", sa.String(64), nullable=False),
        sa.Column("evidence", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "dedup_fingerprint"),
        sa.CheckConstraint("status IN ('ACTIVE','PROMOTED','EXPIRED')", name="ck_watches_status"),
    )
    op.create_index("ix_watches_organization", "watches", ["organization_id"])
    op.create_index("ix_watches_due", "watches", ["organization_id", "status", "next_check_at"])

    # applications: permitir SPONTANEOUS_APPLICATION sem Job fabricado.
    op.alter_column("applications", "job_id", nullable=True)
    op.add_column("applications", sa.Column("opportunity_id", UUID))
    op.add_column("applications", sa.Column("selection_reason", sa.String(300)))
    op.create_foreign_key(
        "fk_applications_opportunity_id_opportunities",
        "applications", "opportunities", ["opportunity_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_applications_opportunity", "applications", ["organization_id", "opportunity_id"])
    op.create_check_constraint(
        "ck_applications_job_or_opportunity",
        "applications",
        "job_id IS NOT NULL OR opportunity_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_applications_job_or_opportunity", "applications", type_="check")
    op.drop_index("ix_applications_opportunity", table_name="applications")
    op.drop_constraint("fk_applications_opportunity_id_opportunities", "applications", type_="foreignkey")
    op.drop_column("applications", "selection_reason")
    op.drop_column("applications", "opportunity_id")
    op.alter_column("applications", "job_id", nullable=False)

    op.drop_index("ix_watches_due", table_name="watches")
    op.drop_index("ix_watches_organization", table_name="watches")
    op.drop_table("watches")

    op.drop_index("ix_opportunity_channels_opportunity", table_name="opportunity_channels")
    op.drop_table("opportunity_channels")

    op.drop_index("ix_opportunities_status", table_name="opportunities")
    op.drop_index("ix_opportunities_company", table_name="opportunities")
    op.drop_index("ix_opportunities_organization", table_name="opportunities")
    op.drop_table("opportunities")

    op.drop_index("ix_signals_status", table_name="signals")
    op.drop_index("ix_signals_company", table_name="signals")
    op.drop_index("ix_signals_organization", table_name="signals")
    op.drop_table("signals")
