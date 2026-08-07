"""Stage 5 — optional benchmark evaluation against ground truth."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from dfat.core.enums import PipelineStage
from dfat.core.models.pipeline import StageResult
from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader
from dfat.pipeline.enums import StageStatus
from dfat.pipeline.progress_tracker import ProgressNotFoundError, ProgressTracker
from dfat.pipeline.stage_interface import IPipelineStage, PipelineContext
from dfat.services.audit_service import AuditService
from dfat.settings import DFATSettings

logger = logging.getLogger(__name__)


class EvaluationStage(IPipelineStage):
    """Compare recovered artefacts to ground truth when configured; else skip."""

    def __init__(
        self,
        benchmark_comparator: BenchmarkComparator,
        ground_truth_loader: GroundTruthLoader,
        progress_tracker: ProgressTracker,
        audit_service: AuditService,
        settings: DFATSettings,
    ) -> None:
        """Initialise the evaluation stage.

        Args:
            benchmark_comparator: Ground-truth comparison engine.
            ground_truth_loader: Loader for DFRWS/CFReDS ground-truth files.
            progress_tracker: Job/stage progress tracker.
            audit_service: Dual-write audit trail service.
            settings: Application settings (evaluation paths).
        """
        self._comparator = benchmark_comparator
        self._ground_truth = ground_truth_loader
        self._progress = progress_tracker
        self._audit = audit_service
        self._settings = settings

    @property
    def stage_name(self) -> PipelineStage:
        """Return ``PipelineStage.EVALUATION``."""
        return PipelineStage.EVALUATION

    @property
    def description(self) -> str:
        """Return a human-readable description of this stage."""
        return "Evaluate recovered artefacts against configured ground truth"

    async def validate_preconditions(self, context: PipelineContext) -> bool:
        """Always allow evaluation (may skip when ground truth is absent)."""
        return True

    async def execute(self, context: PipelineContext) -> StageResult:
        """Run benchmark comparison when a ground-truth path is configured.

        Ground truth is resolved from, in order:
            1. ``context.metadata["ground_truth_path"]``
            2. ``context.metadata["ground_truth_dataset"]`` under
               ``settings.evaluation.ground_truth_dir``
            3. Otherwise the stage is marked ``SKIPPED``.

        Args:
            context: Shared pipeline context.

        Returns:
            ``StageResult`` (success even when skipped).
        """
        started = time.perf_counter()
        job = context.job
        evidence_id = (
            context.evidence.evidence_id
            if context.evidence is not None
            else job.evidence_id
        )

        self._ensure_progress_job(job.job_id)
        self._progress.start_stage(job.job_id, self.stage_name, parser_count=0)

        await self._audit.log_action(
            stage=self.stage_name,
            action="EVALUATION_STAGE_STARTED",
            evidence_id=evidence_id,
            user_id=job.user_id,
            details={"job_id": job.job_id},
        )

        ground_truth_path = self._resolve_ground_truth_path(context)
        if ground_truth_path is None:
            duration = time.perf_counter() - started
            context.stage_timings[self.stage_name.value] = duration
            skip_payload = {
                "status": StageStatus.SKIPPED.value,
                "reason": "No ground truth path or dataset configured",
            }
            context.metadata["evaluation"] = skip_payload
            self._progress.complete_stage(job.job_id, self.stage_name, artefacts_found=0)
            await self._audit.log_action(
                stage=self.stage_name,
                action="EVALUATION_STAGE_SKIPPED",
                evidence_id=evidence_id,
                user_id=job.user_id,
                details={"job_id": job.job_id, **skip_payload},
            )
            return StageResult(
                stage=self.stage_name,
                success=True,
                duration_seconds=duration,
                output_data=skip_payload,
                errors=[],
            )

        if context.artefact_set is None:
            duration = time.perf_counter() - started
            return StageResult(
                stage=self.stage_name,
                success=False,
                duration_seconds=duration,
                errors=["Evaluation requires artefact_set when ground truth is set"],
            )

        try:
            ground_truth = self._ground_truth.load(ground_truth_path)
            dataset_name = str(
                context.metadata.get("ground_truth_dataset")
                or ground_truth.get("dataset_name")
                or ground_truth_path.stem
            )
            ground_truth["dataset_name"] = dataset_name

            pipeline_start = self._pipeline_start(context)
            pipeline_end = datetime.now(UTC)
            result = self._comparator.compare(
                recovered=context.artefact_set,
                ground_truth=ground_truth,
                pipeline_start=pipeline_start,
                pipeline_end=pipeline_end,
            )

            duration = time.perf_counter() - started
            context.stage_timings[self.stage_name.value] = duration
            evaluation_payload: dict[str, Any] = {
                "status": StageStatus.COMPLETED.value,
                "ground_truth_path": str(ground_truth_path),
                "dataset_name": dataset_name,
                "benchmark_result": result.model_dump(mode="json"),
            }
            context.metadata["evaluation"] = evaluation_payload
            context.metadata["benchmark_result"] = evaluation_payload["benchmark_result"]

            self._progress.complete_stage(job.job_id, self.stage_name, artefacts_found=0)
            await self._audit.log_action(
                stage=self.stage_name,
                action="EVALUATION_STAGE_COMPLETED",
                evidence_id=evidence_id,
                user_id=job.user_id,
                details={
                    "job_id": job.job_id,
                    "dataset_name": dataset_name,
                    "precision": getattr(result, "precision", None),
                    "recall": getattr(result, "recall", None),
                    "f1_score": getattr(result, "f1_score", None),
                },
            )
            return StageResult(
                stage=self.stage_name,
                success=True,
                duration_seconds=duration,
                output_data=evaluation_payload,
                errors=[],
            )
        except Exception as exc:  # noqa: BLE001 — stage-level failure
            duration = time.perf_counter() - started
            logger.exception("Evaluation stage failed for job %s", job.job_id)
            await self._audit.log_action(
                stage=self.stage_name,
                action="EVALUATION_STAGE_FAILED",
                evidence_id=evidence_id,
                user_id=job.user_id,
                details={"job_id": job.job_id, "error": str(exc)},
            )
            return StageResult(
                stage=self.stage_name,
                success=False,
                duration_seconds=duration,
                output_data=None,
                errors=[str(exc)],
            )

    def _resolve_ground_truth_path(self, context: PipelineContext) -> Optional[Path]:
        """Resolve an explicit ground-truth file path when configured."""
        raw_path = context.metadata.get("ground_truth_path")
        if raw_path:
            path = Path(str(raw_path))
            if path.is_file():
                return path
            logger.warning("Configured ground_truth_path not found: %s", path)
            return None

        dataset = context.metadata.get("ground_truth_dataset")
        if not dataset:
            return None

        found = self._find_dataset_file(str(dataset))
        if found is None:
            logger.warning("Ground truth dataset not found: %s", dataset)
        return found

    def _find_dataset_file(self, dataset_name: str) -> Optional[Path]:
        """Best-effort locate a dataset JSON under the ground-truth directory."""
        base = Path(self._settings.evaluation.ground_truth_dir)
        name = dataset_name if dataset_name.endswith(".json") else f"{dataset_name}.json"
        for candidate in (
            base / name,
            base / "dfrws" / name,
            base / "cfreds" / name,
        ):
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _pipeline_start(context: PipelineContext) -> datetime:
        """Infer pipeline start from job timestamps or stage timings."""
        if context.job.started_at is not None:
            started = context.job.started_at
            if started.tzinfo is None:
                return started.replace(tzinfo=UTC)
            return started.astimezone(UTC)
        if context.job.created_at is not None:
            created = context.job.created_at
            if created.tzinfo is None:
                return created.replace(tzinfo=UTC)
            return created.astimezone(UTC)
        return datetime.now(UTC)

    def _ensure_progress_job(self, job_id: str) -> None:
        """Ensure progress tracking has been initialised for ``job_id``."""
        try:
            self._progress.get_progress(job_id)
        except ProgressNotFoundError:
            self._progress.start_job(job_id, total_stages=5)
