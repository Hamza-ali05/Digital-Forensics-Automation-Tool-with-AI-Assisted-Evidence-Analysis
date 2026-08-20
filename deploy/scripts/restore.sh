#!/bin/bash
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup_archive.tar.gz>"
    echo ""
    echo "Available backups:"
    ls -lt "${DFAT_BACKUP_DIR:-/var/backups/dfat}"/*.tar.gz 2>/dev/null || echo "  No backups found."
    exit 1
fi

ARCHIVE="$1"
COMPOSE_FILE="${COMPOSE_FILE:-deploy/docker-compose.production.yml}"

if [ ! -f "$ARCHIVE" ]; then
    echo "ERROR: Backup archive not found: $ARCHIVE"
    exit 1
fi

echo "DFAT Restore"
echo "============"
echo "Archive: $ARCHIVE"
echo ""
read -rp "This will overwrite current data. Continue? (y/N): " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted."
    exit 0
fi

TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

echo "Extracting backup..."
tar -xzf "$ARCHIVE" -C "$TEMP_DIR"
BACKUP_DIR=$(ls "$TEMP_DIR")

echo "Stopping services..."
docker compose -f "$COMPOSE_FILE" stop backend

# Restore database
if [ -f "$TEMP_DIR/$BACKUP_DIR/dfat.db" ]; then
    echo "Restoring database..."
    cp "$TEMP_DIR/$BACKUP_DIR/dfat.db" /var/lib/dfat/dfat.db
fi

# Restore audit logs
if [ -d "$TEMP_DIR/$BACKUP_DIR/audit_logs" ]; then
    echo "Restoring audit logs..."
    cp -r "$TEMP_DIR/$BACKUP_DIR/audit_logs/"* /var/log/dfat/
fi

# Restore reports
if [ -d "$TEMP_DIR/$BACKUP_DIR/reports" ]; then
    echo "Restoring reports..."
    cp -r "$TEMP_DIR/$BACKUP_DIR/reports/"* /var/lib/dfat/reports/
fi

echo "Running database migrations..."
docker compose -f "$COMPOSE_FILE" run --rm backend alembic upgrade head

echo "Restarting services..."
docker compose -f "$COMPOSE_FILE" up -d

echo ""
echo "Restore complete. Verify with:"
echo "  curl -f http://localhost:8000/api/v1/health"
