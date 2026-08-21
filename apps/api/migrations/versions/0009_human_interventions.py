"""Persist human interventions for isolated executors."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_human_interventions"
down_revision = "0008_communication_followup"
UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB()


def upgrade() -> None:
    op.create_table(
        "human_interventions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("application_id", UUID),
        sa.Column("executor_id", sa.String(100), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("page_url", sa.String(1000)),
        sa.Column("evidence", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution", sa.String(40)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_human_interventions_status", "human_interventions", ["organization_id", "status", "created_at"])


def downgrade() -> None:
    op.drop_table("human_interventions")
