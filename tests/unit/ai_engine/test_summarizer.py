"""Unit tests for investigative summarisation (Prompt 5.20)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.ai_engine.llm.client import LLMResponse
from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.summarization import (
    LLMInvestigativeSummarizer,
    NarrativeFormatter,
    SummarizationPromptBuilder,
    SummaryResponseValidator,
)
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import RankedArtefact

_SAMPLE_SUMMARY = """
1. EXECUTIVE SUMMARY
Evidence suggests possible code injection on host [UNCERTAIN].

2. KEY FINDINGS
- CRITICAL injected code in process malware.exe (art-1)
- HIGH external network connection to 8.8.8.8 (art-2)

3. TIMELINE OF EVENTS
2026-01-01T00:00:00Z process created; later network activity observed.

4. INDICATORS OF COMPROMISE
- MZ header in RWX region
- External C2-like connection

5. RECOMMENDED NEXT STEPS
- Acquire full memory dump for process art-1
- Block remote address and re-image host
"""


def _ranked(artefact_id: str, level: SuspicionLevel) -> RankedArtefact:
    return RankedArtefact(
        artefact_id=artefact_id,
        category=ArtefactCategory.INJECTED_CODE,
        source_evidence_id="ev-1",
        raw_data={"name": artefact_id},
        suspicion_level=level,
        relevance_score=0.9,
        classification_reasoning="test",
    )


@pytest.mark.asyncio
async def test_summary_includes_all_sections(mock_audit_logger: MagicMock) -> None:
    """Verify summary parsing extracts all five investigative sections."""
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=LLMResponse(text=_SAMPLE_SUMMARY, model="llama3")
    )
    summarizer = LLMInvestigativeSummarizer(
        ollama_client=ollama,
        prompt_builder=SummarizationPromptBuilder(),
        response_validator=SummaryResponseValidator(),
        audit_logger=mock_audit_logger,
        config=LLMConfig(model="llama3"),
    )
    result = await summarizer.generate_summary(
        [
            _ranked("art-1", SuspicionLevel.CRITICAL),
            _ranked("art-2", SuspicionLevel.HIGH),
        ]
    )
    assert result.executive_summary
    assert result.key_findings
    assert result.timeline_narrative
    assert result.iocs_identified
    assert result.recommended_actions


@pytest.mark.asyncio
async def test_summary_includes_disclaimer(
    mock_audit_logger: MagicMock,
) -> None:
    """Verify narrative formatting attaches the Scanlon disclaimer."""
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=LLMResponse(text=_SAMPLE_SUMMARY, model="llama3")
    )
    summarizer = LLMInvestigativeSummarizer(
        ollama_client=ollama,
        prompt_builder=SummarizationPromptBuilder(),
        response_validator=SummaryResponseValidator(),
        audit_logger=mock_audit_logger,
        config=LLMConfig(model="llama3"),
    )
    summary = await summarizer.generate_summary(
        [_ranked("art-1", SuspicionLevel.CRITICAL)]
    )
    narrative = NarrativeFormatter().format_narrative(
        summary,
        [_ranked("art-1", SuspicionLevel.CRITICAL)],
        case_name="Case",
        evidence_id="ev-1",
    )
    assert "Scanlon" in narrative.disclaimer
    assert narrative.sections.get("disclaimer") or narrative.disclaimer


@pytest.mark.asyncio
async def test_summary_confidence_scoring(mock_audit_logger: MagicMock) -> None:
    """Verify a well-formed summary yields a positive confidence score."""
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=LLMResponse(text=_SAMPLE_SUMMARY, model="llama3")
    )
    summarizer = LLMInvestigativeSummarizer(
        ollama_client=ollama,
        prompt_builder=SummarizationPromptBuilder(),
        response_validator=SummaryResponseValidator(),
        audit_logger=mock_audit_logger,
        config=LLMConfig(model="llama3"),
    )
    result = await summarizer.generate_summary(
        [_ranked("art-1", SuspicionLevel.CRITICAL)]
    )
    assert result.confidence_score > 0.0


@pytest.mark.asyncio
async def test_summary_handles_llm_failure(mock_audit_logger: MagicMock) -> None:
    """Verify summariser returns a structured fallback when LLM fails."""
    ollama = MagicMock()
    ollama.generate = AsyncMock(side_effect=RuntimeError("ollama down"))
    summarizer = LLMInvestigativeSummarizer(
        ollama_client=ollama,
        prompt_builder=SummarizationPromptBuilder(),
        response_validator=SummaryResponseValidator(),
        audit_logger=mock_audit_logger,
        config=LLMConfig(model="llama3"),
    )
    result = await summarizer.generate_summary(
        [_ranked("art-1", SuspicionLevel.HIGH)]
    )
    assert "fallback" in result.full_text.lower() or "unavailable" in result.full_text.lower()
    assert "EXECUTIVE SUMMARY" in result.full_text
