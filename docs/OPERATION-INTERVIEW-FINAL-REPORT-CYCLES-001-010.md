# Operation Interview — Final Report (Cycles 001–010)

**Data:** 2026-09-06
**Escopo:** consolidação de 10 ciclos de melhoria contínua (`docs/continuous-improvement/cycles/`), do estado em 04/09/2026 até este checkpoint estratégico obrigatório.

Este relatório encerra a Operation Interview até decisão do usuário sobre a próxima fase. Nenhum Cycle 011 foi iniciado.

---

## A. Estado inicial (04/09/2026)

Dois pipelines paralelos que nunca trocavam dados: `automation-host` (Playwright, roda sozinho, achava vagas de verdade) e o Core/Postgres (schema rico, zero vagas/scores/candidaturas reais). Gmail quebrado há 13 dias (OAuth expirado) — um convite real de entrevista (Randstad/Mercado Livre) parado sem detecção. 49% das candidaturas falhando por OOM. Zero candidatura já havia chegado a `CONFIRMED`.

## B. Estado final (06/09/2026)

`CONFIRMED: 0 → 1` (Deutsche Bank Brasil, candidatura espontânea por e-mail, evidência real de envio). CI/CD completo e automático (merge → deploy → validação, sem depender de acesso SSH de nenhuma sessão de agente). Gmail restaurado e validado (ciclo natural funcionando). 0 crashes OOM em lotes reais pós-fix. Fila de ação humana real, enriquecida e vinculada à candidatura de verdade. Piso salarial universal (`MINIMUM_SALARY_BLOCK`) protegendo contra SCORE mascarar ELIGIBILITY. Descoberta de oportunidade deixou de depender exclusivamente de LinkedIn/Catho/InfoJobs — Company Intelligence provou (uma vez) encontrar e converter uma oportunidade por rota independente.

## C. Arquitetura atual

```
automation-host (Playwright, VPS, Xvfb)          Core/Postgres (fonte da verdade)
  discovery (LinkedIn/Catho/InfoJobs)     ─┐
  ATS detection (Greenhouse/Lever/Ashby)   │──▶ core_bridge.py (outbox, idempotente,
  email discovery + Gmail (send real)      │     backoff, dead-letter) ──▶ POST /jobs
  reply_tracking.py (bounce/auto-reply)   ─┘     → score → prepare (Resume Router) →
                                                   transition (Eligibility/Quality)

CI (Qualidade): PR + push/main → lint + testes (api/worker/automation-host) +
  alembic real + build de 4 imagens Docker
CD (Deploy VPS): workflow_run após CI verde → SSH com chave dedicada →
  backup Postgres → git reset --hard → build/up → health check de todos os
  serviços → rollback automático em falha
```

Company Intelligence (Cycle 009): `companies` ganhou `careers_url`/`ats_type`/
`official_recruiting_email`/`talent_pool_url`/`br_presence`. `GET`/`PATCH /companies`.

## D. Bugs reais encontrados (não exaustivo — ver `KNOWN_ISSUES.md` para causa raiz de cada um)

1. OOM por reaproveitamento de página do Chrome (49%/48% das candidaturas) — 2 ocorrências (prepare e inspect).
2. Gmail: token OAuth expirado + bug de cota (reprocessava ~350 mensagens/rodada).
3. Relocation implícito não bloqueado (vaga presencial no exterior sem a palavra "relocation").
4. Issue #73: reCAPTCHA Enterprise invisível nunca detectado (`INTERVENTION_PATTERNS` só olhava texto visível).
5. `human_interventions.application_id` sempre `None` — fila de ação humana sem vínculo real.
6. `MINIMUM_SALARY_BLOCK` ausente para qualquer família fora de "support" — candidato com `salary_brl=1500` passava sem bloqueio.
7. `detect_email_application`/`detect_ats` descobriam dado real e nunca chegavam ao Core.
8. Nenhuma distinção entre bounce/auto-reply e resposta humana real no tracking de e-mail.
9. `Chrome --remote-debugging-address=0.0.0.0` silenciosamente ignorado pelo próprio Chrome (endurecimento de segurança do navegador) — descoberto durante a tentativa (revertida) de bridge CDP.
10. CI quebrado por um teste que importava um módulo com dependência pesada não instalada na perna de testes do automation-host.

