"""Pipeline error recovery — parser fallback and partial result assembly."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from dfat.core.enums import ArtefactCategory, EvidenceType, PipelineStage
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.pipeline.enums import ParserStatus, StageStatus
from dfat.pipeline.exceptions import ParserUnavailableError
from dfat.pipeline.models import ParserResult, StageExecution
from dfat.pipeline.pipeline_logger import PipelineLogger

_EVIDENCE_DEFAULT_CATEGORY: dict[EvidenceType, ArtefactCategory] = {
    EvidenceType.DISK_IMAGE: ArtefactCategory.FILESYSTEM_METADATA,
    EvidenceType.MEMORY_DUMP: ArtefactCategory.RUNNING_PROCESS,
}

_PARSER_CATEGORY_HINTS: dict[str, ArtefactCategory] = {
    "filesystem": ArtefactCategory.FILESYSTEM_METADATA,
    "registry": ArtefactCategory.REGISTRY_KEY,
    "browser": ArtefactCategory.BROWSER_HISTORY,
    "eventlog": ArtefactCategory.EVENT_LOG,
    "event_log": ArtefactCategory.EVENT_LOG,
    "process": ArtefactCategory.RUNNING_PROCESS,
    "network": ArtefactCategory.NETWORK_CONNECTION,
    "injection": ArtefactCategory.INJECTED_CODE,
}


class PipelineErrorHandler:
    """Convert pipeline failures into recoverable stage/parser outcomes."""

    def __init__(self, pipeline_logger: PipelineLogger) -> None:
        """Initialise the error handler.

        Args:
            pipeline_logger: Dual-write pipeline event logger.
        """
        self._logger = pipeline_logger

    async def handle_parser_error(
        self,
        job_id: str,
        parser_name: str,
        error: Exception,
        evidence_type: EvidenceType,
    ) -> ParserResult:
        """Convert a parser exception into a ``FAILED``/``UNAVAILABLE`` result.

        Does not re-raise — callers continue with remaining parsers.

        Args:
            job_id: Pipeline job identifier.
            parser_name: Failing parser identifier.
            error: Exception raised by the parser.
            evidence_type: Evidence type under analysis (category fallback).

        Returns:
            ``ParserResult`` describing the failure.
        """
        await self._logger.log_parser_error(job_id, parser_name, str(error))
        if isinstance(error, ParserUnavailableError):
            status = ParserStatus.UNAVAILABLE
        else:
            status = ParserStatus.FAILED
        return ParserResult(
            parser_name=parser_name,
            status=status,
            artefacts_found=0,
            duration_seconds=0.0,
            error=str(error),
            category=self._category_for_parser(parser_name, evidence_type),
        )

    async def handle_stage_error(
        self,
        job_id: str,
        stage: PipelineStage,
        error: Exception,
    ) -> StageExecution:
        """Build a ``StageExecution`` for a stage failure, applying recovery policy.

        Recovery:
            * ``PARSING`` — keep partial parser results when any artefacts exist.
            * ``AI_TRIAGE`` — mark recoverable and request rule-based fallback.
            * Other stages — mark ``FAILED``.

        Args:
            job_id: Pipeline job identifier.
            stage: Stage that failed.
            error: Exception raised during the stage.

        Returns:
            Stage execution snapshot reflecting failure or graceful degradation.
        """
        now = datetime.now(UTC)
        parser_results = self._extract_parser_results(error)
        errors = [str(error)]
        output_summary: dict[str, Any] = {
            "job_id": job_id,
            "error_type": type(error).__name__,
        }

        if stage is PipelineStage.PARSING:
            artefacts = self._count_successful_artefacts(parser_results)
            output_summary["partial"] = artefacts > 0
            output_summary["artefacts_recovered"] = artefacts
            if artefacts > 0:
                # Graceful degradation: stage soft-fails but results are usable.
                status = StageStatus.FAILED
                output_summary["recoverable"] = True
            else:
                status = StageStatus.FAILED
                output_summary["recoverable"] = False
        elif stage is PipelineStage.AI_TRIAGE:
            status = StageStatus.FAILED
            output_summary["use_fallback_analyzer"] = True
            output_summary["recoverable"] = True
        else:
            status = StageStatus.FAILED
            output_summary["recoverable"] = False

        execution = StageExecution(
            stage=stage,
            status=status,
            completed_at=now,
            errors=errors,
            output_summary=output_summary,
            parser_results=parser_results,
        )
        # Reuse parser-error dual-log path for stage failures (event name in details).
        await self._logger.log_parser_error(
            job_id,
            f"stage:{stage.value}",
            str(error),
        )
        return execution

    def should_abort_pipeline(
        self,
        stage: PipelineStage,
        stage_result: StageExecution,
    ) -> bool:
        """Return whether a stage outcome should stop the remainder of the job.

        Policy:
            * ``ACQUISITION`` failure → abort (no evidence to process).
            * ``PARSING`` failure with zero artefacts → abort.
            * ``PARSING`` failure with partial results → continue.
            * ``AI_TRIAGE`` failure → continue (rule-based fallback).
            * ``REPORTING`` failure → abort (no deliverable output).
            * ``EVALUATION`` failure → continue (metrics are optional).

        Args:
            stage: Stage that produced ``stage_result``.
            stage_result: Stage execution outcome.

        Returns:
            ``True`` when the pipeline must abort.
        """
        failed = stage_result.status is StageStatus.FAILED
        if stage is PipelineStage.ACQUISITION:
            return failed
        if stage is PipelineStage.PARSING:
            # Abort only when no artefacts were recovered (total or partial failure).
            return self._count_successful_artefacts(stage_result.parser_results) == 0
        if stage is PipelineStage.AI_TRIAGE:
            return False
        if stage is PipelineStage.REPORTING:
            return failed
        if stage is PipelineStage.EVALUATION:
            return False
        return failed

    def assemble_partial_results(
        self,
        parser_results: dict[str, ParserResult],
        evidence_id: str,
    ) -> Optional[ArtefactSet]:
        """Build an ``ArtefactSet`` from parsers that completed successfully.

        Args:
            parser_results: Per-parser outcomes keyed by parser name.
            evidence_id: Source evidence identifier.

        Returns:
            Assembled set when at least one parser succeeded; otherwise ``None``.
        """
        artefacts: list[Artefact] = []
        categories: set[ArtefactCategory] = set()
        for parser_name, result in parser_results.items():
            if result.status is not ParserStatus.COMPLETED:
                continue
            if result.artefacts_found <= 0:
                categories.add(result.category)
                continue
            categories.add(result.category)
            # Placeholder artefacts preserve count/category for downstream stages
            # until full artefact payloads are threaded through ParserResult.
            for index in range(result.artefacts_found):
                artefacts.append(
                    Artefact(
                        category=result.category,
                        source_evidence_id=evidence_id,
                        raw_data={
                            "parser": parser_name,
                            "partial_assembly": True,
                            "index": index,
                        },
                        metadata={
                            "parser": parser_name,
                            "assembled_from_partial": True,
                        },
                    )
                )

        succeeded = [
            r
            for r in parser_results.values()
            if r.status is ParserStatus.COMPLETED
        ]
        if not succeeded:
            return None

        return ArtefactSet(
            evidence_id=evidence_id,
            artefacts=artefacts,
            categories_present=sorted(categories, key=lambda item: item.value),
        )

    def _category_for_parser(
        self,
        parser_name: str,
        evidence_type: EvidenceType,
    ) -> ArtefactCategory:
        """Infer artefact category from parser name or evidence type."""
        lowered = parser_name.lower()
        for hint, category in _PARSER_CATEGORY_HINTS.items():
            if hint in lowered:
                return category
        return _EVIDENCE_DEFAULT_CATEGORY.get(
            evidence_type,
            ArtefactCategory.FILESYSTEM_METADATA,
        )

    def _extract_parser_results(self, error: Exception) -> dict[str, ParserResult]:
        """Pull parser result snapshots from error context when present."""
        context = getattr(error, "context", None)
        if not isinstance(context, dict):
            return {}
        raw = context.get("parser_results")
        if not isinstance(raw, dict):
            return {}
        results: dict[str, ParserResult] = {}
        for key, value in raw.items():
            if isinstance(value, ParserResult):
                results[str(key)] = value
            elif isinstance(value, dict):
                try:
                    results[str(key)] = ParserResult.model_validate(value)
                except Exception:  # noqa: BLE001 — ignore malformed context
                    continue
        return results

    @staticmethod
    def _count_successful_artefacts(
        parser_results: dict[str, ParserResult],
    ) -> int:
        """Sum artefacts from parsers that completed successfully."""
        return sum(
            result.artefacts_found
            for result in parser_results.values()
            if result.status is ParserStatus.COMPLETED
        )
