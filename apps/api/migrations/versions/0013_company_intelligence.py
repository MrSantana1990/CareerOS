"""Company Intelligence: careers/ATS/talent-pool resolution fields on companies."""

from alembic import op
import sqlalchemy as sa

revision = "0013_company_intelligence"
down_revision = "0012_seed_radars"


def upgrade() -> None:
    op.add_column("companies", sa.Column("careers_url", sa.String(500)))
    op.add_column("companies", sa.Column("ats_type", sa.String(40)))
    op.add_column("companies", sa.Column("official_recruiting_email", sa.String(254)))
    op.add_column("companies", sa.Column("talent_pool_url", sa.String(500)))
    op.add_column("companies", sa.Column("br_presence", sa.Boolean()))
    op.add_column("companies", sa.Column("last_checked_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("companies", "last_checked_at")
    op.drop_column("companies", "br_presence")
    op.drop_column("companies", "talent_pool_url")
    op.drop_column("companies", "official_recruiting_email")
    op.drop_column("companies", "ats_type")
    op.drop_column("companies", "careers_url")
