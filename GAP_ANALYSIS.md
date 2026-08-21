# HelpSystem Career AI — Análise de Lacunas

> Produção `b15503a` versus especificação VPS-first

## Resultado

A fundação é aproveitável; o projeto não deve ser reconstruído. A lacuna principal é que identidade e regras estão no Core, mas descoberta, score e aplicações ainda existem como legado JSON/Playwright e não alimentam o PostgreSQL.

## Lacunas priorizadas

| Prioridade | Lacuna | Impacto | Fase | Resposta |
|---|---|---|---|---|
| P0 | Modelo de vaga incompleto | impede conectores | 1 | migration aditiva |
| P0 | Score V2 não persistido | decisão inconsistente | 1 | motor testado |
| P0 | Estados/eventos ausentes | pouca rastreabilidade | 1 | eventos imutáveis |
| P0 | Worker sem tarefas de negócio | não opera continuamente | 1 | jobs idempotentes |
| P0 | Regras não governam todo fluxo | bloqueios podem ser ignorados | 1 | avaliador único |
| P1 | Sem adapters | zero vagas no Core | 2 | Greenhouse/Lever/Ashby |
| P1 | Deduplicação incompleta | risco de reaplicação | 1/2 | fingerprint + fontes |
| P1 | Resume Router e Answer Memory ausentes | personalização insegura | 3 | famílias/respostas aprovadas |
| P1 | Confirmação incompleta | falso positivo de envio | 3 | provider ID/evidência |
| P1 | Gmail sem correlação completa | pipeline manual | 4 | correlacionador/eventos |
| P2 | Push e analytics ausentes | reação/aprendizado limitados | 4/6 | notifications/agregações |
| P2 | Browser não isolado | risco operacional | 5 | Chromium dedicado |
| P2 | Sem staging | risco de envio em teste | transversal | ambiente/flags separados |

## Dívidas e divergências

- `deploy/vps/README.md` ainda menciona Access; produção usa login próprio.
- documentação antiga era local-first; `ARCHITECTURE.md` agora define VPS-first.
- `automation-host` mistura Google, JSON, IA e navegador.
- CI não constrói explicitamente a imagem de integrations.
- testes não cobrem regras, isolamento, perfil ou decisões.
- faltam CSRF dedicado, rate limiting, CSP completa, `/health/deep`, fila observável e restore test automatizado.

## Riscos

1. Termos e bloqueios das plataformas.
2. Reenvio após timeout sem confirmação.
3. Cookies/OAuth expostos por volume ou log.
4. Prompt injection em vagas/formulários.
5. Score baseado em dados não verificados.
6. Retenção indefinida de documentos e mensagens.
7. Backup sem cópia externa confirmada.

## Plano aprovado

1. Fase 1: schema normalizado, regras, score, estados, eventos e worker.
2. Fase 2: adapters autorizados e deduplicação.
3. Fase 3: currículos, respostas, e-mail/ATS e confirmação.
4. Fase 4: Gmail/Calendar completos, follow-up e push.
5. Fase 5: Playwright isolado e intervenção manual.
6. Fase 6: analytics e recomendações.

## Guardrails da Fase 1

- backup e rollback antes da migration;
- nenhuma alteração destrutiva;
- preservar IDs e dados;
- hard block prevalece sobre score;
- testes de score, regras, deduplicação e estados;
- integração PostgreSQL/Redis;
- flags novas começam desligadas;
- produção somente após CI, migration, health e smoke tests.

## Fase 0 concluída quando

Inventário, arquitetura e gaps estiverem publicados; backup protegido existir; nenhuma feature, migration ou dado de produção tiver sido alterado.
