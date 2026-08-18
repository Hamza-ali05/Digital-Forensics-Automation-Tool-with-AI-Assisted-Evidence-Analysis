# DFAT Developer Guide

This guide is for contributors extending DFAT: parsers, triage rules, report
formats, and API endpoints. Coding rules are also in
[CODING_STANDARDS.md](CODING_STANDARDS.md). Git process:
[GIT_WORKFLOW.md](GIT_WORKFLOW.md). Architecture:
[ARCHITECTURE.md](../architecture/ARCHITECTURE.md).

## Project structure

```text
dfat/
├── config/                 # default.yaml, development.yaml, production.yaml, testing.yaml
├── docs/                   # architecture, API, user, development, deployment
├── frontend/               # React CRA app (src/pages, src/services, e2e/)
├── scripts/                # seed, smoke, full-suite runners
├── src/dfat/
│   ├── api/                # FastAPI routes, middleware, schemas, dependencies
│   ├── auth/               # JWT, RBAC, password hashing
│   ├── ai_engine/          # Local LLM client, classification, summarisation, Q&A
│   ├── case_management/    # Case lifecycle domain
│   ├── core/               # Domain models, enums, ports, exceptions (no outward deps)
│   ├── database/           # SQLAlchemy engine, ORM, repositories, Alembic
│   ├── evaluation/         # DFRWS/CFReDS benchmarks, usability questionnaire
│   ├── evidence_management/# Hashing, MIME, validation, custody
│   ├── forensic_engine/    # Acquisition, parsers, triage rules, scoring, IOCs
│   ├── infrastructure/     # File storage, audit JSONL, file repos
│   ├── monitoring/         # HealthAggregator
│   ├── pipeline/           # Orchestrator, stages, parser/stage registries
│   ├── reporting/          # Dual-output builder, exporters, schema
│   ├── services/           # Application services used by routes
│   ├── container.py        # dependency-injector wiring
│   ├── settings.py         # YAML + DFAT_* env
│   └── app.py              # FastAPI factory
├── tests/                  # unit, integration, contract, security, validation, regression
└── data/                   # gitignored: db, evidence, outputs, audit.log
```

**Layering:** `core/` must not import engines or FastAPI. Services orchestrate
repositories and engines. Routes stay thin: validate → service → response DTO.

Wire new collaborators in `src/dfat/container.py` rather than constructing them
inside route handlers.

## How to add a new parser

Parsers extract a typed `ArtefactSet` from disk images or memory dumps.

1. **Implement the port** `IArtefactParser` by subclassing `BaseParser`
   (`src/dfat/forensic_engine/parsers/base.py`).
2. Set `parser_name`, `supported_categories()`, `supported_evidence_types()`.
3. Implement `_do_parse(evidence: EvidenceImage) -> list[Artefact]`.
4. Fill `Artefact.raw_data` according to the category contract in
   [PIPELINE.md](../architecture/PIPELINE.md) / [ADR-015](../architecture/adr/ADR-015-artefact-raw-data-contracts.md).
5. Lazy-import native libraries. Expose `is_available()` (or rely on
   `_PARSER_LIBRARY_PROBES` in `ParserRegistry`). Missing deps must not raise at
   import time ([ADR-013](../architecture/adr/ADR-013-parser-lazy-imports.md),
   [ADR-014](../architecture/adr/ADR-014-graceful-parser-degradation.md)).
6. **Register** the parser in `ForensicEngineContainer` in `container.py`
   (singleton Factory like `FileSystemParser`) and include it in
   `_build_forensic_parsers`.
7. If the library name is new, add it to `ParserRegistry._PARSER_LIBRARY_PROBES`
   and to the `forensic` extra in `pyproject.toml`.
8. Unit-test with a tiny fixture under `tests/unit/forensic_engine/` and, if the
   parser is disk/memory specific, extend `tests/unit/forensic_engine/test_base_parser.py`
   patterns.

Sketch:

