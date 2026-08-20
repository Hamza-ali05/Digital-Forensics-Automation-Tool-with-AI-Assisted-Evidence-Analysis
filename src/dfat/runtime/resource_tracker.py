"""System resource utilization tracking and threshold alerting."""

from __future__ import annotations

import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.pipeline.enums import JobStatus

logger = logging.getLogger(__name__)

_ACTIVE_JOB_STATUSES = frozenset(
    {
        JobStatus.QUEUED,
        JobStatus.INITIALISING,
        JobStatus.RUNNING,
        JobStatus.STAGE_COMPLETE,
    }
)

_MEMORY_ALERT_THRESHOLD = 80.0
_DISK_ALERT_THRESHOLD = 90.0
_DATABASE_ALERT_THRESHOLD_MB = 1024.0


class ResourceSnapshot(BaseModel):
    """Point-in-time system resource utilization."""

    model_config = ConfigDict(validate_assignment=True)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    cpu_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    memory_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_free_gb: float = 0.0
    disk_total_gb: float = 0.0
    disk_percent: float = 0.0
    evidence_size_gb: float = 0.0
    knowledge_base_size_mb: float = 0.0
    database_size_mb: float = 0.0
    active_pipeline_jobs: int = 0
    background_tasks_running: int = 0


class ResourceAlert(BaseModel):
    """Threshold breach notification for a monitored resource."""

    model_config = ConfigDict(validate_assignment=True)

    resource: str
    current_value: float
    threshold: float
    severity: str
    message: str


