#!/bin/bash
set -euo pipefail

BACKUP_BASE="${DFAT_BACKUP_DIR:-/var/backups/dfat}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_BASE/$TIMESTAMP"
RETAIN_COUNT="${DFAT_BACKUP_RETAIN:-30}"

echo "DFAT Backup - $TIMESTAMP"
echo "========================"

mkdir -p "$BACKUP_DIR"

# Backup database
if [ -f /var/lib/dfat/dfat.db ]; then
    echo "Backing up database..."
    cp /var/lib/dfat/dfat.db "$BACKUP_DIR/dfat.db"
fi

# Backup audit logs
if [ -d /var/log/dfat/ ]; then
    echo "Backing up audit logs..."
    cp -r /var/log/dfat/ "$BACKUP_DIR/audit_logs/"
fi

# Backup reports
if [ -d /var/lib/dfat/reports/ ]; then
    echo "Backing up reports..."
    cp -r /var/lib/dfat/reports/ "$BACKUP_DIR/reports/"
fi

# Backup configuration (not secrets)
if [ -f config/production.yaml ]; then
    echo "Backing up configuration..."
    cp config/production.yaml "$BACKUP_DIR/"
fi

# Compress
echo "Compressing..."
tar -czf "$BACKUP_DIR.tar.gz" -C "$BACKUP_BASE" "$TIMESTAMP"
rm -rf "$BACKUP_DIR"

echo "Backup created: $BACKUP_DIR.tar.gz"

# Retain last N backups
EXCESS=$(ls -t "$BACKUP_BASE"/*.tar.gz 2>/dev/null | tail -n +$((RETAIN_COUNT + 1)))
if [ -n "$EXCESS" ]; then
    echo "$EXCESS" | xargs rm -f
    echo "Pruned old backups (retaining last $RETAIN_COUNT)"
fi

echo "Done."
