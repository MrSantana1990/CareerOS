# APIs locais

## Automation Host — porta 8765

| Método | Rota | Finalidade |
|---|---|---|
| `GET` | `/health` | Saúde do agente |
| `GET` | `/status` | Estado da automação |
| `POST` | `/play` | Pipeline diário completo |
| `POST` | `/stop` | Parada de emergência |
| `GET/PUT` | `/profile` | Perfil profissional aprovado |
| `POST` | `/profile/resume` | Importação de currículo |
| `GET` | `/jobs` | Vagas coletadas |
| `POST` | `/analyze` | Score e decisão explicável |
| `GET` | `/applications` | Candidaturas e feedback |
| `POST` | `/applications/prepare` | Inspeção e preparação |
| `POST` | `/applications/execute` | Execução controlada |
| `GET` | `/ai/status` | Disponibilidade da IA local |
| `POST` | `/ai/advice` | Resposta fundamentada no perfil |
| `GET` | `/google/status` | Gmail, Agenda e alertas |
| `POST` | `/google/scan` | Varredura de recrutamento |
| `POST` | `/google/draft` | Cria rascunho, não envia |
| `POST` | `/google/calendar` | Cria compromisso comprovado |
| `POST` | `/google/questionnaire/complete` | Marca conclusão manual |

Swagger: `http://localhost:8765/docs`.

## API de fundação — porta 8001

- `GET /health/live`
- `GET /health/ready`
- `GET /api/v1/system/status`
- `GET /metrics`
- Swagger em `/docs`

O dashboard usa o rewrite `/agent/:path*` para acessar o host sem expor URLs diferentes ao usuário.
