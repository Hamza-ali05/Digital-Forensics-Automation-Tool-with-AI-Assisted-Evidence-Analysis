"""Unit tests for LLM investigative summarization (Prompt 5.8)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.ai_engine.llm.client import LLMResponse
from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.llm.prompts import PROMPT_VERSION
from dfat.ai_engine.summarization import (
    LLMInvestigativeSummarizer,
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
async def test_summary_includes_five_sections_and_metadata(
    mock_audit_logger: MagicMock,
) -> None:
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=LLMResponse(text=_SAMPLE_SUMMARY, model="llama3")
    )
    summarizer = LLMInvestigativeSummarizer(
        ollama_client=ollama,
        prompt_builder=SummarizationPromptBuilder(),
        response_validator=SummaryResponseValidator(),
        audit_logger=mock_audit_logger,
        config=LLMConfig(model="llama3", temperature=0.1),
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
    assert result.confidence_score > 0.0
    assert result.model_used == "llama3"
    assert result.prompt_version == PROMPT_VERSION == "1.0.0"
    assert result.generation_params["temperature"] == 0.1
    details = mock_audit_logger.log_action.call_args.kwargs["details"]
    assert details["prompt_version"] == "1.0.0"


def test_prompt_builder_includes_high_plus_detail() -> None:
    prompt = SummarizationPromptBuilder().build_summary_prompt(
        [
            _ranked("crit-1", SuspicionLevel.CRITICAL),
            _ranked("low-1", SuspicionLevel.LOW),
        ]
    )
    assert "crit-1" in prompt
    assert "EXECUTIVE SUMMARY" in prompt or "investigative summary" in prompt.lower()
