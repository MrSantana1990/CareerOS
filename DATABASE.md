# Database

PostgreSQL 16 com pgvector e migrations Alembic. IDs são UUID; timestamps usam timezone. A fundação cria `system_settings` e `audit_logs`. O modelo de domínio completo será adicionado por fatias verticais, com índices, constraints e soft delete definidos por entidade.

