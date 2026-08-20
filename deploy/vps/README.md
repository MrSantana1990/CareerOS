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
