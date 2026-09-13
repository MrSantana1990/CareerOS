"""Fase 2 (Prompt 9.1) - Job Canonicalization & Dedup Repair.

Achado real de producao: 1 vaga real (Zeleno Meds) foi raspada 7 vezes com
parametros de tracking diferentes do LinkedIn e virou 7 linhas distintas em
`jobs`, porque `job_fingerprint` (quality.py) hasheia tokens do
`description` raspado - e o "description" do LinkedIn inclui UI/sidebar
volatil (contagem de candidaturas, "ha X dias", vagas similares no rodape)
que muda a cada nova raspagem da MESMA vaga real (comprovado: os 7
descriptions reais tem tamanhos diferentes - 8378 a 8588 caracteres).

Este e um problema de QUALIDADE DE DADOS, nao de schema - a correcao real
(preferir um provider job ID estavel extraido da URL) vive em
job_identity.py e no ingest. Esta migration so adiciona a capacidade de
MARCAR um Job como duplicata conhecida de outro, de forma 100% aditiva e
nao-destrutiva:

- Nenhuma linha e deletada.
- Nenhuma FK existente (job_scores/applications/decision_inbox/
  opportunities) e repontada - o historico real permanece exatamente como
  esta (Secao 6/7 do prompt: "preservar audit trail", "nunca perder
  evidencia de candidatura real").
- `dedup_status='CANONICAL'` e o default para TODA linha (existente ou
  nova) - nenhum comportamento existente muda ate uma reconciliacao
  explicita marcar um grupo confirmado como DUPLICATE.
- `canonical_job_id` e NULL exceto quando um Job foi confirmado (por
  `POST /jobs/reconcile-duplicates`, nunca automaticamente por um
  scheduler) como duplicata de outro - contagem de "quantas vezes esta
  vaga real foi observada" vira uma consulta simples
  (`count(*) WHERE canonical_job_id = X OR id = X`), sem precisar de
  tabela nova (Secao 10: JOB_OBSERVATION != CANONICAL_JOB).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0019_job_canonical_dedup"
down_revision = "0018_profile_evidence"

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("jobs", sa.Column("dedup_status", sa.String(20), nullable=False, server_default="CANONICAL"))
    op.add_column("jobs", sa.Column("canonical_job_id", UUID, nullable=True))
    op.create_check_constraint("ck_jobs_dedup_status", "jobs", "dedup_status IN ('CANONICAL', 'DUPLICATE')")
    op.create_foreign_key("fk_jobs_canonical_job_id", "jobs", "jobs", ["canonical_job_id"], ["id"],
                           ondelete="SET NULL")
    op.create_index("ix_jobs_canonical_job_id", "jobs", ["canonical_job_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_canonical_job_id", table_name="jobs")
    op.drop_constraint("fk_jobs_canonical_job_id", "jobs", type_="foreignkey")
    op.drop_constraint("ck_jobs_dedup_status", "jobs", type_="check")
    op.drop_column("jobs", "canonical_job_id")
    op.drop_column("jobs", "dedup_status")
