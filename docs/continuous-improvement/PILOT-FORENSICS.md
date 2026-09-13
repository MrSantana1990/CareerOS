# Pilot Forensics — Prompt 7.1 (Autonomy Bottleneck Audit)

**Janela do Pilot analisada:** `2026-09-09T01:50:00Z` até `2026-09-13T01:41:00Z` (~4 dias corridos, sem nenhum redeploy no meio — todos os containers seguem "Up 4 days" na auditoria).

**Regra deste documento:** todo número aqui vem de consulta direta ao Postgres de produção ou ao log `automation-events.jsonl` do `automation-host`, com o timestamp da consulta registrado. Nenhum dado foi fabricado, nenhuma ação real foi disparada para produzir evidência.

---

## 1. Baseline (repetido do Prompt 7)

| Entidade | Baseline (09/09 01:50 UTC) |
|---|---|
| signals | 168 |
| jobs (structured_extraction) | 183 (0) |
| opportunities | 16 |
| applications | 111 (CONFIRMED=1) |
| human_interventions | 63 (10 pending) |

## 2. Evidência real de scheduler autônomo (2026-09-09 → 2026-09-12)

| Scheduler | Disparos naturais no Pilot | Timestamps reais |
|---|---|---|
| `market_scan_scheduler` | 4/4 dias, sempre ~06:00 UTC | 09-09 06:00:18 / 09-10 06:00:26 / 09-11 06:00:36 / 09-12 06:00:49 |
| `watch_recheck_scheduler` | 4/4 dias, sempre ~07:00 UTC | 09-09 07:00:18 / 09-10 07:00:21 / 09-11 07:00:25 / 09-12 07:00:32 |
| `daily_scheduler` | 12/12 janelas (3×4 dias), 08/12/18 UTC | confirmado nos 4 dias, sem falha |
| `google_mail_scheduler` | contínuo, ~10min | 2113 scans bem-sucedidos no total do log |
| `core_sync_scheduler` | contínuo | outbox/dead-letter = 0 durante todo o período |

O drift progressivo de segundos por dia (06:00:18 → 06:00:26 → 06:00:36 → 06:00:49) é a assinatura real de um loop `while True: sleep(60)` — não um evento fabricado.

## 3. O achado central

Durante os 4 dias: **96 Jobs novos** (100% com `structured_extraction`), **130 Signals novos** (96 `JOB_DISCOVERED` + 34 vindos do `market_scan`), **96/96 job_scores calculados**, **59 Applications tradicionais preparadas** (via `full_daily_pipeline`, sem passar por Opportunity/Brain) — mas **ZERO Opportunities novas**, **ZERO Application Plans novos**, **ZERO Channels novos resolvidos**, **ZERO intervenções novas do Action Engine**.

**Causa raiz confirmada no código**: nenhum scheduler registrado em `startup_scheduler()` (`daily_scheduler`, `google_mail_scheduler`, `core_sync_scheduler`, `market_scan_scheduler`, `watch_recheck_scheduler`) chama `POST /jobs/{id}/evaluate`, `POST /signals/{id}/evaluate` ou `POST /opportunities/{id}/action-plan`. Essas rotas (Prompts 4/5/6) existem, funcionam corretamente quando chamadas, e nunca são chamadas autonomamente.

## 4. Estrutura das duas linhagens de pipeline

Confirmado que hoje existem **dois pipelines paralelos**, sem ponte autônoma entre eles:

1. **Pipeline tradicional (`full_daily_pipeline`)**: Job → Score V2 → Prepare → Application (`job_id`). Autônomo, funcionando, produziu 59 applications reais no Pilot.
2. **Organismo Vivo (Fase 2)**: Signal/Job → Opportunity Brain → Action Engine → Opportunity/Application Plan (`opportunity_id`). Todos os componentes funcionam quando invocados manualmente/via API — nenhum é invocado autonomamente.

## 5. EXTERNAL MANUAL BENCHMARKS

### J&T Express — Analista de Dados Júnior (Nova Odessa/SP)

Classificação: **EXTERNAL_MANUAL_BENCHMARK / MISSED_OPPORTUNITY_EVIDENCE**. Não é entidade operacional do CareerOS — nenhum Signal, Job, Opportunity, Application ou Event foi criado para este caso, e nenhum será criado retroativamente.

