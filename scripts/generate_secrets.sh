#!/bin/bash
set -euo pipefail

echo "Generating DFAT production secrets..."

if [ -f .env.production.local ]; then
    echo "WARNING: .env.production.local already exists."
    read -rp "Overwrite? (y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Aborted."
        exit 0
    fi
fi

cat > .env.production.local <<EOF
# DFAT Production Secrets — Generated $(date -u +"%Y-%m-%dT%H:%M:%SZ")
DFAT_ENV=production
DFAT_JWT_SECRET=$(openssl rand -hex 32)
DFAT_DATABASE_URL=sqlite+aiosqlite:///var/lib/dfat/dfat.db
EOF

chmod 600 .env.production.local

echo ""
echo "Secrets written to .env.production.local"
echo "IMPORTANT: Keep this file secure and never commit it to version control."
