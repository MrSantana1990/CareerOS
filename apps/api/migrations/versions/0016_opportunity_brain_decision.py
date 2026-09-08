"""Fase 2 (Prompt 4) - Opportunity Brain: 4 additive columns on opportunities
for the persisted decision (fit_score/confidence/evaluated_at/brain_version).

Deliberately NOT a new table: opportunities.status already carries the
decision itself (DISCOVERED/EVALUATING/WATCH/RECHECK/ACTIONABLE/PREPARED/
HUMAN_REQUIRED/BLOCKED/DROPPED/APPLIED/CLOSED - defined in migration 0014,
anticipating exactly this prompt), and opportunities.evidence (JSONB,
migration 0014) already exists to hold reasons/hard_blocks/
transferable_matches/preferred_gaps/unknowns/evidence_refs, merged under a
"brain" namespace key so it never clobbers evidence already stored there
(e.g. the Deutsche Bank/Nubank Prompt 2 historical backfill). fit_score and
confidence get dedicated columns because they are the two fields a future
dashboard/priority queue would need to sort/filter on directly.
"""

from alembic import op
import sqlalchemy as sa

revision = "0016_opportunity_brain_decision"
down_revision = "0015_job_structured_extraction"


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("fit_score", sa.Integer()))
    op.add_column("opportunities", sa.Column("brain_confidence", sa.Integer()))
    op.add_column("opportunities", sa.Column("evaluated_at", sa.DateTime(timezone=True)))
    op.add_column("opportunities", sa.Column("brain_version", sa.String(20)))
    op.create_check_constraint(
        "ck_opportunities_fit_score", "opportunities",
        "fit_score IS NULL OR fit_score BETWEEN 0 AND 100",
    )
    op.create_check_constraint(
        "ck_opportunities_brain_confidence", "opportunities",
        "brain_confidence IS NULL OR brain_confidence BETWEEN 0 AND 100",
    )


def downgrade() -> None:
    op.drop_constraint("ck_opportunities_brain_confidence", "opportunities", type_="check")
    op.drop_constraint("ck_opportunities_fit_score", "opportunities", type_="check")
    op.drop_column("opportunities", "brain_version")
    op.drop_column("opportunities", "evaluated_at")
    op.drop_column("opportunities", "brain_confidence")
    op.drop_column("opportunities", "fit_score")
