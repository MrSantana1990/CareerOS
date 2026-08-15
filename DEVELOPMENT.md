# Development

Use Python 3.12, Node 22 e pnpm 10. API: `python -m pip install -e ".\apps\api[dev]"` e `uvicorn src.main:app --app-dir apps/api --reload`. Web: `pnpm --dir apps/web dev`. Prefira testes mockados; nunca execute candidatura real em testes.

