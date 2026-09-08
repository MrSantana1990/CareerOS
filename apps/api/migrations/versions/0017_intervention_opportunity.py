"""Fase 2 (Prompt 5) - Action Engine: 1 additive column so human_interventions
can reference an Opportunity directly, not only an Application.

human_interventions (migration 0009) already covers exactly the Human
Action Queue this prompt needs (dedup via evidence.deduplication_key,
status/resolution lifecycle, career_notifications wiring) - reused as-is,
not rebuilt. Its only gap: application_id is the sole foreign key, so a
profile-level intervention (e.g. "declare your language level") or an
Opportunity-level one that has no Application yet (PREPARE/HUMAN_REQUIRED
before any real submission attempt) had nowhere to point. Both columns
stay nullable - a pure profile-level intervention leaves both null.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0017_intervention_opportunity"
down_revision = "0016_opportunity_brain_decision"

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("human_interventions", sa.Column("opportunity_id", UUID))
    op.create_foreign_key(
        "fk_human_interventions_opportunity_id_opportunities",
        "human_interventions", "opportunities", ["opportunity_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_human_interventions_opportunity", "human_interventions", ["opportunity_id"])


def downgrade() -> None:
    op.drop_index("ix_human_interventions_opportunity", table_name="human_interventions")
    op.drop_constraint("fk_human_interventions_opportunity_id_opportunities",
                        "human_interventions", type_="foreignkey")
    op.drop_column("human_interventions", "opportunity_id")
