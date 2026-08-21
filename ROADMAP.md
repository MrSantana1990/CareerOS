# Roadmap

## Entregue

- Fase 0 — inventário, arquitetura VPS-first, análise de lacunas e backup.
- Fase 1 — vagas e fontes normalizadas, deduplicação, Score V2 explicável, hard blocks, máquina de estados, eventos imutáveis, worker idempotente e flags seguras.
- Fundação — monorepo, Docker Compose, API, PostgreSQL, Redis, worker e observabilidade.
- Produto — login próprio, PWA mobile-first, perfil, competências, currículo versionado, regras e Caixa de Decisões.
- Integrações — Gmail e Google Calendar em serviço privado na VPS.

## Próximas fases

1. Fase 2 — adapters autorizados para fontes estruturadas, normalização e ingestão contínua no Core.
2. Fase 3 — Resume Router, Answer Memory aprovada, candidatura assistida por e-mail/ATS e confirmação comprovada.
3. Fase 4 — correlação Gmail/Agenda, follow-up e notificações push.
4. Fase 5 — executor Playwright isolado, seleção versionada e intervenção humana para CAPTCHA/MFA.
5. Fase 6 — analytics de conversão, riscos, recomendações e preparação comercial SaaS.

## Regra de evolução

Cada fase começa com backup, usa migrations aditivas, nasce desligada por feature flag e só chega à produção após CI, migration real, health checks e smoke tests. Plataformas externas mudam frequentemente; conectores devem permanecer isolados, auditáveis e reversíveis.
