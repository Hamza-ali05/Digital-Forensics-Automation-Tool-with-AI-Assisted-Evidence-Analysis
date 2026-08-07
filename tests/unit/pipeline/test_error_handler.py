"""Unit tests for PipelineErrorHandler recovery policies."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.core.enums import ArtefactCategory, EvidenceType, PipelineStage
from dfat.pipeline.enums import ParserStatus, StageStatus
from dfat.pipeline.error_handler import PipelineErrorHandler
from dfat.pipeline.exceptions import ParserUnavailableError
from dfat.pipeline.models import ParserResult, StageExecution


@pytest.fixture
def error_handler() -> PipelineErrorHandler:
    """Error handler with mocked pipeline logger."""
    logger = MagicMock()
    logger.log_parser_error = AsyncMock()
    return PipelineErrorHandler(pipeline_logger=logger)


@pytest.mark.asyncio
async def test_handle_parser_error_marks_unavailable(
    error_handler: PipelineErrorHandler,
) -> None:
    """Verify ParserUnavailableError maps to UNAVAILABLE status."""
    # Arrange
    error = ParserUnavailableError(
        "missing lib",
        parser_name="FileSystemParser",
        library_name="pytsk3",
    )

    # Act
    result = await error_handler.handle_parser_error(
        "job-1",
        "FileSystemParser",
        error,
        EvidenceType.DISK_IMAGE,
    )

    # Assert
    assert result.status is ParserStatus.UNAVAILABLE
    assert result.category is ArtefactCategory.FILESYSTEM_METADATA
    assert "missing lib" in (result.error or "")


@pytest.mark.asyncio
async def test_handle_parser_error_marks_failed(
    error_handler: PipelineErrorHandler,
) -> None:
    """Verify generic exceptions map to FAILED with category hint."""
    # Act
    result = await error_handler.handle_parser_error(
        "job-1",
        "NetworkArtefactParser",
        RuntimeError("boom"),
        EvidenceType.MEMORY_DUMP,
    )

    # Assert
    assert result.status is ParserStatus.FAILED
    assert result.category is ArtefactCategory.NETWORK_CONNECTION


@pytest.mark.asyncio
async def test_handle_stage_error_triage_requests_fallback(
    error_handler: PipelineErrorHandler,
) -> None:
    """Verify AI_TRIAGE failures request rule-based fallback."""
    # Act
    execution = await error_handler.handle_stage_error(
        "job-1",
        PipelineStage.AI_TRIAGE,
        RuntimeError("llm down"),
    )

    # Assert
    assert execution.status is StageStatus.FAILED
    assert execution.output_summary.get("use_fallback_analyzer") is True
    assert execution.output_summary.get("recoverable") is True


def test_should_abort_pipeline_policy(error_handler: PipelineErrorHandler) -> None:
    """Verify abort policy across acquisition/parsing/reporting/evaluation."""
    # Arrange
    failed = StageExecution(stage=PipelineStage.ACQUISITION, status=StageStatus.FAILED)
    parsing_empty = StageExecution(
        stage=PipelineStage.PARSING,
        status=StageStatus.FAILED,
        parser_results={},
    )
    parsing_partial = StageExecution(
        stage=PipelineStage.PARSING,
        status=StageStatus.FAILED,
        parser_results={
            "FileSystemParser": ParserResult(
                parser_name="FileSystemParser",
                status=ParserStatus.COMPLETED,
                artefacts_found=3,
                category=ArtefactCategory.FILESYSTEM_METADATA,
            )
        },
    )
    reporting = StageExecution(stage=PipelineStage.REPORTING, status=StageStatus.FAILED)
    evaluation = StageExecution(
        stage=PipelineStage.EVALUATION,
        status=StageStatus.FAILED,
    )
    triage = StageExecution(stage=PipelineStage.AI_TRIAGE, status=StageStatus.FAILED)

    # Act / Assert
    assert error_handler.should_abort_pipeline(PipelineStage.ACQUISITION, failed) is True
    assert (
        error_handler.should_abort_pipeline(PipelineStage.PARSING, parsing_empty) is True
    )
    assert (
        error_handler.should_abort_pipeline(PipelineStage.PARSING, parsing_partial)
        is False
    )
    assert error_handler.should_abort_pipeline(PipelineStage.AI_TRIAGE, triage) is False
    assert error_handler.should_abort_pipeline(PipelineStage.REPORTING, reporting) is True
    assert (
        error_handler.should_abort_pipeline(PipelineStage.EVALUATION, evaluation) is False
    )


def test_assemble_partial_results(error_handler: PipelineErrorHandler) -> None:
    """Verify successful parser results assemble into an ArtefactSet."""
    # Arrange
    results = {
        "ok": ParserResult(
            parser_name="ok",
            status=ParserStatus.COMPLETED,
            artefacts_found=2,
            category=ArtefactCategory.EVENT_LOG,
        ),
        "bad": ParserResult(
            parser_name="bad",
            status=ParserStatus.FAILED,
            artefacts_found=0,
            category=ArtefactCategory.REGISTRY_KEY,
        ),
    }

    # Act
    assembled = error_handler.assemble_partial_results(results, "ev-1")
    empty = error_handler.assemble_partial_results(
        {
            "bad": ParserResult(
                parser_name="bad",
                status=ParserStatus.FAILED,
                artefacts_found=0,
                category=ArtefactCategory.REGISTRY_KEY,
            )
        },
        "ev-1",
    )

    # Assert
    assert assembled is not None
    assert assembled.evidence_id == "ev-1"
    assert assembled.total_count == 2
    assert empty is None
