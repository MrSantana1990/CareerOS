"""Add tenant analytics goals."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_analytics_goals"
down_revision = "0009_human_interventions"
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "career_goals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False, unique=True),
        sa.Column("weekly_applications", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("weekly_responses", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("minimum_response_percent", sa.Numeric(5, 2), nullable=False, server_default="10"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.CheckConstraint("weekly_applications BETWEEN 1 AND 500"),
        sa.CheckConstraint("weekly_responses BETWEEN 0 AND 500"),
        sa.CheckConstraint("minimum_response_percent BETWEEN 0 AND 100"),
    )


def downgrade() -> None:
    op.drop_table("career_goals")
