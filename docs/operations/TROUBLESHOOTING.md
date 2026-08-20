# Troubleshooting — Startup and Runtime

Common DFAT bootstrap failures and how to resolve them. For the full phase
order, see `docs/architecture/SYSTEM_INITIALIZATION.md`.

## Database connection failed

**Symptom:** Boot aborts with `UNAVAILABLE`; critical failure mentions
`database` / connection.

**Solutions:**
1. Check `DFAT_DATABASE__URL` (or `config/*.yaml` `database.url`).
2. For SQLite, ensure the parent directory exists and is writable
   (e.g. `data/dfat.db`).
3. For PostgreSQL, verify the server is running, credentials are correct, and
   the host/port are reachable.
4. Re-run: `make db-upgrade` or restart after fixing connectivity.

## Ollama not reachable

**Symptom:** LLM phase `DEGRADED`; system may be `DEGRADED`; rule-based fallback
active.

**Solutions:**
1. Install [Ollama](https://ollama.com/) and start the local service.
2. Pull the configured model (default `llama3`): `ollama pull llama3`.
3. Confirm `DFAT_AI_ENGINE__LLM_API_URL` points at localhost
   (e.g. `http://localhost:11434/api/generate`).
4. External LLM URLs are rejected by design (ADR-031).

## No forensic parsers available

**Symptom:** Forensic parsers phase `DEGRADED`; parser inventory shows
unavailable libraries.

**Solutions:**
1. Install disk parsing: `pip install pytsk3` (or `make install-forensic`).
2. Install memory analysis: `pip install volatility3`.
3. Optional: `python-registry`, `python-evtx` for registry/event-log parsers.
4. Restart DFAT and check `/api/v1/system/capabilities` → `parsers`.

## Knowledge base initialization failed

**Symptom:** Knowledge / RAG phases `DEGRADED`; vector store unavailable.

**Solutions:**
1. Install `chromadb` and `sentence-transformers` in the DFAT environment.
2. Ensure `data/knowledge/vector_store` is writable.
3. Confirm disk space for embeddings and Chroma persistence.
4. Empty knowledge bases are acceptable — RAG simply falls back to plain LLM
   prompts.

## JWT secret is default

**Symptom:** Configuration validation fails (especially production) with a
message about the JWT secret / placeholder.

**Solutions:**
1. Run `bash scripts/generate_secrets.sh` (or your environment’s secret
   generator) to create a strong `DFAT_AUTH__SECRET_KEY`.
2. Place the value in `.env` or production secrets management — never commit it.
3. Development may allow a non-production test secret; production must not use
   `CHANGE-ME-IN-PRODUCTION`.

## Authentication: missing users for roles

**Symptom:** Auth phase fails requiring investigator/analyst/viewer users.

**Solutions:**
1. Ensure database initialisation completed (roles seeded).
2. Create at least one active user per role, or use the first-run admin flow
   and seed additional role users for lab environments.
3. Integration tests seed role users automatically after the database phase.

## Backend not running (frontend)

**Symptom:** Frontend `StartupScreen` shows “Backend not running”.

**Solutions:**
1. Start the API: `make run-api` or `make dev-backend`.
2. Confirm CORS origins include the frontend URL (`http://localhost:3000`).
3. Check firewall / port 8000 binding.

## Still stuck?

```bash
make verify-system-init
curl -s http://localhost:8000/api/v1/system/startup | python -m json.tool
curl -s http://localhost:8000/api/v1/system/diagnostics \
  -H "Authorization: Bearer <admin-token>"
```

Review `data/outputs/audit.log` and the startup JSON saved under the reporting
output directory when enabled.
