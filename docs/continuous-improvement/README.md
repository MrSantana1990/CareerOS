# CareerOS — Melhoria Contínua (Pilar 5)

Este diretório é a memória operacional obrigatória do projeto. Ele existe porque descobrimos, na prática, o padrão que ele foi criado para impedir:

> Construímos bastante motor (descoberta, Core, elegibilidade, roteamento de currículo, segurança) e só ao final de uma validação real de ponta a ponta ficou claro que a métrica que importa — candidatura → resposta → entrevista — nunca tinha sido provada.

## A regra central

**Passar nos testes técnicos não é sucesso do produto.** O único teste que importa:

> O CareerOS está melhorando a taxa de conversão profissional do Rodolfo (candidatura → resposta → entrevista → oferta → contratação)?

Hierarquia de prioridade, nessa ordem — nunca invertida:

1. Integridade (nunca inventar experiência, idioma, certificação ou dado do candidato)
2. Elegibilidade (nunca candidatar onde há requisito eliminatório real)
3. Qualidade (aderência real, currículo certo, evidência real)
4. Conversão (resposta, entrevista, oferta)
5. Escala (volume de vagas/candidaturas)

Uma mudança que melhora uma métrica de nível 5 (ex: "vagas encontradas: 2.081 → 10.000") **não é uma melhoria de produto** se não move nenhuma métrica de nível 4 ou superior. Ver [`CURRENT_STATE.md`](CURRENT_STATE.md) para o funil real hoje.

## O ciclo obrigatório

Toda IA que trabalhar neste repositório segue este ciclo — não "implementa e para":

```
1. LER   → CURRENT_STATE.md, KNOWN_ISSUES.md, IMPROVEMENT_BACKLOG.md, e o histórico
           relevante em D:\DEV\HELPSYSTEM-CONTINUIDADE.md antes de mudar qualquer coisa.
2. AGIR  → implementar a melhoria (bug fix, feature, correção de rota).
3. TESTAR → suíte automatizada + validação real quando a mudança afeta pipeline em produção.
4. OBSERVAR → resultado real: eventos, screenshots, métricas do Core — nunca assumir.
5. CORRIGIR → se a observação revelar um problema novo, ele entra no mesmo ciclo,
              não fica anotado para "depois".
6. REPORTAR → atualizar CURRENT_STATE.md / KNOWN_ISSUES.md / IMPROVEMENT_BACKLOG.md
              com o que mudou de verdade, antes × depois, com números reais ou
              "impacto ainda não mensurável" — nunca uma melhoria inventada.
```

Isso não substitui o fluxo de entrega já estabelecido (branch → implementação → testes → PR → CI → merge → backup → deploy → validação em produção) — é a camada que garante que cada entrega feche o loop até a evidência real, e que a próxima IA não recomece do zero.

## Antes de qualquer mudança relevante

1. Ler [`CURRENT_STATE.md`](CURRENT_STATE.md) — o funil real, não o desenhado.
2. Ler [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) — não redescobrir um problema já diagnosticado.
3. Ler [`IMPROVEMENT_BACKLOG.md`](IMPROVEMENT_BACKLOG.md) — a prioridade real, P0 antes de P2.
4. Ler `D:\DEV\HELPSYSTEM-CONTINUIDADE.md` inteiro — decisões, credenciais, regras que nunca devem ser violadas.
5. Confirmar o que já foi tentado e descartado, pra não repetir.

## Depois de qualquer mudança relevante

Preencha um registro de ciclo (arquivo novo `docs/continuous-improvement/cycles/AAAA-MM-DD-cycle-NNN.md`, criar a pasta `cycles/` na primeira vez que for preciso) usando este modelo:

```markdown
# Cycle NNN — <título curto>

**Data:** AAAA-MM-DD
**Commit(s)/PR(s):**

## Objetivo
Qual problema real estamos tentando resolver? (não "qual feature", qual *problema*)

## Baseline
Como o sistema estava antes, com números reais quando existirem.

## Mudanças
O que foi alterado, e por quê.

## Testes
Automatizados + validação real (se aplicável). Inclua o que falhou, não só o que passou.

## Causa raiz
Se corrigiu um bug: por que ele acontecia de verdade (não a hipótese inicial, a causa confirmada).

## Regressão
Qual teste novo garante que isso não volta a quebrar em silêncio.

## Métricas — antes × depois
| Métrica | Antes | Depois |
|---|---|---|
| ... | ... | ... |

Se não houver número disponível: "Impacto ainda não mensurável." Nunca inventar melhoria.

## Impacto no negócio
Isso move Discovery, Application, Response, Interview, Offer ou Hiring? Se não move nenhum, diga isso explicitamente.

## Pendências
O que continua ruim, incluído no IMPROVEMENT_BACKLOG.md.

## Recomendação
Continuar / corrigir mais / reverter / investigar / não mexer.
```

Depois de escrever o ciclo, atualize `CURRENT_STATE.md` e `KNOWN_ISSUES.md` com o que mudou de fato — o registro de ciclo é o histórico, esses dois arquivos são o estado atual.

## O que este pilar não é

- Não é burocracia paralela ao processo de deploy já estabelecido — é parte dele.
- Não é motivo para parar de corrigir bugs reversíveis durante uma execução autorizada (ver `KNOWN_ISSUES.md` para o que já está mapeado).
- Não é licença para inventar uma métrica de sucesso quando ela ainda não existe — "impacto ainda não mensurável" é uma resposta honesta, não uma falha do relatório.
