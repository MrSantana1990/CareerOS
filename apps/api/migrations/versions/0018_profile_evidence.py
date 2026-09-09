"""Fase 2 (Prompt 6) - Profile Intelligence: 1 additive JSONB column so
candidate_profiles can hold resume-extracted evidence (employment,
education, certifications, skill mentions, extraction timestamp).

Deliberately NOT new tables for employment/education/certifications:
candidate_profiles has no structured columns for those today, and adding
a full relational history model would be far more schema than a single
resume's worth of evidence justifies right now. The richer evidence
shape (value/evidence_snippet/confidence/extraction_method per fact)
doesn't fit any existing flat column, same reasoning as jobs.
structured_extraction (migration 0015).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0018_profile_evidence"
down_revision = "0017_intervention_opportunity"

JSON = postgresql.JSONB()


def upgrade() -> None:
    op.add_column("candidate_profiles", sa.Column("resume_evidence", JSON))


def downgrade() -> None:
    op.drop_column("candidate_profiles", "resume_evidence")
