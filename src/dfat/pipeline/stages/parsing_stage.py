"""Stage 2 — parse forensic evidence and extract normalised artefacts."""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from dfat.core.enums import ArtefactCategory, EvidenceType, PipelineStage
from dfat.core.interfaces.parser import IArtefactParser
from dfat.core.models.artefact import ArtefactSet
from dfat.core.models.pipeline import StageResult
from dfat.forensic_engine.normalizer import ArtefactNormalizer
from dfat.pipeline.enums import ParserStatus
from dfat.pipeline.error_handler import PipelineErrorHandler
from dfat.pipeline.evidence_router import EvidenceRouter
from dfat.pipeline.exceptions import AllParsersFailedError
from dfat.pipeline.models import ParserResult
from dfat.pipeline.parser_registry import ParserRegistry
from dfat.pipeline.progress_tracker import ProgressNotFoundError, ProgressTracker
from dfat.pipeline.stage_interface import IPipelineStage, PipelineContext
from dfat.services.audit_service import AuditService


class ParsingStage(IPipelineStage):
    """Coordinate artefact parsers and produce a normalised ``ArtefactSet``."""

    def __init__(
        self,
        parser_registry: ParserRegistry,
        evidence_router: EvidenceRouter,
        normalizer: ArtefactNormalizer,
        progress_tracker: ProgressTracker,
        error_handler: PipelineErrorHandler,
        audit_service: AuditService,
        parser_timeout_seconds: float = 300.0,
    ) -> None:
        """Initialise the parsing stage.

        Args:
            parser_registry: Registry of artefact parsers.
            evidence_router: Routes evidence types to available parsers.
            normalizer: Merges and deduplicates parser ``ArtefactSet`` outputs.
            progress_tracker: Job/stage/parser progress tracker.
            error_handler: Parser/stage error recovery helper.
            audit_service: Dual-write audit trail service.
            parser_timeout_seconds: Per-parser wall-clock timeout.
        """
        self._registry = parser_registry
        self._router = evidence_router
        self._normalizer = normalizer
        self._progress = progress_tracker
        self._errors = error_handler
        self._audit = audit_service
        self._parser_timeout = max(1.0, float(parser_timeout_seconds))

    @property
    def stage_name(self) -> PipelineStage:
        """Return ``PipelineStage.PARSING``."""
        return PipelineStage.PARSING

    @property
    def description(self) -> str:
        """Return a human-readable description of this stage."""
        return "Parse forensic evidence and extract artefacts"

    async def validate_preconditions(self, context: PipelineContext) -> bool:
        """Verify evidence is present and at least one parser is available."""
        if context.evidence is None:
            return False
        parsers = self._router.route(context.evidence.evidence_type)
        return len(parsers) > 0

    async def execute(self, context: PipelineContext) -> StageResult:
        """Run routed parsers, normalise outputs, and update context.

        Args:
            context: Shared pipeline context (must include ``evidence``).

        Returns:
            ``StageResult`` for the parsing stage.
        """
        started = time.perf_counter()
        errors: list[str] = []
        evidence = context.evidence
        if evidence is None:
            return StageResult(
                stage=self.stage_name,
                success=False,
                duration_seconds=time.perf_counter() - started,
                errors=["No evidence available for parsing"],
            )

        job_id = context.job.job_id
        evidence_type = evidence.evidence_type
        parsers = self._router.route(evidence_type)
        self._ensure_progress_job(job_id)
        self._progress.start_stage(
            job_id,
            self.stage_name,
            parser_count=len(parsers),
        )
        await self._audit.log_action(
            stage=self.stage_name,
            action="PARSING_STAGE_STARTED",
            evidence_id=evidence.evidence_id,
            user_id=context.job.user_id,
            details={
                "job_id": job_id,
                "parser_count": len(parsers),
                "parsers": [parser.parser_name for parser in parsers],
            },
        )

        successful_sets: list[ArtefactSet] = []
        parser_results: dict[str, ParserResult] = {}

        for parser in parsers:
            result = await self._run_one_parser(
                parser=parser,
                context=context,
                evidence_type=evidence_type,
            )
            parser_results[parser.parser_name] = result.parser_result
            if result.artefact_set is not None:
                successful_sets.append(result.artefact_set)
            if result.error_message:
                errors.append(result.error_message)

        duration = time.perf_counter() - started
        context.stage_timings[self.stage_name.value] = duration

        if not successful_sets:
            all_failed = AllParsersFailedError(
                f"All parsers failed for {evidence_type.value}",
                evidence_type=evidence_type,
                context={
                    "job_id": job_id,
                    "parser_results": {
                        name: result.model_dump(mode="json")
                        for name, result in parser_results.items()
                    },
                },
            )
            stage_execution = await self._errors.handle_stage_error(
                job_id,
                self.stage_name,
                all_failed,
            )
            # Preserve structured parser outcomes for abort policy.
            stage_execution.parser_results = parser_results
            abort = self._errors.should_abort_pipeline(
                self.stage_name,
                stage_execution,
            )
            self._progress.complete_stage(job_id, self.stage_name, artefacts_found=0)
            await self._audit.log_action(
                stage=self.stage_name,
                action="PARSING_STAGE_FAILED",
                evidence_id=evidence.evidence_id,
                user_id=context.job.user_id,
                details={
                    "job_id": job_id,
                    "abort": abort,
                    "errors": errors,
                },
            )
            return StageResult(
                stage=self.stage_name,
                success=False,
                duration_seconds=duration,
                output_data={
                    "abort": abort,
                    "parser_results": {
                        name: result.model_dump(mode="json")
                        for name, result in parser_results.items()
                    },
                },
                errors=errors or [str(all_failed)],
            )

        normalised = self._normalizer.normalize(
            successful_sets,
            evidence.evidence_id,
        )
        context.artefact_set = normalised
        context.job.artefact_count = normalised.total_count
        # Parser-level progress already accumulated artefact counts.
        self._progress.complete_stage(
            job_id,
            self.stage_name,
            artefacts_found=0,
        )
        await self._audit.log_action(
            stage=self.stage_name,
            action="PARSING_STAGE_COMPLETED",
            evidence_id=evidence.evidence_id,
            user_id=context.job.user_id,
            details={
                "job_id": job_id,
                "artefact_count": normalised.total_count,
                "categories": [c.value for c in normalised.categories_present],
                "parsers_succeeded": len(successful_sets),
                "parsers_failed": len(errors),
            },
        )
        return StageResult(
            stage=self.stage_name,
            success=True,
            duration_seconds=duration,
            output_data={
                "artefact_count": normalised.total_count,
                "categories_present": [
                    category.value for category in normalised.categories_present
                ],
                "parser_results": {
                    name: result.model_dump(mode="json")
                    for name, result in parser_results.items()
                },
                "partial": bool(errors),
            },
            errors=errors,
        )

    async def _run_one_parser(
        self,
        *,
        parser: IArtefactParser,
        context: PipelineContext,
        evidence_type: EvidenceType,
    ) -> _ParserRunOutcome:
        """Execute a single parser with timeout and progress updates."""
        assert context.evidence is not None
        job_id = context.job.job_id
        name = parser.parser_name
        self._progress.start_parser(job_id, name)
        started = time.perf_counter()
        try:
            artefact_set = await asyncio.wait_for(
                asyncio.to_thread(parser.parse, context.evidence),
                timeout=self._parser_timeout,
            )
            duration = time.perf_counter() - started
            count = artefact_set.total_count if artefact_set is not None else 0
            category = self._primary_category(parser, evidence_type)
            self._progress.complete_parser(job_id, name, artefacts_found=count)
            return _ParserRunOutcome(
                parser_result=ParserResult(
                    parser_name=name,
                    status=ParserStatus.COMPLETED,
                    artefacts_found=count,
                    duration_seconds=duration,
                    category=category,
                ),
                artefact_set=artefact_set,
            )
        except Exception as exc:  # noqa: BLE001 — isolate parser failures
            duration = time.perf_counter() - started
            parser_result = await self._errors.handle_parser_error(
                job_id,
                name,
                exc,
                evidence_type,
            )
            parser_result.duration_seconds = duration
            self._progress.fail_parser(job_id, name, str(exc))
            return _ParserRunOutcome(
                parser_result=parser_result,
                artefact_set=None,
                error_message=f"{name}: {exc}",
            )

    def _ensure_progress_job(self, job_id: str) -> None:
        """Ensure progress tracking has been initialised for ``job_id``."""
        try:
            self._progress.get_progress(job_id)
        except ProgressNotFoundError:
            self._progress.start_job(job_id, total_stages=5)

    @staticmethod
    def _primary_category(
        parser: IArtefactParser,
        evidence_type: EvidenceType,
    ) -> ArtefactCategory:
        """Return the parser's primary category, with a type-based fallback."""
        categories = parser.supported_categories()
        if categories:
            return categories[0]
        if evidence_type is EvidenceType.MEMORY_DUMP:
            return ArtefactCategory.RUNNING_PROCESS
        return ArtefactCategory.FILESYSTEM_METADATA


class _ParserRunOutcome:
    """Internal outcome of a single parser invocation."""

    __slots__ = ("parser_result", "artefact_set", "error_message")

    def __init__(
        self,
        parser_result: ParserResult,
        artefact_set: Optional[ArtefactSet],
        error_message: Optional[str] = None,
    ) -> None:
        self.parser_result = parser_result
        self.artefact_set = artefact_set
        self.error_message = error_message
