# Estado real do funil — 05/09/2026

Atualizado após o Cycle 002 (Operation Interview). Ver histórico da validação P0 (23-24/08) referenciado em `HELPSYSTEM-CONTINUIDADE.md`. Este arquivo reflete o que foi **comprovado com evidência real**, não o que foi desenhado em `V2-CAREER-INTELLIGENCE.md`.

## Baseline objetivo (produção real, 05/09/2026)

| Métrica | Valor |
|---|---|
| Vagas descobertas (histórico) | 2.887 |
| Vagas qualificadas (`APPROVED_AUTO`) | 693 |
| Candidaturas totais | 693 |
| Candidaturas `FAILED` | 504 (72%, era 533/77% no Cycle 001) |
| Candidaturas `READY_FOR_REVIEW` | 75 |
| Candidaturas `BLOCKED` | 68 |
| Candidaturas `MANUAL_REQUIRED` | 20 |
| Candidaturas `READY_TO_PREPARE` | 17 |
| Candidaturas `CLOSED` | 9 |
| **Candidaturas `APPLIED` (confirmadas)** | **0** |
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
| Application (preparo/clique) | **PARCIAL, melhorando** | 77% das candidaturas terminavam `FAILED`; 49% delas por um único bug (OOM ao reaproveitar página do Chrome no lote inteiro) — corrigido e medido no Cycle 001 (PR #80): lote de 14 candidaturas reais, 0 crashes. Clique real de envio observado e correto em 4/10 candidaturas testadas na validação P0; nenhuma chegou a CONFIRMED ainda |
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
