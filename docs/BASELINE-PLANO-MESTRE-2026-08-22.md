# Baseline — Plano Mestre CareerOS (22/08/2026)

Este documento congela o estado do sistema **antes** de iniciar a execução do Plano Mestre de 37 fases (Bloco A/B/C/D). Serve como ponto de comparação para qualquer migration, mudança de schema ou unificação de pipeline feita a partir daqui.

> Nomenclatura: este plano usa "Bloco A/B/C/D — item N" para se referir às suas fases, **não** "Fase 0/1/2..." — esse numeral já é usado pelo `ROADMAP.md` existente (Fase 0–6, já implementada e mesclada) e reutilizá-lo geraria confusão entre dois planos diferentes.

## Serviços em produção (`deploy/vps/docker-compose.yml`, projeto `helpsystem-carreira`)

| Serviço | Build/Imagem | Papel | Volumes |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | Banco único do Core (`apps/api`) | `postgres_data:/var/lib/postgresql/data` |
| `redis` | `redis:7.4-alpine` | Fila do Dramatiq (`apps/worker`) | `redis_data:/data` |
| `api` | build `apps/api` | FastAPI — Core, única fonte com schema rico | `resume_data:/data/resumes` (rw) |
| `worker` | build `apps/worker` | Dramatiq — consome fila do Core | — |
| `scheduler` | build `apps/worker`, `python -m src.scheduler` | Agenda descoberta do Core | — |
| `integrations` | build `apps/automation-host` | Playwright — pipeline paralelo, baseado em JSON, é o que roda de verdade hoje | `integrations_data:/data/runtime` (rw), `resume_data:/data/resumes:ro` |
| `web` | build raiz, `apps/web/Dockerfile` | Painel (`carreira.helpsystempro.site`) | — |

Volumes nomeados a proteger em qualquer backup: `postgres_data`, `redis_data`, `resume_data`, `integrations_data`.

## Flags de automação hoje

Definidas em `apps/api/src/config.py` (Pydantic `Settings`, todas com default `False`) e replicadas via `os.getenv` sem módulo compartilhado em `apps/worker` e `apps/automation-host`:

| Flag | Onde é lida | Valor em produção (`deploy/vps/docker-compose.yml`) |
|---|---|---|
| `GLOBAL_AUTOMATION_ENABLED` | `apps/api/src/config.py` (nova, ainda sem lógica de gating) | `false` |
| `AUTO_APPLY_ENABLED` | `api`, `worker`, `integrations` (cada um lê separadamente) | `false` em todos — **corrigido nesta entrega**: o serviço `integrations` estava com `true` no arquivo versionado desde antes do incidente de 21/08/2026, enquanto a VPS já rodava com `false` por hotfix manual via SSH. Ver `HELPSYSTEM-CONTINUIDADE.md`, seção 18.21a |
| `AUTO_APPLY_SAFETY_ACKNOWLEDGED` | `api` | `false` |
| `AUTO_DISCOVERY_ENABLED` | `api`, `worker`, `scheduler` | `false` |
| `AUTO_SCORE_ENABLED` | `api`, `worker` | `false` |
| `AUTO_EMAIL_APPLY_ENABLED` | `api` | `false` |
| `AUTO_BROWSER_APPLY_ENABLED` | `api` | `false` |
| `AUTO_FOLLOWUP_ENABLED` | `api` | `false` |
| `AUTO_CALENDAR_ENABLED` | `api` | `false` |
| `PUSH_NOTIFICATIONS_ENABLED` | `api` | `false` |

Não existe hoje nenhum kill switch persistente (`PAUSE_*`) — isso é o item 6 do Bloco A, ainda não implementado. O único mecanismo de parada é o endpoint `POST /stop` do `automation-host` (`apps/automation-host/src/main.py`), que cancela só a execução em andamento, sem persistir estado.

## Schema atual (Alembic, `apps/api/migrations/versions/`)

Cadeia linear, 10 revisões, sem branches: `0001_foundation` → `0002_career_domain` → `0003_initial_career_rules` → `0004_profile_storage` → `0005_core_quality` → `0006_discovery_sources` → `0007_application_preparation` → `0008_communication_followup` → `0009_human_interventions` → `0010_analytics_goals` (revisão mais recente).

**Tabelas que já existem** e cobrem total ou parcialmente o que o Plano Mestre pede: `system_settings`, `audit_logs`, `organizations`, `users`, `candidate_profiles`, `career_rules`, `skills`, `skill_evidence`, `resumes`, `resume_versions`, `companies`, `jobs`, `job_scores`, `applications`, `decision_inbox`, `job_sources`, `application_events`, `source_connections`, `discovery_runs`, `application_questions`, `application_drafts`, `recruitment_communications`, `career_notifications`, `human_interventions`, `career_goals`.

**Tabelas que o Plano Mestre pede e ainda não existem** (precisarão de migration nova quando o item 3 — Source of Truth única — for planejado): `job_source_occurrences`, `radars`, `radar_rules`, `recruiters` (hoje só campos livres `recruiter_email`/`recruiter_name` em `jobs`), `candidate_skills` (mais próximo: `skills` + `skill_evidence`), `email_events` (mais próximo: `recruitment_communications`), `calendar_events`, `notifications` (mais próximo: `career_notifications`), `automation_runs` (mais próximo: `discovery_runs`).

Isso confirma o achado central da Auditoria Funcional de 21/08: o Core (`apps/api`) já tem um schema rico e maduro para praticamente tudo que o Plano Mestre descreve — o gap não é "construir do zero", é que o `automation-host` (o pipeline que roda de verdade hoje) nunca escreve nesse schema. O item 3 do Bloco A é sobre **conectar** os dois, não recriar o que já existe.

## Backup

Antes desta entrega não havia automação de backup — só a instrução manual em `deploy/vps/README.md`. `scripts/backup-postgres.sh` (adicionado nesta entrega) automatiza isso via `docker compose exec postgres pg_dump -Fc`, com timestamp e `chmod 600`, salvando em `/opt/backups/helpsystempro-carreira/`.

Um backup de baseline real (`--label baseline-plano-mestre`) deve ser gerado na VPS logo após o deploy desta entrega, antes de qualquer trabalho do item 3 em diante.
