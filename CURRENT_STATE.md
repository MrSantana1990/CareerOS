# HelpSystem Career AI — Estado Atual

> Auditoria da Fase 0 · 20/08/2026 · produção `b15503a`

## Resumo executivo

O produto existente foi preservado. A fundação está saudável e contém autenticação, PWA, API, PostgreSQL, Redis, worker, perfil, currículo, regras, Caixa de Decisões e Google. Ainda não há descoberta real, score V2 completo, execução de candidaturas ou analytics.

## Matriz de componentes

| Componente | Status real | Localização | Dependências | Pendência | Ação incremental |
|---|---|---|---|---|---|
| Portal/PWA | Operacional | `apps/web/app` | Next.js, sessão | vagas sem fonte real | conectar ao Core |
| Login | Operacional | `apps/web/app/login`, `middleware.ts` | PBKDF2, HMAC | sem recuperação/2FA | hardening futuro |
| BFF protegido | Operacional | `apps/web/app/api/portal` | API, token server-side | cobertura parcial | ampliar por fatias |
| API Core | Operacional | `apps/api/src` | PostgreSQL | poucas rotas de domínio | Fase 1 |
| PostgreSQL | Operacional | migrations `0001`–`0004` | volume privado | modelo incompleto | migrations aditivas |
| Redis | Operacional | Compose | volume privado | fila quase sem tarefas | Fase 1/2 |
| Worker | Saudável, mínimo | `apps/worker/src/tasks.py` | Redis | somente `health_probe` | jobs idempotentes |
| Integrações | Operacional | `apps/automation-host` | Google, volume privado | mistura legado e VPS | separar gradualmente |
| Gmail/Agenda | Conectados | `google_career.py` | OAuth Google | correlação limitada | Fase 4 |
| Perfil | Operacional | `/api/v1/profile` | users/profiles | evidências incompletas | Fase 1 |
| Currículo | Operacional | `/api/v1/profile/resume` | `resume_data` | uma família geral | Fase 3 |
| Regras | 7 persistidas | migration `0003` | API | nem todo fluxo as aplica | Fase 1 |
| Decisões | Básico operacional | `decision_inbox` | jobs/scores | ações incompletas | Fase 1/3 |
| Score | Parcial/legado | `automation-host/main.py` | JSON local | não usa nove dimensões | Fase 1 |
| Discovery | Não operacional | legado local | navegador | zero vagas no Core | Fase 2 |
| Applications | Estrutura somente | tabelas/legado | jobs/currículo | zero no Core | Fase 3 |
| Auditoria | Estrutura básica | `audit_logs` | Core | eventos ausentes | Fase 1 |
| Push/Analytics | Não implementados | — | eventos históricos | infraestrutura ausente | Fases 4/6 |

## Produção confirmada

- Domínio `https://carreira.helpsystempro.site`; Cloudflare Tunnel comum, sem Zero Trust.
- Origem em `127.0.0.1:8093`.
- Seis serviços saudáveis: web, API, PostgreSQL, Redis, worker e integrations.
- Migration `0004_profile_storage (head)`.
- Quatro volumes: PostgreSQL, Redis, currículos e integrações.
- `.env` em modo `600`; valores não foram exibidos.
- Banco: 1 organização, 1 usuário, 1 perfil, 7 regras, 15 competências, 1 versão de currículo, 0 vagas e 0 candidaturas.
- Backup: `/opt/backups/helpsystempro-carreira/phase0-b15503a.dump`, modo `600`.

## Rotas e flags

O Core expõe saúde, status, workspace, perfil, currículo, regras e decisões. O portal possui login/logout e BFF para dashboard, perfil, currículo e decisões. Integrações expõem Google, estado e endpoints legados de Playwright.

Somente `AUTO_APPLY_ENABLED` e `AUTO_APPLY_SAFETY_ACKNOWLEDGED` existem no Core e permanecem desligadas. As demais flags da especificação ainda precisam ser modeladas.

## Preservação

As próximas fases devem usar migrations aditivas, manter volumes e `.env`, nunca executar `down -v` e validar restauração antes de mudanças destrutivas.
