#!/usr/bin/env bash
# Nightly SQLite snapshot; uploads to Oracle Object Storage when configured.
set -euo pipefail
cd "$(dirname "$0")/.."
DB_PATH="${APT_DB_PATH:-data/apt.db}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
OUT="backups/apt-${STAMP}.db"
mkdir -p backups
sqlite3 "$DB_PATH" ".backup '${OUT}'"
gzip "$OUT"
if [ -n "${APT_BACKUP_BUCKET:-}" ]; then
    oci os object put --bucket-name "$APT_BACKUP_BUCKET" --file "${OUT}.gz" --name "apt-${STAMP}.db.gz"
fi
find backups -name 'apt-*.db.gz' -mtime +14 -delete
echo "backup written: ${OUT}.gz"
