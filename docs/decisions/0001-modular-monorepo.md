# ADR 0001 — Monorepo modular local-first

**Status:** aceito e implementado.

## Decisão

Usar Next.js para o painel, FastAPI para API e host de automação, Playwright no host Windows, IA local via llama.cpp, PostgreSQL/pgvector, Redis e worker em serviços separados. Gmail e Agenda usam OAuth oficial.

## Motivação

O Chrome precisa permanecer visível para login, MFA e intervenção. IA e dados profissionais devem ficar locais. Integrações externas precisam ser substituíveis sem acoplar o painel aos layouts das plataformas.

## Consequências

Fronteiras claras, operação auditável e privacidade maior, ao custo de múltiplos processos locais e manutenção contínua de seletores. Acesso por celular funciona na LAN, mas exige futuro hardening de autenticação e HTTPS.
