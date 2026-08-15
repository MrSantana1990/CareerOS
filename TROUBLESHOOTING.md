# Troubleshooting

- Docker indisponível: abra Docker Desktop e execute `docker info`.
- Porta ocupada: ajuste portas no `.env` ou encerre o processo conflitante.
- Compose recusa iniciar: configure senhas não vazias no `.env`.
- Readiness 503: confira `docker compose logs api postgres`.
- Para parar preservando dados: `.\scripts\stop.ps1`.

