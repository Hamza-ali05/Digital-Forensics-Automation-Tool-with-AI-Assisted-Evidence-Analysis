.PHONY: install install-dev install-forensic test test-unit test-integration test-integration-full test-all test-cov test-coverage test-coverage-check lint format type-check clean run-api run-pipeline db-init db-migrate db-upgrade db-downgrade db-current db-history db-optimize test-auth test-database test-services test-middleware test-backend test-integration-auth test-cases test-evidence-mgmt test-prompt3 test-parsers test-pipeline test-processing test-prompt4 test-ai test-prompt5 test-reporting test-evaluation test-prompt6 test-contract test-validation test-regression test-full-suite frontend-install frontend-start frontend-build frontend-test frontend-test-pages frontend-test-coverage frontend-lint e2e-test e2e-test-headed e2e-test-report test-accessibility test-responsive all dev-start dev-backend dev-frontend smoke-test seed-dev dev-setup test-performance test-api-performance test-ai-performance test-ai-quality security-scan test-security production-check production-check-quick docker-build docker-up docker-down project-stats

ALEMBIC := alembic -c src/dfat/database/migrations/alembic.ini
export PYTHONPATH := src$(if $(PYTHONPATH),:$(PYTHONPATH),)

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

install-forensic:
	pip install -e ".[forensic]"

test:
	pytest

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

test-integration-full:
	pytest tests/integration/test_full_pipeline_flow.py \
		tests/integration/test_case_lifecycle_flow.py \
		tests/integration/test_evidence_workflow.py \
		tests/integration/test_reporting_flow.py \
		tests/integration/test_evaluation_flow.py -v

test-all:
	pytest tests/ -v

test-cov:
	pytest --cov=dfat --cov-report=term-missing --cov-report=html

test-coverage:
	pytest tests/ --cov=src/dfat --cov-report=html --cov-report=term-missing --cov-report=json:coverage.json

test-coverage-check:
	python tests/coverage_targets.py

test-auth:
	pytest tests/unit/auth/ -v

test-database:
	pytest tests/unit/database/ -v

test-services:
	pytest tests/unit/services/ -v

test-middleware:
	pytest tests/unit/middleware/ -v

test-backend:
	pytest tests/unit/database/ tests/unit/auth/ tests/unit/services/ tests/unit/middleware/ -v

test-integration-auth:
	pytest tests/integration/test_auth_flow.py -v

test-cases:
	pytest tests/unit/case_management/ tests/unit/database/test_case_repo.py tests/integration/test_case_lifecycle.py -v

test-evidence-mgmt:
	pytest tests/unit/evidence_management/ tests/unit/database/test_custody_repo.py tests/integration/test_evidence_management_api.py -v

test-prompt3:
	pytest tests/unit/case_management/ tests/unit/evidence_management/ tests/unit/database/test_case_repo.py tests/unit/database/test_custody_repo.py tests/integration/test_case_lifecycle.py tests/integration/test_evidence_management_api.py -v

test-parsers:
	pytest tests/unit/forensic_engine/test_filesystem_parser.py tests/unit/forensic_engine/test_registry_parser.py tests/unit/forensic_engine/test_browser_parser.py tests/unit/forensic_engine/test_eventlog_parser.py tests/unit/forensic_engine/test_process_parser.py tests/unit/forensic_engine/test_network_parser.py tests/unit/forensic_engine/test_injection_parser.py tests/unit/forensic_engine/test_base_parser.py tests/unit/forensic_engine/test_normalizer.py -v

test-pipeline:
	pytest tests/unit/pipeline/ tests/integration/test_pipeline_orchestrator.py tests/integration/test_pipeline_api.py tests/integration/test_pipeline_end_to_end.py -v

test-processing:
	pytest tests/unit/forensic_engine/test_categoriser.py tests/unit/forensic_engine/test_correlator.py tests/unit/forensic_engine/test_timeline.py tests/unit/forensic_engine/test_ioc_detector.py tests/unit/forensic_engine/test_scoring.py tests/unit/forensic_engine/test_rule_engine.py -v

test-prompt4:
	pytest tests/unit/pipeline/ tests/unit/forensic_engine/ tests/integration/test_pipeline_orchestrator.py tests/integration/test_pipeline_api.py tests/integration/test_pipeline_end_to_end.py -v

test-ai:
	pytest tests/unit/ai_engine/ tests/integration/test_ai_routes.py tests/integration/test_ai_pipeline.py -v

test-prompt5:
	pytest tests/unit/ai_engine/ tests/integration/test_ai_routes.py tests/integration/test_ai_pipeline.py -v --cov=dfat.ai_engine --cov-report=term-missing

