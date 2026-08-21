# Comunicações, entrevistas e follow-up

## Princípios

- Gmail é lido pelo serviço privado de integrações na VPS.
- Somente metadados necessários são enviados ao Core; o corpo completo não é copiado.
- Cada mensagem possui chave única por organização e provedor.
- A correlação usa domínio do remetente, empresa e título da vaga.
- Empates e sinais insuficientes permanecem para revisão humana.
- Entrevistas e propostas recebem prioridade urgente.
- Follow-up gera apenas um lembrete; nunca envia mensagem automaticamente.

## Fluxo

1. A integração classifica mensagens de recrutamento.
2. O lote é sincronizado com `/api/v1/communications/sync`.
3. O Core tenta correlacionar com candidaturas abertas.
4. Uma notificação deduplicada é criada no PostgreSQL.
5. O portal mostra a central responsiva e permite marcar itens como lidos.
6. A avaliação de follow-up procura candidaturas aplicadas há pelo menos sete dias e sem resposta posterior.

## Segurança e privacidade

O navegador nunca recebe o token administrativo. Notificações exibem texto genérico e não incluem conteúdo sensível do e-mail. Flags de push e follow-up automático continuam desligadas. CAPTCHA, MFA, envio de e-mail e decisões irreversíveis continuam sob controle humano.
