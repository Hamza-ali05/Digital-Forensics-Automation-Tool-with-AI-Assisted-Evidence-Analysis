"""Startup status, runtime monitoring, and system diagnostics endpoints."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import Field

from dfat.api.dependencies import require_role
from dfat.api.schemas.base import APIModel
from dfat.bootstrap.models import (
    InitPhase,
    InitStatus,
    ServiceHealth,
    StartupReport,
)
from dfat.database.models.user import UserORM
from dfat.runtime.resource_tracker import ResourceAlert, ResourceSnapshot
from dfat.runtime.task_manager import TaskStatus

router = APIRouter(prefix="/system", tags=["System"])

_SECRET_KEY_FRAGMENTS = ("secret", "password", "token", "api_key", "credential")
_DATABASE_URL_PATTERN = re.compile(r"://([^:/@]+):([^@]+)@")


class SystemStatusResponse(APIModel):
    """Current system readiness and per-service runtime health."""

    system_readiness: str
    services: dict[str, ServiceHealth] = Field(default_factory=dict)
    degraded_mode: bool = False


class CapabilitiesResponse(APIModel):
    """Feature availability across DFAT subsystems."""

    parsers: dict[str, bool] = Field(default_factory=dict)
    ai: dict[str, bool] = Field(default_factory=dict)
    threat_intel: dict[str, bool] = Field(default_factory=dict)
    knowledge: dict[str, bool] = Field(default_factory=dict)
    benchmarks: dict[str, bool] = Field(default_factory=dict)


class TaskStatusMapResponse(APIModel):
    """Background task runtime statuses keyed by task name."""

    tasks: dict[str, TaskStatus] = Field(default_factory=dict)


class ResourceAlertsResponse(APIModel):
    """Active resource threshold alerts."""

    alerts: list[ResourceAlert] = Field(default_factory=list)


class DiagnosticsResponse(APIModel):
    """Full admin diagnostic dump with secrets redacted."""

    startup_report: Optional[StartupReport] = None
    system_readiness: str
    services: dict[str, ServiceHealth] = Field(default_factory=dict)
    resources: ResourceSnapshot
    resource_alerts: list[ResourceAlert] = Field(default_factory=list)
    tasks: dict[str, TaskStatus] = Field(default_factory=dict)
    capabilities: CapabilitiesResponse
    config_summary: dict[str, Any] = Field(default_factory=dict)
    degraded_mode: bool = False


def _container(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.container


def _startup_report(request: Request) -> Optional[StartupReport]:
    report = getattr(request.app.state, "startup_report", None)
    if report is not None:
        return report

    path = Path("data/outputs/startup_report.json")
    if path.exists():
        try:
            return StartupReport.model_validate_json(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError):
            return None
    return None


def _task_manager(request: Request):
    return getattr(request.app.state, "task_manager", None) or _container(request).task_manager()


def _phase_result(report: StartupReport, phase: InitPhase):
    for result in report.phases:
        if result.phase == phase:
            return result
    return None


def _phase_capability_available(result, capability: str) -> bool:
    if result is None:
        return False
    if result.status == InitStatus.COMPLETED:
        return True
    if result.status == InitStatus.DEGRADED:
        return capability not in result.degraded_capabilities
    return False


def _build_capabilities(request: Request) -> CapabilitiesResponse:
    container = _container(request)
    report = _startup_report(request)

    parsers: dict[str, bool] = {}
    try:
        orchestrator = container.pipeline.pipeline_orchestrator()
        parsers = {
            str(item["parser_name"]): bool(item["available"])
            for item in orchestrator.list_parsers()
        }
    except Exception:  # noqa: BLE001
        parsers = {}

    llm = rag = ml_available = False
    yara = sigma = mitre = False
    vector_store = graph = ioc_db = False
    dfrws = cfreds = False

    if report is not None:
        llm = _phase_capability_available(
            _phase_result(report, InitPhase.LLM_SERVICE),
            "llm_service",
        )
        rag = _phase_capability_available(
            _phase_result(report, InitPhase.RAG_PIPELINE),
            "rag_pipeline",
        )
        ml_available = _phase_capability_available(
            _phase_result(report, InitPhase.ML_MODELS),
            "ml_models",
        )

        ti = _phase_result(report, InitPhase.THREAT_INTELLIGENCE)
        if ti is not None:
            yara = (
                ti.details.get("yara_rules_loaded", 0) > 0
                and "yara_rules" not in ti.degraded_capabilities
            )
            sigma = (
                ti.details.get("sigma_rules_loaded", 0) > 0
                and "sigma_rules" not in ti.degraded_capabilities
            )
            mitre = ti.details.get("mitre_techniques_mapped", 0) > 0

        kb = _phase_result(report, InitPhase.KNOWLEDGE_BASE)
        ioc = _phase_result(report, InitPhase.IOC_DATABASE)
        vector_store = _phase_capability_available(kb, "vector_store")
        graph = _phase_capability_available(kb, "knowledge_graph")
        ioc_db = _phase_capability_available(ioc, "ioc_database")

        evaluation = _phase_result(report, InitPhase.EVALUATION)
        if evaluation is not None:
            dfrws = bool(evaluation.details.get("dfrws_datasets"))
            cfreds = bool(evaluation.details.get("cfreds_datasets"))

    if not dfrws and not cfreds:
        try:
            loader = container.evaluation_engine.ground_truth_loader()
            datasets = loader.list_all_datasets()
            dfrws = bool(datasets.get("dfrws"))
            cfreds = bool(datasets.get("cfreds"))
        except Exception:  # noqa: BLE001
            pass

    return CapabilitiesResponse(
        parsers=parsers,
        ai={"llm": llm, "rag": rag, "ml": ml_available},
        threat_intel={"yara": yara, "sigma": sigma, "mitre": mitre},
        knowledge={
            "vector_store": vector_store,
            "graph": graph,
            "ioc_db": ioc_db,
        },
        benchmarks={"dfrws": dfrws, "cfreds": cfreds},
    )


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    return any(fragment in lower for fragment in _SECRET_KEY_FRAGMENTS)


def _redact_value(key: str, value: Any) -> Any:
    if _is_sensitive_key(key):
        return "[REDACTED]"
    if key.lower() in {"url", "database_url"} and isinstance(value, str):
        if _DATABASE_URL_PATTERN.search(value):
            return _DATABASE_URL_PATTERN.sub("://[REDACTED]:[REDACTED]@", value)
    return value


def _redact_config(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {key: _redact_config(_redact_value(key, value)) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_redact_config(item) for item in obj]
    return obj


def _config_summary(request: Request) -> dict[str, Any]:
    settings = _container(request).settings()
    return _redact_config(settings.model_dump(mode="json"))


@router.get("/startup", response_model=StartupReport)
async def get_startup_report(request: Request) -> StartupReport:
    """Return the bootstrap startup report (no authentication)."""
    report = _startup_report(request)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Startup report is not available",
        )
    return report


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(request: Request) -> SystemStatusResponse:
    """Return current system readiness and per-service health (no authentication)."""
    container = _container(request)
    monitor = container.service_monitor()
    services = await monitor.check_all()
    recovery = container.recovery_manager()
    return SystemStatusResponse(
        system_readiness=monitor.get_overall_status().value,
        services=services,
        degraded_mode=recovery.degraded_mode,
    )


@router.get("/resources", response_model=ResourceSnapshot)
async def get_system_resources(
    request: Request,
    _: UserORM = Depends(require_role(["admin"])),
) -> ResourceSnapshot:
    """Return a point-in-time resource utilization snapshot (admin only)."""
    tracker = _container(request).resource_tracker()
    return tracker.get_snapshot()


@router.get("/resources/alerts", response_model=ResourceAlertsResponse)
async def get_resource_alerts(
    request: Request,
    _: UserORM = Depends(require_role(["admin"])),
) -> ResourceAlertsResponse:
    """Return active resource threshold alerts (admin only)."""
    tracker = _container(request).resource_tracker()
    return ResourceAlertsResponse(alerts=tracker.get_resource_alerts())


@router.get("/tasks", response_model=TaskStatusMapResponse)
async def get_background_tasks(
    request: Request,
    _: UserORM = Depends(require_role(["admin"])),
) -> TaskStatusMapResponse:
    """Return background task runtime statuses (admin only)."""
    return TaskStatusMapResponse(tasks=_task_manager(request).get_task_status())


@router.post("/tasks/{name}/restart", response_model=TaskStatus)
async def restart_background_task(
    name: str,
    request: Request,
    _: UserORM = Depends(require_role(["admin"])),
) -> TaskStatus:
    """Restart a named background task (admin only)."""
    manager = _task_manager(request)
    try:
        return await manager.restart_task(name)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_system_capabilities(request: Request) -> CapabilitiesResponse:
    """Return available feature capabilities (no authentication)."""
    return _build_capabilities(request)


@router.get("/diagnostics", response_model=DiagnosticsResponse)
async def get_system_diagnostics(
    request: Request,
    _: UserORM = Depends(require_role(["admin"])),
) -> DiagnosticsResponse:
    """Return a full diagnostic dump with secrets redacted (admin only)."""
    container = _container(request)
    monitor = container.service_monitor()
    tracker = container.resource_tracker()
    recovery = container.recovery_manager()
    services = await monitor.check_all()
    capabilities = _build_capabilities(request)
    config = _config_summary(request)

    return DiagnosticsResponse(
        startup_report=_startup_report(request),
        system_readiness=monitor.get_overall_status().value,
        services=services,
        resources=tracker.get_snapshot(),
        resource_alerts=tracker.get_resource_alerts(),
        tasks=_task_manager(request).get_task_status(),
        capabilities=capabilities,
        config_summary=config,
        degraded_mode=recovery.degraded_mode,
    )
