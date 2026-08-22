"""Add radars, recruiters and calendar events; extend skill evidence review fields.

Schema foundation for the Plano Mestre "Source of Truth unica" (Bloco A, item 3).
job_source_occurrences, email_events, notifications and automation_runs already
have working analogs in this schema (job_sources, recruitment_communications,
career_notifications, discovery_runs) and are intentionally not duplicated here.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_radars_recruiters_calendar"
down_revision = "0010_analytics_goals"

UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB()


def upgrade() -> None:
    op.create_table(
        "radars",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("autonomy_mode", sa.String(20), nullable=False, server_default="MANUAL"),
        sa.Column("schedule_expression", sa.String(120)),
        sa.Column("daily_limit", sa.Integer()),
        sa.Column("score_threshold", sa.Integer()),
        sa.Column("locations", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("roles", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("keywords", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("exclusions", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("salary_floor", sa.Numeric(14, 2)),
        sa.Column("work_model", sa.String(30)),
        sa.Column("languages", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("sources", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "code"),
        sa.CheckConstraint("autonomy_mode IN ('MANUAL', 'ASSISTED', 'AUTONOMOUS')", name="ck_radars_autonomy_mode"),
        sa.CheckConstraint("score_threshold IS NULL OR score_threshold BETWEEN 0 AND 100", name="ck_radars_score_threshold"),
    )

    op.create_table(
        "radar_rules",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("radar_id", UUID, nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("rule_type", sa.String(30), nullable=False),
        sa.Column("configuration", JSON, nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["radar_id"], ["radars.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("radar_id", "code"),
    )
    op.create_index("ix_radar_rules_radar", "radar_rules", ["radar_id"])

    op.create_table(
        "recruiters",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("company_id", UUID),
        sa.Column("name", sa.String(200)),
        sa.Column("email", sa.String(254)),
        sa.Column("source", sa.String(40)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "email"),
    )
    op.create_index("ix_recruiters_company", "recruiters", ["company_id"])

    op.add_column("jobs", sa.Column("recruiter_id", UUID))
    op.create_foreign_key(
        "fk_jobs_recruiter_id_recruiters",
        "jobs",
        "recruiters",
        ["recruiter_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "calendar_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("application_id", UUID),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("timezone", sa.String(60), nullable=False),
        sa.Column("meeting_url", sa.String(1000)),
        sa.Column("description", sa.Text()),
        sa.Column("external_event_id", sa.String(255)),
        sa.Column("source", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "external_event_id"),
    )
    op.create_index("ix_calendar_events_application", "calendar_events", ["application_id", "starts_at"])

    op.add_column("skills", sa.Column("years_claimed", sa.Numeric(4, 1)))
    op.add_column("skill_evidence", sa.Column("last_reviewed_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("skill_evidence", "last_reviewed_at")
    op.drop_column("skills", "years_claimed")
    op.drop_table("calendar_events")
    op.drop_constraint("fk_jobs_recruiter_id_recruiters", "jobs", type_="foreignkey")
    op.drop_column("jobs", "recruiter_id")
    op.drop_table("recruiters")
    op.drop_table("radar_rules")
    op.drop_table("radars")
