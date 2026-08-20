"""Initial explainable career rules for the personal workspace."""

from alembic import op

revision = "0003_initial_career_rules"
down_revision = "0002_career_domain"


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO career_rules
            (id, organization_id, code, label, rule_type, configuration, priority)
        VALUES
            (gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
             'SUPPORT_SENIOR_PRIORITY', 'Suporte sênior é prioridade máxima', 'BONUS',
             '{"families":["SUPPORT"],"seniority":["SENIOR","SPECIALIST"],"points":20}'::jsonb, 10),
            (gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
             'DBA_SQL_PRIORITY', 'DBA, SQL e sustentação têm prioridade alta', 'BONUS',
             '{"families":["DBA","SQL","SUPPORT"],"points":15}'::jsonb, 20),
            (gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
             'REMOTE_PRIORITY', 'Trabalho remoto recebe bônus', 'BONUS',
             '{"work_models":["REMOTE"],"points":15}'::jsonb, 30),
            (gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
             'SPANISH_FLUENT_BLOCK', 'Espanhol fluente obrigatório elimina a vaga', 'BLOCK',
             '{"language":"es","minimum":"FLUENT","when_required":true}'::jsonb, 40),
            (gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
             'ENGLISH_C1_REVIEW', 'Inglês C1 obrigatório exige revisão humana', 'REVIEW',
             '{"language":"en","minimum":"C1","when_required":true}'::jsonb, 50),
            (gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
             'GUPY_BLOCK', 'Gupy permanece bloqueada', 'BLOCK',
             '{"sources":["GUPY"],"domains":["gupy.io"]}'::jsonb, 60),
            (gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
             'QUALIFIED_DAILY_LIMIT', 'Limite diário considera somente vagas qualificadas',
             'THRESHOLD', '{"maximum":20,"minimum_fit":75}'::jsonb, 70)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM career_rules
        WHERE organization_id = '00000000-0000-0000-0000-000000000001'
          AND code IN (
            'SUPPORT_SENIOR_PRIORITY', 'DBA_SQL_PRIORITY', 'REMOTE_PRIORITY',
            'SPANISH_FLUENT_BLOCK', 'ENGLISH_C1_REVIEW', 'GUPY_BLOCK',
            'QUALIFIED_DAILY_LIMIT'
          )
        """
    )
