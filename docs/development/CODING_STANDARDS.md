# Coding Standards

## Language and Typing

- Python 3.11+.
- Type hints are mandatory on all function signatures.
- Compliance target: `mypy --strict`.

## Docstrings

- Google-style docstrings on every public class and method.

## Formatting and Imports

- Formatter: **Black**, line length **100**.
- Import ordering: **isort** with `profile = "black"` (stdlib → third-party → local).
- Linting: **Ruff**; type checking: **MyPy**.

## Naming Conventions

| Kind | Convention | Example |
|------|------------|---------|
| Classes | PascalCase | `ArtefactSet` |
| Functions / methods | snake_case | `verify_evidence_hashes` |
| Constants | UPPER_SNAKE_CASE | `SCHEMA_VERSION` |
| Private members | `_prefixed` | `_assert_local_endpoint` |

## Architectural Boundaries

- Domain (`core/`) depends on nothing.
- Engines and infrastructure depend only on `core/`.
- No engine-to-engine imports of internal classes.
