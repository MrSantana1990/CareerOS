# Backlog priorizado — Operation Interview

Objetivo único até novo aviso: **gerar a primeira entrevista rastreável gerada 100% pelo pipeline.** Nenhum item fora deste backlog deve consumir esforço de engenharia enquanto isso não acontecer — sem novas fontes de vaga, sem novo dashboard, sem novo canal, sem mobile.

## P0 — bloqueia "Operation Interview"

- [x] **Corrigir o crash de memória (OOM) que derrubava 49% das candidaturas.** Cycle 001, PR #80 — medido: 0 crashes em lote real de 14 candidaturas pós-correção.
- [ ] **Reautorizar o Gmail (ação humana, urgente).** `RefreshError` ininterrupto há 13 dias — nenhuma resposta de recrutador está sendo detectada. Rodar `scripts/authorize-google.py` com sessão humana disponível. Bloqueia toda medição de resposta/entrevista.
- [ ] **Renovar sessão do InfoJobs** (login interativo humano + migração de perfil). Sem isso, o canal com mais candidatos score-alto testados hoje fica inutilizável.
- [ ] **Levantar as 23 vagas do Catho de 13/08/2026** e excluí-las explicitamente de qualquer seleção futura, pra não repetir o risco de contaminação.
- [ ] **Investigar `fill_known_fields` em ATS de terceiros não-semânticos** (Quickin confirmado; provavelmente outros). Sem isso, qualquer redirecionamento externo bem-sucedido termina em formulário vazio.
- [ ] **Investigar `LOCAL_AI_UNAVAILABLE`** — apareceu em 4 de 14 candidaturas do lote de validação do Cycle 001, gerando `UNKNOWN_FIELD`. Ainda não quantificado como gargalo, mas real e recorrente.
- [ ] **Selecionar e validar 1 candidatura real de alta qualidade em canal já saudável** (LinkedIn, evitando Agibank) até CONFIRMED — ou até um novo limite externo genuíno, documentado como tal.

## P1 — necessário para "Operation Interview" produzir sinal, não só 1 evento

- [ ] Instrumentar taxa de resposta por família de vaga (Sustentação / DBA / Data / Support), por currículo usado, por fonte — os quatro números listados em `CURRENT_STATE.md`. Sem isso, Score V2 e Resume Router não têm nenhum dado real pra aprender.
- [ ] Corrigir detecção de dropdown customizado em `required_unknown_fields` (achado de 22/08, ainda aberto — ver `KNOWN_ISSUES.md`).
- [ ] Investigar por que "0 candidaturas chegavam a APPLIED" historicamente (auditoria de 22/08) segue relevante mesmo após os fixes desta sessão — confirmar que os 6 bugs corrigidos (#74–#79) realmente elevam a taxa de conclusão, não só a taxa de diagnóstico.
- [ ] Diagnóstico do Issue #73 (Agibank/LinkedIn) via CDP remoto — sem disputar o lock do perfil ativo.

## P2 — só depois de pelo menos 1 entrevista rastreável

- [ ] Ampliar fontes de vaga além das 4 atuais.
- [ ] Painel com funil completo (Discovery → Hire), substituindo o painel atual que mostra "Respostas/Entrevistas/Propostas" fixados em zero no código.
- [ ] Modo Seguro/Assistido/Automático como conceito de UX explícito pro usuário final (hoje existe como `AUTO_APPLY_ENABLED`/kill-switches técnicos, não como experiência).
- [ ] Learning loop de verdade: recalcular prioridade de família de vaga com base em taxa de resposta real, não em regra estática.

## Congelado até novo aviso

Qualquer item que não esteja listado acima e que envolva:
- novo job board / nova fonte de descoberta;
- nova funcionalidade de dashboard;
- chatbot, app mobile, ou qualquer canal de UX novo;
- nova migration não estritamente necessária para os itens P0/P1.

Congelar não significa ignorar um bug real encontrado durante o trabalho nos itens acima — bug real sempre entra no ciclo (ver `README.md`), só não abre escopo novo por iniciativa própria.

## Definição de "resolvido" para este backlog

Um item só sai daqui quando o `CURRENT_STATE.md` for atualizado com evidência real do resultado — nunca só porque o código foi implantado. Ver o template de ciclo em `README.md`.
