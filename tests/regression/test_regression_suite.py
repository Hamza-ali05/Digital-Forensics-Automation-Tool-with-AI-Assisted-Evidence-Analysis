"""Regression tests for Prompt 9.12/9.13 bug fixes and cross-layer contracts."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import BaseModel

from dfat.api.middleware.cache import DEFAULT_CACHE_TTLS
from dfat.auth.rbac import ROLE_PERMISSIONS as BACKEND_ROLE_PERMISSIONS
from dfat.case_management.enums import (
    CASE_STATUS_TRANSITIONS,
    CaseStatus,
    CustodyAction,
    EvidenceStatus,
)
from dfat.core.enums import (
    ArtefactCategory,
    EvidenceType,
    HashAlgorithm,
    PipelineStage,
    SuspicionLevel,
)
from dfat.core.interfaces.case_repository import ICaseRepository
from dfat.core.interfaces.repository import (
    IArtefactRepository,
    IEvidenceRepository,
    IReportRepository,
    IRepository,
)
from dfat.core.models import (
    Artefact,
    ArtefactSet,
    AuditEntry,
    BenchmarkResult,
    Case,
    CaseInvestigator,
    CaseMetadata,
    EvidenceImage,
    ForensicReport,
    JSONReport,
    MemoryDump,
    NarrativeReport,
    PipelineState,
    RankedArtefact,
    StageResult,
    UsabilityResponse,
)
from dfat.database import models as orm_models
from dfat.database.mappers import (
    artefact_domain_to_orm,
    artefact_orm_to_domain,
    audit_domain_to_orm,
    audit_orm_to_domain,
    benchmark_domain_to_orm,
    benchmark_orm_to_domain,
    case_domain_to_orm,
    case_orm_to_domain,
    custody_domain_to_orm,
    custody_orm_to_domain,
    evidence_domain_to_orm,
    evidence_metadata_domain_to_orm,
    evidence_metadata_orm_to_domain,
    evidence_orm_to_domain,
    evidence_status_domain_to_orm,
    evidence_status_orm_to_domain,
    report_domain_to_orm,
    report_orm_to_domain,
    usability_domain_to_orm,
    usability_orm_to_domain,
)
from dfat.database.repositories.artefact_repo import SQLAlchemyArtefactRepository
from dfat.database.repositories.case_repo import SQLAlchemyCaseRepository
from dfat.database.repositories.evidence_repo import SQLAlchemyEvidenceRepository
from dfat.database.repositories.pipeline_repo import (
    pipeline_job_domain_to_orm,
    pipeline_job_orm_to_domain,
)
from dfat.database.repositories.report_repo import SQLAlchemyReportRepository
from dfat.evidence_management.models import (
    ChainOfCustodyRecord,
    EvidenceMetadataRecord,
    EvidenceStatusChange,
    HashSet,
)
from dfat.infrastructure.repositories.artefact_repo import JSONArtefactRepository
from dfat.infrastructure.repositories.evidence_repo import FileSystemEvidenceRepository
from dfat.infrastructure.repositories.report_repo import FileSystemReportRepository
from dfat.pipeline.enums import JobStatus
from dfat.pipeline.models import PipelineJob
from dfat.pipeline.stage_registry import StageRegistry
from tests.conftest import TEST_INVESTIGATOR_PASSWORD, TEST_INVESTIGATOR_USERNAME

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND_CONSTANTS = _REPO_ROOT / "frontend" / "src" / "utils" / "constants.js"
_FRONTEND_PERMISSIONS = _REPO_ROOT / "frontend" / "src" / "utils" / "permissions.js"

_SERVICE_PROVIDERS = (
    "user_service",
    "case_service",
    "evidence_service",
    "evidence_management_service",
    "analysis_service",
    "report_service",
    "evaluation_service",
    "audit_service",
    "chain_of_custody_service",
)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _extract_js_frozen(source: str, const_name: str) -> Any:
    """Parse ``export const NAME = Object.freeze({...})`` into Python data."""
    needle = f"export const {const_name} = Object.freeze("
    start = source.index(needle) + len(needle)
    while start < len(source) and source[start].isspace():
        start += 1
    if start >= len(source) or source[start] != "{":
        raise AssertionError(f"{const_name} is not an Object.freeze({{...}})")
    depth = 0
    in_str = False
    escape = False
    index = start
    while index < len(source):
        char = source[index]
        if in_str:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_str = False
        elif char == '"':
            in_str = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                blob = source[start : index + 1]
                jsonish = re.sub(
                    r"([{\[,]\s*)([A-Za-z_][\w]*)\s*:",
                    r'\1"\2":',
                    blob,
                )
                jsonish = re.sub(r",(\s*[}\]])", r"\1", jsonish)
                return json.loads(jsonish)
        index += 1
    raise AssertionError(f"Unclosed Object.freeze for {const_name}")


def _enum_values(enum_cls: type) -> set[str]:
    return {member.value for member in enum_cls}


def _case_metadata() -> CaseMetadata:
    return CaseMetadata(case_name="Regression", investigator="Inv")


def _evidence() -> EvidenceImage:
    return EvidenceImage(
        file_path=Path("/tmp/regression.dd"),
        evidence_type=EvidenceType.DISK_IMAGE,
        original_hash="a" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=32,
        acquired_at=datetime(2024, 1, 1, tzinfo=UTC),
        case=_case_metadata(),
    )


def _artefact() -> Artefact:
    return Artefact(
        category=ArtefactCategory.BROWSER_HISTORY,
        source_evidence_id="ev-1",
        raw_data={"url": "https://example.test"},
        source_path="/Users/hist",
    )


def _domain_models() -> list[BaseModel]:
    case_meta = _case_metadata()
    artefact = _artefact()
    ranked = RankedArtefact(
        **artefact.model_dump(),
        suspicion_level=SuspicionLevel.HIGH,
        relevance_score=0.9,
        classification_reasoning="match",
    )
    json_report = JSONReport(evidence_id="ev-1", integrity_hash="c" * 64)
    narrative = NarrativeReport(
        evidence_id="ev-1",
        summary_text="summary",
        llm_model_used="llama3",
    )
    return [
        case_meta,
        _evidence(),
        MemoryDump(
            **{
                **_evidence().model_dump(),
                "evidence_type": EvidenceType.MEMORY_DUMP,
                "volatility_profile": "Win10x64",
            }
        ),
        artefact,
        ranked,
        ArtefactSet(evidence_id="ev-1", artefacts=[artefact]),
        CaseInvestigator(
            user_id="u1", username="inv", full_name="Inv", role="lead"
        ),
        Case(metadata=case_meta, status=CaseStatus.CREATED),
        AuditEntry(
            entry_number=1,
            stage=PipelineStage.ACQUISITION,
            action="test",
            evidence_id="ev-1",
        ),
        StageResult(
            stage=PipelineStage.PARSING, success=True, duration_seconds=0.1
        ),
        PipelineState(case=case_meta, current_stage=PipelineStage.ACQUISITION),
        json_report,
        narrative,
        ForensicReport(
            case=case_meta,
            json_report=json_report,
            narrative_report=narrative,
            pipeline_duration_seconds=1.0,
        ),
        BenchmarkResult(
            dataset_name="dfrws",
            precision=1.0,
            recall=1.0,
            f1_score=1.0,
            time_to_triage_seconds=1.0,
            artefacts_expected=1,
            artefacts_recovered=1,
            false_positives=0,
            false_negatives=0,
        ),
        UsabilityResponse(
            participant_id="p1",
            usefulness_rating=4,
            accuracy_rating=4,
            clarity_rating=5,
        ),
        PipelineJob(evidence_id="ev-1", case_id="c1", user_id="u1"),
    ]


def test_bug_001_missing_case_status_transitions_import() -> None:
    """CaseService must import CASE_STATUS_TRANSITIONS (NameError on open)."""
    import dfat.services.case_service as module

    assert hasattr(module, "CASE_STATUS_TRANSITIONS")
    assert module.CASE_STATUS_TRANSITIONS is CASE_STATUS_TRANSITIONS
    assert CaseStatus.OPEN in module.CASE_STATUS_TRANSITIONS[CaseStatus.CREATED]


def test_regression_bug001_case_open_uses_transition_map(
    app_client: TestClient,
    seeded_db: dict[str, Any],
) -> None:
    """Opening a case no longer raises NameError for CASE_STATUS_TRANSITIONS."""
    headers = _auth(app_client.investigator_token)  # type: ignore[attr-defined]
    created = app_client.post(
        "/api/v1/cases",
        headers=headers,
        json={"case_name": "Bug001", "description": "regression"},
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["case_id"]
    assigned = app_client.post(
        f"/api/v1/cases/{case_id}/investigators",
        headers=headers,
        json={"user_id": seeded_db["user_ids"]["investigator"], "role": "lead"},
    )
    assert assigned.status_code == 200, assigned.text
    opened = app_client.post(f"/api/v1/cases/{case_id}/open", headers=headers)
    assert opened.status_code == 200, opened.text
    assert opened.json()["status"] == CaseStatus.OPEN.value


def test_bug_002_audit_middleware_ignores_container_override(
    app_client: TestClient,
) -> None:
    """API_REQUEST entries must land on the container forensic logger."""
    request_id = f"bug002-{uuid4().hex[:10]}"
    response = app_client.get(
        "/api/v1/health",
        headers={"X-Request-ID": request_id},
    )
    assert response.status_code == 200
    audit_logger = app_client.app.state.container.logging.forensic_audit_logger()
    path = Path(audit_logger._audit_log_path)
    blob = path.read_text(encoding="utf-8") if path.exists() else ""
    assert request_id in blob
    assert "API_REQUEST" in blob


def test_regression_bug002_request_id_reaches_container_audit_log(
    app_client: TestClient,
) -> None:
    """Request IDs continue to propagate into the overridden audit JSONL file."""
    test_bug_002_audit_middleware_ignores_container_override(app_client)


def test_bug_003_stale_readiness_cache() -> None:
    """Readiness must not be in the response-cache TTL map."""
    assert "/api/v1/health/ready" not in DEFAULT_CACHE_TTLS


def test_regression_bug003_readiness_reflects_live_database_state(
    app_client: TestClient,
) -> None:
    """Flipping database connectivity is visible on the next /health/ready GET."""
    engine = app_client.app.state.container.database.database_engine()
    original = engine.check_connection

    async def _down() -> bool:
        return False

    engine.check_connection = _down  # type: ignore[method-assign]
    try:
        down = app_client.get("/api/v1/health/ready")
    finally:
        engine.check_connection = original  # type: ignore[method-assign]
    up = app_client.get("/api/v1/health/ready")
    assert down.json()["checks"]["database"] is False
    assert up.json()["checks"]["database"] is True
    assert down.headers.get("x-cache") != "HIT"
    assert up.headers.get("x-cache") != "HIT"


def test_bug_004_usability_submit_unhandled_valueerror(
    app_client: TestClient,
) -> None:
    """Empty questionnaire ratings must be 422, not an unhandled 500."""
    response = app_client.post("/api/v1/evaluation/usability/respond", json={})
    assert response.status_code == 422
    detail = str(response.json())
    assert "usefulness" in detail.lower() or "rating" in detail.lower()


def test_regression_bug004_usability_validation_is_client_error(
    app_client: TestClient,
) -> None:
    """Invalid usability payloads stay in the 4xx range."""
    test_bug_004_usability_submit_unhandled_valueerror(app_client)


def test_all_domain_models_serialisable() -> None:
    """Every core domain model round-trips through JSON serialisation."""
    exported = {
        Artefact,
        ArtefactSet,
        AuditEntry,
        BenchmarkResult,
        Case,
        CaseInvestigator,
        CaseMetadata,
        EvidenceImage,
        ForensicReport,
        JSONReport,
        MemoryDump,
        NarrativeReport,
        PipelineState,
        RankedArtefact,
        StageResult,
        UsabilityResponse,
    }
    instances = _domain_models()
    covered = {type(item) for item in instances}
    assert exported <= covered
    for model in instances:
        payload = model.model_dump(mode="json")
        restored = type(model).model_validate(payload)
        assert restored.model_dump(mode="json") == payload


def test_all_orm_models_mappable() -> None:
    """ORM ↔ domain mapper pairs round-trip identity fields."""
    evidence = _evidence()
    artefact = _artefact()
    case = Case(metadata=_case_metadata(), status=CaseStatus.CREATED)
    audit = AuditEntry(
        entry_number=7,
        stage=PipelineStage.REPORTING,
        action="mapped",
        evidence_id=evidence.evidence_id,
    )
    json_report = JSONReport(
        evidence_id=evidence.evidence_id, integrity_hash="d" * 64
    )
    narrative = NarrativeReport(
        evidence_id=evidence.evidence_id,
        summary_text="n",
        llm_model_used="llama3",
    )
    report = ForensicReport(
        case=evidence.case,
        json_report=json_report,
        narrative_report=narrative,
        pipeline_duration_seconds=2.0,
    )
    bench = BenchmarkResult(
        dataset_name="cfreds",
        precision=0.5,
        recall=0.5,
        f1_score=0.5,
        time_to_triage_seconds=2.0,
        artefacts_expected=2,
        artefacts_recovered=1,
        false_positives=1,
        false_negatives=1,
    )
    usability = UsabilityResponse(
        participant_id="p-map",
        usefulness_rating=3,
        accuracy_rating=3,
        clarity_rating=3,
    )
    custody = ChainOfCustodyRecord(
        evidence_id=evidence.evidence_id,
        action=CustodyAction.ACQUIRED,
        performed_by_user_id="u1",
        performed_by_name="Inv",
        reason="intake",
        hash_at_action="e" * 64,
    )
    metadata = EvidenceMetadataRecord(
        evidence_id=evidence.evidence_id,
        mime_type="application/octet-stream",
        mime_detected_from="extension",
        file_extension=".dd",
        file_size_bytes=32,
        hash_set=HashSet(
            md5="1" * 32, sha1="2" * 40, sha256="3" * 64, file_size_bytes=32
        ),
        is_valid_format=True,
    )
    status = EvidenceStatusChange(
        evidence_id=evidence.evidence_id,
        new_status=EvidenceStatus.REGISTERED,
        changed_by_user_id="u1",
        reason="register",
    )
    job = PipelineJob(
        evidence_id=evidence.evidence_id,
        case_id=evidence.case.case_id,
        user_id="u1",
        status=JobStatus.QUEUED,
    )

    assert (
        evidence_orm_to_domain(evidence_domain_to_orm(evidence)).evidence_id
        == evidence.evidence_id
    )
    assert (
        artefact_orm_to_domain(
            artefact_domain_to_orm(artefact, evidence.evidence_id)
        ).artefact_id
        == artefact.artefact_id
    )
    case_orm = case_domain_to_orm(case, created_by_user_id="u1")
    case_orm.investigators = []
    assert case_orm_to_domain(case_orm).case_id == case.case_id
    assert audit_orm_to_domain(audit_domain_to_orm(audit, user_id="u1")).action == "mapped"
    assert (
        report_orm_to_domain(report_domain_to_orm(report)).json_report.evidence_id
        == evidence.evidence_id
    )
    assert (
        benchmark_orm_to_domain(benchmark_domain_to_orm(bench)).dataset_name == "cfreds"
    )
    assert (
        usability_orm_to_domain(usability_domain_to_orm(usability)).participant_id
        == "p-map"
    )
    assert (
        custody_orm_to_domain(
            custody_domain_to_orm(custody, entry_number=1)
        ).action
        is CustodyAction.ACQUIRED
    )
    assert (
        evidence_metadata_orm_to_domain(
            evidence_metadata_domain_to_orm(metadata)
        ).evidence_id
        == evidence.evidence_id
    )
    assert (
        evidence_status_orm_to_domain(
            evidence_status_domain_to_orm(status)
        ).new_status
        is EvidenceStatus.REGISTERED
    )
    assert (
        pipeline_job_orm_to_domain(pipeline_job_domain_to_orm(job)).job_id == job.job_id
    )
    exported_orm = {
        getattr(orm_models, name)
        for name in orm_models.__all__
        if name.endswith("ORM")
    }
    assert len(exported_orm) >= 10


def test_all_repository_interfaces_implemented() -> None:
    """Declared repository ports have concrete, non-abstract implementations."""
    expected: dict[type, tuple[type, ...]] = {
        IEvidenceRepository: (
            SQLAlchemyEvidenceRepository,
            FileSystemEvidenceRepository,
        ),
        IArtefactRepository: (
            SQLAlchemyArtefactRepository,
            JSONArtefactRepository,
        ),
        IReportRepository: (
            SQLAlchemyReportRepository,
            FileSystemReportRepository,
        ),
        ICaseRepository: (SQLAlchemyCaseRepository,),
    }
    for iface, classes in expected.items():
        assert iface is ICaseRepository or issubclass(iface, IRepository)
        for cls in classes:
            assert issubclass(cls, iface), cls
            abstracts = getattr(cls, "__abstractmethods__", frozenset())
            assert not abstracts, (cls, abstracts)


def test_all_service_dependencies_resolvable(app_client: TestClient) -> None:
    """ApplicationContainer can construct every application service."""
    container = app_client.app.state.container
    for name in _SERVICE_PROVIDERS:
        provider = getattr(container.services, name)
        instance = provider()
        assert instance is not None, name
    assert container.pipeline.pipeline_orchestrator() is not None
    assert container.ai_engine.ai_monitor() is not None


def test_all_api_routes_reachable(app_client: TestClient) -> None:
    """Every published OpenAPI path returns a handled (non-5xx) response."""
    headers = _auth(app_client.investigator_token)  # type: ignore[attr-defined]
    param = re.compile(r"\{[^}]+\}")
    spec = app_client.app.openapi()
    seen = 0
    for path, operations in spec.get("paths", {}).items():
        methods = [
            name.upper()
            for name in operations
            if name.lower() not in {"head", "options", "parameters"}
        ]
        if not methods:
            continue
        method = "GET" if "GET" in methods else sorted(methods)[0]
        concrete = param.sub("00000000-0000-0000-0000-000000000001", path)
        request_headers = headers
        data: dict[str, str] | None = None
        json_body: dict[str, str] | None = None
        if concrete.endswith("/auth/login") and method == "POST":
            request_headers = {}
            data = {
                "username": TEST_INVESTIGATOR_USERNAME,
                "password": TEST_INVESTIGATOR_PASSWORD,
            }
        elif method in {"POST", "PUT", "PATCH"}:
            json_body = {}
        response = app_client.request(
            method,
            concrete,
            headers=request_headers,
            data=data,
            json=json_body,
        )
        assert response.status_code < 500, (
            f"{method} {concrete} -> {response.status_code}: {response.text[:240]}"
        )
        seen += 1
    assert seen >= 20


def test_frontend_constants_match_backend_enums() -> None:
    """frontend/src/utils/constants.js mirrors backend enum values."""
    source = _FRONTEND_CONSTANTS.read_text(encoding="utf-8")
    pairs = {
        "CASE_STATUS": CaseStatus,
        "EVIDENCE_STATUS": EvidenceStatus,
        "EVIDENCE_TYPE": EvidenceType,
        "ARTEFACT_CATEGORY": ArtefactCategory,
        "SUSPICION_LEVEL": SuspicionLevel,
        "PIPELINE_STAGE": PipelineStage,
        "JOB_STATUS": JobStatus,
    }
    for name, enum_cls in pairs.items():
        frontend = _extract_js_frozen(source, name)
        assert set(frontend.values()) == _enum_values(enum_cls), name

    roles = _extract_js_frozen(source, "USER_ROLES")
    assert set(roles.values()) == set(BACKEND_ROLE_PERMISSIONS)
    modes = _extract_js_frozen(source, "PIPELINE_MODE")
    registry = StageRegistry()
    for mode in modes.values():
        try:
            registry.get_ordered_stages(mode)
        except KeyError:
            pass
        except ValueError as exc:
            raise AssertionError(f"frontend PIPELINE_MODE {mode!r} is unknown") from exc


def test_frontend_permissions_match_backend_rbac() -> None:
    """frontend/src/utils/permissions.js ROLE_PERMISSIONS matches rbac.py."""
    source = _FRONTEND_PERMISSIONS.read_text(encoding="utf-8")
    frontend = _extract_js_frozen(source, "ROLE_PERMISSIONS")
    assert frontend == BACKEND_ROLE_PERMISSIONS