## E. Fixes / regressões

Cada bug acima tem PR, teste de regressão e validação real documentados no cycle correspondente. Nenhuma regressão nova foi introduzida sem teste cobrindo o caso.

## F. CI/CD

Antes: CI completo, mas deploy 100% manual via SSH interativo de uma sessão de agente — dependência estrutural incorreta. Depois (Cycle 006, PR #94): `deploy.yml` dispara automaticamente via `workflow_run` após CI verde em `main`, chave SSH dedicada só para CD (nunca a mesma de acesso interativo), backup → build → health check de todo serviço → rollback automático em falha. Validado ao vivo múltiplas vezes nesta sessão (PRs #94 a #103, todos com deploy automático confirmado).

## G. Applications (estado real em produção, 06/09/2026)

```
Total: 814 | FAILED: 503 | READY_FOR_REVIEW: 132 | BLOCKED: 92 |
READY_TO_PREPARE: 40 | MANUAL_REQUIRED: 38 | CLOSED: 9
Por fonte: LinkedIn 597, Catho 114, InfoJobs 103
Core (Postgres): jobs=123, job_scores=120, applications: READY=18, PREPARING=42, ERROR=13, MANUAL_REQUIRED=3
```

## H. First CONFIRMED

```
FIRST_CONFIRMED_AT:      2026-09-06T08:58:46Z
COMPANY:                 Deutsche Bank Brasil
OPPORTUNITY_TYPE:        SPONTANEOUS_APPLICATION
DISCOVERY_SOURCE:        COMPANY_INTELLIGENCE
APPLICATION_CHANNEL:     EMAIL (recursos.humanos@db.com, publicado oficialmente em country.db.com)
RESUME_FAMILY:           GENERAL (pt-BR, único aprovado)
GMAIL_MESSAGE_ID:        1a075f10df38136e
GMAIL_THREAD_ID:         1a075f10df38136e
EVIDENCE:                labelIds=["SENT"] confirmado por leitura independente da API do
                         Gmail (não só a resposta do próprio envio) — To header e Subject
                         conferidos.
```

Nenhuma experiência, idioma, formação ou dado foi inventado no conteúdo da mensagem — só afirmações já presentes e aprovadas no currículo.

## I. Canais testados

| Canal | Estado | Observação |
|---|---|---|
| LinkedIn (External Apply) | `ASSISTED` (reCAPTCHA legítimo) | 2 candidatos reais no cap de tentativas (Exadel, Analista BI II) |
| InfoJobs | `AUTH_REQUIRED` | Parede de sessão; tentativa de bridge CDP revertida por decisão de segurança |
| Catho | Estoque atual majoritariamente contaminado (candidaturas antigas pré-existentes no perfil) | 5/5 amostrados já tinham "CV enviado!" |
| Gupy | Bloqueado por regra explícita do produto | Nunca perseguido |
| Greenhouse/Lever/Ashby (Company Intelligence) | Testados em ~28 empresas | 1 CONFIRMED (Deutsche Bank, canal EMAIL — não ATS); vários `STALE`/`GEO_BLOCKED`/`SKILL_MISMATCH` |
| E-mail oficial (spontaneous/talent pool) | **Provado uma vez** | Deutsche Bank Brasil |

## J. Discovery sources testados

LinkedIn/Catho/InfoJobs (job boards tradicionais) — exauridos/bloqueados nos 3. Job aggregators (Jobgether, WeWorkRemotely, RemoteRocketship, BuiltIn) — taxa de stale alta (36% no sample combinado de 28). Company-first (busca direta em board oficial) — mais confiável, mas trabalhoso (Workday não responde a filtro por URL, Ashby/Lever exigem navegador real). Signal-based (notícias de expansão/investimento) — 3 sinais reais encontrados (Nubank Campinas, TIP Brasil, DPaschoal), nenhum convertido ainda (`WATCH`).

## K. Pontos de intervenção humana

```
INFOJOBS_AUTH_REQUIRED         — pendente, ação humana necessária
LINKEDIN_ASSISTED_EXADEL       — reCAPTCHA, attempts=3/3, ação humana necessária
LINKEDIN_ASSISTED_BI_II        — reCAPTCHA, attempts=3/3, ação humana necessária
Randstad/Mercado Livre (e-mail)— decisão humana pendente desde Cycle 001, ainda sem resposta do usuário
human_interventions PENDING    — 15 no total em produção (2 CAPTCHA, 6 UNKNOWN_FIELD, 7 SUBMISSION_UNCONFIRMED) —
                                  a maioria gerada pelo scheduler rotineiro, independente destes ciclos
```

## L. Funil de conversão (estado real)

```
DISCOVERED → ELIGIBLE/SCORED → PREPARED → SUBMITTED → CONFIRMED → RECRUITER_RESPONSE → INTERVIEW → OFFER → HIRED
  2.887+        123 (Core)      132        1 (e-mail)     1            0               0          0       0
```

## M. Recruiter responses

`0`. Não fabricado.

## N. Interviews

`0` novas geradas por este pipeline. A única entrevista real conhecida (Randstad/Mercado Livre) veio de um processo anterior, detectada só depois do Gmail ser restaurado (Cycle 001), e segue sem resposta humana à convocação.

## O. Blockers

Ver `KNOWN_ISSUES.md` para detalhe completo de cada um: InfoJobs (auth), LinkedIn (reCAPTCHA legítimo), Catho (contaminação de estoque), Gupy (bloqueio de produto), inglês fluente exigido em vagas internacionais elegíveis, stacks modernos (dbt/Airflow/Snowflake/Go/Kubernetes) exigidos onde o candidato não tem experiência real.

## P. Career Gap Intelligence (consolidado, Cycles 008–010)

**MARKET/CANDIDATE GAP** (do candidato/mercado, não da automação):
- `ENGLISH_FLUENCY` — nível real "em evolução"; bloqueou os 2 únicos achados live+oficiais+não-Gupy com fit técnico real (NPS Prism Product Data Analyst, Wellhub BI Analytics Senior).
- `CORE_SKILL` — stacks modernos (dbt/Airflow/Snowflake/BigQuery, Go/Kubernetes/gRPC) nas vagas internacionais de "Data Engineer"/"Platform Engineer" mais bem pagas encontradas; o candidato tem SQL Server/PostgreSQL/Oracle/Java/produção tradicional, não ELT/cloud-native moderno.
- `LOCATION/WORK_MODEL` — vagas presenciais 100% em São Paulo (C6 Bank) inviáveis a partir de Campinas.

**AUTOMATION/CHANNEL FRICTION** (da automação/canal, não do candidato):
- `CAPTCHA` (LinkedIn, legítimo, nunca contornado).
- `AUTH` (InfoJobs).
- `STALE` (36% de taxa em agregadores de vaga).
- `BOT_GATED` (portal próprio da Nubank; corretamente não contornado).
- `GUPY_BLOCK` (regra de produto, não uma falha).

## Q. O que está provado

- CI/CD completo, automático, com rollback real — validado repetidamente.
- Loop de melhoria contínua real (observar → causa raiz → fix → teste → regressão → merge → CD → validação) — ~15 bugs reais corrigidos assim nesta sessão.
- Company Intelligence **pode** produzir um CONFIRMED real e verificável, fora dos 3 canais tradicionais — uma vez.
- Disciplina de integridade (SCORE != ELIGIBILITY, nunca inventar stack/idioma/experiência) segurou sob pressão real (CharterUP $6-7k/mês, TigerData, C6 Bank) — nenhuma candidatura forçada só para gerar KPI.
- Arquitetura de segurança (attempts cap, nunca Agibank, nunca CAPTCHA/MFA contornado) segurou mesmo quando uma abordagem inteira (CDP bridge) precisou ser revertida.
- Tracking agora distingue bounce/auto-reply de resposta humana real (RFC 3834 `Auto-Submitted`).

## R. O que NÃO está provado

- Repetibilidade da rota Company Intelligence → EMAIL em escala — tentada de novo (5 empresas), 0 segundo CONFIRMED.
- `RECRUITER_RESPONSE >= 1` — zero até agora; só 1 dia se passou desde o único envio.
- `INTERVIEW >= 1` novo — zero.
- Resume Router além de `GENERAL` — só existe 1 família de currículo aprovada no Core hoje; a lógica de seleção multi-família nunca foi exercida com dados reais.
- Follow-up de verdade (só a elegibilidade foi implementada; nenhum follow-up foi enviado ainda, corretamente).
- Talent pool / spontaneous via ATS (só via e-mail foi testado).

## S. Technical debt

- `applications` (Core) exige `job_id` — uma candidatura espontânea sem vaga específica (o próprio Deutsche Bank) não tem onde morar como registro estruturado; vive só como evidência de Gmail + documentação.
- Só 1 resume family aprovada — Resume Router pronto, mas sem conteúdo real pra escolher.
- Nenhuma entidade SIGNAL/OPPORTUNITY/WATCH persistida no Core — os 3 sinais reais encontrados (Nubank, TIP Brasil, DPaschoal) só existem nesta conversa/relatório.
- `human_interventions` PENDING cresceu para 15 em produção, fora do escopo direto destes ciclos.

## T. Recomendação para a próxima fase (não implementar ainda)

1. Decisão do usuário sobre InfoJobs (via suportada, não CDP genérico) e sobre os 2 LinkedIn no cap — desbloqueiam o maior volume de estoque já preparado (95+ candidaturas `READY_FOR_REVIEW`).
2. Decisão sobre aprovar uma segunda família de currículo real, para testar o Resume Router de verdade.
3. Se a direção for continuar Company Intelligence: persistir SIGNAL/COMPANY/OPPORTUNITY no Core (não só em relatório) antes de escalar o sample.
4. Decisão sobre o e-mail do Randstad/Mercado Livre, pendente desde Cycle 001.
5. Arquitetura permanente do "Organismo Vivo de Carreira" (Market → Signal → Company → Opportunity → Job Discovery → Channel Resolution → Application → Tracking → Follow-up → Response → Interview → Offer → Hire → Conversion Learning → Career Gap Intelligence) segue como visão válida — este relatório prova a fatia mínima (Company Intelligence → Email → CONFIRMED) funciona; a decisão de expandi-la é do usuário.

## U. Cycles 001–010 (índice)

| Cycle | Foco | PR(s) |
|---|---|---|
| 001 | Baseline real + OOM #1 + Gmail | #80, #82, #83 |
| 002 | OOM #2 (inspect_application_queue) | #85 |
| 003 | Conversion Lane, gargalo #3 (relocation), Issue #73 (1ª ocorrência) | #87 |
| 004 | Direct Conversion Lane, auditoria e-mail/ATS, contaminação Catho | — |
| 005 | Issue #73 causa raiz (reCAPTCHA Enterprise) | #90 |
| 006 | Human-in-the-loop: fila de ação humana vinculada | #92 |
| 007 | SCORE != ELIGIBILITY (piso salarial); CDP revertido; LinkedIn no cap | #94–#101 |
| 008 | Expand Conversion Surface (company-first, 28 empresas, 0 eligible high-fit) | — |
| 009 | Opportunity Intelligence: email/ATS→Core, **CONFIRMED 0→1** | #102 |
| 010 | Tracking (bounce vs. resposta real), follow-up, repeatability (0 novo) | #103 |

---

**Fim do Operation Interview. Cycle 011 não iniciado. Aguardando decisão do usuário.**
