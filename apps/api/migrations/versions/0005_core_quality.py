"""Normalized jobs, related sources and immutable application events."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_core_quality"
down_revision = "0004_profile_storage"

UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB()


def upgrade() -> None:
    for column in (
        sa.Column("canonical_url", sa.String(1000)),
        sa.Column("country", sa.String(80)),
        sa.Column("employment_type", sa.String(40)),
        sa.Column("seniority", sa.String(40)),
        sa.Column("salary_period", sa.String(20)),
        sa.Column("language_requirements", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("required_skills", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("preferred_skills", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("application_channel", sa.String(40)),
        sa.Column("recruiter_name", sa.String(200)),
        sa.Column("recruiter_email", sa.String(254)),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("validated_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("jobs", column)
    op.execute("UPDATE jobs SET canonical_url = source_url WHERE canonical_url IS NULL")
    op.alter_column("jobs", "canonical_url", nullable=False)

    op.create_table(
        "job_sources",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("job_id", UUID, nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("external_id", sa.String(255)),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "source", "source_url"),
    )
    op.create_index("ix_job_sources_job", "job_sources", ["job_id"])

    op.add_column("applications", sa.Column("automation_mode", sa.String(20), nullable=False, server_default="ASSISTED"))
    op.add_column("applications", sa.Column("confirmation_evidence", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("applications", sa.Column("provider_message_id", sa.String(500)))
    op.execute("UPDATE applications SET status = 'DISCOVERED' WHERE status = 'DRAFT'")
    op.alter_column("applications", "status", server_default="DISCOVERED")

    op.create_table(
        "application_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("application_id", UUID, nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("from_status", sa.String(40)),
        sa.Column("to_status", sa.String(40), nullable=False),
        sa.Column("actor", sa.String(120), nullable=False),
        sa.Column("automation_mode", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("evidence", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_application_events_application", "application_events", ["application_id", "created_at"])
    op.execute("""
        CREATE FUNCTION prevent_application_event_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'application_events is append-only';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER application_events_append_only
        BEFORE UPDATE OR DELETE ON application_events
        FOR EACH ROW EXECUTE FUNCTION prevent_application_event_mutation()
    """)
    op.create_unique_constraint("uq_job_scores_job_model", "job_scores", ["job_id", "model_version"])
    op.create_unique_constraint("uq_decision_inbox_org_job", "decision_inbox", ["organization_id", "job_id"])
    op.execute("""
        INSERT INTO career_rules (id, organization_id, code, label, rule_type, configuration, priority)
        VALUES (gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
                'SUPPORT_N1_MINIMUM', 'Suporte N1 exige remuneração mínima de R$ 4.000',
                'BLOCK', jsonb_build_object('family', 'SUPPORT', 'seniority', 'N1', 'salary_min', 4000), 45)
        ON CONFLICT (organization_id, code) DO NOTHING
    """)
    op.execute("""
        INSERT INTO career_rules (id, organization_id, code, label, rule_type, configuration, priority)
        VALUES (gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
                'RELOCATION_REQUIRED', 'Mudança obrigatória de cidade ou país',
                'BLOCK', jsonb_build_object('required', true), 46)
        ON CONFLICT (organization_id, code) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM career_rules WHERE code IN ('SUPPORT_N1_MINIMUM', 'RELOCATION_REQUIRED')")
    op.drop_constraint("uq_decision_inbox_org_job", "decision_inbox", type_="unique")
    op.drop_constraint("uq_job_scores_job_model", "job_scores", type_="unique")
    op.execute("DROP TRIGGER application_events_append_only ON application_events")
    op.execute("DROP FUNCTION prevent_application_event_mutation()")
    op.drop_table("application_events")
    op.alter_column("applications", "status", server_default="DRAFT")
    for name in ("provider_message_id", "confirmation_evidence", "automation_mode"):
        op.drop_column("applications", name)
    op.drop_table("job_sources")
    for name in (
        "validated_at", "discovered_at", "recruiter_email", "recruiter_name",
        "application_channel", "preferred_skills", "required_skills",
        "language_requirements", "salary_period", "seniority", "employment_type",
        "country", "canonical_url",
    ):
        op.drop_column("jobs", name)
