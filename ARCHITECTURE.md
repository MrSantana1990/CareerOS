# HelpSystem Career AI — Arquitetura

> Arquitetura real e alvo incremental · Fase 0

## Princípio

O produto é **VPS-first**. Nenhum fluxo periódico depende do Windows. Interações inseguras ou impossíveis na VPS viram `MANUAL_REQUIRED` e são resolvidas pelo usuário no navegador ou celular.

## Produção atual

```text
Internet
  └─ Cloudflare Tunnel
      └─ 127.0.0.1:8093
          └─ web (Next.js/PWA + sessão + BFF)
              ├─ api (FastAPI Core)
              │   ├─ PostgreSQL/pgvector
              │   └─ currículo privado
              └─ integrations (FastAPI Google + legado Playwright)

Redis ── worker Dramatiq
```

Somente `web` publica porta, ligada ao loopback. PostgreSQL, Redis, API e integrações permanecem privadas. `integrations` possui saída para as APIs Google, mas nenhuma porta publicada.

## Limites de confiança

| Zona | Conteúdo | Regra |
|---|---|---|
| Navegador | sessão do portal | nunca recebe token administrativo |
| Web/BFF | sessão e chamadas internas | credencial somente server-side |
| Core | regras e domínio | isolamento por organização |
| Dados | PostgreSQL e volumes | sem portas públicas |
| Integrações | OAuth e mensagens | tokens fora do Git/frontend |
| Browser futuro | cookies/screenshots | processo e volume isolados |

## Persistência

- PostgreSQL é a fonte da verdade do domínio.
- Redis é broker transitório, nunca fonte da verdade.
- `resume_data` armazena currículos versionados.
- `integrations_data` armazena OAuth e cache Google.
- `.runtime` local é legado e não integra a arquitetura definitiva.

## Arquitetura alvo

```text
Scheduler → Queue → Workers idempotentes
     ├─ Source adapters → normalize → deduplicate → validate
     ├─ Score/Rules → Decision Inbox
     ├─ Resume/Answer routers → Application Strategy
     ├─ Email/ATS/Browser executors → submission verification
     └─ Gmail/Calendar/Notifications → pipeline/events/analytics
```

A prioridade é API autorizada, feed, página pública, parser HTTP e somente então navegador. Cada fonte e executor possui adapter próprio; não haverá script universal monolítico.

## Estados canônicos alvo

Vaga: `OPEN`, `UNCERTAIN`, `CLOSED`, `DUPLICATE`, `ALREADY_APPLIED`, `BLOCKED`, `MANUAL_REQUIRED`.

Aplicação: `DISCOVERED`, `VALIDATING`, `VALIDATED`, `QUALIFIED`, `WAITING_DECISION`, `PREPARING`, `READY`, `SUBMITTING`, `SENT`, `CONFIRMED`, `RECRUITER_RESPONSE`, `INTERVIEW`, `TECHNICAL_TEST`, `FINAL_STAGE`, `OFFER`, `REJECTED`, `CLOSED`, `DISCARDED`, `ERROR`.

## Autonomia

- `AUTO`: tarefa determinística, comprovada e de baixo risco.
- `ASSISTED`: decisão subjetiva ou de impacto vai para a Inbox.
- `MANUAL`: CAPTCHA, MFA, teste, vídeo, consentimento ou fato desconhecido.

Autoenvio só existe com as duas flags de segurança, regras validadas e canal autorizado. Confirmação do provedor é obrigatória antes de `SENT` ou `CONFIRMED`.

## Deploy e rollback

Deploy usa `main`, build, migrations transacionais, healthchecks e smoke tests públicos. Rollback de código usa imagem/commit anterior sem remover volumes. Migration destrutiva exige backup, restauração testada e plano específico. `down -v` é proibido em atualização comum.
