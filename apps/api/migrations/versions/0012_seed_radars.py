"""Seed the three baseline radars described in the Plano Mestre (Fase 4).

Todos os radares nascem desligados (enabled=false) e em modo MANUAL - isso
so cria dados editaveis via /api/v1/radars; o automation-host ainda nao
consome essa tabela (fica para uma entrega separada). As regras semeadas
espelham os hard blocks que ja existem por texto livre em
apps/automation-host/src/hard_blocks.py, agora tambem como configuracao
consultavel, nao substituindo o codigo existente ainda.
"""

import json
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0012_seed_radars"
down_revision = "0011_radars_recruiters_calendar"

ORG_ID = "00000000-0000-0000-0000-000000000001"

RADARS = [
    {
        "code": "RADAR_SUPPORT",
        "label": "Suporte / Sustentação",
        "roles": [
            "Senior Support Analyst", "Application Support", "Production Support",
            "Sustentação", "Support Engineer", "Systems Analyst", "Backend Support",
            "Database Support", "Cloud Support", "Infraestrutura",
        ],
        "keywords": ["suporte", "sustentação", "n1", "n2", "n3", "n4", "support"],
        "sources": ["LINKEDIN", "INDEED", "CATHO", "INFOJOBS"],
        "languages": {},
        "rules": [
            {
                "code": "SUPPORT_N1_MINIMUM",
                "label": "Suporte N1 exige salário mínimo de R$4.000",
                "rule_type": "BLOCK",
                "configuration": {"level": "N1", "minimum_salary_brl": 4000},
                "priority": 10,
            },
        ],
    },
    {
        "code": "RADAR_DATA",
        "label": "Dados / DBA / BI",
        "roles": [
            "Data Analyst", "Analista de Dados", "DBA SQL Server", "DBA PostgreSQL",
            "DBA Oracle", "SQL Developer", "Database Analyst", "Database Specialist",
            "BI Analyst", "Power BI", "Data Engineer", "Azure Data Engineer",
            "AWS Data Engineer", "GCP Data Engineer", "BigQuery",
        ],
        "keywords": ["dados", "sql", "dba", "power bi", "data engineer", "bigquery"],
        "sources": ["LINKEDIN", "INDEED", "CATHO", "INFOJOBS"],
        "languages": {},
        "rules": [],
    },
    {
        "code": "RADAR_INTERNATIONAL",
        "label": "Internacional / Remoto Global",
        "roles": ["Support Engineer", "DBA", "Data Engineer", "Cloud Engineer"],
        "keywords": ["brazil remote", "latam", "worldwide", "contractor", "eor", "usd", "eur"],
        "sources": ["LINKEDIN", "GREENHOUSE", "LEVER", "ASHBY"],
        "languages": {"english_required_level": "C1", "spanish_required_level": "fluent"},
        "rules": [
            {
                "code": "RELOCATION_REQUIRED",
                "label": "Mudança de país/cidade obrigatória",
                "rule_type": "BLOCK",
                "configuration": {"trigger": "relocation_required"},
                "priority": 10,
            },
            {
                "code": "SPANISH_FLUENT_BLOCK",
                "label": "Espanhol fluente obrigatório",
                "rule_type": "BLOCK",
                "configuration": {"language": "spanish", "minimum_level": "fluent"},
                "priority": 20,
            },
            {
                "code": "ENGLISH_C1_REVIEW",
                "label": "Inglês C1/fluente exige revisão humana",
                "rule_type": "REVIEW",
                "configuration": {"language": "english", "minimum_level": "C1"},
                "priority": 30,
            },
        ],
    },
]


def upgrade() -> None:
    connection = op.get_bind()
    for radar in RADARS:
        radar_id = str(uuid.uuid4())
        result = connection.execute(
            sa.text(
                """
                INSERT INTO radars (id, organization_id, code, label, enabled, autonomy_mode,
                                     roles, keywords, sources, languages)
                VALUES (:id, :organization_id, :code, :label, false, 'MANUAL',
                        CAST(:roles AS jsonb), CAST(:keywords AS jsonb), CAST(:sources AS jsonb),
                        CAST(:languages AS jsonb))
                ON CONFLICT (organization_id, code) DO NOTHING
                RETURNING id
                """
            ),
            {
                "id": radar_id,
                "organization_id": ORG_ID,
                "code": radar["code"],
                "label": radar["label"],
                "roles": json.dumps(radar["roles"]),
                "keywords": json.dumps(radar["keywords"]),
                "sources": json.dumps(radar["sources"]),
                "languages": json.dumps(radar["languages"]),
            },
        )
        row = result.first()
        if row is None:
            continue
        for rule in radar["rules"]:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO radar_rules (id, organization_id, radar_id, code, label,
                                              rule_type, configuration, priority, enabled)
                    VALUES (:id, :organization_id, :radar_id, :code, :label, :rule_type,
                            CAST(:configuration AS jsonb), :priority, true)
                    ON CONFLICT (radar_id, code) DO NOTHING
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "organization_id": ORG_ID,
                    "radar_id": row.id,
                    "code": rule["code"],
                    "label": rule["label"],
                    "rule_type": rule["rule_type"],
                    "configuration": json.dumps(rule["configuration"]),
                    "priority": rule["priority"],
                },
            )


def downgrade() -> None:
    connection = op.get_bind()
    codes = [radar["code"] for radar in RADARS]
    connection.execute(
        sa.text(
            "DELETE FROM radar_rules WHERE organization_id = :organization_id "
            "AND radar_id IN (SELECT id FROM radars WHERE organization_id = :organization_id AND code = ANY(:codes))"
        ),
        {"organization_id": ORG_ID, "codes": codes},
    )
    connection.execute(
        sa.text("DELETE FROM radars WHERE organization_id = :organization_id AND code = ANY(:codes)"),
        {"organization_id": ORG_ID, "codes": codes},
    )
