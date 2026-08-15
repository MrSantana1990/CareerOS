# Architecture

CareerOS usa monorepo modular. `apps/web` contém apresentação; `apps/api` expõe casos de uso e health checks; `apps/worker` executa tarefas idempotentes; `packages` receberá domínio e adapters compartilhados; `infrastructure` contém runtime local e observabilidade.

Princípios: domínio independente de frameworks, adapters por plataforma, autoaplicação opt-in, Gupy bloqueada em múltiplas camadas, nenhuma senha de plataforma armazenada, correlação e auditoria em ações relevantes.

Veja `docs/decisions/0001-modular-monorepo.md` e `docs/PROJECT_DISCOVERY.md`.

