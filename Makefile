.PHONY: install install-dev install-forensic test test-cov lint format type-check clean run-api run-pipeline all

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

install-forensic:
	pip install -e ".[forensic]"

test:
	pytest

test-cov:
	pytest --cov=dfat --cov-report=term-missing --cov-report=html

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

all: format lint type-check test

