# Motor de preparação de candidaturas

## Objetivo

A Fase 3 transforma uma oportunidade qualificada em uma candidatura preparada, rastreável e idempotente. Nenhuma mensagem é enviada automaticamente nesta fase.

## Fluxo seguro

1. A vaga precisa estar aberta, sem bloqueio e com score mínimo de 75.
2. O Resume Router escolhe somente um currículo ativo e aprovado, considerando família profissional e idioma.
3. O sistema cria uma chave idempotente por organização e vaga; repetir a operação não duplica candidatura.
4. A estratégia é escolhida entre e-mail publicado, ATS estruturado ou revisão manual.
5. Para e-mail, o texto usa apenas nome, cargo e empresa conhecidos. Não são inventadas experiências ou qualificações.
6. A aprovação humana muda o rascunho para `APPROVED` e registra evento imutável.
7. A materialização cria apenas um rascunho no Gmail com o currículo anexado. O envio continua sob controle humano.

## Resume Router

Famílias aceitas: `GENERAL`, `PT_SUPPORT_SENIOR`, `PT_DBA_SQL`, `PT_DATA`, `EN_SUPPORT_DATABASE`, `EN_DATA_DATABASE` e `EN_DATA_ENGINEERING`. Currículos não aprovados ou inativos nunca são usados.

## Answer Memory

Respostas são normalizadas por pergunta e idioma, versionadas no PostgreSQL e marcadas como verificadas. Uma pergunta desconhecida não recebe resposta estimada: ela retorna para revisão humana. O contador de uso fornece rastreabilidade.

## Estados e prova

- `PREPARING`: candidatura e currículo congelados para preparação.
- `READY`: conteúdo aprovado pelo usuário.
- `REVIEW_REQUIRED`: rascunho aguarda aprovação.
- `MATERIALIZED`: rascunho criado no provedor, ainda não enviado.
- eventos `APPLICATION_PREPARED` e `DRAFT_APPROVED`: trilha append-only.

## Limites desta fase

Não há clique automático em “enviar”, bypass de CAPTCHA/MFA, preenchimento com informação não comprovada nem tentativa de candidatura em fonte não suportada. Confirmação real de envio será um evento separado, vinculado à prova do provedor.
