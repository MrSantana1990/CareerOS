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

## 6. Gaps comprovados (para o backlog)

1. **Não existe scheduler que conecta Perception → Opportunity Brain → Action Engine.** Todo o volume de Signals/Jobs autônomos fica represado sem nunca virar Opportunity. Este é o gargalo #1, confirmado por evidência direta (0 Opportunities em 4 dias com 130 Signals + 96 Jobs disponíveis).
2. **`structured_extraction` em vagas do LinkedIn captura texto de UI/sidebar, não do conteúdo real da vaga**, para os campos `location`/`work_model` extraídos via `keyword_regex` sobre o texto completo da página (ex.: `evidence_snippet` idêntico em vagas diferentes, batendo com rótulos de filtro de busca do LinkedIn como "Presencial ou Remoto ou Híbrido"). A coluna está populada (100%), mas o conteúdo de parte dos campos é de qualidade duvidosa nesta fonte especificamente.
3. **O sistema nunca visita o feed/posts do LinkedIn** (`main.py` só monta URLs de `/jobs/search/` e `/jobs/view/`) — vagas divulgadas só como post social/imagem são estruturalmente invisíveis hoje, independente de QR Code.
4. **Nenhuma dependência de imagem/OCR/QR/visão computacional existe no `automation-host`** — confirmado por ausência total no `pyproject.toml`.
5. **Correlação de e-mail depende de o Job/Application existir em Core com `company_domain` real** — 2 comunicações reais (TEMBICI, GRUPO GPS) chegaram e foram classificadas corretamente, mas ficaram `UNMATCHED` pela mesma razão estrutural do caso Randstad/Mercado Livre (Prompt 6): nenhuma Application correspondente existe no Core para essas empresas.

Estes 5 itens foram adicionados ao final de `IMPROVEMENT_BACKLOG.md` sob uma nova seção "Fase 2 — achados do Pilot (Prompt 7.1)".
