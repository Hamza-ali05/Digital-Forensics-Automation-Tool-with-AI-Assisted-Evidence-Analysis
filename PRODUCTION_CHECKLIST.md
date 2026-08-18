# DFAT Production Checklist

Manual verification before exposing DFAT to investigators or research
participants. Complement the automated gate with
`make production-check` (`scripts/production_readiness_check.py`).

## Security and configuration

- [ ] **Change default JWT secret key** — set `DFAT_AUTH__SECRET_KEY` to a
  cryptographically random value (32+ bytes). Do not use
  `CHANGE-ME-IN-PRODUCTION` or the `.env.example` placeholder.
- [ ] **Configure production database URL** — prefer PostgreSQL
  (`postgresql+asyncpg://…`) over SQLite for concurrent investigators. Run
  `alembic upgrade head` before first boot with
  `DFAT_DATABASE__CREATE_TABLES_ON_STARTUP=false`.
- [ ] **Configure production CORS** — set `DFAT_API__CORS_ALLOW_ORIGINS` to your
  HTTPS frontend origin(s) only. Remove `localhost` entries from production
  `.env`.
- [ ] **Verify HTTPS termination** — terminate TLS at nginx, Caddy, or a cloud
  load balancer. Do not expose Uvicorn directly on the public internet.
- [ ] **Review and approve RBAC configuration** — confirm role assignments in
  `src/dfat/auth/rbac.py` match your organisation (admin / investigator /
  analyst / viewer).

## AI and Ollama

- [ ] **Set up Ollama with LLaMA-3 model** — `ollama pull llama3` on a host the
  API can reach at `http://127.0.0.1:11434` (ADR-017 loopback-only). Docker
  Compose includes an Ollama service for model storage; for full LLM connectivity
  from a containerised API, run Ollama on the host or use host networking on
  Linux. Keep `DFAT_AI_ENGINE__ENABLE_FALLBACK=true` until LLM is verified.
- [ ] **Review all LLM disclaimers are present in reports** — narrative and
  JSON `ai_metadata.disclaimer` must state that LLM output is advisory; JSON is
  the evidential record ([ADR-021](docs/architecture/adr/021-json-layer-primary-record.md)).

## Data integrity and operations

- [ ] **Configure backup schedule** — database (`pg_dump` or SQLite copy),
  `data/evidence/`, and `data/outputs/audit.log` on a daily (or case-closure)
  schedule. Encrypt backups at rest.
- [ ] **Verify audit log write permissions** — confirm the API user can append
  to `DFAT_LOGGING__AUDIT_LOG_PATH` and that DB `audit_log` rows are written on
  login and evidence actions.
- [ ] **Test evidence integrity verification with real datasets** — register a
  known image, run `POST /api/v1/evidence/{id}/verify-integrity`, tamper with a
  copy, and confirm mismatch detection.

## Forensic validation

- [ ] **Test with production-sized forensic images** — exercise disk and memory
  paths near your `max_evidence_size_gb` limit. Confirm pipeline timeouts and
  disk space on the evidence volume.
- [ ] **Run DFRWS benchmark against reference datasets** — place ground truth
  under `data/ground_truth/`, run `POST /api/v1/evaluation/benchmark`, and
  archive precision/recall/F1 for the thesis artefact.
- [ ] **Conduct dry-run usability questionnaire** — walk through
  `/questionnaire` anonymously, export results as admin, and verify ethics
  deletion (`DELETE /api/v1/evaluation/usability/responses`) if required.

## Automated sign-off

```bash
make test-full-suite          # all tests (set DFAT_SKIP_E2E=1 to skip Playwright)
make security-scan            # zero Bandit HIGH issues
make test-coverage-check      # package-level backend targets
make docker-build             # production images build
make production-check         # automated readiness script
make project-stats            # regenerate docs/PROJECT_STATS.md
```

When every automated check is **PASS** and every manual box above is ticked,
DFAT is ready for production deployment per
[docs/deployment/DEPLOYMENT.md](docs/deployment/DEPLOYMENT.md).
