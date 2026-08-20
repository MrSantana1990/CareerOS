"""Core career domain with organization isolation."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_career_domain"
down_revision = "0001_foundation"

UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB()


def common() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    ]


def tenant_table(name: str, *columns: sa.Column, constraints: tuple = ()) -> None:
    op.create_table(
        name,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        *columns,
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        *constraints,
        *common(),
    )
    op.create_index(f"ix_{name}_organization", name, ["organization_id"])


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("plan", sa.String(40), nullable=False, server_default="PERSONAL"),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        *common(),
    )
    tenant_table(
        "users",
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("full_name", sa.String(160), nullable=False),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("role", sa.String(30), nullable=False, server_default="OWNER"),
        sa.Column("status", sa.String(30), nullable=False, server_default="INVITED"),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        constraints=(sa.UniqueConstraint("organization_id", "email"),),
    )
    tenant_table(
        "candidate_profiles",
        sa.Column("user_id", UUID),
        sa.Column("headline", sa.String(240)),
        sa.Column("city", sa.String(100)),
        sa.Column("state", sa.String(80)),
        sa.Column("country", sa.String(80), nullable=False, server_default="Brasil"),
        sa.Column("linkedin_url", sa.String(500)),
        sa.Column("summary", sa.Text()),
        sa.Column("work_models", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("target_roles", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("language_levels", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        constraints=(
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("organization_id", "user_id"),
        ),
    )
    tenant_table(
        "career_rules",
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("rule_type", sa.String(40), nullable=False),
        sa.Column("configuration", JSON, nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        constraints=(sa.UniqueConstraint("organization_id", "code"),),
    )
    tenant_table(
        "skills",
        sa.Column("name", sa.String(140), nullable=False),
        sa.Column("level", sa.String(40), nullable=False),
        sa.Column("years_experience", sa.Numeric(4, 1)),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        constraints=(sa.UniqueConstraint("organization_id", "name"),),
    )
    tenant_table(
        "skill_evidence",
        sa.Column("skill_id", UUID, nullable=False),
        sa.Column("evidence_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("source", sa.String(500)),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        constraints=(sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),),
    )
    tenant_table(
        "resumes",
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("family", sa.String(60), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        constraints=(sa.UniqueConstraint("organization_id", "code"),),
    )
    tenant_table(
        "resume_versions",
        sa.Column("resume_id", UUID, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        constraints=(
            sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("resume_id", "version"),
        ),
    )
    tenant_table(
        "companies",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("domain", sa.String(255)),
        sa.Column("notes", sa.Text()),
    )
    tenant_table(
        "jobs",
        sa.Column("company_id", UUID),
        sa.Column("external_id", sa.String(255)),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("family", sa.String(60)),
        sa.Column("location", sa.String(200)),
        sa.Column("work_model", sa.String(30)),
        sa.Column("description", sa.Text()),
        sa.Column("salary_min", sa.Numeric(14, 2)),
        sa.Column("salary_max", sa.Numeric(14, 2)),
        sa.Column("salary_currency", sa.String(3)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("validation_status", sa.String(30), nullable=False, server_default="UNCERTAIN"),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        constraints=(
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("organization_id", "fingerprint"),
        ),
    )
    tenant_table(
        "job_scores",
        sa.Column("job_id", UUID, nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("dimensions", JSON, nullable=False),
        sa.Column("reasons", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("gaps", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("model_version", sa.String(40), nullable=False),
        constraints=(sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),),
    )
    tenant_table(
        "applications",
        sa.Column("job_id", UUID, nullable=False),
        sa.Column("resume_version_id", UUID),
        sa.Column("status", sa.String(40), nullable=False, server_default="DRAFT"),
        sa.Column("channel", sa.String(40)),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("external_reference", sa.String(500)),
        constraints=(
            sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["resume_version_id"], ["resume_versions.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("organization_id", "job_id"),
        ),
    )
    tenant_table(
        "decision_inbox",
        sa.Column("job_id", UUID, nullable=False),
        sa.Column("recommendation", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("summary", JSON, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decided_by", UUID),
        constraints=(
            sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="SET NULL"),
        ),
    )
    op.create_index("ix_jobs_validation_status", "jobs", ["validation_status"])
    op.create_index("ix_applications_status", "applications", ["status"])
    op.create_index("ix_decision_inbox_status", "decision_inbox", ["status"])
    op.execute(
        "INSERT INTO organizations (id, name, slug) VALUES "
        "('00000000-0000-0000-0000-000000000001', 'Rodolfo Santana', 'rodolfo')"
    )


def downgrade() -> None:
    for table in (
        "decision_inbox", "applications", "job_scores", "jobs", "companies",
        "resume_versions", "resumes", "skill_evidence", "skills", "career_rules",
        "candidate_profiles", "users", "organizations",
    ):
        op.drop_table(table)
