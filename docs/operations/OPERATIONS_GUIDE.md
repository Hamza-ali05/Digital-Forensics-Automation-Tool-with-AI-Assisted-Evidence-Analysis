# DFAT Operations Guide

System administration and operational procedures for the Digital Forensics Automation Tool.

---

## Table of Contents

1. [Daily Operations Checklist](#1-daily-operations-checklist)
2. [Backup and Restore](#2-backup-and-restore)
3. [Log Monitoring and Rotation](#3-log-monitoring-and-rotation)
4. [Database Maintenance](#4-database-maintenance)
5. [Ollama Model Management](#5-ollama-model-management)
6. [Troubleshooting Guide](#6-troubleshooting-guide)
7. [Emergency Procedures](#7-emergency-procedures)

---

## 1. Daily Operations Checklist

Perform these checks daily (or automate via cron):

### Morning Checks

- [ ] **Verify all services are running**

  ```bash
  make deploy-up
  docker compose -f deploy/docker-compose.production.yml ps
  ```

- [ ] **Check health endpoint**

  ```bash
  curl -sf https://localhost/api/v1/health | python -m json.tool
  ```

- [ ] **Check readiness (all components)**

  ```bash
  curl -sf https://localhost/api/v1/health/ready | python -m json.tool
  ```

- [ ] **Review error logs from the last 24 hours**

  ```bash
  docker compose -f deploy/docker-compose.production.yml logs --since 24h backend | grep -i error
  ```

- [ ] **Verify Ollama is responsive**

  ```bash
  docker exec dfat-ollama-1 ollama list
  ```

- [ ] **Check disk space**

  ```bash
  df -h /var/lib/dfat /var/log/dfat /var/backups/dfat
  ```

### Weekly Checks

- [ ] Verify backup integrity (restore a recent backup to a test environment)
- [ ] Review audit logs for unusual activity
- [ ] Check for security updates (`pip list --outdated`, `npm audit`)
- [ ] Review monitoring metrics for performance trends
- [ ] Verify SSL certificate expiry (`openssl x509 -enddate -noout -in deploy/nginx/ssl/cert.pem`)

---

## 2. Backup and Restore

### Automated Backup

DFAT includes a backup script that creates compressed archives:

```bash
make deploy-backup
```

This backs up:
- SQLite database (`/var/lib/dfat/dfat.db`)
- Audit logs (`/var/log/dfat/`)
- Generated reports (`/var/lib/dfat/reports/`)
- Production configuration (`config/production.yaml`)

Backups are saved to `/var/backups/dfat/` with timestamps. The last 30 backups are retained by default (configurable via `DFAT_BACKUP_RETAIN`).

### Scheduled Backups

Set up a daily backup cron job:

```bash
# Daily at 02:00
echo "0 2 * * * cd /opt/dfat && bash deploy/scripts/backup.sh >> /var/log/dfat/backup.log 2>&1" | crontab -
```

### Manual Backup

```bash
bash deploy/scripts/backup.sh
```

### Restore from Backup

```bash
make deploy-restore ARCHIVE=/var/backups/dfat/20260818_020000.tar.gz
```

The restore process:
1. Prompts for confirmation
2. Stops the backend service
3. Extracts and restores database, logs, and reports
4. Runs database migrations to ensure schema compatibility
5. Restarts all services

### Backup Verification

Periodically test restores in a staging environment:

```bash
# Create a temporary test environment
mkdir /tmp/dfat-restore-test
cd /tmp/dfat-restore-test
tar -xzf /var/backups/dfat/latest.tar.gz
sqlite3 */dfat.db "SELECT COUNT(*) FROM users;"
```

---

## 3. Log Monitoring and Rotation

### Log Locations

| Log | Path | Purpose |
|-----|------|---------|
| Audit log | `/var/log/dfat/audit.log` | All system actions (JSON format) |
| Error log | `/var/log/dfat/errors.log` | ERROR+ severity only |
| Nginx access | `/var/log/nginx/access.log` | HTTP request log |
| Nginx error | `/var/log/nginx/error.log` | Nginx errors |

### Log Format

Production logs use structured JSON:

```json
{"timestamp": "2026-08-18T10:30:00Z", "level": "WARNING", "logger": "dfat.pipeline", "message": "Parser timeout exceeded"}
```

### Log Rotation

**Application logs** are rotated by Python's `RotatingFileHandler`:
- `audit.log`: 100 MB max, 10 backup files
- `errors.log`: 50 MB max, 5 backup files

**System-level rotation** via logrotate (installed at `deploy/logrotate/dfat`):

```bash
sudo cp deploy/logrotate/dfat /etc/logrotate.d/dfat
```

Configuration: daily rotation, 30 days retention, compressed.

### Monitoring Logs in Real Time

```bash
# All service logs
make deploy-logs

# Backend only
docker compose -f deploy/docker-compose.production.yml logs -f backend

# Filter errors
docker compose -f deploy/docker-compose.production.yml logs -f backend 2>&1 | grep '"level":"ERROR"'
```

### Log Analysis via API

Admins can query recent logs via the monitoring endpoint:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://localhost/api/v1/monitoring/logs?level=ERROR&limit=50"
```

---

## 4. Database Maintenance

### Database Location

Production: `/var/lib/dfat/dfat.db` (SQLite)

### Running Migrations

After code updates, apply database migrations:

```bash
docker compose -f deploy/docker-compose.production.yml \
  run --rm backend alembic upgrade head
```

Check current migration status:

```bash
docker compose -f deploy/docker-compose.production.yml \
  run --rm backend alembic current
```

View migration history:

```bash
docker compose -f deploy/docker-compose.production.yml \
  run --rm backend alembic history
```

### Database Vacuum

SQLite databases benefit from periodic vacuuming to reclaim space:

```bash
# Stop the backend first
docker compose -f deploy/docker-compose.production.yml stop backend

# Vacuum
sqlite3 /var/lib/dfat/dfat.db "VACUUM;"

# Restart
docker compose -f deploy/docker-compose.production.yml start backend
```

Schedule monthly:

```bash
# First Sunday of each month at 03:00
echo "0 3 1-7 * 0 docker compose -f /opt/dfat/deploy/docker-compose.production.yml stop backend && sqlite3 /var/lib/dfat/dfat.db 'VACUUM;' && docker compose -f /opt/dfat/deploy/docker-compose.production.yml start backend" | crontab -
```

### Database Integrity Check

```bash
sqlite3 /var/lib/dfat/dfat.db "PRAGMA integrity_check;"
```

Expected output: `ok`

### Checking Table Sizes

```bash
sqlite3 /var/lib/dfat/dfat.db ".tables"
sqlite3 /var/lib/dfat/dfat.db "SELECT name, COUNT(*) FROM (SELECT 'users' as name UNION ALL SELECT 'cases' UNION ALL SELECT 'evidence_records' UNION ALL SELECT 'artefact_records' UNION ALL SELECT 'audit_log') t LEFT JOIN (SELECT 'users' as tbl, COUNT(*) as cnt FROM users UNION ALL SELECT 'cases', COUNT(*) FROM cases UNION ALL SELECT 'evidence_records', COUNT(*) FROM evidence_records UNION ALL SELECT 'artefact_records', COUNT(*) FROM artefact_records UNION ALL SELECT 'audit_log', COUNT(*) FROM audit_log) c ON t.name = c.tbl;"
```

---

## 5. Ollama Model Management

### Checking Model Status

```bash
docker exec dfat-ollama-1 ollama list
```

### Pulling/Updating the Model

```bash
# Pull LLaMA-3 (default)
bash deploy/scripts/setup_ollama_model.sh

# Pull a specific model
docker exec dfat-ollama-1 ollama pull llama3:8b

# Update to latest version
docker exec dfat-ollama-1 ollama pull llama3
```

### Testing the Model

```bash
docker exec dfat-ollama-1 ollama run llama3 "What is digital forensics?"
```

### Model Memory Requirements

| Model | RAM Required | Disk Space |
|-------|-------------|-----------|
| LLaMA-3 8B (Q4) | ~6 GB | ~4.7 GB |
| LLaMA-3 8B (FP16) | ~16 GB | ~15 GB |

The Docker Compose configuration limits Ollama to 8 GB RAM by default. Adjust in `deploy/docker-compose.production.yml` if using larger models.

### Graceful Degradation

If Ollama is unavailable:
- Pipeline triage falls back to rule-based analysis
- AI endpoints return appropriate error responses
- Health checks report AI as degraded (not failed)
- All non-AI functionality continues normally

---

## 6. Troubleshooting Guide

### Services Won't Start

**Symptom**: `docker compose up` fails or containers restart repeatedly.

**Diagnosis**:
```bash
docker compose -f deploy/docker-compose.production.yml logs --tail 50
docker compose -f deploy/docker-compose.production.yml ps
```

**Common causes and fixes**:

| Cause | Fix |
|-------|-----|
| Port 80/443 already in use | Stop other web servers: `sudo systemctl stop nginx apache2` |
| Missing `.env.production.local` | Run `bash scripts/generate_secrets.sh` |
| SSL certificates missing | Generate or copy certs to `deploy/nginx/ssl/` |
| Insufficient memory for Ollama | Increase Docker memory limit or reduce Ollama limit |

### Database Locked

**Symptom**: `sqlite3.OperationalError: database is locked`

**Fix**: Ensure only one backend instance writes to the database. If using multiple workers, only one should handle write operations, or switch to PostgreSQL for concurrent access.

```bash
# Check for stuck processes
fuser /var/lib/dfat/dfat.db

# Force unlock (last resort — may cause data loss)
sqlite3 /var/lib/dfat/dfat.db ".backup /tmp/dfat_backup.db"
cp /tmp/dfat_backup.db /var/lib/dfat/dfat.db
```

### Pipeline Jobs Stuck

**Symptom**: Jobs remain in "processing" status indefinitely.

**Diagnosis**:
```bash
# Check backend logs
docker compose -f deploy/docker-compose.production.yml logs --tail 100 backend | grep -i pipeline

# Check if Ollama is responsive (triage stage depends on it)
docker exec dfat-ollama-1 ollama list
```

**Fix**: Restart the backend service. Stuck jobs will be marked as failed on restart.

```bash
docker compose -f deploy/docker-compose.production.yml restart backend
```

### Ollama Out of Memory

**Symptom**: AI requests fail with OOM errors.

**Fix**:
1. Check memory usage: `docker stats dfat-ollama-1`
2. Increase the memory limit in `deploy/docker-compose.production.yml`
3. Use a smaller quantised model (Q4 instead of FP16)
4. Restart Ollama: `docker compose -f deploy/docker-compose.production.yml restart ollama`

### SSL/TLS Errors

**Symptom**: Browser shows certificate warnings or connections fail.

**Fix**:
1. Verify certificate files exist: `ls deploy/nginx/ssl/`
2. Check certificate validity: `openssl x509 -in deploy/nginx/ssl/cert.pem -text -noout`
3. Ensure the certificate matches the domain
4. For self-signed certs in testing, add an exception in the browser

### Health Check Failing

**Symptom**: `/api/v1/health` returns non-200 or readiness checks fail.

**Diagnosis**:
```bash
curl -v https://localhost/api/v1/health
curl -v https://localhost/api/v1/health/ready
curl -v -H "Authorization: Bearer $TOKEN" https://localhost/api/v1/health/detailed
```

The readiness endpoint reports individual component status. Fix the failing component.

### Frontend Not Loading

**Symptom**: Browser shows blank page or Nginx errors.

**Fix**:
1. Check frontend container: `docker compose -f deploy/docker-compose.production.yml logs frontend`
2. Verify Nginx config: `docker exec dfat-nginx-1 nginx -t`
3. Rebuild frontend: `docker compose -f deploy/docker-compose.production.yml build frontend`

---

## 7. Emergency Procedures

### System Recovery

If the system is completely unresponsive:

```bash
# 1. Stop all services
make deploy-down

# 2. Check disk space
df -h

# 3. Check Docker daemon
sudo systemctl status docker

# 4. Review system logs
journalctl -u docker --since "1 hour ago"

# 5. Restart Docker if needed
sudo systemctl restart docker

# 6. Start services
make deploy-up

# 7. Verify health
curl https://localhost/api/v1/health
```

### Data Corruption Recovery

If database corruption is suspected:

```bash
# 1. Stop services immediately
make deploy-down

# 2. Check database integrity
sqlite3 /var/lib/dfat/dfat.db "PRAGMA integrity_check;"

# 3. If corrupted, restore from last known good backup
make deploy-restore ARCHIVE=/var/backups/dfat/LATEST_GOOD_BACKUP.tar.gz

# 4. If no backup, attempt recovery
sqlite3 /var/lib/dfat/dfat.db ".dump" | sqlite3 /var/lib/dfat/dfat_recovered.db
mv /var/lib/dfat/dfat_recovered.db /var/lib/dfat/dfat.db

# 5. Run migrations to ensure schema is current
docker compose -f deploy/docker-compose.production.yml \
  run --rm backend alembic upgrade head

# 6. Restart services
make deploy-up
```

### Evidence Integrity Breach

If evidence integrity verification fails:

1. **Do not modify any evidence files.**
2. Record the failed integrity check (screenshot or API response).
3. Check the audit log for any actions on the evidence:

   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     "https://localhost/api/v1/monitoring/logs?level=WARNING&limit=100"
   ```

4. Compare current hashes against the original registration hashes.
5. If the evidence file has been modified, quarantine it:

   ```bash
   curl -X POST -H "Authorization: Bearer $TOKEN" \
     "https://localhost/api/v1/evidence/ID/quarantine" \
     -H "Content-Type: application/json" \
     -d '{"reason": "Integrity verification failed"}'
   ```

6. Restore the original evidence from its source and re-register.

### Rollback After Failed Update

```bash
# 1. Stop services
make deploy-down

# 2. Revert to previous code version
git checkout PREVIOUS_TAG

# 3. Restore database from pre-update backup
make deploy-restore ARCHIVE=/var/backups/dfat/PRE_UPDATE_BACKUP.tar.gz

# 4. Rebuild and restart
make deploy-build
make deploy-up
```

### Contact and Escalation

For issues beyond this guide:

- **Developer**: Muhammad Aaqif Afzaal (100176885@canterbury.ac.uk)
- **Supervisor**: Dr. Mandy Qi, Canterbury Christ Church University
