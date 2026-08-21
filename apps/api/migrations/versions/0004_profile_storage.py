"""Persist the complete professional profile used by the portal."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_profile_storage"
down_revision = "0003_initial_career_rules"


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(40)))
    op.add_column("candidate_profiles", sa.Column("salary_expectation", sa.String(120)))
    op.add_column(
        "candidate_profiles",
        sa.Column("approved_answers", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("candidate_profiles", "approved_answers")
    op.drop_column("candidate_profiles", "salary_expectation")
    op.drop_column("users", "phone")
