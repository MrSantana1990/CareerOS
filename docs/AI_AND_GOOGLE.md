# IA local, Gmail e Google Calendar

## IA local

O CareerOS não inclui pesos de modelo no Git. Ele se conecta a uma API local compatível com OpenAI, configurada por `LOCAL_AI_URL`. O script de início procura por padrão:

```text
D:\DEV\IA-Local\runtime\llama-server.exe
D:\DEV\IA-Local\models\Qwen3-4B-Q4_K_M.gguf
```

A IA recebe pergunta, descrição da vaga e perfil aprovado. A resposta deve ser JSON com ação, texto, confiança e evidências. Fatos ausentes nunca são inferidos; confiança baixa gera `ASK_USER`.

## Google OAuth

Ative Gmail API e Google Calendar API em um projeto Google Cloud. Crie um cliente OAuth do tipo **Aplicativo para computador**, mantenha o app em teste e adicione a conta em **Usuários de teste**.

Salve o JSON baixado em:

```text
.runtime/google/google-credentials.json
```

Autorize uma vez:

```powershell
./.venv/Scripts/python.exe ./scripts/authorize-google.py
```

O token será criado em `.runtime/google/google-token.json`. Nenhum desses arquivos entra no Git.

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
