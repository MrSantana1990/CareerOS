# HelpSystem Carreira na VPS

Implantação privada do núcleo server-side. O painel escuta somente em 127.0.0.1 e deve ser publicado exclusivamente por Cloudflare Tunnel + Access.

## Preparação

1. Copie .env.example para .env.
2. Gere três segredos diferentes.
3. Restrinja o arquivo com chmod 600.
4. Suba o ambiente:

       docker compose --env-file .env up -d --build

5. Verifique:

       docker compose --env-file .env ps
       curl http://127.0.0.1:8093/health/live

## Travas iniciais

- banco e Redis não possuem portas públicas;
- web ligada apenas a localhost;
- API protegida por token em produção;
- autoenvio e reconhecimento de risco permanecem desligados;
- o executor Playwright local não é exposto pela VPS;
- o domínio só deve ser conectado depois da política Cloudflare Access.

## Backup

Faça pg_dump diariamente, criptografe o arquivo e envie uma cópia para armazenamento externo. Teste a restauração mensalmente. Tokens Google, currículos e documentos nunca devem entrar no Git.

## CI/CD — o que existe, o que foi automatizado (05/09/2026)

**Antes deste documento, o deploy dependia de uma sessão de agente (Claude/Codex) ter acesso SSH prévio à VPS** — uma dependência estrutural incorreta, corrigida abaixo.

### CI existente

- `.github/workflows/ci.yml` ("Qualidade"): roda em todo PR e em todo push para `main`. Três jobs: `web` (lint/test/build do painel), `api` (ruff, pytest de `api`/`worker`/`automation-host`, `alembic upgrade head` contra um Postgres real de CI), `containers` (valida o `docker-compose.yml` de produção e builda as 4 imagens reais). **Isso já gate-keeps todo merge — não precisa ser reimplementado pelo workflow de deploy.**

### CD existente (novo — antes não existia)

- `.github/workflows/deploy.yml` ("Deploy VPS"): dispara via `workflow_run` quando "Qualidade" conclui com sucesso em `main`, ou manualmente via `workflow_dispatch`. Conecta na VPS via `appleboy/ssh-action` usando o secret `CAREEROS_DEPLOY_SSH_KEY` (chave dedicada, só para CD — instalada em `~/.ssh/authorized_keys` da VPS, nunca a mesma chave usada por uma sessão interativa de agente). Sequência: backup do Postgres (`pg_dump`, mantém 14 dias) → `git fetch && git reset --hard origin/main` → `docker compose build && up -d --remove-orphans` (migrations do Alembic rodam automaticamente no `CMD` do container `api`) → health check de todos os serviços com healthcheck definido (`postgres`, `redis`, `api`, `integrations`, `web`) via `docker inspect`, com timeout → em falha: dump de logs de cada serviço + rollback automático (`git reset --hard` para o commit anterior + rebuild) + `exit 1` (falha visível no Actions, é o "failure report").

### Deploy manual por agente (método usado até 05/09/2026, mantido só como fallback de emergência)

`ssh` direto na VPS + `git pull --ff-only` + `docker compose --env-file .env up -d --build <serviço>` a partir deste diretório. Ainda funciona (útil para hotfix fora do fluxo normal ou para depurar um serviço específico), mas **não é mais o caminho principal** — o caminho principal agora é PR → merge → CI → CD automático.

### Credenciais necessárias

- **Deploy automático (CD):** só o secret `CAREEROS_DEPLOY_SSH_KEY` no repositório GitHub (chave privada dedicada; a pública está em `authorized_keys` da VPS). Nenhuma sessão local precisa de nada.
- **Acesso interativo humano/agente (depuração, não deploy):** chave SSH pessoal instalada em `authorized_keys` (ex.: `~/.ssh/careeros_vps` + `Host careeros-vps` em `~/.ssh/config`). `D:/DEV/VPS.txt` guarda a senha de root só como **recuperação de acesso de último recurso** — nunca deve virar dependência permanente de pipeline nem ser referenciado por automação.
- `deploy/vps/.env` já existe na VPS com os segredos de aplicação (`POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `ADMIN_API_TOKEN`, etc.) — nem o deploy manual nem o CD escrevem nesse arquivo; ele é gerido fora do Git, manualmente, uma vez.

### Scripts já disponíveis

- Nenhum script de deploy dedicado existia antes — o processo era 100% comandos manuais documentados só neste README. `deploy.yml` agora é a única fonte de verdade do processo de deploy; qualquer mudança no fluxo de deploy deve ser feita nesse workflow, não em instruções soltas.

### Comparação com o projeto AEG (`aeg-gestao-operacional`)

O AEG já tinha exatamente este problema resolvido: `.github/workflows/deploy-contabo.yml`, mesmo padrão (`appleboy/ssh-action`, chave dedicada em secret, backup → build → up → healthcheck → rollback/relatório de falha). `deploy.yml` do CareerOS segue o mesmo mecanismo por consistência — a diferença é que o CareerOS já tem CI própria e completa rodando em `push: main` (o AEG combina validação e deploy no mesmo workflow), então o deploy do CareerOS dispara em cima da CI existente via `workflow_run` em vez de duplicar os testes.
