#!/bin/bash
# Backs up dev and prod SQLite databases to backups/ with a timestamp.
# Uses sqlite3 .backup for an atomic snapshot (safe against concurrent writers);
# falls back to cp only if sqlite3 CLI is unavailable.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$REPO_ROOT/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

mkdir -p "$BACKUP_DIR"

if command -v sqlite3 >/dev/null 2>&1; then
    BACKUP_METHOD="sqlite3"
else
    BACKUP_METHOD="cp"
    echo "  ⚠ sqlite3 CLI not found, falling back to cp (not safe if app is running)"
fi

backup_one() {
    local label="$1"
    local source="$2"
    local target="$3"

    if [ ! -f "$source" ]; then
        echo "  — $label DB not found, skipping"
        return
    fi

    if [ "$BACKUP_METHOD" = "sqlite3" ]; then
        sqlite3 "$source" ".backup '$target'"
    else
        cp "$source" "$target"
    fi
    echo "  ✓ $label → backups/$(basename "$target")"
}

backup_one "dev"  "$REPO_ROOT/instance/database_dev.db"  "$BACKUP_DIR/database_dev_$TIMESTAMP.db"
backup_one "prod" "$REPO_ROOT/instance/database_prod.db" "$BACKUP_DIR/database_prod_$TIMESTAMP.db"
