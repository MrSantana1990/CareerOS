# Instalação no Windows

## Pré-requisitos

- Windows 11 e Google Chrome.
- Python 3.12+, Node.js 22+ e Git.
- Docker Desktop para PostgreSQL, Redis, API, worker e observabilidade.
- Opcional: IA local com `llama-server.exe` e modelo GGUF.

## Projeto

```powershell
git clone https://github.com/MrSantana1990/CareerOS.git
Set-Location CareerOS
Copy-Item .env.example .env
./scripts/setup.ps1
```

Troque obrigatoriamente `POSTGRES_PASSWORD` e `GRAFANA_ADMIN_PASSWORD` no `.env`.

## Google

Coloque o cliente OAuth Desktop em `.runtime/google/google-credentials.json` e execute:

```powershell
./.venv/Scripts/python.exe ./scripts/authorize-google.py
```

Consulte [docs/AI_AND_GOOGLE.md](docs/AI_AND_GOOGLE.md).

## Iniciar

```powershell
./scripts/start.ps1
```

Para iniciar apenas os processos locais em segundo plano:

```powershell
./scripts/start-background.ps1
```

Painel: `http://localhost:3000`. Para celular, descubra o IPv4 do Wi‑Fi com `ipconfig` e acesse `http://IP:3000` na mesma rede.

## Parar

```powershell
./scripts/stop.ps1
```

Os dados locais permanecem em `.runtime/` e nos volumes Docker.
