"""Fase 2 (Prompt 3) - one small additive JSONB column for structured Job
Content Understanding (title/salary/work_model/location/language/mandatory
vs preferred requirements/application instructions), each field carrying
value+confidence+evidence_snippet+source_url+extraction_method.

Deliberately NOT a new table: jobs already has language_requirements/
required_skills/preferred_skills (migration 0005) for the flat values other
code already reads. This column is additive, holds the richer evidence
that doesn't fit those flat shapes, and feeds Prompt 4 (Opportunity Brain)
without duplicating the whole schema.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015_job_structured_extraction"
down_revision = "0014_market_memory"

JSON = postgresql.JSONB()


def upgrade() -> None:
    op.add_column("jobs", sa.Column("structured_extraction", JSON))


def downgrade() -> None:
    op.drop_column("jobs", "structured_extraction")