Fluxo real executado 100% pelo usuário: LinkedIn (post/imagem) → leitura visual → QR Code → formulário externo → currículo anexado → candidatura enviada → confirmação vinculada a `helpsystempro@gmail.com`.

Usado exclusivamente como benchmark de percepção (ver Perception Gap Matrix no relatório principal).

## 5.1 ADENDO CRÍTICO — Gmail scanning quebrado durante o Pilot (achado em 13/09, 01:52 UTC)

Ao tentar reconfirmar o thread do Deutsche Bank (leitura, sem envio), a chamada real ao Gmail falhou:

```
google.auth.exceptions.RefreshError: ('invalid_grant: Token has been expired or revoked.', ...)
```

Investigação no log confirmou que isso **não é transitório**: o último `GOOGLE_MAIL_SCANNED` bem-sucedido foi em **2026-09-11 23:16:07 UTC**. Desde então, `GOOGLE_MAIL_SCAN_FAILED` (`RefreshError`) se repete a cada ~10min, **159 tentativas consecutivas** até o momento desta auditoria (2026-09-13 01:46:47 UTC, a última antes de agora) — mais de **26 horas contínuas de falha**, ainda ativa.

Causa raiz: o refresh token OAuth do Gmail foi revogado/expirado — mesma classe de problema já documentada no backlog para o InfoJobs ("renovar sessão"). **Não é corrigível por código** — exige reautorização humana real (fluxo de consentimento OAuth do Google), não uma correção cirúrgica de bug.

Impacto direto na auditoria: qualquer resposta real de recrutador chegada após 2026-09-11 23:16 UTC é **invisível ao Core** hoje. Os números de `RECRUITER_RESPONSES`/`INTERVIEWS` deste relatório cobrem com confiança apenas até esse instante — para o restante da janela do Pilot (~26h), a resposta correta é `UNKNOWN`, nunca `0`.

O mecanismo do scheduler (`google_mail_scheduler`) continua **AUTONOMOUS_OBSERVED** (dispara sozinho a cada ~10min, sem intervenção) — mas seu **resultado** está `FAILED` de forma contínua e ativa. Adicionado como item P0 no backlog.

## 6. Gaps comprovados (para o backlog)

1. **Não existe scheduler que conecta Perception → Opportunity Brain → Action Engine.** Todo o volume de Signals/Jobs autônomos fica represado sem nunca virar Opportunity. Este é o gargalo #1, confirmado por evidência direta (0 Opportunities em 4 dias com 130 Signals + 96 Jobs disponíveis).
2. **`structured_extraction` em vagas do LinkedIn captura texto de UI/sidebar, não do conteúdo real da vaga**, para os campos `location`/`work_model` extraídos via `keyword_regex` sobre o texto completo da página (ex.: `evidence_snippet` idêntico em vagas diferentes, batendo com rótulos de filtro de busca do LinkedIn como "Presencial ou Remoto ou Híbrido"). A coluna está populada (100%), mas o conteúdo de parte dos campos é de qualidade duvidosa nesta fonte especificamente.
3. **O sistema nunca visita o feed/posts do LinkedIn** (`main.py` só monta URLs de `/jobs/search/` e `/jobs/view/`) — vagas divulgadas só como post social/imagem são estruturalmente invisíveis hoje, independente de QR Code.
4. **Nenhuma dependência de imagem/OCR/QR/visão computacional existe no `automation-host`** — confirmado por ausência total no `pyproject.toml`.
5. **Correlação de e-mail depende de o Job/Application existir em Core com `company_domain` real** — 2 comunicações reais (TEMBICI, GRUPO GPS) chegaram e foram classificadas corretamente, mas ficaram `UNMATCHED` pela mesma razão estrutural do caso Randstad/Mercado Livre (Prompt 6): nenhuma Application correspondente existe no Core para essas empresas.

Estes 5 itens foram adicionados ao final de `IMPROVEMENT_BACKLOG.md` sob uma nova seção "Fase 2 — achados do Pilot (Prompt 7.1)".

---

## 7. OPPORTUNITY_ASSEMBLY_ARCHITECTURE (Prompt 8)

