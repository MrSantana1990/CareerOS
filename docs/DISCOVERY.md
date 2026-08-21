# Discovery Engine

## Escopo da Fase 2

O motor descobre vagas publicadas por APIs públicas de ATS, normaliza os campos e envia cada registro ao Core, que aplica deduplicação e preserva todas as fontes relacionadas.

Adapters entregues:

- Greenhouse Job Board API;
- Lever Postings API;
- Ashby Job Postings API.

Não há scraping, login em plataforma, candidatura ou tentativa de contornar CAPTCHA/MFA nesta fase.

## Segurança operacional

- `AUTO_DISCOVERY_ENABLED=false` por padrão no worker e scheduler;
- cada fonte persistida também nasce com `enabled=false`;
- identificadores aceitam apenas letras, números, `_` e `-`, impedindo URL arbitrária;
- endpoints externos são fixos no código;
- no máximo 500 vagas por fonte e intervalo mínimo de 30 minutos;
- somente dados publicados são normalizados; campos ausentes continuam ausentes;
- o token administrativo fica apenas entre containers privados.

## Fluxo

1. Scheduler consulta fontes habilitadas no Core.
2. Cadência individual impede polling antecipado.
3. Worker consulta uma API pública estruturada.
4. Adapter remove HTML e cria o contrato normalizado.
5. Core calcula o fingerprint e faz upsert da relação em `job_sources`.
6. `discovery_runs` registra encontrado, criado, deduplicado ou erro.

## Ativação consciente

Cadastrar fontes via `POST /api/v1/sources`, inicialmente com `enabled=false`. Depois de validar os identificadores das empresas, habilitar as conexões escolhidas e alterar `AUTO_DISCOVERY_ENABLED` no worker e scheduler durante uma janela controlada.

## Rollback

Rollback preferencial: definir `AUTO_DISCOVERY_ENABLED=false` e reiniciar worker/scheduler. Isso interrompe novas coletas sem apagar vagas. A migration `0006` é aditiva; não executar downgrade em produção sem backup e janela aprovada.
