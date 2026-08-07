.PHONY: install install-dev install-forensic test test-unit test-integration test-all test-cov lint format type-check clean run-api run-pipeline db-init db-migrate db-upgrade db-downgrade db-current db-history test-auth test-database test-services test-middleware test-backend test-integration-auth test-cases test-evidence-mgmt test-prompt3 test-parsers test-pipeline test-processing test-prompt4 test-ai test-prompt5 all

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

test-all:
	pytest tests/ -v

test-cov:
	pytest --cov=dfat --cov-report=term-missing --cov-report=html

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

all: format lint type-check test
