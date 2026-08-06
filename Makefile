.PHONY: install install-dev install-forensic test test-unit test-integration test-all test-cov lint format type-check clean run-api run-pipeline db-init db-migrate db-upgrade db-downgrade db-current db-history test-auth test-database test-services test-middleware test-backend test-integration-auth all

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
