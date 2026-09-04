# HelpSystem Carreira V2 — Career Intelligence

## Missão

Buscar, validar, qualificar, preparar, acompanhar e otimizar oportunidades profissionais com intervenção humana somente quando necessária. O objetivo não é volume de candidaturas; é conversão com aderência, evidência e rastreabilidade.

## Fluxo canônico

`DISCOVER → VALIDATE → MATCH → SCORE → DECIDE → CUSTOMIZE → APPLY → TRACK → FOLLOW-UP → INTERVIEW → OFFER`

Nenhuma etapa pode pular validação, inventar experiência ou assumir que um envio foi concluído sem confirmação.

## Oito motores

1. **Discovery:** APIs, feeds e páginas estruturadas antes de parser HTTP; navegador somente como última milha.
2. **Eligibility:** regras salariais, modalidade, localização, idioma, senioridade, país e canal.
3. **Fit Scoring:** stack 30, experiência 20, senioridade 10, modalidade 10, remuneração 10, localização 5, idioma 5, canal 5 e recência 5.
4. **Validation:** `OPEN`, `UNCERTAIN`, `CLOSED`, `DUPLICATE`, `ALREADY_APPLIED` ou `BLOCKED`.
5. **Application Strategy:** e-mail, Easy Apply, ATS estruturado ou revisão humana.
6. **Resume Router:** currículo por família, idioma e versão; nomes em inglês começam com `EN_`.
7. **AI Application Agent:** responde somente com perfil, evidências e respostas previamente aprovadas.
8. **Gmail, Calendar e Follow-up:** transforma retorno em evento do pipeline e alerta acionável.

## Autonomia

- **AUTO:** descoberta, validação, score, escolha de currículo, registro e monitoramento seguro.
- **ASSISTED:** candidatura com risco, impacto ou decisão subjetiva entra na Inbox.
- **MANUAL:** CAPTCHA, MFA, vídeo, teste, consentimento sensível ou resposta sem evidência.

Autoenvio continua bloqueado até dupla habilitação técnica, revisão das regras e validação jurídica/operacional.

## Regras iniciais de Rodolfo

- Suporte N1 somente com remuneração mínima adequada.
- Suporte N2 competitivo ou remoto.
- Suporte Sênior, Sustentação, DBA, SQL e Dados recebem prioridade.
- Internacional exige aceite de Brasil/LATAM; relocation obrigatório descarta.
- Inglês C1/fluente obrigatório é risco para revisão, não afirmação automática.
- Espanhol fluente obrigatório bloqueia.
- Presencial fora de Campinas recebe penalidade forte.
- Remoto, candidatura por e-mail e ATS simples recebem bônus.
- Gupy somente com fit alto e nunca como canal preferencial.
- Meta é “até N qualificadas”, nunca preencher cota com vagas ruins.

## Currículos planejados

- `PT_SUPORTE_SENIOR.pdf`
- `PT_DBA_SQL.pdf`
- `PT_DADOS.pdf`
- `EN_SUPPORT_DATABASE.pdf`
- `EN_DATA_DATABASE.pdf`
- `EN_DATA_ENGINEERING.pdf`

Cada candidatura registra arquivo, versão, idioma e hash do currículo realmente enviado.

## Releases

| Release | Escopo | Estado |
|---|---|---|
| V1 Foundation | domínio, login, PostgreSQL, Redis, regras, auditoria e PWA | entregue |
| V2 Radar | dashboard, Inbox, validação, scoring e deduplicação | entregue |
| V3 Apply | currículo, e-mail, formulários, respostas e Playwright assistido | validado parcialmente (ver `continuous-improvement/CURRENT_STATE.md` — clique real e ponte com o Core comprovados; CONFIRMED ainda não alcançado) |
| V4 Intelligence | Gmail, Calendar, follow-up, métricas e aprendizado de conversão | Gmail restaurado; follow-up/aprendizado bloqueados até haver ao menos 1 CONFIRMED real |
| V5 Commercial | multiempresa, onboarding, planos, cobrança e suporte | congelada — ver `continuous-improvement/IMPROVEMENT_BACKLOG.md`, seção "Operation Interview" |

Antes de trabalhar em qualquer item deste documento, ler [`continuous-improvement/README.md`](continuous-improvement/README.md) — o funil real de hoje pode divergir do desenho acima, e o backlog priorizado vive em `continuous-improvement/IMPROVEMENT_BACKLOG.md`.

## Critério de verdade no painel

- Dado persistido vem da API/PostgreSQL.
- Integração ausente aparece como `configurar`, nunca como ativa.
- Executor local offline não significa que a VPS caiu.
- Envio só conta após confirmação do canal.
- Métricas zero devem orientar o próximo passo, não gerar telas vazias sem explicação.