Resposta ao gargalo #1 da Seção 6: um novo scheduler, `opportunity_assembly_scheduler`, registrado em `startup_scheduler()` no `automation-host` (mesmo padrão de `market_scan_scheduler`/`watch_recheck_scheduler`), rodando a cada 15 minutos (não 1x/dia — Signals/Jobs chegam o dia inteiro). Ele **só orquestra rotas já existentes e testadas** (Prompts 4/5/6) via HTTP:

```
NEW/PENDING Job/Signal → POST /jobs/{id}/evaluate ou /signals/{id}/evaluate (Opportunity Brain)
  → se decisão ∈ {PREPARE, ACTIONABLE, HUMAN_REQUIRED}:
    → POST /opportunities/{id}/channels/discover (Channel Resolution)
    → POST /opportunities/{id}/action-plan (Action Engine, sempre DRY RUN)
```

Nenhuma lógica de eligibility/scoring/channel/policy foi recriada — o Brain e o Action Engine continuam sendo a única fonte de verdade dessas decisões.

**Checkpoint**: 100% derivado do Postgres, nunca de um watermark em memória — `GET /jobs?pending_evaluation=true` (`company_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM opportunities WHERE job_id=jobs.id)`) e `GET /signals?status=NEW` (já existente) filtrando `type != JOB_DISCOVERED` no scheduler. Sobrevive a restart/deploy/crash sem estado externo para perder — comprovado na prática nesta mesma validação (ver Seção 9: o container foi reiniciado por um redeploy no meio da validação e nenhum job foi reprocessado nem perdido).

**Exclusão deliberada de `JOB_DISCOVERED`** (Seção 11 do prompt): todo Signal `JOB_DISCOVERED` já tem o Job canônico correspondente, que produz sua própria Opportunity pelo caminho de Job — avaliar o Signal também duplicaria a Opportunity da mesma vaga real. Confirmado em produção: 0 duplicatas (ver Seção 9).

**Provenance**: novo parâmetro opcional `triggered_by` em `/jobs/{id}/evaluate` e `/signals/{id}/evaluate`, gravado em `evidence.orchestration` (jsonb, **nenhuma migration**) apenas quando informado. O scheduler passa `triggered_by=opportunity_assembly_scheduler`; qualquer chamada manual/futura sem esse parâmetro continua funcionando exatamente como antes.

**Coexistência com o pipeline tradicional** (Seção 12 do prompt, decisão explícita): **coexistir**, não substituir nem consumir. As duas linhagens operam sobre chaves estruturalmente disjuntas (`job_id` em `applications` vs `opportunity_id` em `opportunities`) — `full_daily_pipeline` continua intocado (nenhuma linha de código alterada em `daily_scheduler`/`full_daily_pipeline`), confirmado por teste de regressão (`test_traditional_pipeline_scheduler_is_untouched_by_opportunity_assembly`) e por contagem estável de `applications` (170, igual ao fim do Prompt 7.1) até o próximo ciclo natural do `daily_scheduler` (8/12/18h UTC).

## 8. AUTONOMY_LOOP

O loop PERCEIVE → REMEMBER → REASON → PLAN/ACTION agora fecha de ponta a ponta sem intervenção humana, até o ponto correto de parada (decisão do próprio Action Engine, nunca um bypass):

```
Job pendente (Perception, Prompts 3/8)
  → Opportunity Brain avalia (Prompt 4): eligibility/fit_score/hard_blocks/unknowns
  → Opportunity persistida com discovery_source=OPPORTUNITY_BRAIN + evidence.orchestration.triggered_by=opportunity_assembly_scheduler
  → Channel Resolution tenta resolver um canal real (Prompt 6)
  → Action Engine calcula Action Policy + Application Plan (Prompt 5), sempre DRY RUN
  → se autonomy_class=HUMAN_REQUIRED: Human Intervention criada (fila humana), NUNCA um envio automático
```

Nenhum passo aqui envia e-mail, submete formulário ou muda estado externo — `AUTO_APPLY_ENABLED` permanece `false` em ambos os containers (`api`, `integrations`), confirmado por leitura direta do ambiente de produção após o deploy.

## 9. GMAIL_HEALTH

