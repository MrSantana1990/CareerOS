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

## API Core — porta 8000

- `GET /health/live`
- `GET /health/ready`
- `GET /api/v1/system/status`
- `POST /api/v1/jobs` — ingere ou deduplica uma vaga
- `GET /api/v1/jobs` — lista vagas e último score
- `POST /api/v1/jobs/{job_id}/score` — calcula e persiste o Score V2
- `POST /api/v1/applications/{application_id}/transition` — aplica transição válida e registra evento imutável
- `GET /api/v1/sources` — lista configurações de fontes estruturadas
- `POST /api/v1/sources` — cria ou atualiza uma fonte, desligada por padrão
- `POST /api/v1/sources/{connection_id}/runs` — registra execução e resultado do worker
- `GET /metrics`
- Swagger em `/docs`

As rotas de domínio exigem o token administrativo no servidor. O navegador usa o BFF do portal e não recebe esse segredo.

O dashboard usa o rewrite `/agent/:path*` para acessar o host sem expor URLs diferentes ao usuário.