```python
from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.models.artefact import Artefact
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers.base import BaseParser


class PrefetchParser(BaseParser):
    @property
    def parser_name(self) -> str:
        return "PrefetchParser"

    def supported_categories(self) -> list[ArtefactCategory]:
        return [ArtefactCategory.FILESYSTEM_METADATA]

    def supported_evidence_types(self) -> list[EvidenceType]:
        return [EvidenceType.DISK_IMAGE]

    def is_available(self) -> bool:
        try:
            import prefetch  # noqa: F401
        except ImportError:
            return False
        return True

    def _do_parse(self, evidence: EvidenceImage) -> list[Artefact]:
        # Read evidence.file_path; return Artefact instances with raw_data.
        return []
```

`GET /api/v1/pipeline/parsers` will list the new name once it is in the
container parser list.

## How to add a new triage rule

Rules are declarative objects in `src/dfat/forensic_engine/triage/rules.py`.
`RuleBasedTriageEngine` applies `DEFAULT_TRIAGE_RULES` after `ScoringEngine`.

1. Append a `TriageRule` to `DEFAULT_TRIAGE_RULES`.
2. Choose a stable `rule_id` (`FS-0xx`, `NET-0xx`, …).
3. Set `category` to the `ArtefactCategory` the rule applies to.
4. `condition_field` is a `raw_data` key (dot-path allowed, e.g.
   `event_data.ProcessId`).
5. `condition_operator`: `contains` | `equals` | `regex` | `greater_than` | `in_list`.
6. `suspicion_boost` in `[0.0, 1.0]`.
7. Add unit tests in `tests/unit/forensic_engine/` for match and non-match.

Example:

```python
TriageRule(
    rule_id="NET-010",
    name="High ephemeral port to rare host",
    description="Outbound connection on a non-standard high port.",
    category=ArtefactCategory.NETWORK_CONNECTION,
    condition_field="foreign_port",
    condition_operator="greater_than",
    condition_value=49152,
    suspicion_boost=0.15,
    tags=["network", "c2"],
)
```

Do not put LLM calls in rules. Rules stay deterministic
([ADR-016](../architecture/adr/ADR-016-rule-based-triage-first.md),
[ADR-020](../architecture/adr/020-rule-based-triage-primary.md)).

To inject a custom list in tests, construct
`RuleBasedTriageEngine(scoring_engine, rules=[...])`.

## How to add a new report format

Dual-output generation (`IReportGenerator` / `ReportBuilder`) stays JSON +
narrative. Extra **export** formats are adapters under
`src/dfat/reporting/exporters/`.

1. Implement an exporter class with `export(...)` that writes a file under
   `settings.reporting.output_dir` and returns a `Path`.
2. Follow existing patterns:
   - `JSONFileExporter` — pretty JSON + integrity verify
   - `HTMLReportExporter` — Jinja2 template (`html_report.j2`), no CDN
   - `PDFReportExporter` — ReportLab with plaintext fallback
3. Add a service method on `ReportService` (e.g. `export_csv`) and a route on
   `src/dfat/api/routes/reports.py` returning `FileResponse`.
4. Register the exporter in `container.py` if it has collaborators.
5. If the format is a new template, add it under
   `src/dfat/reporting/templates/` and keep it self-contained (offline package).
6. Do not treat the new format as the evidential record — JSON remains primary
   ([ADR-003](../architecture/adr/ADR-003-dual-output-report.md),
   [ADR-021](../architecture/adr/021-json-layer-primary-record.md)).
7. Cover export in `tests/unit/reporting/` and `tests/integration/test_reporting_flow.py`.

Changing the **JSON schema** requires a schema version bump
([ADR-022](../architecture/adr/022-report-schema-versioning.md)) and updates to
`report_schema.json` plus `schema_versions.py`.

## How to add a new API endpoint

1. **Domain first.** If the behaviour is new, add or extend a service in
   `src/dfat/services/` (not business logic in the router).
2. **Schemas.** Request models in `api/schemas/requests.py` (or the bounded
   context `schemas.py`). Responses in `api/schemas/responses.py` / context
   schemas. Inherit `APIModel` where other DTOs do.
