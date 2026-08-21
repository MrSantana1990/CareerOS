"""Persist recruitment communications and notifications."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_communication_followup"
down_revision = "0007_application_preparation"
UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB()


def upgrade() -> None:
    op.create_table(
        "recruitment_communications",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("application_id", UUID),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_message_id", sa.String(255), nullable=False),
        sa.Column("thread_id", sa.String(255)),
        sa.Column("sender", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_status", sa.String(30), nullable=False, server_default="UNMATCHED"),
        sa.Column("evidence", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "provider", "provider_message_id"),
    )
    op.create_index("ix_communications_application", "recruitment_communications", ["application_id", "received_at"])
    op.create_table(
        "career_notifications",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("application_id", UUID),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False, server_default="NORMAL"),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("deduplication_key", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "deduplication_key"),
    )


def downgrade() -> None:
    op.drop_table("career_notifications")
    op.drop_table("recruitment_communications")