test-reporting:
	pytest tests/unit/reporting/ tests/integration/test_reporting_pipeline.py -v --cov=dfat.reporting --cov-report=term-missing

test-evaluation:
	pytest tests/unit/evaluation/ tests/integration/test_evaluation_api.py -v --cov=dfat.evaluation --cov-report=term-missing

test-prompt6:
	pytest tests/unit/reporting/ tests/unit/evaluation/ tests/integration/test_reporting_pipeline.py tests/integration/test_evaluation_api.py -v --cov=dfat.reporting --cov=dfat.evaluation --cov-report=term-missing

test-contract:
	pytest tests/contract/ -v

test-validation:
	pytest tests/validation/ -v

test-regression:
	pytest tests/regression/ -v

test-full-suite:
	@bash scripts/run_full_test_suite.sh 2>/dev/null || python scripts/run_full_test_suite.py

frontend-install:
	cd frontend && npm install --legacy-peer-deps

frontend-start:
	cd frontend && npm start

frontend-build:
	cd frontend && npm run build

frontend-test:
	cd frontend && npm test -- --watchAll=false

frontend-test-pages:
	cd frontend && npm run test:pages

frontend-test-coverage:
	cd frontend && npm run test:coverage

frontend-lint:
	cd frontend && npx eslint src/ --ext .js,.jsx

# --- Prompt 9.6: Playwright E2E ---

e2e-test:
	cd frontend && npx playwright test

e2e-test-headed:
	cd frontend && npx playwright test --headed

e2e-test-report:
	cd frontend && npx playwright show-report

test-accessibility:
	cd frontend && npx playwright test e2e/accessibility.spec.js

test-responsive:
	cd frontend && npx playwright test e2e/responsive.spec.js

# --- Prompt 9.1: local integration / smoke ---

dev-backend:
	uvicorn dfat.app:create_app --factory --reload --host 127.0.0.1 --port 8000

dev-frontend:
	cd frontend && npm start

dev-start:
	$(MAKE) -j2 dev-backend dev-frontend

seed-dev:
	python scripts/seed_dev_data.py

smoke-test:
	@bash scripts/integration_smoke_test.sh 2>/dev/null || python scripts/integration_smoke_test.py

dev-setup: install install-dev frontend-install db-init
	@echo "=== DFAT Dev Setup ==="
	@echo "Starting API briefly to seed development data..."
	@bash -c 'set -e; \
		uvicorn dfat.app:create_app --factory --host 127.0.0.1 --port 8000 & \
		pid=$$!; \
		trap "kill $$pid 2>/dev/null || true" EXIT; \
		for i in 1 2 3 4 5 6 7 8 9 10; do \
			curl -sf http://127.0.0.1:8000/api/v1/health >/dev/null && break; \
			sleep 1; \
		done; \
		python scripts/seed_dev_data.py; \
		kill $$pid; \
		wait $$pid 2>/dev/null || true'
	@echo "Seed complete. Starting backend + frontend..."
	$(MAKE) -j2 dev-backend dev-frontend

lint:
	ruff check src tests

format:
	black src tests
	isort src tests

type-check:
	mypy src/dfat

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build dist htmlcov .coverage

run-api:
	uvicorn dfat.app:create_app --factory --reload --host 127.0.0.1 --port 8000

run-pipeline:
	python -m dfat

db-init:
	mkdir -p data
	$(ALEMBIC) upgrade head

db-migrate:
	$(ALEMBIC) revision --autogenerate -m "$(message)"

db-upgrade:
	$(ALEMBIC) upgrade head

db-downgrade:
	$(ALEMBIC) downgrade -1

db-current:
	$(ALEMBIC) current

db-history:
	$(ALEMBIC) history

db-optimize:
	$(ALEMBIC) upgrade head
	python -m dfat.database.indexes

test-performance:
	pytest tests/performance -m performance -o addopts="-v --tb=short --strict-markers"

test-api-performance:
	pytest tests/performance/test_api_performance.py -m performance -o addopts="-v --tb=short --strict-markers"

test-ai-performance:
	pytest tests/performance/test_ai_performance.py -m performance -o addopts="-v --tb=short --strict-markers"

test-ai-quality:
	pytest tests/quality/test_ai_quality.py -v

security-scan:
	mkdir -p reports
	python -m bandit -r src/dfat -f json -o reports/bandit_report.json || true
	python -m bandit -r src/dfat -ll

test-security:
	pytest tests/security/ -v

# --- Prompt 9.15: production readiness ---

production-check:
	python scripts/production_readiness_check.py

production-check-quick:
	python scripts/production_readiness_check.py --skip-tests --skip-docker --skip-frontend-coverage

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

project-stats:
	python scripts/generate_project_stats.py

all: format lint type-check test
