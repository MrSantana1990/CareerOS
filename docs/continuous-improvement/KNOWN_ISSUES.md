# Problemas conhecidos — não redescobrir

Consultar antes de investigar qualquer falha de candidatura real. Cada item tem causa raiz confirmada (não hipótese) e o que já foi tentado.

## Aberto — requer participação humana

### Gmail — OAuth quebrado há 13 dias (crítico, bloqueia Tracking/Interview)
- **Sintoma:** `GOOGLE_MAIL_SCAN_FAILED` com `error: "RefreshError"` a cada ~10 minutos, ininterrupto desde `2026-08-22T03:38:43` (mais de 1.800 falhas consecutivas até 04/09/2026).
- **Impacto real:** nenhuma resposta de recrutador ou convite de entrevista está sendo correlacionada automaticamente há quase duas semanas — mesmo que tenha chegado por e-mail de verdade. Isso bloqueia completamente o estágio de Tracking/Interview Detection, o coração de "Operation Interview".
- **Causa provável:** token de refresh do OAuth do Google revogado, expirado ou inválido (comum quando o app está em modo de teste/consentimento não usado por muito tempo, ou a senha da conta Google mudou).
- **Não é corrigível por código.** Exige reautorização interativa humana.
- **Ação necessária:** rodar `scripts/authorize-google.py` novamente (mesmo procedimento de `TROUBLESHOOTING.md`, seção "Google desconectado") e confirmar `.runtime/google/google-token.json` renovado, com sessão humana disponível para completar o consentimento OAuth no navegador.

### LinkedIn/Agibank — clique sem navegação observável
- **Aplicação:** `ce0370a8-2c1d-45f5-9e1a-4fa7ea89052d`, `attempts=3` (cap atingido, não tocar novamente).
- **Sintoma:** o clique no CTA final não produz nenhuma nova aba, mudança de domínio, nem qualquer efeito observável — reproduzido em 3 tentativas distintas, cada uma após uma correção diferente ter descartado a hipótese anterior.
- **Rastreamento:** [Issue #73](https://github.com/MrSantana1990/CareerOS/issues/73).
- **Não fazer:** resetar `attempts`, aumentar retry, ou tratar qualquer clique nessa vaga como confirmação.
- **Próximo passo real:** diagnóstico via CDP remoto ou sessão WSL manual, evitando disputar o lock do perfil do navegador com o servidor ativo.

### InfoJobs — parede de sessão sistêmica
- **Sintoma:** duas vagas distintas (Manpower Staffing, Luandre Serviços Temporários), mesmo com 15 cookies válidos no perfil, redirecionaram para a tela de login do InfoJobs ("Acesso para usuários", "O e-mail é obrigatório") em vez do formulário de candidatura.
- **Confirmado com evidência visual** (screenshot da própria tela de login) em ambos os casos — não é uma falha pontual de uma vaga.
- **Causa provável:** sessão insuficiente/expirada para esse fluxo específico de candidatura rápida, mesmo navegando o resto do site normalmente.
- **Não fazer:** tentar mais candidaturas reais no InfoJobs até isso ser resolvido — vai bater na mesma parede e gastar tentativas à toa.
- **Próximo passo real:** login interativo humano + migração de perfil, mesmo procedimento já usado para LinkedIn e para a sessão original do Catho (documentado em `HELPSYSTEM-CONTINUIDADE.md`, seção 18).

### Catho — contaminação de sessão real
- **Sintoma:** o perfil de navegador migrado para a VPS carrega o histórico real de 23 candidaturas feitas em 13/08/2026 (local, antes desta automação). Qualquer uma dessas vagas específicas, se selecionada de novo, mostra "CV enviado!" antes de qualquer ação nova — risco real de falso-positivo de duplicação ou de atribuir uma confirmação a uma ação que não foi nossa.
- **Não fazer:** selecionar candidato do Catho sem antes confirmar que não está entre as 23 de 13/08 (a lista exata ainda não foi levantada).
- **Próximo passo real:** levantar a lista real dessas 23 vagas (via histórico do próprio site logado) antes de reutilizar este canal.

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
