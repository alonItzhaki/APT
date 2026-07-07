#!/usr/bin/env bash
# Restore a backup over the live DB. Stop the services first!
set -euo pipefail
cd "$(dirname "$0")/.."
BACKUP="${1:?usage: restore.sh backups/apt-YYYYmmdd-HHMMSS.db.gz}"
DB_PATH="${APT_DB_PATH:-data/apt.db}"
gunzip -kc "$BACKUP" > "${DB_PATH}.restored"
mv "${DB_PATH}.restored" "$DB_PATH"
rm -f "${DB_PATH}-wal" "${DB_PATH}-shm"
echo "restored $BACKUP -> $DB_PATH"
