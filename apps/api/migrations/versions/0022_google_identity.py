"""Google Sign-In (Fase 2 - Adendo de Autenticacao).

GOOGLE LOGIN != GMAIL INTEGRATION (Secao 2 do prompt) - esta migration
so acrescenta os campos de IDENTIDADE necessarios para login via Google
OIDC (openid/email/profile) na tabela `users` JA EXISTENTE (migration
0002 - "candidate_profiles"/"users" e o registro do dono da carreira,
nao um sistema de auth ate agora: nenhuma linha aqui tem qualquer relacao
com o token/refresh_token do Gmail em google_career.py/scripts/authorize-
google.py, que continuam 100% separados). Nunca cria uma tabela paralela
(Secao 4: "nao criar sistema paralelo se ja houver Users/Auth").

- auth_provider / provider_subject: identificador canonico externo e o
  Google `sub` (Secao 4: "o identificador canonico externo deve ser
  Google sub e nao apenas email" - email pode mudar, sub nao).
- email_verified: vem do proprio id_token do Google, nunca inferido.
- avatar_url: opcional, so quando o Google devolve.

Indice unico PARCIAL (so quando provider_subject nao e nulo) permite
que linhas antigas sem nenhum provider vinculado (o registro de perfil
ja existente, sem login algum ainda) continuem existindo sem conflito.
"""

from alembic import op
import sqlalchemy as sa

revision = "0022_google_identity"
down_revision = "0021_channel_whatsapp_ats"


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_provider", sa.String(20)))
    op.add_column("users", sa.Column("provider_subject", sa.String(255)))
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("avatar_url", sa.String(500)))
    op.create_check_constraint(
        "ck_users_auth_provider", "users", "auth_provider IS NULL OR auth_provider IN ('GOOGLE')",
    )
    op.create_index(
        "ux_users_provider_identity", "users", ["auth_provider", "provider_subject"],
        unique=True, postgresql_where=sa.text("provider_subject IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_users_provider_identity", table_name="users")
    op.drop_constraint("ck_users_auth_provider", "users", type_="check")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "provider_subject")
    op.drop_column("users", "auth_provider")
