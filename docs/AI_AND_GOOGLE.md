# IA local, Gmail e Google Calendar

## IA local

O CareerOS não inclui pesos de modelo no Git. Ele se conecta a uma API local compatível com OpenAI, configurada por `LOCAL_AI_URL`. O script de início procura por padrão:

```text
D:\DEV\IA-Local\runtime\llama-server.exe
D:\DEV\IA-Local\models\Qwen3-4B-Q4_K_M.gguf
```

A IA recebe pergunta, descrição da vaga e perfil aprovado. A resposta deve ser JSON com ação, texto, confiança e evidências. Fatos ausentes nunca são inferidos; confiança baixa gera `ASK_USER`.

## Google OAuth (integração Gmail/Calendar)

> **IMPORTANTE:** este cliente OAuth serve SOMENTE para a integração de Gmail/Calendar (`apps/automation-host/src/google_career.py`) - acesso offline, scopes sensíveis (`gmail.readonly`/`gmail.compose`/`gmail.send`/`calendar.events`). Ele é um cliente **separado** do usado para "Continuar com Google" (login do portal), documentado na seção seguinte. Nunca reusar um client_id/client_secret no outro fluxo.

Ative Gmail API e Google Calendar API em um projeto Google Cloud. Crie um cliente OAuth do tipo **Aplicativo para computador**, adicione a conta em **Usuários de teste** durante o desenvolvimento.

**Publique o app (Testing → In production) no OAuth consent screen assim que possível.** Um app em modo "Testing" tem seus refresh tokens expirados pelo próprio Google em 7 dias, independente de uso - essa foi a causa raiz confirmada de reautorizações recorrentes desta integração. "In production" remove esse limite (o Google pode mostrar uma tela de "app não verificado" durante o consentimento para scopes sensíveis - normal para um app de uso pessoal/interno, o dono do projeto pode prosseguir).

Salve o JSON baixado em:

```text
.runtime/google/google-credentials.json
```

Autorize uma vez:

```powershell
./.venv/Scripts/python.exe ./scripts/authorize-google.py
```

O token será criado em `.runtime/google/google-token.json`. Nenhum desses arquivos entra no Git.

## Google Sign-In (login do portal)

> **GOOGLE LOGIN != GMAIL INTEGRATION.** Este é um cliente OAuth **separado**, do tipo **Aplicativo da Web**, usado somente para autenticar a sessão do CareerOS (`apps/web`) - scopes `openid email profile`, `access_type=online` (nunca solicita Gmail/Calendar, nunca gera refresh token do Google). A sessão do CareerOS continua sendo o cookie HMAC já existente (`apps/web/lib/portal-auth.ts`); o Google só fornece a identidade verificada (issuer/audience/assinatura/nonce conferidos em `apps/web/lib/google-oidc.ts`).

No Google Cloud Console (pode ser o mesmo projeto do Gmail, com um cliente OAuth diferente):

1. **APIs & Services → Credentials → Create Credentials → OAuth client ID**, tipo **Web application**.
2. Authorized redirect URI: `https://<seu-domínio>/api/auth/google/callback` (produção) e, se necessário, `http://localhost:3000/api/auth/google/callback` (desenvolvimento).
3. Publique o OAuth consent screen para **In production** (o mesmo passo do Gmail acima resolve os dois clientes, já que o consent screen é por projeto).

Variáveis de ambiente do serviço `web` (sem valores reais aqui - configure via o mecanismo de secrets já usado para `ADMIN_API_TOKEN`/`PORTAL_SESSION_SECRET`):

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `GOOGLE_LOGIN_CLIENT_ID` | Não (login por senha continua funcionando sem ela) | Client ID do cliente OAuth **Web application** dedicado ao login. |
| `GOOGLE_LOGIN_CLIENT_SECRET` | Não | Client secret correspondente. Nunca commitar. |
| `GOOGLE_LOGIN_REDIRECT_URI` | Não (default aponta para o domínio de produção) | Deve bater exatamente com o redirect URI autorizado no Cloud Console. |

Sem essas variáveis definidas, o botão "Continuar com Google" responde 503 e o login por e-mail/senha continua disponível normalmente.

## Gmail

O monitor consulta uma janela geral de 90 dias e uma busca específica de questionários de até 180 dias. Mensagens são classificadas como entrevista, questionário, proposta, rejeição, confirmação ou contato de recrutador. Resultados são deduplicados.

Respostas são criadas como **rascunho**. Envio automático não é implícito.

## Questionários

O extrator ignora pixels, CDN, imagens, redes sociais, privacidade e descadastro. Para Pandapé, prioriza `/Test` e valida o redirecionamento:

- `/Test/TestResult`: concluído com evidência.
- HTTP 404/410: indisponível.
- destino ativo: pendente e pode ser aberto pelo painel.

Uma marcação manual é preservada quando a plataforma não fornece confirmação verificável.

## Agenda

Eventos só podem ser criados quando data e horário completos são extraídos. Antes da gravação, o sistema pesquisa o mesmo intervalo para evitar duplicidade. Eventos recebem lembretes de 24 horas e 1 hora.
