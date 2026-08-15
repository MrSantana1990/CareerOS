# Segurança

## Nunca versionar

- `.env`, senhas ou chaves de API.
- `.runtime/google/google-credentials.json` e `google-token.json`.
- Cookies, perfil do Chrome, currículos, screenshots e dados do Gmail.
- Modelos GGUF e binários locais.

Esses caminhos já estão cobertos por `.gitignore`; valide com `git check-ignore` antes de publicar.

## Controles atuais

- OAuth oficial para Gmail e Agenda.
- IA local com fatos limitados ao perfil aprovado.
- Gupy bloqueada.
- CAPTCHA e MFA não são contornados.
- Confirmação real antes de contabilizar envio.
- Parada de emergência e logs locais.
- CORS restrito a localhost e redes privadas no host de automação.
- Rastreadores, imagens e links de rodapé excluídos dos questionários.

## Exposição de rede

O painel e o host podem escutar na rede local para uso pelo celular. Isso não equivale a autenticação. Use apenas em Wi‑Fi confiável e não encaminhe as portas 3000/8765 no roteador. Autenticação local é item de hardening futuro.

Reporte vulnerabilidades diretamente ao mantenedor sem anexar dados pessoais, tokens ou logs completos.
