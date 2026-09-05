# Problemas conhecidos — não redescobrir

Consultar antes de investigar qualquer falha de candidatura real. Cada item tem causa raiz confirmada (não hipótese) e o que já foi tentado.

## Aberto — requer participação humana

### Gmail — OAuth quebrado há 13 dias (RESOLVIDO em duas camadas, 04-05/09/2026)
- **Sintoma original:** `GOOGLE_MAIL_SCAN_FAILED` com `error: "RefreshError"` a cada ~10 minutos, ininterrupto desde `2026-08-22T03:38:43` (mais de 1.800 falhas consecutivas).
- **Impacto real confirmado:** um convite de entrevista real (Randstad/Mercado Livre, "2ª Etapa") ficou 13 dias sem resposta detectada pelo sistema, além de múltiplas confirmações de candidatura reais (Poliedro Educação, JAMEF, Squadra Digital, Gupy/Stefanini) e questionários.
- **Camada 1 (ação humana):** token OAuth revogado/expirado. Reautorizado via `scripts/authorize-google.py` (login interativo humano, 04/09/2026 20:21) + token levado manualmente pra VPS + restart do `integrations`.
- **Camada 2 (bug de código, achado só depois da camada 1):** mesmo com token válido, o scan continuava falhando com `HttpError 403 rateLimitExceeded` ("Quota exceeded... Units per minute per user"). Causa raiz real: (a) toda rodada de 10 em 10 minutos buscava o corpo completo de TODAS as ~350 mensagens do período de 90 dias, mesmo as já classificadas antes; (b) o ciclo rotineiro usava os mesmos parâmetros caros de um catch-up completo (90 dias/250 resultados) pra sempre. Corrigido em dois PRs: [#82](https://github.com/MrSantana1990/CareerOS/pull/82) (não reprocessar mensagem já classificada + retry com backoff) e [#83](https://github.com/MrSantana1990/CareerOS/pull/83) (ciclo rotineiro usa janela leve de 7 dias/40 resultados; `/google/scan` manual mantém a janela funda de 90d/250 para catch-up deliberado).
- **Validar:** próximo ciclo agendado (10 min) deve gerar `GOOGLE_MAIL_SCANNED` sem `HttpError`.

### LinkedIn External Apply — reCAPTCHA invisível (RESOLVIDO tecnicamente, 05/09/2026)
- **Aplicação original:** `ce0370a8-2c1d-45f5-9e1a-4fa7ea89052d` (Agibank), `attempts=3` (cap atingido, não tocar novamente).
- **Causa raiz identificada (Cycle 005):** a plataforma aciona um reCAPTCHA Enterprise invisível (bot-detection, `li.protechts.net/...&uc=scraping&...`) no momento do clique em "Candidatar-se no site da empresa" — nunca resolvido, bloqueando a navegação externa sem lançar erro algum. Confirmado via diagnóstico isolado (perfil clonado, sem risco à produção) reproduzido contra vaga real (Evertec Brasil).
- **Corrigido:** [PR #90](https://github.com/MrSantana1990/CareerOS/pull/90) — detecta iframe de reCAPTCHA via `page.frames()` e reporta honestamente como `CAPTCHA`/`MANUAL_REQUIRED`, em vez da mensagem genérica anterior. Validado em produção real (mesmo candidato, mesmo clique, motivo agora preciso).
- **Rastreamento:** [Issue #73](https://github.com/MrSantana1990/CareerOS/issues/73) — causa raiz registrada, recomendado fechar.
- **Não fazer:** tentar contornar o reCAPTCHA — é uma barreira legítima da plataforma, por princípio do produto. Não resetar `attempts` do Agibank.
- **Limitação de negócio que permanece:** candidaturas 100% automatizadas via LinkedIn External Apply continuam bloqueadas quando a plataforma decide desafiar a sessão — agora corretamente diagnosticado como `MANUAL_REQUIRED`/CAPTCHA, viabilizando uma "Candidatura Assistida" real (humano completa o passo apontado com precisão).

### InfoJobs — parede de sessão sistêmica
- **Sintoma:** duas vagas distintas (Manpower Staffing, Luandre Serviços Temporários), mesmo com 15 cookies válidos no perfil, redirecionaram para a tela de login do InfoJobs ("Acesso para usuários", "O e-mail é obrigatório") em vez do formulário de candidatura.
- **Confirmado com evidência visual** (screenshot da própria tela de login) em ambos os casos — não é uma falha pontual de uma vaga.
- **Causa provável:** sessão insuficiente/expirada para esse fluxo específico de candidatura rápida, mesmo navegando o resto do site normalmente.
- **Não fazer:** tentar mais candidaturas reais no InfoJobs até isso ser resolvido — vai bater na mesma parede e gastar tentativas à toa.
- **Próximo passo real:** login interativo humano + migração de perfil, mesmo procedimento já usado para LinkedIn e para a sessão original do Catho (documentado em `HELPSYSTEM-CONTINUIDADE.md`, seção 18).

### Catho — contaminação de sessão real (escopo ampliado, 05/09/2026)
- **Sintoma:** o perfil de navegador migrado para a VPS carrega histórico real de candidaturas feitas fora desta automação. Originalmente identificado com 23 candidaturas de 13/08/2026, mas o Cycle 004 testou uma vaga **genuinamente nova** (publicada 27/08, descoberta em 05/09, nunca antes vista pelo sistema) e ela também mostrou "CV enviado!" pré-existente, mesmo com `filled_fields: []`/`submitted_at: null` no nosso registro.
- **Conclusão atualizada: a contaminação não está limitada às 23 vagas de 13/08 — é mais ampla e imprevisível.** Trate qualquer candidato Catho como potencialmente já aplicado.
- **Não fazer:** avançar para envio real em qualquer candidato Catho sem antes verificar visualmente (screenshot da etapa de preparo) que "CV enviado!" está ausente.
- **Mitigação já em uso:** a verificação visual antes do envio real já pegou corretamente os 2 casos encontrados até agora (SQL Server DBA em 23/08, Analista de Dados II em 05/09) — nenhuma duplicação real ocorreu.
- **Próximo passo real:** ainda não levantado — precisaria checar o histórico de candidaturas da própria conta Catho logada para mapear a extensão real da contaminação.

## Corrigido nesta sessão (23/08/2026) — regressão coberta por teste

| Bug | PR | Sintoma real | Causa raiz |
|---|---|---|---|
| Classificação interna/externa por texto, não por comportamento | [#71](https://github.com/MrSantana1990/CareerOS/pull/71), [#72](https://github.com/MrSantana1990/CareerOS/pull/72) | Link externo do LinkedIn tratado como SUBMIT | Botão JS-driven, não `<a href>` simples — corrigido pra observar nova aba/mudança de domínio após o clique |
| Formulário preenchido nunca era retentável | [#74](https://github.com/MrSantana1990/CareerOS/pull/74) | Candidatura real controlada autorizada não avançava | `retryable()` não cobria `READY_FOR_REVIEW` + "autoenvio desligado" |
| Externo não-resolvido sem caminho de retry | [#75](https://github.com/MrSantana1990/CareerOS/pull/75) | Idem, motivo genérico de externo | Cap `attempts>=3` preservado, condição nova adicionada |
| Banner de cookies do InfoJobs não reconhecido | [#76](https://github.com/MrSantana1990/CareerOS/pull/76) | Clique final expirava (`Locator.click` timeout), mascarado como "candidatura externa" | Botões "Aceitar"/"Disagree and close" fora do padrão de `dismiss_overlays` |
| Exceção de preparo/clique só registrava o tipo, sem mensagem | [#77](https://github.com/MrSantana1990/CareerOS/pull/77), [#78](https://github.com/MrSantana1990/CareerOS/pull/78) | "Falha na preparação: Error." sem detalhe algum — impossível diagnosticar | `except Exception as exc` descartava `str(exc)`; agora capturado + evento emitido |
| `href="javascript:void(0)"` tratado como link navegável | [#79](https://github.com/MrSantana1990/CareerOS/pull/79) | `page.goto` com `net::ERR_ABORTED`, candidatura inteira terminava `FAILED` | Botão JS-driven sem link real — comum, provavelmente afeta outras vagas do InfoJobs |
| Página do Chrome reaproveitada no lote inteiro causava OOM | [#80](https://github.com/MrSantana1990/CareerOS/pull/80) | 260/533 `FAILED` reais (49%) com `Page.goto: Page crashed`; confirmado no `dmesg` do host como OOM killer matando o Chrome, em quase toda execução agendada desde 24/08 | Uma única página reaproveitada para ~20 candidaturas seguidas sem nunca reciclar memória; corrigido e medido: lote de 14 candidaturas, 0 crashes |

## Aberto — gap de código, não testado ainda em produção real

### `fill_known_fields` não reconhece ATS de terceiros com HTML não-semântico
- **Onde apareceu:** formulário real da Quickin (via LinkedIn/Geeker Company) — campos "Nome completo", "E-mail", "Telefone" ficaram todos vazios (`filled_fields: []`) apesar de labels com correspondência óbvia.
- **Hipótese (não confirmada):** `get_by_label` depende de associação semântica `<label for>`; se o ATS usa `<div>` estilizado como label sem essa associação, o campo nunca é encontrado.
- **Não fazer:** inventar conteúdo pra campos sem dado real (foto, data de nascimento, resumo de qualificações) só pra forçar um envio.

### Dropdowns customizados não detectados como campo obrigatório
- **Documentado em:** `HELPSYSTEM-CONTINUIDADE.md`, achado de 22/08/2026.
- **Sintoma:** `required_unknown_fields` só enxerga `input`/`textarea`/`select` com atributo `required` nativo — um dropdown customizado (JS, sem `required` nativo) fica vazio e não detectado, correndo o risco de o sistema tentar enviar um formulário com esse campo em branco.
- **Ainda não corrigido.**
