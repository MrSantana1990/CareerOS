"""Fase 2 (Prompt 13) - Multimodal Market Perception: expande o CHECK
constraint de opportunity_channels.type com 2 valores novos exigidos
pela QR Destination Resolution (Secao 10):

- RECRUITER_WHATSAPP: canal explicito de WhatsApp de recrutamento
  (achado real de benchmark humano - caso BMW Group TechWorks/ACT
  Digital, WhatsApp publicado como contato de candidatura). Nao existia
  NENHUM tipo de canal equivalente ate agora.
- EXTERNAL_ATS: um board de ATS real, mas hospedado fora do dominio da
  propria empresa (ex.: Refor Jobs, achado real do caso J&T Express) -
  distinto de OFFICIAL_ATS (que ja assume o board no proprio dominio/
  subdominio verificado da empresa, Prompt 11/12).

Puramente aditivo - nenhum valor existente e removido, nenhuma linha e
alterada.
"""

from alembic import op

revision = "0021_channel_whatsapp_ats"
down_revision = "0020_company_evidence"


def upgrade() -> None:
    op.drop_constraint("ck_opportunity_channels_type", "opportunity_channels", type_="check")
    op.create_check_constraint(
        "ck_opportunity_channels_type",
        "opportunity_channels",
        "type IN ('OFFICIAL_ATS','OFFICIAL_CAREERS','OFFICIAL_EMAIL','TALENT_POOL',"
        "'SPONTANEOUS_APPLICATION','RECRUITER_INSTRUCTION','ASSISTED','WATCH',"
        "'RECRUITER_WHATSAPP','EXTERNAL_ATS')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_opportunity_channels_type", "opportunity_channels", type_="check")
    op.create_check_constraint(
        "ck_opportunity_channels_type",
        "opportunity_channels",
        "type IN ('OFFICIAL_ATS','OFFICIAL_CAREERS','OFFICIAL_EMAIL','TALENT_POOL',"
        "'SPONTANEOUS_APPLICATION','RECRUITER_INSTRUCTION','ASSISTED','WATCH')",
    )
