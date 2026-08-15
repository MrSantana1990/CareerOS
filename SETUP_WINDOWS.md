# Setup Windows

Pré-requisitos: Docker Desktop ativo, Git, Node 22+, pnpm e Python 3.12+.

```powershell
Set-Location D:\DEV\career-automation-platform
.\scripts\setup.ps1
# edite .env e troque POSTGRES_PASSWORD e GRAFANA_ADMIN_PASSWORD
.\scripts\start.ps1
```

Acesse `http://localhost:3000`. API em `http://localhost:8001/docs`; Grafana em `http://localhost:3001`.
