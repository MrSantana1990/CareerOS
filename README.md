# CareerOS — Career Automation Platform

Plataforma local, modular e auditável para apoiar descoberta, análise e acompanhamento de vagas. Esta entrega contém somente a fundação: não busca vagas nem envia candidaturas reais.

## Arquitetura

Next.js no dashboard, FastAPI na API, Dramatiq/Redis no worker, PostgreSQL/pgvector, Prometheus e Grafana via Docker Compose. Autoaplicação inicia desligada e Gupy é bloqueada.

## Início rápido no Windows

Requer Docker Desktop, Git, Node 22+, pnpm 10+ e Python 3.12+.

```powershell
Set-Location D:\DEV\career-automation-platform
.\scripts\setup.ps1
# troque as senhas no .env
.\scripts\start.ps1
```

Dashboard: `http://localhost:3000`. OpenAPI: `http://localhost:8001/docs`.

## Testes

```powershell
.\scripts\run-tests.ps1
```

## Segurança e limitações

Não use dados reais antes de revisar `SECURITY.md`, `THREAT_MODEL.md` e `DATA_PRIVACY.md`. Nenhum conector, navegador Playwright ou fluxo de candidatura foi implementado. O botão de emergência no dashboard é apenas visual nesta fundação e permanece desabilitado até existir uma automação controlável.

## Documentação

Discovery em `docs/PROJECT_DISCOVERY.md`; arquitetura em `ARCHITECTURE.md`; instalação detalhada em `SETUP_WINDOWS.md`; API em `API.md`; roadmap em `ROADMAP.md`.
