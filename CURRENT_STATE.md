# HelpSystem Career AI — Estado Atual

> Fase 1 · 20/08/2026 · núcleo de qualidade pronto para produção

## Resumo executivo

O produto existente foi preservado. A fundação agora contém vagas normalizadas, fontes deduplicadas, Score V2 explicável, regras de bloqueio, pipeline de estados e eventos imutáveis. Descoberta real, execução de candidaturas e analytics permanecem nas fases seguintes.

## Matriz de componentes

| Componente | Status real | Localização | Dependências | Pendência | Ação incremental |
|---|---|---|---|---|---|
| Portal/PWA | Operacional | `apps/web/app` | Next.js, sessão | vagas sem fonte real | conectar ao Core |
| Login | Operacional | `apps/web/app/login`, `middleware.ts` | PBKDF2, HMAC | sem recuperação/2FA | hardening futuro |
| BFF protegido | Operacional | `apps/web/app/api/portal` | API, token server-side | cobertura parcial | ampliar por fatias |
| API Core | Operacional | `apps/api/src` | PostgreSQL | conectores ainda ausentes | Fase 2 |
| PostgreSQL | Operacional | migrations `0001`–`0005` | volume privado | adapters ausentes | migrations aditivas |
| Redis | Operacional | Compose | volume privado | fila quase sem tarefas | Fase 1/2 |
| Worker | Operacional | `apps/worker/src/tasks.py` | Redis/API | score desligado por flag | Fase 2 |
| Integrações | Operacional | `apps/automation-host` | Google, volume privado | mistura legado e VPS | separar gradualmente |
| Gmail/Agenda | Conectados | `google_career.py` | OAuth Google | correlação limitada | Fase 4 |
| Perfil | Operacional | `/api/v1/profile` | users/profiles | evidências incompletas | Fase 1 |
| Currículo | Operacional | `/api/v1/profile/resume` | `resume_data` | uma família geral | Fase 3 |
| Regras | 9 persistidas | migrations `0003`/`0005` | API | conectores ainda não as consomem | Fase 2 |
| Decisões | Básico operacional | `decision_inbox` | jobs/scores | ações incompletas | Fase 1/3 |
| Score | V2 operacional no Core | `apps/api/src/quality.py` | PostgreSQL | falta alimentação real | Fase 2 |
| Discovery | Não operacional | legado local | navegador | zero vagas no Core | Fase 2 |
| Applications | Estrutura somente | tabelas/legado | jobs/currículo | zero no Core | Fase 3 |
| Auditoria | Eventos append-only | `application_events` | Core | ampliar eventos externos | Fase 3/4 |
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

## Entregas das Fases 1 e 2

- ingestão de vaga com fingerprint determinístico e múltiplas fontes;
- Score V2 com nove dimensões, pontos fortes, lacunas, riscos e bloqueios;
- hard blocks prevalecem sobre a pontuação;
- transições de candidatura validadas por máquina de estados;
- eventos de candidatura protegidos contra alteração e exclusão;
- score reprocessável por worker sem duplicação;
- compatibilidade do estado legado `DRAFT` com `DISCOVERED`;
- flags granulares de automação, todas desligadas por padrão.
- adapters de leitura pública para Greenhouse, Lever e Ashby;
- cadastro persistente de fontes e histórico de varreduras;
- scheduler VPS-first com cadência mínima e limites por fonte;
- nenhuma fonte cadastrada ou automação habilitada automaticamente.

## Rotas e flags

O Core expõe saúde, status, workspace, perfil, currículo, regras e decisões. O portal possui login/logout e BFF para dashboard, perfil, currículo e decisões. Integrações expõem Google, estado e endpoints legados de Playwright.

O Core também expõe ingestão/listagem de vagas, cálculo de score e transição controlada de candidaturas. As flags de descoberta, score, candidatura por e-mail, candidatura por navegador, follow-up, agenda e push existem e permanecem desligadas por padrão.

## Preservação

As próximas fases devem usar migrations aditivas, manter volumes e `.env`, nunca executar `down -v` e validar restauração antes de mudanças destrutivas.

## Fase 3

- Resume Router por família profissional e idioma, usando apenas arquivos ativos e aprovados;
- Answer Memory persistida, verificada e acessível no portal;
- preparação idempotente por organização e vaga;
- estratégia segura entre e-mail publicado, ATS estruturado e revisão manual;
- aprovação humana obrigatória antes da criação do rascunho;
- integração privada cria rascunho Gmail com anexo, mas não envia;
- eventos imutáveis preservam preparação e aprovação;
- migration `0007_application_preparation` é aditiva e mantém todos os dados existentes.

## Fase 4

- comunicações de recrutamento persistidas e deduplicadas no PostgreSQL;
- correlação explicável por domínio, empresa e título da vaga;
- ambiguidades permanecem em revisão, sem associação forçada;
- entrevistas e propostas recebem prioridade urgente;
- central de notificações disponível no portal e no celular;
- follow-up apenas gera lembrete após sete dias sem resposta;
- nenhum e-mail ou candidatura é enviado automaticamente.

## Fase 5

- intervenções humanas persistidas no PostgreSQL com executor, motivo, evidências e resolução;
- deduplicação de alertas por candidatura legada e motivo;
- CAPTCHA, MFA, campos desconhecidos e envio não confirmado interrompem o fluxo;
- o executor não tenta resolver, contornar ou inventar respostas;
- central móvel permite abrir a página, concluir ou ignorar com registro;
- autoenvio e descoberta continuam desligados por padrão.
