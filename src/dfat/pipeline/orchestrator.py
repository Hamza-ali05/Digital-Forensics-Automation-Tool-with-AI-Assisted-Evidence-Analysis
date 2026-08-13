"""Top-level five-stage pipeline orchestrator."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from dfat.case_management.enums import EvidenceStatus
from dfat.core.enums import PipelineStage
from dfat.core.exceptions import EvidenceNotFoundError
from dfat.core.models.artefact import ArtefactSet
from dfat.core.models.evaluation import BenchmarkResult
from dfat.core.models.evidence import CaseMetadata
from dfat.core.models.pipeline import PipelineState, StageResult
from dfat.core.models.report import ForensicReport
from dfat.database.repositories.case_repo import SQLAlchemyCaseRepository
from dfat.database.repositories.evidence_repo import SQLAlchemyEvidenceRepository
from dfat.database.repositories.pipeline_repo import SQLAlchemyPipelineRepository
from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader
from dfat.evidence_management.custody_service import ChainOfCustodyService
from dfat.evidence_management.exceptions import InvalidEvidenceTransitionError
from dfat.pipeline.enums import JobStatus
from dfat.pipeline.exceptions import PipelineJobNotFoundError
from dfat.pipeline.job_manager import JobManager
from dfat.pipeline.job_runner import JobRunner
from dfat.pipeline.models import PipelineJob, PipelineProgress
from dfat.pipeline.parser_registry import ParserRegistry
from dfat.pipeline.pipeline_logger import PipelineLogger
from dfat.pipeline.progress_tracker import ProgressNotFoundError, ProgressTracker
from dfat.pipeline.stage_interface import PipelineContext
from dfat.pipeline.stage_registry import StageRegistry
from dfat.services.audit_service import AuditService
from dfat.services.evidence_management_service import EvidenceManagementService
from dfat.settings import DFATSettings

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Coordinate the full job lifecycle across registered pipeline stages."""

    def __init__(
        self,
        stage_registry: StageRegistry,
        job_manager: JobManager,
        job_runner: JobRunner,
        progress_tracker: ProgressTracker,
        pipeline_logger: PipelineLogger,
        evidence_repo: SQLAlchemyEvidenceRepository,
        case_repo: SQLAlchemyCaseRepository,
        audit_service: AuditService,
        settings: DFATSettings,
        evidence_management_service: EvidenceManagementService,
        custody_service: ChainOfCustodyService,
        ground_truth_loader: GroundTruthLoader,
        benchmark_comparator: BenchmarkComparator,
        pipeline_repo: Optional[SQLAlchemyPipelineRepository] = None,
        parser_registry: Optional[ParserRegistry] = None,
    ) -> None:
        """Initialise the top-level pipeline orchestrator.

        Args:
            stage_registry: Registry of all five stage handlers.
            job_manager: In-memory job queue and status manager.
            job_runner: Sequential stage executor.
            progress_tracker: Real-time progress / ETA tracker.
            pipeline_logger: Structured pipeline logger.
            evidence_repo: SQLAlchemy evidence repository.
            case_repo: SQLAlchemy case repository.
            audit_service: Dual-write audit trail service.
            settings: Application settings.
            evidence_management_service: Status transition helper.
            custody_service: Chain-of-custody recorder.
            ground_truth_loader: Benchmark ground-truth loader.
            benchmark_comparator: Benchmark comparison engine.
            pipeline_repo: Optional SQLAlchemy pipeline job repository.
            parser_registry: Optional parser registry for availability APIs.
        """
        self._registry = stage_registry
        self._job_manager = job_manager
        self._job_runner = job_runner
        self._progress = progress_tracker
        self._pipeline_logger = pipeline_logger
        self._evidence_repo = evidence_repo
        self._case_repo = case_repo
        self._audit = audit_service
        self._settings = settings
        self._evidence_mgmt = evidence_management_service
        self._custody = custody_service
        self._ground_truth_loader = ground_truth_loader
        self._benchmark_comparator = benchmark_comparator
        self._pipeline_repo = pipeline_repo
        self._parser_registry = parser_registry

        self._job_contexts: dict[str, PipelineContext] = {}
        self._pipeline_states: dict[str, PipelineState] = {}
        self._pipeline_reports: dict[str, str] = {}
        self._artefact_cache: dict[str, ArtefactSet] = {}
        self._benchmark_results: list[BenchmarkResult] = []

    async def submit_pipeline(
        self,
        evidence_id: str,
        case_id: str,
        user_id: str,
        mode: str = "full",
        use_fallback: bool = False,
        *,
        metadata: Optional[dict[str, Any]] = None,
    ) -> PipelineJob:
        """Submit a pipeline job and prepare context without running stages.

        Persists the QUEUED job when a pipeline repository is configured.

        Args:
            evidence_id: Target evidence identifier.
            case_id: Owning case identifier.
            user_id: Submitting user identifier.
            mode: ``full``, ``parse-only``, or ``triage-only``.
            use_fallback: Force rule-based triage analyzer.
            metadata: Optional extra context metadata.

        Returns:
            Newly submitted ``PipelineJob`` in ``QUEUED`` status.
        """
        evidence = await self._evidence_repo.get(evidence_id)
        if evidence is None:
            raise EvidenceNotFoundError(
                f"Evidence not found: {evidence_id}",
                context={"evidence_id": evidence_id},
            )

        case = await self._case_repo.get(case_id)
        case_metadata = (
            case.metadata
            if case is not None and getattr(case, "metadata", None) is not None
            else evidence.case
        )

        job = await self._job_manager.submit_job(
            evidence_id=evidence_id,
            case_id=case_id,
            user_id=user_id,
            mode=mode,
            use_fallback=use_fallback,
        )

        stages = self._safe_stage_count(mode)
        try:
            self._progress.get_progress(job.job_id)
        except ProgressNotFoundError:
            self._progress.start_job(job.job_id, total_stages=stages)

        context_meta: dict[str, Any] = {
            "case_id": case_id,
            "case": case_metadata,
            "case_name": case_metadata.case_name,
            "investigator": case_metadata.investigator,
            "user_name": user_id,
        }
        if metadata:
            context_meta.update(metadata)

        context = PipelineContext(job=job, metadata=context_meta)
        if mode == "triage-only" and context.artefact_set is None:
            cached = self._artefact_cache.get(evidence_id)
            if cached is not None:
                context.artefact_set = cached
        self._job_contexts[job.job_id] = context

        await self._audit.log_action(
            stage=PipelineStage.ACQUISITION,
            action="PIPELINE_EXECUTE_STARTED",
            evidence_id=evidence_id,
            user_id=user_id,
            details={
                "job_id": job.job_id,
                "case_id": case_id,
                "mode": mode,
                "use_fallback": use_fallback,
            },
        )
        await self._pipeline_logger.log_job_start(job)
        await self._persist_job(job)
        return job

    async def execute_submitted_job(self, job_id: str) -> PipelineJob:
        """Run stages for a previously submitted job and persist the result."""
        job = await self._job_manager.get_job(job_id)
        if job is None:
            raise PipelineJobNotFoundError(
                f"Pipeline job not found: {job_id}",
                job_id=job_id,
            )
        context = self._job_contexts.get(job_id)
        if context is None:
            raise PipelineJobNotFoundError(
                f"Pipeline job context not found: {job_id}",
                job_id=job_id,
            )

        case_metadata = context.metadata.get("case")
        if not isinstance(case_metadata, CaseMetadata):
            case_metadata = CaseMetadata(
                case_id=job.case_id,
                case_name=str(context.metadata.get("case_name") or job.case_id),
                investigator=str(context.metadata.get("investigator") or job.user_id),
            )

        completed = await self._job_runner.run_job(job, context)
        self._job_contexts[job.job_id] = context
        self._cache_job_outputs(completed, context)
        self._record_pipeline_state(completed, context, case_metadata)

        if completed.status is JobStatus.COMPLETED:
            await self._finalise_success(completed, context)

        await self._audit.log_action(
            stage=completed.current_stage or PipelineStage.EVALUATION,
            action="PIPELINE_EXECUTE_FINISHED",
            evidence_id=completed.evidence_id,
            user_id=completed.user_id,
            details={
                "job_id": completed.job_id,
                "status": completed.status.value,
                "report_id": completed.report_id,
                "artefact_count": completed.artefact_count,
            },
        )
        await self._persist_job(completed)
        return completed

    async def execute_pipeline(
        self,
        evidence_id: str,
        case_id: str,
        user_id: str,
        mode: str = "full",
        use_fallback: bool = False,
        *,
        metadata: Optional[dict[str, Any]] = None,
    ) -> PipelineJob:
        """Submit and run a pipeline job through the registered stages.

        Steps:
            1. Submit job via ``job_manager``.
            2. Build ``PipelineContext`` with evidence/case metadata.
            3. Run job via ``job_runner``.
            4. On completion: transition evidence to PROCESSED and record
               ANALYSED custody.
            5. Return the completed ``PipelineJob``.

        Args:
            evidence_id: Target evidence identifier.
            case_id: Owning case identifier.
            user_id: Submitting user identifier.
            mode: ``full``, ``parse-only``, or ``triage-only``.
            use_fallback: Force rule-based triage analyzer.
            metadata: Optional extra context metadata (e.g. ground truth).

        Returns:
            Completed (or failed/cancelled) ``PipelineJob``.
        """
        job = await self.submit_pipeline(
            evidence_id=evidence_id,
            case_id=case_id,
            user_id=user_id,
            mode=mode,
            use_fallback=use_fallback,
            metadata=metadata,
        )
        return await self.execute_submitted_job(job.job_id)

    async def get_job(self, job_id: str) -> PipelineJob:
        """Return a job from memory or the database.

        Raises:
            PipelineJobNotFoundError: If the job is unknown.
        """
        job = await self._job_manager.get_job(job_id)
        if job is not None:
            return job
        if self._pipeline_repo is not None:
            persisted = await self._pipeline_repo.get(job_id)
            if persisted is not None:
                return persisted
        raise PipelineJobNotFoundError(
            f"Pipeline job not found: {job_id}",
            job_id=job_id,
        )

    async def list_pipeline_jobs(
        self,
        *,
        status: Optional[JobStatus] = None,
        case_id: Optional[str] = None,
    ) -> list[PipelineJob]:
        """List jobs from the database when available, else in-memory queue."""
        if self._pipeline_repo is not None:
            return await self._pipeline_repo.list_jobs(status=status, case_id=case_id)
        return await self._job_manager.list_jobs(status=status, case_id=case_id)

    def list_parsers(self) -> list[dict[str, Any]]:
        """Return registered parsers with availability status."""
        if self._parser_registry is None:
            return []
        availability = self._parser_registry.check_availability()
        return [
            {
                "parser_name": parser.parser_name,
                "available": availability.get(parser.parser_name, False),
                "supported_evidence_types": [
                    item.value for item in parser.supported_evidence_types()
                ],
            }
            for parser in self._parser_registry.get_all_parsers()
        ]

    async def get_pipeline_status(self, job_id: str) -> PipelineProgress:
        """Return real-time progress for ``job_id``.

        Args:
            job_id: Pipeline job identifier.

        Returns:
            ``PipelineProgress`` snapshot.

        Raises:
            PipelineJobNotFoundError: If the job is unknown.
        """
        job = await self.get_job(job_id)
        try:
            return self._progress.get_progress(job_id)
        except ProgressNotFoundError:
            # Synthesise minimal progress from job status.
            return PipelineProgress(
                job_id=job_id,
                status=job.status,
                current_stage=(
                    job.current_stage.value if job.current_stage is not None else None
                ),
                stages_completed=sum(
                    1
                    for execution in job.stage_executions.values()
                    if execution.status.value == "completed"
                ),
                stages_total=self._safe_stage_count(job.mode),
                current_parser=None,
                elapsed_seconds=job.total_duration_seconds or 0.0,
                estimated_remaining_seconds=None,
                artefacts_found_so_far=job.artefact_count,
            )

    async def cancel_pipeline(self, job_id: str, user_id: str) -> PipelineJob:
        """Cancel a queued or running pipeline job.

        Args:
            job_id: Job identifier.
            user_id: Acting user identifier.

        Returns:
            Updated ``PipelineJob`` with ``CANCELLED`` status.
        """
        # Ensure the job exists in memory (hydrate from DB when needed).
        in_memory = await self._job_manager.get_job(job_id)
        if in_memory is None and self._pipeline_repo is not None:
            persisted = await self._pipeline_repo.get(job_id)
            if persisted is not None:
                self._job_manager._jobs[job_id] = persisted  # noqa: SLF001
            else:
                raise PipelineJobNotFoundError(
                    f"Pipeline job not found: {job_id}",
                    job_id=job_id,
                )
        cancelled = await self._job_manager.cancel_job(job_id, user_id)
        await self._persist_job(cancelled)
        return cancelled

    async def _persist_job(self, job: PipelineJob) -> None:
        """Best-effort persistence of a job record."""
        if self._pipeline_repo is None:
            return
        try:
            await self._pipeline_repo.save(job)
        except Exception as exc:  # noqa: BLE001 — do not fail the pipeline on DB write
            logger.warning(
                "Failed to persist pipeline job %s: %s",
                job.job_id,
                exc,
            )

    def get_pipeline_state(self, pipeline_id: str) -> Optional[PipelineState]:
        """Return a compatibility ``PipelineState`` snapshot by job/pipeline ID."""
        return self._pipeline_states.get(pipeline_id)

    def get_job_report(self, job_id: str) -> Optional[ForensicReport]:
        """Return the forensic report produced by ``job_id``, if any."""
        context = self._job_contexts.get(job_id)
        if context is not None and context.report is not None:
            return context.report
        return None

    def get_job_artefact_set(self, job_id: str) -> Optional[ArtefactSet]:
        """Return the artefact set produced by ``job_id``, if any."""
        context = self._job_contexts.get(job_id)
        if context is not None and context.artefact_set is not None:
            return context.artefact_set
        return None

    def get_report_id_for_pipeline(self, pipeline_id: str) -> Optional[str]:
        """Return report ID associated with a pipeline/job ID."""
        return self._pipeline_reports.get(pipeline_id)

    def list_benchmark_results(self) -> list[BenchmarkResult]:
        """Return stored benchmark results."""
        return list(self._benchmark_results)

    async def run_benchmark(
        self,
        evidence_id: str,
        ground_truth_path: Path,
        dataset_name: str,
    ) -> BenchmarkResult:
        """Run benchmark comparison for recovered artefacts.

        Args:
            evidence_id: Evidence identifier.
            ground_truth_path: Path to ground-truth JSON.
            dataset_name: Dataset display name override.

        Returns:
            Benchmark result.
        """
        artefact_set = self._artefact_cache.get(evidence_id)
        if artefact_set is None:
            raise EvidenceNotFoundError(
                f"No cached artefacts for evidence: {evidence_id}",
                context={"evidence_id": evidence_id},
            )
        ground_truth = self._ground_truth_loader.load(ground_truth_path)
        name = dataset_name or ground_truth.dataset_name or dataset_name
        ground_truth.dataset_name = name
        end = datetime.now(UTC)
        # Use a one-second window when start/end are not tracked for ad-hoc runs.
        start = end - timedelta(seconds=1)
        result = await self._benchmark_comparator.compare(
            recovered=artefact_set,
            ground_truth=ground_truth,
            pipeline_start=start,
            pipeline_end=end,
            dataset_name=name,
        )
        self._benchmark_results.append(result)
        return result

    async def _finalise_success(
        self,
        job: PipelineJob,
        context: PipelineContext,
    ) -> None:
        """Transition evidence to PROCESSED and record ANALYSED custody."""
        evidence = context.evidence
        if evidence is None:
            evidence = await self._evidence_repo.get(job.evidence_id)
        if evidence is None:
            logger.warning(
                "Cannot finalise pipeline %s: evidence %s missing",
                job.job_id,
                job.evidence_id,
            )
            return

        try:
            await self._evidence_mgmt.transition_evidence_status(
                job.evidence_id,
                EvidenceStatus.PROCESSED,
                job.user_id,
                reason=f"Pipeline job {job.job_id} completed",
            )
        except InvalidEvidenceTransitionError as exc:
            logger.info(
                "Evidence %s status transition to PROCESSED skipped: %s",
                job.evidence_id,
                exc,
            )

        try:
            await self._custody.record_analysis(
                job.evidence_id,
                evidence.file_path,
                job.user_id,
                str(context.metadata.get("user_name") or job.user_id),
                pipeline_id=job.job_id,
            )
        except Exception as exc:  # noqa: BLE001 — do not fail completed jobs
            logger.warning(
                "ANALYSED custody recording failed for job %s: %s",
                job.job_id,
                exc,
            )

    def _cache_job_outputs(self, job: PipelineJob, context: PipelineContext) -> None:
        """Cache artefact sets and report IDs for API/service consumers."""
        if context.artefact_set is not None:
            self._artefact_cache[job.evidence_id] = context.artefact_set
            self._artefact_cache[context.artefact_set.evidence_id] = context.artefact_set
        if context.report is not None:
            self._pipeline_reports[job.job_id] = context.report.report_id
            job.report_id = context.report.report_id
        if context.ranked_artefacts is not None:
            job.artefact_count = max(job.artefact_count, len(context.ranked_artefacts))
        elif context.artefact_set is not None:
            job.artefact_count = max(job.artefact_count, context.artefact_set.total_count)

    def _record_pipeline_state(
        self,
        job: PipelineJob,
        context: PipelineContext,
        case: CaseMetadata,
    ) -> None:
        """Build a compatibility ``PipelineState`` for legacy status APIs."""
        stage_results: dict[str, StageResult] = {}
        for key, execution in job.stage_executions.items():
            stage_results[key] = StageResult(
                stage=execution.stage,
                success=execution.status.value == "completed",
                duration_seconds=execution.duration_seconds or 0.0,
                output_data=execution.output_summary,
                errors=list(execution.errors),
            )
        state = PipelineState(
            pipeline_id=job.job_id,
            case=case,
            current_stage=job.current_stage or PipelineStage.EVALUATION,
            stage_results=stage_results,
            started_at=job.started_at or job.created_at,
            completed_at=job.completed_at,
        )
        self._pipeline_states[job.job_id] = state

    def _safe_stage_count(self, mode: str) -> int:
        """Return expected stage count for ``mode`` without raising."""
        try:
            return len(self._registry.get_ordered_stages(mode))
        except (KeyError, ValueError):
            return 5
