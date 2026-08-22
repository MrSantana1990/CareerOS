#!/usr/bin/env bash
# Backup do PostgreSQL do CareerOS / HelpSystem Carreira (pensado para rodar na VPS).
#
# Uso:
#   scripts/backup-postgres.sh [--label texto] [--compose-file caminho] [--out-dir caminho]
#
# Exemplo:
#   scripts/backup-postgres.sh --label baseline-plano-mestre
set -euo pipefail

LABEL="manual"
COMPOSE_FILE="deploy/vps/docker-compose.yml"
OUT_DIR="/opt/backups/helpsystempro-carreira"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --label)
      LABEL="$2"
      shift 2
      ;;
    --compose-file)
      COMPOSE_FILE="$2"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="$2"
      shift 2
      ;;
    *)
      echo "Argumento desconhecido: $1" >&2
      exit 1
      ;;
  esac
done

mkdir -p "$OUT_DIR"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo "sem-git")"
OUT_FILE="$OUT_DIR/carreira-${LABEL}-${TIMESTAMP}-${COMMIT}.dump"

docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$OUT_FILE"

chmod 600 "$OUT_FILE"

echo "Backup criado: $OUT_FILE"
ls -lh "$OUT_FILE"
