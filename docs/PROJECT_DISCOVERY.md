# Project Discovery

Data: 22/07/2026. Escopo: inspeção somente leitura de `D:\DEV`; nenhum projeto preexistente foi alterado.

## Ambiente

Windows com Git 2.45.1, Docker 29.4.1 (Engine ativo), Node.js 22.20.0, npm 10.9.3, pnpm 10.19.0 e Python 3.12.3. Chrome e Edge estão instalados. `psql`, Redis, Poetry, uv e Yarn não estão no PATH. PostgreSQL e Redis serão executados por containers. O navegador Playwright, quando implementado, rodará no host para permitir acompanhamento visual.

## Inventário de projetos

Foram encontrados: `.claude`, `.github`, `aeg-gestao-operacional`, `alerta-cidadao`, `atualizacoes`, `baixar_videos_helpsystem`, `cfpc-demo`, `CifrasPalco`, `docs`, `empadas-da-lia`, `Helpsystempro_Bot`, `Helpsystem_Pro`, `img-cfpc`, `jd-marcia`, `jd-marcia-modified`, `jd-marcia-pro`, `pintor-pro-ssa`, `pintura_orcamento`, `RLMANUTENCAOES`, `SDK`, `temurin17`, `tools`, `VF_TOLDOS` e `windows-maintenance`.

## Referências selecionadas

- `aeg-gestao-operacional`: estrutura com front-end separado, Dockerfiles e Compose com health checks e volumes.
- `Helpsystempro_Bot`: aplicação Python/FastAPI local e bind de portas em loopback.
- `jd-marcia-pro`: PostgreSQL em Compose, migrations e dependências condicionadas à saúde.

Os projetos foram usados apenas como referência conceitual. Nenhum código foi copiado. Credenciais padrão presentes em projetos antigos foram identificadas como padrão a evitar.

## Stack e decisões

Monorepo pnpm; Next.js/React/TypeScript/Tailwind no web; FastAPI/Pydantic/SQLAlchemy/Alembic no API; Dramatiq/Redis no worker; PostgreSQL 16 com pgvector; Prometheus/Grafana; logs JSON. Playwright e InfoJobs ficam para a etapa de automação assistida, após domínio/perfil/vagas.

## Riscos

- Termos e layouts das plataformas mudam; conectores precisam de feature flags, ritmo controlado e intervenção humana.
- Automação pode causar bloqueios de conta; nenhuma ação real deve ocorrer sem confirmação explícita.
- Perfil persistente, currículos e screenshots são dados sensíveis e ficam fora do Git.
- Docker Desktop precisa estar ativo e as portas 3000, 3001, 5432, 6379, 8000 e 9090 livres.
- Dependências foram fixadas inicialmente, mas exigem auditoria contínua.
- O registry marcou versões iniciais de Next.js/Recharts como antigas; atualizar e auditar antes de usar dados reais.
- Windows Defender/locking pode tornar o primeiro `pnpm install` lento ou gerar `EBUSY`; repetir após liberar o arquivo costuma reutilizar o cache.
- O modelo completo possui muitas entidades; a migration inicial cria apenas infraestrutura de settings/auditoria para evitar schema prematuro.

## Arquitetura proposta

`web -> api -> domínio/repositórios -> PostgreSQL`, com tarefas assíncronas em `api -> Redis -> worker`. Automação de navegador será um processo host isolado, comandado por fila e com parada de emergência. Eventos auditáveis alimentam tempo real e métricas. Adaptadores isolam fontes de vagas, IA e e-mail.

## Modelo de dados inicial

Fundações criadas: `system_settings` e `audit_logs`. Próximo corte: `profiles`, `skills`, `experiences`, `resumes`, `resume_versions`, `job_sources`, `jobs`, `job_matches`, `applications`, `application_events`, `automation_runs` e `blocked_entities`, todos com UUID, timestamps, constraints e soft delete onde fizer sentido.

## Roadmap e backlog MVP

1. Fundação: Compose, API, worker, web, migration, saúde, métricas, scripts e documentação.
2. Perfil: CRUD, habilidades, experiências, preferências e upload seguro de currículo.
3. Vagas: modelo normalizado, regras Gupy, deduplicação e matching explicável.
4. Automação: Playwright visível, perfil persistente, InfoJobs em modo coleta e candidatura assistida.
5. Operação: SSE, histórico, evidências, pausa/retomada e relatório diário.
6. Hardening: auditoria, sanitização, testes de integração/E2E e threat-model review.

## Critérios de aceite da fundação

- Um comando sobe os serviços após configuração do `.env`.
- Web e API respondem; PostgreSQL e Redis possuem health checks.
- Migration executa automaticamente; API publica liveness/readiness e métricas.
- Autoaplicação nasce desligada e Gupy aparece bloqueada.
- Arquivos sensíveis e runtime estão ignorados.
- Testes mínimos comprovam saúde e defaults de segurança.

## Decisões que exigem confirmação futura

- Dados profissionais reais, localização, salário, modalidades e currículos.
- Estratégia de autenticação local (usuário único ou login local).
- Consentimento para instalar Playwright e criar perfil persistente.
- Seletores/termos aceitos do InfoJobs e limite diário por plataforma.
- Política exata de confirmação antes do envio (recomendação: sempre no MVP).
- Retenção e criptografia de screenshots, currículos e logs.
