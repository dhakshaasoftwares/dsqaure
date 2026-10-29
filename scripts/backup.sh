#!/bin/sh
# Backup of one installation: database dump + uploaded photos/documents.
#
#   scripts/backup.sh                    # the main install (uses .env)
#   scripts/backup.sh selvam-builders    # a client created with new_client.sh
#
# Schedule it nightly (Linux/Mac: crontab -e →  0 2 * * * /path/to/scripts/backup.sh)
# and copy ./backups off the machine with rclone:  rclone copy backups gdrive:dsquare-backups
set -e
cd "$(dirname "$0")/.."

if [ -n "$1" ]; then
  ENV_FILE="clients/$1/.env"; PROJECT="$1"
else
  ENV_FILE=".env"; PROJECT="$(basename "$(pwd)")"
fi
[ -f "$ENV_FILE" ] || { echo "No $ENV_FILE found"; exit 1; }
. "./$ENV_FILE"
export ENV_FILE

STAMP=$(date +%Y-%m-%d_%H%M)
OUT="backups/$PROJECT"
mkdir -p "$OUT"
DC="docker compose -p $PROJECT --env-file $ENV_FILE"
$DC exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$OUT/db_$STAMP.sql.gz"
$DC exec -T web tar czf - -C /app media > "$OUT/media_$STAMP.tar.gz"
# keep the last 30 days locally
find "$OUT" -type f -mtime +30 -delete
echo "Backup written to $OUT/*_$STAMP.*"