Estado real classificado (função pura `classify_gmail_health`, valores HEALTHY/DEGRADED/AUTH_REQUIRED/DOWN): **`AUTH_REQUIRED`** — o refresh token OAuth do Gmail segue revogado/expirado (mesmo outage documentado na Seção 5.1), agora em **166 falhas consecutivas** no momento desta validação.

Causa raiz classificada por `classify_gmail_auth_failure_root_cause`: **`REFRESH_TOKEN_INVALID`** — o próprio Google não distingue "expirado" de "revogado" no corpo do erro (ambos chegam como `invalid_grant` idêntico), então reportar os dois juntos é a classificação honesta, não uma simplificação.

**Bug real encontrado e corrigido durante a validação em produção deste mesmo prompt** (PR #121, commit `bd04d18`): a primeira versão do gate de criação de intervenção usava `consecutive_failures == GOOGLE_HEALTH_ALERT_THRESHOLD` (3) — como esse contador persiste em disco entre restarts e o outage real já estava em 165 falhas antes deste deploy, ele nunca voltaria a cruzar o valor exato de 3, e a intervenção nunca seria criada para o outage já em curso. Corrigido para `>=` (dissociado do evento `GOOGLE_MAIL_AUTH_BROKEN`, que continua disparando só uma vez no cruzamento exato, para não inundar o log). Validado em produção logo em seguida: `GMAIL_REAUTH_INTERVENTION_CREATED` disparou e uma `human_interventions` real foi criada (`id=35bd5f41-e30e-4f72-9d44-9aad8f4ea33f`, `reason=AUTH_REQUIRED`, `status=PENDING`, `evidence.root_cause=REFRESH_TOKEN_INVALID`).

Nenhum retry silencioso infinito permanece sem sinal acionável para o humano — o scheduler continua tentando a cada 10 minutos (comportamento correto, o token pode ser renovado a qualquer momento por uma reautorização humana real), mas agora existe exatamente uma Human Intervention pendente e visível na fila, não 166 falhas silenciosas no log.

## 10. POST_PROMPT_8_METRICS

Consultado diretamente no Postgres de produção, ~15 minutos após o deploy (2 ciclos naturais completos do `opportunity_assembly_scheduler`, nenhum Job/Signal fabricado para a validação):

| Métrica | Valor | Observação |
|---|---|---|
| OPPORTUNITY_ASSEMBLY_RUNS | 2 (naturais, +mais a cada 15min) | ambos com `failed=0` |
| ITEMS_FOUND (cumulativo) | 61 | 32 + 29 |
| ITEMS_PROCESSED | 61 | 100% dos encontrados |
| OPPORTUNITIES_CREATED | 50 | limitado pelo batch de 25 jobs/ciclo |
| ELIGIBLE (fit_score calculado) | 50/50 | todas com `fit_score` do Score V2 reusado |
| CHANNELS_RESOLVED (tentativa) | 50 | 43 CAPTCHA_REQUIRED, 7 AUTH_REQUIRED — nenhum canal VERIFIED_AVAILABLE ainda nesta amostra |
| ACTION_PLANS_CREATED | 50 | todos DRY RUN |
| HUMAN_REQUIRED | 50/50 | consequência honesta de nenhum canal seguro disponível na amostra, não um bug |
| FAILED | 0 | |
| RETRIED | 0 (não aplicável — falha de item não tem retry automático, só isolamento) | |
| DUPLICATES_PREVENTED | confirmado 0 duplicatas reais (50 `job_id` distintos para 50 Opportunities, `SELECT job_id, count(*) ... HAVING count(*)>1` vazio) | |
| PRE_EXISTING_PENDING processados | 50 (todos — backlog de 269 Jobs pendentes acumulado desde antes deste deploy) | |
| POST_DEPLOY_NEW processados | 0 até o momento desta medição | nenhum Job novo chegou via `ingest_job`/`market_scan` na janela observada |
| Jobs pendentes restantes | 219 (de um backlog de 269) | será drenado em ciclos subsequentes, ~25/15min |
| EXTERNAL_ACTION_OCCURRED | NÃO | `applications.status IN (SENT,CONFIRMED)` inalterado (`CONFIRMED=1`, o mesmo caso histórico Deutsche Bank) |
| AUTO_APPLY_ENABLED | false (confirmado nos containers `api` e `integrations`) | |
| GMAIL_REAUTH_INTERVENTION | criada (ver Seção 9) | |
