"""Resume routing, approved answer memory and safe application drafts."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_application_preparation"
down_revision = "0006_discovery_sources"

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("applications", sa.Column("resume_hash", sa.String(64)))
    op.add_column("applications", sa.Column("strategy", sa.String(30)))
    op.add_column("applications", sa.Column("idempotency_key", sa.String(64)))
    op.add_column("applications", sa.Column("prepared_at", sa.DateTime(timezone=True)))
    op.create_unique_constraint("uq_applications_idempotency", "applications", ["organization_id", "idempotency_key"])
    op.create_table(
        "application_questions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("normalized_question", sa.String(500), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("approved_answer", sa.Text()),
        sa.Column("language", sa.String(10), nullable=False, server_default="pt-BR"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "normalized_question", "language"),
    )
    op.create_table(
        "application_drafts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("application_id", UUID, nullable=False),
        sa.Column("recipient", sa.String(254)),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="REVIEW_REQUIRED"),
        sa.Column("provider_draft_id", sa.String(500)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("application_id"),
    )


def downgrade() -> None:
    op.drop_table("application_drafts")
    op.drop_table("application_questions")
    op.drop_constraint("uq_applications_idempotency", "applications", type_="unique")
    for name in ("prepared_at", "idempotency_key", "strategy", "resume_hash"):
        op.drop_column("applications", name)
