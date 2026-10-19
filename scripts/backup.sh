#!/bin/sh
# Nightly backup: database dump + uploaded photos/documents.
# Schedule it (Linux: crontab -e →  0 2 * * * /path/to/scripts/backup.sh)
# and copy ./backups to Google Drive with rclone:  rclone copy backups gdrive:dsquare-backups
set -e
cd "$(dirname "$0")/.."
. ./.env
STAMP=$(date +%Y-%m-%d_%H%M)
mkdir -p backups
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "backups/db_$STAMP.sql.gz"
docker compose exec -T web tar czf - -C /app media > "backups/media_$STAMP.tar.gz"
# keep the last 30 days locally
find backups -type f -mtime +30 -delete
echo "Backup written to backups/*_$STAMP.*"
