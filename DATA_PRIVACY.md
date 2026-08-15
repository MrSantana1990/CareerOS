# Privacidade de dados

CareerOS é local-first. Perfil, currículo, cookies, screenshots, histórico de candidaturas, decisões da IA, mensagens classificadas e tokens Google permanecem em `.runtime/` no computador.

## Dados enviados externamente

- Plataformas recebem apenas os dados necessários à candidatura iniciada pelo usuário.
- Gmail e Agenda usam APIs oficiais e escopos OAuth explícitos.
- A IA padrão é local; o projeto não envia currículo para um provedor de IA remoto.

## Minimização

Logs não devem conter senha, cookie, token, CPF, currículo integral ou corpo completo de e-mail. O painel exibe trechos necessários ao acompanhamento. Links com tokens não são documentados nem versionados.

## Retenção

O usuário controla `.runtime/` e os volumes Docker. Antes de apagar, faça backup seletivo. Criptografia local e retenção automática configurável permanecem no roadmap.
