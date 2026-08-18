# DFAT Production Deployment

DFAT is a local-first research artefact. This guide describes a single-host
production-style deployment: Dockerised API, reverse-proxied HTTPS, local
Ollama, and SQLite or PostgreSQL. It is not a multi-region HA runbook.

Development Compose: [`docker-compose.dev.yml`](../../docker-compose.dev.yml)
(API, React, Ollama). Backend image: [`Dockerfile`](../../Dockerfile).

## Production deployment with Docker

### Build the API image

```bash
docker build -t dfat-api:0.1.0 .
```

The image installs extras `auth`, `reporting`, and `production` (includes
`asyncpg`). It does **not** install optional forensic wheels (`pytsk3`,
Volatility3). For parser-complete hosts, extend the Dockerfile:

```dockerfile
RUN pip install --no-cache-dir -e ".[forensic]"
```

Native forensic libraries often need extra OS packages; prefer a dedicated
forensic workstation image rather than a generic slim Python base.

### Run the API

```bash
docker run --rm -p 8000:8000 \
  --env-file .env \
  -e DFAT_ENV=production \
  -e DFAT_AUTH__SECRET_KEY="$(openssl rand -hex 32)" \
  -e DFAT_DATABASE__URL="postgresql+asyncpg://dfat:dfat@db:5432/dfat" \
  -e DFAT_AI_ENGINE__LLM_API_URL="http://127.0.0.1:11434/api/generate" \
  -v dfat-data:/app/data \
  --name dfat-api \
  dfat-api:0.1.0
```

For a full stack, start from `docker-compose.dev.yml` and:

- Set `DFAT_ENV=production` on the backend.
- Bind the frontend behind a production static build (CRA `npm run build`)
  served by nginx, or keep `frontend/Dockerfile.dev` for lab use only.
- Do not publish Ollama or the API on the public internet without TLS and auth.

Uvicorn in the stock Dockerfile listens on `0.0.0.0:8000` with the FastAPI
factory `dfat.app:create_app`.

### PostgreSQL (recommended beyond lab SQLite)

Default config uses `sqlite+aiosqlite:///./data/dfat.db`. For production:

