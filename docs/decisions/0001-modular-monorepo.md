# ADR 0001 — Monorepo modular local-first

Status: aceito.

Escolha: Next.js, FastAPI, Dramatiq, PostgreSQL/pgvector e Redis em serviços separados por Docker Compose; navegador visual futuramente no host Windows.

Consequências: fronteiras claras e evolução independente, ao custo de mais serviços locais. O navegador no host facilita login manual, MFA e intervenção sem colocar cookies em containers.

