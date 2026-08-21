# Roadmap

## Entregue

- Fase 0 — inventário, arquitetura VPS-first, análise de lacunas e backup.
- Fase 1 — vagas e fontes normalizadas, deduplicação, Score V2 explicável, hard blocks, máquina de estados, eventos imutáveis, worker idempotente e flags seguras.
- Fase 2 — adapters públicos Greenhouse, Lever e Ashby, fontes persistidas, scheduler conservador e histórico de descoberta.
- Fase 3 — Resume Router, Answer Memory verificada, preparação idempotente, rascunho de e-mail com aprovação humana e auditoria imutável.
- Fase 4 — correlação Gmail/candidatura, notificações priorizadas, histórico persistente e lembretes seguros de follow-up.
- Fase 5 — fila persistente de intervenção humana, bloqueios seguros para CAPTCHA/MFA e central móvel de resolução.
- Fundação — monorepo, Docker Compose, API, PostgreSQL, Redis, worker e observabilidade.
- Produto — login próprio, PWA mobile-first, perfil, competências, currículo versionado, regras e Caixa de Decisões.
- Integrações — Gmail e Google Calendar em serviço privado na VPS.

## Próximas fases

1. Fase 6 — analytics de conversão, riscos, recomendações e preparação comercial SaaS.

## Regra de evolução

Cada fase começa com backup, usa migrations aditivas, nasce desligada por feature flag e só chega à produção após CI, migration real, health checks e smoke tests. Plataformas externas mudam frequentemente; conectores devem permanecer isolados, auditáveis e reversíveis.
