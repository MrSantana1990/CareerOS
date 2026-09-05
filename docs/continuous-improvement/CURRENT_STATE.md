# Estado real do funil — 05/09/2026

Atualizado após o Cycle 006 (Human-in-the-loop Conversion). Ver histórico da validação P0 (23-24/08) referenciado em `HELPSYSTEM-CONTINUIDADE.md`. Este arquivo reflete o que foi **comprovado com evidência real**, não o que foi desenhado em `V2-CAREER-INTELLIGENCE.md`.

## Baseline objetivo (produção real, 05/09/2026, pós-Cycle 006)

| Métrica | Valor |
|---|---|
| Vagas descobertas (histórico) | 2.887 |
| Vagas qualificadas (`APPROVED_AUTO`) | 693 |
| Candidaturas totais | 693 |
| Candidaturas `FAILED` | 503 |
| Candidaturas `READY_FOR_REVIEW` (PREPARED) | 95 — 71 LinkedIn (assistido, reCAPTCHA), 15 InfoJobs (reauth pendente), 9 Catho (checar contaminação antes de enviar) |
| Candidaturas `BLOCKED` | 74 |
| Candidaturas `MANUAL_REQUIRED` | 24 — 1 com intervenção `PENDING` real na fila (Cycle 006) |
| Candidaturas `READY_TO_PREPARE` | 29 |
| Candidaturas `CLOSED` | 9 |
| **Candidaturas `APPLIED`/`CONFIRMED`** | **0** |
| Respostas de recrutador | 1 entrevista real detectada (Randstad/Mercado Livre) + múltiplas confirmações de candidatura — Gmail restaurado no Cycle 001 |
| Entrevistas | 1 detectada, aguardando resposta humana |
| Ofertas | não mensurado |
| Contratações | não mensurado |

## Funil, estágio por estágio

| Estágio | Estado | Evidência |
|---|---|---|
| Discovery | **OK** | 2.887 vagas reais no histórico, 4 fontes ativas (LinkedIn, InfoJobs, Catho, Indeed — Indeed bloqueado por Cloudflare, fora de escopo) |
| Dedup | **OK** | `POST /jobs` do Core dedupe por fingerprint; nenhuma vaga duplicada observada |
| Core sync (JOB→SCORE→PREPARE) | **OK** | `core_application_id` e `resume_version_id` reais confirmados em múltiplas candidaturas |
| Eligibility Gate | **OK** | Bloqueou corretamente `RELOCATION_REQUIRED` sem intervenção manual |
| Scoring | **PARCIAL** | Funciona; não validado se prioriza de fato as famílias que convertem (não há dado de conversão ainda) |
| Resume Router | **OK** | Currículo real por família/idioma, via Core, nunca caminho estático local |
| Application (preparo/clique) | **PARCIAL — 3 canais mapeados e bloqueados/exauridos** | OOM corrigido em preparo (Cycle 001) e inspeção (Cycle 002), relocation implícito corrigido (Cycle 003). Cycle 003 tentou 1 candidatura real de ponta a ponta (Atento/LinkedIn, pipeline+Resume Router validados) e confirmou a **segunda ocorrência real** do mistério do Issue #73 (clique externo do LinkedIn sem navegação) — não é mais caso isolado do Agibank. InfoJobs: parede de sessão confirmada ainda ativa. Catho: sem candidato fresco elegível remanescente. Nenhuma chegou a CONFIRMED ainda |
| Gmail / Tracking | **OK (restaurado 05/09/2026)** | Reautorizado (ação humana) + 2 bugs de cota corrigidos (PRs #82, #83). Ciclo natural confirmado: `GOOGLE_MAIL_SCANNED, scanned: 30`. Revelou uma entrevista real sem resposta há 13 dias (Randstad/Mercado Livre) — aguardando decisão humana sobre a resposta, ver `KNOWN_ISSUES.md` |
| Interview detection | **OK** | Já detectou 1 entrevista real (categoria `INTERVIEW`, confiança 98%) e múltiplas confirmações de candidatura reais |
| Offer | **NÃO VALIDADO** | — |
| Hiring | **NÃO VALIDADO** | — |

## Por que "Application" está parcial, não "não funciona"

A validação de 23-24/08/2026 testou **10 candidaturas reais distintas** e alcançou, em pelo menos um caso (Geeker Company/LinkedIn → Quickin), o estágio mais profundo possível sem inventar dado: clique real observado, seguindo um redirecionamento genuíno até um ATS de terceiros, chegando a um formulário nativo de verdade. Nenhuma das 10 chegou a CONFIRMED, mas por três classes de causa, nenhuma delas um defeito da rede de segurança:

1. **Bugs reais de código**, todos corrigidos e implantados nesta mesma validação (ver `KNOWN_ISSUES.md` e os commits/PRs #74–#79).
2. **Limitações externas comprovadas** (parede de sessão do InfoJobs, contaminação de histórico do Catho) — fora do que a automação deve resolver sozinha.
3. **Conteúdo humano insubstituível** (foto, data de nascimento, resumo de qualificações num ATS de terceiros) — o sistema corretamente se recusou a inventar, terminando em `MANUAL_REQUIRED`.

## O paradoxo que motivou este pilar

Descoberta de **2.081+ vagas por execução** nunca se traduziu em nenhuma entrevista rastreável. Aumentar fontes/volume não é mais uma prioridade válida enquanto isso não mudar — ver `IMPROVEMENT_BACKLOG.md`, seção "Operation Interview".

## Métrica que falta existir

Não há hoje nenhum dado de:
- taxa de resposta por família de vaga (Sustentação vs DBA vs Data vs Support);
- taxa de resposta por currículo usado;
- taxa de resposta por fonte (LinkedIn vs InfoJobs vs Catho);
- tempo entre candidatura e resposta.

Esses quatro números são o próximo objetivo de instrumentação real — sem eles, "Score V2" e "Resume Router" não podem aprender nada, só executar a regra estática que já têm.
