# Backlog priorizado — Operation Interview

Objetivo único até novo aviso: **gerar a primeira entrevista rastreável gerada 100% pelo pipeline.** Nenhum item fora deste backlog deve consumir esforço de engenharia enquanto isso não acontecer — sem novas fontes de vaga, sem novo dashboard, sem novo canal, sem mobile.

**Marco atingido em 06/09/2026 (Cycle 009): `CONFIRMED 0 → 1`.** Primeira candidatura confirmada real (Deutsche Bank Brasil, candidatura espontânea por e-mail oficial publicado, `GMAIL_MESSAGE_ID=1a075f10df38136e`) — não veio de nenhum dos 4 canais tradicionais (LinkedIn/Catho/InfoJobs/Gupy), veio de Company Intelligence. Ver `docs/OPERATION-INTERVIEW-FINAL-REPORT-CYCLES-001-010.md` para o relatório consolidado completo.

## P0 — bloqueia "Operation Interview"

- [x] **Corrigir o crash de memória (OOM) que derrubava 49% das candidaturas.** Cycle 001, PR #80 — medido: 0 crashes em lote real de 14 candidaturas pós-correção.
- [x] **Reautorizar o Gmail.** Feito 04-05/09/2026 + 2 bugs de cota corrigidos (PRs #82, #83). Ciclo natural confirmado funcionando. Revelou 1 entrevista real sem resposta (Randstad/Mercado Livre) — decisão humana pendente, não é mais item de engenharia.
- [ ] **Renovar sessão do InfoJobs** (login interativo humano + migração de perfil). Sem isso, o canal com mais candidatos score-alto testados hoje fica inutilizável.
- [ ] **Contaminação do Catho — escopo ampliado (Cycle 004).** Não são só as 23 vagas de 13/08: uma vaga genuinamente nova (05/09) também mostrou "CV enviado!" pré-existente. Mitigação em uso (verificação visual antes de qualquer envio real) está funcionando, mas a causa raiz completa ainda não foi mapeada.
- [ ] **Investigar `fill_known_fields` em ATS de terceiros não-semânticos** (Quickin confirmado; provavelmente outros). Sem isso, qualquer redirecionamento externo bem-sucedido termina em formulário vazio.
- [x] **Corrigir o mesmo crash de memória (OOM) em `inspect_application_queue`.** Cycle 002, PR #85 — era 249/519 (48%) das candidaturas `FAILED`, sem diagnóstico algum. Medido: 15/15 vagas reprocessadas, 0 crashes, todas resolvidas em estado real (`CLOSED`/`BLOCKED`/`READY_TO_PREPARE`).
- [x] **Investigar `LOCAL_AI_UNAVAILABLE`** — confirmado estrutural (nenhuma IA local rodando na VPS). Sistema já lida com segurança (nunca inventa resposta). Baixo volume (14 ocorrências) — não é o gargalo de maior impacto agora, decisão de implantar fica para quando isso for limitante de verdade.
- [ ] **Reprocessar o backlog histórico de 248 candidaturas com `Page crashed` no preparo** (anteriores à correção do Cycle 001) — ainda sentadas em `FAILED`, não reprocessadas automaticamente ainda.
- [x] **Corrigir relocation implícito** (vaga presencial no exterior sem a palavra "relocation"). Cycle 003, PR #87 — testado e validado em produção real.
- [x] **Selecionar e validar 1 candidatura real de alta qualidade em canal já saudável até CONFIRMED.** Cycle 003 — tentado (Atento/LinkedIn, pipeline completo validado), mas bateu no mesmo mistério do Issue #73 (clique externo sem navegação). **Não é mais caso isolado do Agibank — confirmado recorrente.**
- [x] **Diagnóstico real do Issue #73.** Cycle 005, PR #90 — **causa raiz identificada**: reCAPTCHA Enterprise invisível acionado pela plataforma (bot-detection), nunca detectado antes porque `INTERVENTION_PATTERNS["CAPTCHA"]` só olhava texto visível. Corrigido para reportar honestamente como CAPTCHA/MANUAL_REQUIRED. Validado em produção real. É barreira legítima da plataforma — não contornável por princípio do produto.
- [x] **Verificar se a parede de sessão do InfoJobs ainda está ativa.** Cycle 003 — **confirmado que sim** (mesma tela de login). Todos os candidatos de alto score já esgotaram o cap tentando automaticamente. Segue precisando de reautorização humana.
- [x] **Auditar rotas de candidatura por e-mail/ATS/careers já existentes no código.** Cycle 004 — `detect_email_application`+`create_application_email_draft` existem e funcionam isoladamente, mas nada os conecta ainda. 0/41 vagas novas + 0 no histórico têm e-mail detectável — sem candidato real para validar a conexão ainda.
- [x] **Rodar radar novo pequeno (TIER A) e verificar canais alternativos.** Cycle 004 — 41 vagas novas processadas com segurança, 0 canais ATS/e-mail encontrados, 5/5 LinkedIn e 2/2 Catho testados confirmam os mesmos 3 bloqueios já mapeados.
- [x] **Vincular intervenções humanas (`human_interventions`) à candidatura real.** Cycle 006, PR #92 — `application_id` sempre ia `None`; 6/6 intervenções pendentes em produção estavam sem vínculo. Corrigido + enriquecido (`source`/`score`/`region`/`salary_brl`/`job_url`) e validado com uma intervenção real nova pós-fix.
- [ ] **`unknown_fields` só guarda o nome do campo, não o texto da pergunta** (achado real, Cycle 006 — candidato Catho com 13 "killer questions" sem texto capturado). Mesmo com a fila enriquecida, o humano ainda precisa abrir a página pra saber o que responder.
- [x] **SCORE != ELIGIBILITY: piso salarial universal.** Cycle 007 — `MINIMUM_SALARY_BLOCK` (R$4.000, qualquer família) em ambos os pipelines. Achado real: candidato InfoJobs com `salary_brl=1500` passava sem bloqueio algum antes disso.
- [x] **Conectar Discovery/ATS detection ao Core (`recruiter_email`/`application_channel`).** Cycle 009 — `detect_email_application`/`detect_ats` já descobriam dado real, mas nada propagava pro Core, que já sabia decidir a estratégia `EMAIL` sozinho. PR #102.
- [x] **Distinguir bounce/auto-reply de resposta humana real no tracking.** Cycle 010 — `check_application_thread()` usa o header RFC 3834 `Auto-Submitted` + padrões de remetente/assunto. PR #103.
- [ ] **Resolver o InfoJobs por outra via que não CDP/relay genérico** (tentativa revertida no Cycle 007 — PRs #95-#99 — por ser dual-use tooling). Segue `AUTH_REQUIRED`.
- [ ] **Aprovar pelo menos uma segunda família de currículo real** (`PT_SUPPORT_SENIOR`/`PT_DBA_SQL`/`PT_DATA` etc). Achado real do Cycle 010: só existe `GENERAL` (pt-BR) aprovado no Core hoje — o Resume Router (`route_resume()`) está implementado e testado, mas nunca teve mais de uma opção real para escolher.
- [ ] **Application-por-e-mail sem `job_id` não tem onde morar no Core.** O primeiro CONFIRMED (Deutsche Bank, candidatura espontânea) só existe como evidência de Gmail + documentação — `applications` exige `job_id`. Decisão de schema pendente (ex.: `job_id` nullable + `application_type=SPONTANEOUS`).

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

## Fase 2 — achados do Pilot (Prompt 7.1, 09-13/09/2026)

Ver `docs/continuous-improvement/PILOT-FORENSICS.md` para a auditoria completa. Gaps comprovados por evidência real de 4 dias de produção:

- [ ] **P0 — reautorizar o Gmail (URGENTE, achado em 13/09 durante a auditoria).** `google_mail_scheduler` está falhando continuamente há mais de 26h (`RefreshError: invalid_grant`, refresh token revogado/expirado) — último scan bem-sucedido em 2026-09-11 23:16 UTC, 166+ tentativas falhas consecutivas até agora. Não corrigível por código, exige reautorização humana real (mesma classe do histórico "renovar sessão do InfoJobs"). **Prompt 8 (13/09) adicionou observabilidade real**: `GMAIL_HEALTH=AUTH_REQUIRED` exposto em `/metrics`, causa raiz classificada (`REFRESH_TOKEN_INVALID`) e uma `human_interventions` real criada (dedup, uma só por outage) — o item de engenharia (parar de mascarar com retry silencioso) está feito; falta só a ação humana (reautorizar via OAuth).
- [x] **P0 — nenhum scheduler conecta Perception → Opportunity Brain → Action Engine.** Resolvido no Prompt 8 (13/09/2026, PRs #120/#121): `opportunity_assembly_scheduler` em `automation-host` (a cada 15min) orquestra `POST /jobs/{id}/evaluate`, `POST /signals/{id}/evaluate`, `POST /opportunities/{id}/channels/discover` e `POST /opportunities/{id}/action-plan` sobre Jobs/Signals pendentes. Validado em produção: 2 ciclos naturais, 61 itens processados, 50 Opportunities autônomas criadas, 0 falhas, 0 duplicatas (ver `PILOT-FORENSICS.md`, seções 7-10). Gargalo #1 do Prompt 7.1 fechado — todas ainda terminam em `HUMAN_REQUIRED` por falta de canal seguro (CAPTCHA/AUTH), o que é honesto, não um bug.
- [ ] **`structured_extraction` de vagas do LinkedIn captura texto de UI/sidebar em `location`/`work_model`** (achado real: `evidence_snippet` idêntico — rótulo de filtro de busca — em vagas de empresas diferentes). Coluna populada 100%, mas parte do conteúdo extraído via `keyword_regex` sobre o texto completo da página não é confiável para essa fonte.
- [ ] **Sistema nunca visita o feed/posts do LinkedIn**, só `/jobs/search/` e `/jobs/view/` — vagas divulgadas como post social/imagem (caso real J&T Express) são estruturalmente invisíveis, independente de QR Code/OCR.
- [ ] **Correlação de e-mail falha quando não existe Application em Core para a empresa** (2 casos reais no Pilot: TEMBICI, GRUPO GPS — mesma causa estrutural do caso Randstad/Mercado Livre do Prompt 6).

## Definição de "resolvido" para este backlog

Um item só sai daqui quando o `CURRENT_STATE.md` for atualizado com evidência real do resultado — nunca só porque o código foi implantado. Ver o template de ciclo em `README.md`.