class ResourceTracker:
    """Monitors CPU, memory, disk, and DFAT storage consumption."""

    def __init__(
        self,
        settings: Any,
        database_engine: Any | None = None,
        vector_store: Any | None = None,
        job_manager: Any | None = None,
        task_manager: Any | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self._settings = settings
        self._database_engine = database_engine
        self._vector_store = vector_store
        self._job_manager = job_manager
        self._task_manager = task_manager
        self._data_dir = data_dir or Path("data")

    def get_snapshot(self) -> ResourceSnapshot:
        """Capture current CPU, memory, disk, and DFAT storage metrics."""
        cpu_percent, memory_used_mb, memory_total_mb = _cpu_and_memory()
        memory_percent = (
            (memory_used_mb / memory_total_mb) * 100.0 if memory_total_mb else 0.0
        )

        disk_used_gb, disk_free_gb, disk_total_gb, disk_percent = _disk_usage(
            self._data_dir
        )
        evidence_dir = Path(self._settings.evidence.evidence_dir)
        knowledge_dir = _knowledge_base_dir(self._settings, self._vector_store)

        return ResourceSnapshot(
            timestamp=datetime.now(UTC),
            cpu_percent=round(cpu_percent, 2),
            memory_used_mb=round(memory_used_mb, 2),
            memory_total_mb=round(memory_total_mb, 2),
            memory_percent=round(memory_percent, 2),
            disk_used_gb=round(disk_used_gb, 3),
            disk_free_gb=round(disk_free_gb, 3),
            disk_total_gb=round(disk_total_gb, 3),
            disk_percent=round(disk_percent, 2),
            evidence_size_gb=round(_directory_size_gb(evidence_dir), 3),
            knowledge_base_size_mb=round(_directory_size_mb(knowledge_dir), 2),
            database_size_mb=round(_database_size_mb(self._settings.database.url), 2),
            active_pipeline_jobs=_count_active_pipeline_jobs(self._job_manager),
            background_tasks_running=_count_background_tasks(self._task_manager),
        )

    def get_resource_alerts(self) -> list[ResourceAlert]:
        """Return alerts when memory, disk, or database exceed thresholds."""
        snapshot = self.get_snapshot()
        alerts: list[ResourceAlert] = []

        if snapshot.memory_percent > _MEMORY_ALERT_THRESHOLD:
            alerts.append(
                ResourceAlert(
                    resource="memory",
                    current_value=snapshot.memory_percent,
                    threshold=_MEMORY_ALERT_THRESHOLD,
                    severity="warning",
                    message=(
                        f"Memory usage at {snapshot.memory_percent:.1f}% "
                        f"(threshold {_MEMORY_ALERT_THRESHOLD:.0f}%)"
                    ),
                )
            )

        if snapshot.disk_percent > _DISK_ALERT_THRESHOLD:
            alerts.append(
                ResourceAlert(
                    resource="disk",
                    current_value=snapshot.disk_percent,
                    threshold=_DISK_ALERT_THRESHOLD,
                    severity="critical",
                    message=(
                        f"Disk usage at {snapshot.disk_percent:.1f}% "
                        f"(threshold {_DISK_ALERT_THRESHOLD:.0f}%)"
                    ),
                )
            )

        if snapshot.database_size_mb > _DATABASE_ALERT_THRESHOLD_MB:
            alerts.append(
                ResourceAlert(
                    resource="database",
                    current_value=snapshot.database_size_mb,
                    threshold=_DATABASE_ALERT_THRESHOLD_MB,
                    severity="warning",
                    message=(
                        f"Database size {snapshot.database_size_mb:.1f} MB "
                        f"exceeds {_DATABASE_ALERT_THRESHOLD_MB:.0f} MB threshold"
                    ),
                )
            )

        return alerts


def _cpu_and_memory() -> tuple[float, float, float]:
    """Return ``(cpu_percent, memory_used_mb, memory_total_mb)``."""
    try:
        import psutil  # type: ignore[import-untyped]

        cpu_percent = float(psutil.cpu_percent(interval=0.0))
        memory = psutil.virtual_memory()
        return cpu_percent, memory.used / (1024 * 1024), memory.total / (1024 * 1024)
    except Exception:  # noqa: BLE001
        pass

    memory_used_mb = 0.0
    memory_total_mb = 0.0
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        memory_used_mb = usage.ru_maxrss / 1024.0
    except Exception:  # noqa: BLE001
        logger.debug("Process memory metrics unavailable")

    return 0.0, memory_used_mb, memory_total_mb


def _disk_usage(path: Path) -> tuple[float, float, float, float]:
    """Return disk used/free/total (GB) and utilisation percent for ``path``."""
    target = path if path.exists() else path.parent
    if not target.exists():
        target = Path.cwd()
    try:
        usage = shutil.disk_usage(target)
    except OSError:
        return 0.0, 0.0, 0.0, 0.0
    total_gb = usage.total / (1024**3)
    used_gb = usage.used / (1024**3)
    free_gb = usage.free / (1024**3)
    percent = (usage.used / usage.total) * 100.0 if usage.total else 0.0
    return used_gb, free_gb, total_gb, percent


def _directory_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for file_name in files:
            file_path = Path(root) / file_name
            try:
                total += file_path.stat().st_size
            except OSError:
                continue
    return total


def _directory_size_mb(path: Path) -> float:
    return _directory_size_bytes(path) / (1024 * 1024)


def _directory_size_gb(path: Path) -> float:
    return _directory_size_bytes(path) / (1024**3)


def _database_size_mb(database_url: str) -> float:
    if "sqlite" not in database_url.lower():
        return 0.0
    db_path = _sqlite_path_from_url(database_url)
    if db_path is None or not db_path.exists():
        return 0.0
    return db_path.stat().st_size / (1024 * 1024)


def _sqlite_path_from_url(database_url: str) -> Optional[Path]:
    marker = ":///"
    if marker in database_url:
        raw = database_url.split(marker, 1)[1]
    elif "://" in database_url:
        raw = database_url.split("://", 1)[1]
    else:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _knowledge_base_dir(settings: Any, vector_store: Any | None) -> Path:
    if vector_store is not None:
        persist_path = getattr(vector_store, "_persist_path", None)
        if persist_path is not None:
            return Path(persist_path).parent
    dataset_settings = getattr(settings, "dataset_intelligence", None)
    if dataset_settings is not None:
        return Path(getattr(dataset_settings, "vector_store_path", Path("data/knowledge")))
    return Path("data/knowledge")


def _count_active_pipeline_jobs(job_manager: Any | None) -> int:
    if job_manager is None:
        return 0
    jobs = getattr(job_manager, "_jobs", {})
    return sum(
        1
        for job in jobs.values()
        if getattr(job, "status", None) in _ACTIVE_JOB_STATUSES
    )


def _count_background_tasks(task_manager: Any | None) -> int:
    if task_manager is None:
        return 0
    if not hasattr(task_manager, "get_task_status"):
        return 0
    return sum(
        1 for status in task_manager.get_task_status().values() if status.is_running
    )