1. Provision PostgreSQL 14+.
2. `pip` extra `production` / image already includes `asyncpg`.
3. Set `DFAT_DATABASE__URL=postgresql+asyncpg://USER:PASS@HOST:5432/dfat`.
4. Set `DFAT_DATABASE__CREATE_TABLES_ON_STARTUP=false` and run Alembic
   (see [Database migration](#database-migration-in-production)).

Raw evidence files must stay on a volume (`./data/evidence`), not in the DB.

## Environment variable reference

Precedence: `config/default.yaml` → `config/{env}.yaml` → `.env` → process
environment. Nested keys use prefix `DFAT_` and delimiter `__`
(see `src/dfat/settings.py`).

| Variable | Purpose | Example |
|----------|---------|---------|
| `DFAT_ENV` | Selects `{env}.yaml` overlay | `production` |
| `DFAT_AUTH__SECRET_KEY` | JWT signing key — **must change** | 32+ byte random |
| `DFAT_AUTH__ALGORITHM` | JWT algorithm | `HS256` |
| `DFAT_AUTH__ACCESS_TOKEN_EXPIRE_MINUTES` | Access token TTL | `60` |
| `DFAT_AUTH__REFRESH_TOKEN_EXPIRE_DAYS` | Refresh TTL | `7` |
| `DFAT_AUTH__PASSWORD_MIN_LENGTH` | Password policy | `12` |
| `DFAT_AUTH__MAX_LOGIN_ATTEMPTS` | Lockout threshold | `5` |
| `DFAT_AUTH__LOCKOUT_DURATION_MINUTES` | Lockout window | `30` |
| `DFAT_DATABASE__URL` | SQLAlchemy async URL | `postgresql+asyncpg://…` |
| `DFAT_DATABASE__ECHO` | SQL echo | `false` |
| `DFAT_DATABASE__POOL_SIZE` | Pool size (Postgres) | `5` |
| `DFAT_DATABASE__MAX_OVERFLOW` | Pool overflow | `10` |
| `DFAT_DATABASE__CREATE_TABLES_ON_STARTUP` | `create_all` on boot | `false` in prod |
| `DFAT_DATABASE__ENABLE_QUERY_MONITORING` | Slow-query logging | `false` in prod YAML |
| `DFAT_DATABASE__SLOW_QUERY_THRESHOLD_MS` | Slow query threshold | `100` |
| `DFAT_AI_ENGINE__LLM_API_URL` | Ollama generate URL (nested settings key) | `http://127.0.0.1:11434/api/generate` |
| `DFAT_AI_ENGINE__LLM_MODEL` | Model name | `llama3` |
| `DFAT_AI_ENGINE__TEMPERATURE` | Sampling temperature | `0.1` |
| `DFAT_AI_ENGINE__MAX_TOKENS` | Completion cap | `4096` |
| `DFAT_AI_ENGINE__REQUEST_TIMEOUT_SECONDS` | HTTP timeout | `180` |
| `DFAT_AI_ENGINE__ENABLE_FALLBACK` | Rule-based fallback | `true` |
| `DFAT_AI_ENGINE__CACHE_RESPONSES` | Response cache | `true` |
| `DFAT_AI_ENGINE__CACHE_TTL_SECONDS` | Cache TTL | `3600` |
| `DFAT_EVIDENCE__EVIDENCE_DIR` | Evidence directory | `./data/evidence` |
| `DFAT_EVIDENCE__MAX_EVIDENCE_SIZE_GB` | Size cap | `100.0` |
| `DFAT_REPORTING__OUTPUT_DIR` | Report output | `./data/outputs` |
| `DFAT_LOGGING__LOG_LEVEL` | Log level | `INFO` |
| `DFAT_LOGGING__AUDIT_LOG_PATH` | JSONL audit file | `./data/outputs/audit.log` |
| `DFAT_LOGGING__LOG_FORMAT` | App log format | `json` |
| `DFAT_API__CORS_ALLOW_ORIGINS` | JSON list of origins | `["https://dfat.example"]` |
| `DFAT_PIPELINE__MAX_CONCURRENT_JOBS` | Parallel jobs | `1` |
| `DFAT_PIPELINE__STAGE_TIMEOUT_SECONDS` | Stage timeout | `600` |
| `DFAT_EVALUATION__GROUND_TRUTH_DIR` | Benchmark files | `./data/ground_truth` |
| `DFAT_SECURITY__PRIMARY_HASH` | Primary algorithm | `sha256` |

Frontend (build-time `REACT_APP_*`):

| Variable | Purpose | Example |
|----------|---------|---------|
| `REACT_APP_API_BASE_URL` | API prefix | `/api/v1` or `https://dfat.example/api/v1` |
| `REACT_APP_APP_NAME` | UI title | `DFAT` |
| `REACT_APP_APP_VERSION` | Display version | `0.1.0` |
| `REACT_APP_TOKEN_REFRESH_INTERVAL_MS` | Refresh cadence | `300000` |
| `REACT_APP_POLLING_INTERVAL_MS` | Job polling | `5000` |
| `REACT_APP_MAX_FILE_SIZE_MB` | UI hint | `500` |

`.env.example` also lists shorthand names (`DFAT_LLM_API_URL`, `DFAT_LOG_LEVEL`).
Pydantic nested settings bind the `__` form (`DFAT_AI_ENGINE__LLM_API_URL`,
`DFAT_LOGGING__LOG_LEVEL`). Prefer the nested names in production.

Never commit production `.env` files or JWT secrets.

## Database migration in production

```bash
export DFAT_ENV=production
export DFAT_DATABASE__URL="postgresql+asyncpg://dfat:dfat@db:5432/dfat"
export PYTHONPATH=src
alembic -c src/dfat/database/migrations/alembic.ini upgrade head
```

Or `make db-upgrade` with the same environment. Generate a revision only in
development:

```bash
make db-migrate message="add_index_on_evidence_hash"
```

Disable `create_tables_on_startup` in production so schema changes go only
through Alembic. Index helper: `make db-optimize` (runs `python -m dfat.database.indexes`
after upgrade).

Backup the database **before** `upgrade` (see [Backup procedures](#backup-procedures)).

## Ollama model setup

1. Install [Ollama](https://ollama.com/) on the same host (or Compose service).
2. Pull the model DFAT is configured to use (default `llama3`):

   ```bash
   ollama pull llama3
   ```

3. Confirm `http://127.0.0.1:11434/api/generate` responds.
4. Point DFAT at that URL with `DFAT_AI_ENGINE__LLM_API_URL`.
   **Non-loopback hosts are rejected** by `LLMConnectionManager`
   ([ADR-017](../architecture/adr/017-local-llm-only.md)): allowed hostnames are
   `localhost`, `127.0.0.1`, `0.0.0.0`, and `::1`. In Docker, run Ollama on the
   host (or `network_mode: host`) so the API can use `http://127.0.0.1:11434`;
   a Compose DNS name such as `http://ollama:11434` is not accepted.
5. Probe: `GET /api/v1/ai/health` and `GET /api/v1/health/ready` (`llm` check).
6. If the model is absent, enable fallback (`DFAT_AI_ENGINE__ENABLE_FALLBACK=true`)
   so triage still completes with rules.

GPU hosts: follow Ollama’s NVIDIA/AMD container docs; DFAT itself is CPU-only.

## HTTPS configuration

The API does not terminate TLS. Put a reverse proxy in front of Uvicorn (and
the static frontend).

Example nginx:

```nginx
server {
    listen 443 ssl http2;
    server_name dfat.example;

    ssl_certificate     /etc/ssl/certs/dfat.pem;
    ssl_certificate_key /etc/ssl/private/dfat.key;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;
        client_max_body_size 8m;
    }

    location / {
        root /var/www/dfat-frontend;
        try_files $uri /index.html;
    }
}
```

Then:

- Set `DFAT_API__CORS_ALLOW_ORIGINS` to `["https://dfat.example"]`.
- Build the frontend with `REACT_APP_API_BASE_URL=/api/v1`.
- Redirect HTTP → HTTPS.
- Keep HSTS at the proxy; the API already sends security headers
  (`SecurityHeadersMiddleware`) including `Permissions-Policy`.

Lab-only: Caddy `reverse_proxy 127.0.0.1:8000` with automatic certificates.

## Backup procedures

Treat three classes of data separately.

| Asset | Location | Notes |
|-------|----------|--------|
| Metadata DB | `data/dfat.db` or PostgreSQL | Users, cases, jobs, artefacts, reports metadata, audit rows |
| Evidence files | `data/evidence/` | Original images/dumps — highest integrity requirement |
| Outputs + audit JSONL | `data/outputs/` including `audit.log` | Reports, hashes, append-only file audit |
| Ollama models | Ollama data dir / Compose volume `ollama_models` | Re-pullable via `ollama pull` |

**SQLite (app stopped or using backup API):**

```bash
cp data/dfat.db "backups/dfat-$(date +%Y%m%d).db"
sqlite3 data/dfat.db ".backup 'backups/dfat.sqlite.bak'"
```

**PostgreSQL:**

```bash
pg_dump -Fc dfat > "backups/dfat-$(date +%Y%m%d).dump"
```

**Evidence:** copy-on-write or read-only snapshots. Re-hash after restore with
`POST /api/v1/evidence/{id}/verify-integrity`.

**Restore:** restore DB first, then evidence files to the same relative paths
stored in `file_path`. Confirm `GET /api/v1/health/ready` and spot-check a
report `POST /api/v1/reports/{id}/verify`.

Encrypt backups at rest. Dual-write audit (DB `audit_log` + JSONL) should be
backed up together so investigations remain reconstructable.

## Monitoring setup

DFAT exposes application health rather than a Prometheus stack.

| Signal | How to consume |
|--------|----------------|
| Liveness | `GET /api/v1/health` — process up |
| Readiness | `GET /api/v1/health/ready` — `database`, `llm`, `storage`, `pipeline`, `audit` |
| Admin diagnostics | `GET /api/v1/health/detailed` (role admin) — uptime, table counts, memory |
| AI | `GET /api/v1/ai/health`, `GET /api/v1/ai/stats` (admin) |
| Pipeline | `GET /api/v1/pipeline/jobs`; readiness flags jobs stuck > 1 hour |
| Slow SQL | `DFAT_DATABASE__ENABLE_QUERY_MONITORING` + `slow_query_threshold_ms` |
| Audit | DB `audit_log` + `data/outputs/audit.log`; UI **Audit Logs** |
| Request correlation | `X-Request-ID` on every response |
| Structured logs | stdout JSON when `DFAT_LOGGING__LOG_FORMAT=json` |

Point an external uptime check at `/api/v1/health` and `/api/v1/health/ready`.
Alert if readiness is `unavailable`, if `llm` is false for an extended period
while fallback is disabled, or if `pipeline` reports stuck jobs.

Security scan (dev/CI): `make security-scan` (Bandit) and `make test-security`.
