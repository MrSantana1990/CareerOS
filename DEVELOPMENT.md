# Desenvolvimento

## Ambiente

- Python 3.12
- Node.js 22
- Next.js 15
- FastAPI e Playwright
- Docker Desktop para PostgreSQL, Redis e observabilidade

```powershell
./scripts/setup.ps1
./scripts/start-background.ps1
```

## Validação

```powershell
./.venv/Scripts/python.exe -m py_compile ./apps/automation-host/src/main.py ./apps/automation-host/src/google_career.py
npm --prefix ./apps/web run build
./scripts/run-tests.ps1
```

Testes não podem enviar candidaturas, mensagens ou eventos reais. Use mocks e páginas simuladas; qualquer teste de integração Google deve permanecer somente leitura, salvo autorização explícita.

## Convenções

- Comportamento de plataforma fica isolado no automation host.
- Estado precisa ser idempotente e auditável.
- Não registrar falsos sucessos.
- Toda nova resposta automática exige evidência do perfil.
- Arquivos sensíveis e artefatos gerados nunca entram no Git.