3. **Route.** Add a function on the existing router in `src/dfat/api/routes/`
   or create a new router and `app.include_router(..., prefix=API_V1_PREFIX)`
   in `app.py`. Static paths must be declared **before** `/{id}` parameters
   (see evidence management vs legacy evidence).
4. **Auth.** `Depends(require_permission("resource", "action"))` or
   `require_role([...])`. Extend `ROLE_PERMISSIONS` in `src/dfat/auth/rbac.py`
   **and** `frontend/src/utils/permissions.js` if the UI needs the same map.
5. **Errors.** Raise domain exceptions (`CaseNotFoundError`, …) so
   `GlobalExceptionHandler` maps them. Do not return ad-hoc dicts for errors.
6. **DI.** Add a `get_*` helper in `api/dependencies.py` if the service is new.
7. **Frontend.** Add a method on the matching `frontend/src/services/*.js`
   file, a page or action, and a `RoleGuard` if needed. Keep enums in
   `frontend/src/utils/constants.js` aligned with backend enums (regression
   tests assert this).
8. **Tests.** Contract test in `tests/contract/`, unit tests for the service,
   and an API integration test. OpenAPI must list the route
   (`test_all_api_routes_reachable` walks `/openapi.json`).

Minimal router sketch:

```python
@router.post("/{case_id}/note", response_model=CaseResponse)
async def add_note(
    case_id: str,
    body: NoteRequest,
    current_user: UserORM = Depends(require_permission("cases", "update")),
    case_service: CaseService = Depends(get_case_service),
) -> CaseResponse:
    case = await case_service.add_note(case_id, body.text, current_user.id)
    return _to_case_response(case)
```

## Testing guidelines

| Suite | Command | What it covers |
|-------|---------|----------------|
| Unit | `make test-unit` | Isolated domain, parsers, services, middleware |
| Integration | `make test-integration` | API + DB + pipeline flows |
| Contract | `make test-contract` | HTTP shapes vs OpenAPI |
| Security | `make test-security` | Authn/z, headers, injection, LLM boundary |
| Validation | `make test-validation` | Audit, logging, monitoring |
| Regression | `make test-regression` | Known bugs + enum/RBAC/OpenAPI reachability |
| Performance | `make test-performance` | Marked `performance` (deselect Ollama if needed) |
| Frontend unit | `make frontend-test` | Jest |
| E2E | `make e2e-test` | Playwright (API + UI) |
| Full | `make test-full-suite` | Ordered aggregate (`scripts/run_full_test_suite.py`) |

Skip E2E or frontend with `DFAT_SKIP_E2E=1` / `DFAT_SKIP_FRONTEND=1`.

**Rules of thumb:**

- Reproduce a bug with a failing test, then fix it (`tests/regression/`).
- Prefer in-memory SQLite for API tests (`config/testing.yaml`).
- Do not call a real Ollama instance in default CI; use fallback or mocks.
- Frontend tests use `frontend/src/test-utils/render.js` and env stubs.
- Coverage helper: `make test-coverage` then `make test-coverage-check`.

## Coding standards reference

Full text: [CODING_STANDARDS.md](CODING_STANDARDS.md).

- Python 3.11+, type hints on public functions, `mypy --strict` target.
- Google-style docstrings on public classes and methods.
- Black (100 columns), isort (`profile = "black"`), Ruff.
- Naming: `PascalCase` classes, `snake_case` functions, `UPPER_SNAKE` constants.
- Domain (`core/`) depends on nothing. No engine-to-engine internal imports.
- Conventional Commits (`feat:`, `fix:`, `docs:`, …) on `feature/DFAT-*` branches.
- Frontend: keep RBAC and enum constants in sync with the backend; use
  `NODE_OPTIONS=--openssl-legacy-provider` for CRA 3.4 on modern Node.

Quality gates before merge: `make format`, `make lint`, `make type-check`,
`make test-regression` (and the suites that touch your change).
