"""Fase 2 (Prompt 11) - Company Intelligence: 1 coluna JSONB aditiva para
guardar evidence/confidence/verified_at de cada campo resolvido
(domain/careers_url/ats_type), no mesmo padrao ja usado por
jobs.structured_extraction (0015) e candidate_profiles.resume_evidence
(0018) - nunca dezenas de colunas novas quando um JSONB estruturado ja
resolve (Secao 13 do prompt: "Nao criar dezenas de colunas se evidence
JSON ja for suficiente").

companies.domain ja existe desde a migration 0002 (nunca populado ate
agora - achado real: 0/97 empresas). companies.last_checked_at (0013) ja
serve como cooldown/rate-limit generico para reprocessamento (Secao 20).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0020_company_evidence"
down_revision = "0019_job_canonical_dedup"

JSON = postgresql.JSONB()


def upgrade() -> None:
    op.add_column("companies", sa.Column("evidence", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")))


def downgrade() -> None:
    op.drop_column("companies", "evidence")
