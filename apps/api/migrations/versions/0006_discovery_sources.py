"""Persistent discovery source configuration and run history."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_discovery_sources"
down_revision = "0005_core_quality"

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "source_connections",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("adapter", sa.String(40), nullable=False),
        sa.Column("account_key", sa.String(100), nullable=False),
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("maximum_jobs", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("cadence_minutes", sa.Integer(), nullable=False, server_default="360"),
        sa.Column("last_started_at", sa.DateTime(timezone=True)),
        sa.Column("last_completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "adapter", "account_key"),
        sa.CheckConstraint("maximum_jobs BETWEEN 1 AND 500", name="ck_source_maximum_jobs"),
        sa.CheckConstraint("cadence_minutes BETWEEN 30 AND 1440", name="ck_source_cadence"),
    )
    op.create_index("ix_source_connections_enabled", "source_connections", ["enabled"])
    op.create_table(
        "discovery_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("source_connection_id", UUID, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("found_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deduplicated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_connection_id"], ["source_connections.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_discovery_runs_source_started", "discovery_runs", ["source_connection_id", "started_at"])


def downgrade() -> None:
    op.drop_table("discovery_runs")
    op.drop_table("source_connections")
