# DFAT Production Deployment Guide

## Prerequisites

- Docker and Docker Compose v2+
- At least 10GB RAM (8GB for Ollama + 2GB for other services)
- SSL certificate and key (for HTTPS)

## Deployment Steps

### 1. Clone Repository

```bash
git clone <repository-url> dfat
cd dfat
```

### 2. Generate Secrets

```bash
bash scripts/generate_secrets.sh
```

This creates `.env.production.local` with a cryptographically random JWT secret.

### 3. Configure Environment

Edit `.env.production.local` and set all required values. See `.env.production.example` for reference.

### 4. Validate Environment

```bash
python scripts/validate_environment.py
```

Fix any errors before proceeding.

### 5. Set Up SSL Certificates

Place your SSL certificate and key in `deploy/nginx/ssl/`:

```bash
mkdir -p deploy/nginx/ssl
cp /path/to/cert.pem deploy/nginx/ssl/cert.pem
cp /path/to/key.pem deploy/nginx/ssl/key.pem
```

For testing, generate a self-signed certificate:

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout deploy/nginx/ssl/key.pem \
  -out deploy/nginx/ssl/cert.pem \
  -subj "/CN=dfat.local"
```

### 6. Build and Start Services

```bash
make deploy-build
make deploy-up
```

### 7. Set Up Ollama Model

```bash
bash deploy/scripts/setup_ollama_model.sh
```

This pulls the LLaMA-3 model into the Ollama container (~4.7GB download).

### 8. Run Database Migrations

```bash
docker compose -f deploy/docker-compose.production.yml \
  run --rm backend alembic upgrade head
```

### 9. Create Admin User

```bash
docker compose -f deploy/docker-compose.production.yml \
  run --rm backend python -m src.dfat.seed_admin
```

### 10. Verify Health

```bash
curl -f https://localhost/api/v1/health
```

### 11. Configure Backups

Add a daily backup cron job:

```bash
echo "0 2 * * * cd /opt/dfat && bash deploy/scripts/backup.sh" | crontab -
```

## Management Commands

| Command | Description |
|---|---|
| `make deploy-build` | Build all Docker images |
| `make deploy-up` | Start all services |
| `make deploy-down` | Stop all services |
| `make deploy-logs` | Tail service logs |
| `make deploy-backup` | Run backup |
| `make deploy-restore ARCHIVE=<path>` | Restore from backup |

## Architecture

```
[Client] --> [Nginx :443] --> [Frontend :80]
                          --> [Backend :8000] --> [Ollama :11434]
                                             --> [SQLite DB]
```

- **Nginx**: SSL termination, rate limiting, security headers, static file serving
- **Frontend**: React app served via Nginx (in its own container)
- **Backend**: FastAPI with Uvicorn (2 workers)
- **Ollama**: Local LLM inference (LLaMA-3 8B)

## Troubleshooting

**Services not starting:** Check logs with `make deploy-logs`.

**Ollama out of memory:** Increase the memory limit in `docker-compose.production.yml` (default 8GB).

**SSL errors:** Verify certificate files exist in `deploy/nginx/ssl/` and are valid.

**Database locked:** Ensure only one backend instance writes to SQLite at a time.
