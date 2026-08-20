"""Unit tests for ResourceTracker."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.pipeline.enums import JobStatus
from dfat.pipeline.models import PipelineJob
from dfat.runtime.resource_tracker import ResourceTracker
from dfat.runtime.task_manager import BackgroundTaskManager
from dfat.settings import load_settings


def test_resource_tracker_reports_directory_sizes(tmp_path: Path) -> None:
    base = load_settings(env="development")
    evidence_dir = tmp_path / "evidence"
    knowledge_dir = tmp_path / "knowledge" / "vector_store"
    evidence_dir.mkdir(parents=True)
    knowledge_dir.mkdir(parents=True)
    (evidence_dir / "sample.raw").write_bytes(b"x" * (5 * 1024 * 1024))
    (knowledge_dir / "index.bin").write_bytes(b"y" * (2 * 1024 * 1024))

    db_path = tmp_path / "dfat.db"
    db_path.write_bytes(b"z" * (2 * 1024 * 1024))
    settings = base.model_copy(
        update={
            "evidence": base.evidence.model_copy(update={"evidence_dir": evidence_dir}),
            "database": base.database.model_copy(
                update={"url": f"sqlite+aiosqlite:///{db_path.as_posix()}"}
            ),
        }
    )

    vector_store = MagicMock(_persist_path=knowledge_dir)
    snapshot = ResourceTracker(
        settings=settings,
        vector_store=vector_store,
        data_dir=tmp_path,
    ).get_snapshot()

    assert snapshot.evidence_size_gb > 0
    assert snapshot.knowledge_base_size_mb > 0
    assert snapshot.database_size_mb > 0


def test_resource_tracker_alerts_on_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    from dfat.runtime.resource_tracker import ResourceSnapshot

    settings = load_settings(env="development")
    tracker = ResourceTracker(settings=settings, data_dir=Path("data"))
    monkeypatch.setattr(
        tracker,
        "get_snapshot",
        lambda: ResourceSnapshot(
            memory_percent=85.0,
            disk_percent=95.0,
            database_size_mb=2048.0,
        ),
    )

    alerts = tracker.get_resource_alerts()

    assert any(alert.resource == "memory" for alert in alerts)
    assert any(alert.resource == "disk" for alert in alerts)
    assert any(alert.resource == "database" for alert in alerts)


def test_resource_tracker_counts_active_jobs_and_background_tasks() -> None:
    job = PipelineJob(
        evidence_id="ev-1",
        case_id="case-1",
        user_id="user-1",
        status=JobStatus.RUNNING,
    )
    job_manager = MagicMock(_jobs={"job-1": job})
    task_manager = BackgroundTaskManager()
    task_manager.register("worker", AsyncMock(), interval_seconds=60)

    snapshot = ResourceTracker(
        settings=load_settings(env="development"),
        job_manager=job_manager,
        task_manager=task_manager,
    ).get_snapshot()

    assert snapshot.active_pipeline_jobs == 1
    assert snapshot.background_tasks_running == 0
