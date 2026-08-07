"""Unit tests for investigator Q&A assistant (Prompt 5.20)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.ai_engine.assistance import InvestigatorQAAssistant
from dfat.ai_engine.explanation import InMemoryResponseCache
from dfat.ai_engine.llm.client import LLMResponse
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.preprocessing import ArtefactSerializer, TokenTruncator
from dfat.ai_engine.validation import AIResponseValidator
from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet


def _artefact(artefact_id: str) -> Artefact:
    return Artefact(
        artefact_id=artefact_id,
        category=ArtefactCategory.INJECTED_CODE,
        source_evidence_id="ev-1",
        raw_data={"pid": 1, "name": artefact_id},
    )


def _assistant(mock_audit_logger: MagicMock, ollama: MagicMock) -> InvestigatorQAAssistant:
    guard = AIResponseValidator.default_guard({"art-1", "art-2"})
    return InvestigatorQAAssistant(
        ollama_client=ollama,
        templates=ForensicPromptTemplates(),
        serializer=ArtefactSerializer(),
        hallucination_guard=guard,
        response_cache=InMemoryResponseCache(),
        audit_logger=mock_audit_logger,
        truncator=TokenTruncator(max_tokens=6000),
    )


@pytest.mark.asyncio
async def test_answer_references_artefact_ids(mock_audit_logger: MagicMock) -> None:
    """Verify answers surface referenced artefact IDs from the evidence set."""
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=LLMResponse(
            text="Artefact art-1 shows injected code with an MZ header.",
            model="llama3",
        )
    )
    assistant = _assistant(mock_audit_logger, ollama)
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[_artefact("art-1"), _artefact("art-2")],
        categories_present=[ArtefactCategory.INJECTED_CODE],
    )
    result = await assistant.ask("What did you find?", artefact_set)
    assert "art-1" in result.referenced_artefact_ids


@pytest.mark.asyncio
async def test_conversation_history_continuity(mock_audit_logger: MagicMock) -> None:
    """Verify conversation history routes through chat for continuity."""
    ollama = MagicMock()
    ollama.chat = AsyncMock(
        return_value=LLMResponse(
            text="Follow-up: art-1 remains the primary concern.",
            model="llama3",
        )
    )
    ollama.generate = AsyncMock()
    assistant = _assistant(mock_audit_logger, ollama)
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[_artefact("art-1")],
        categories_present=[ArtefactCategory.INJECTED_CODE],
    )
    result = await assistant.ask(
        "Can you elaborate?",
        artefact_set,
        conversation_history=[
            {"role": "user", "content": "What is suspicious?"},
            {"role": "assistant", "content": "art-1 looks injected."},
        ],
    )
    assert "art-1" in result.answer
    ollama.chat.assert_awaited()
    ollama.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_hallucination_check_on_answer(mock_audit_logger: MagicMock) -> None:
    """Verify every answer includes a hallucination check report."""
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=LLMResponse(
            text="Artefact art-1 is benign; art-999 confirms malware_signature.",
            model="llama3",
        )
    )
    assistant = _assistant(mock_audit_logger, ollama)
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[_artefact("art-1")],
        categories_present=[ArtefactCategory.INJECTED_CODE],
    )
    result = await assistant.ask("Is there malware?", artefact_set)
    assert result.hallucination_check is not None
    assert result.hallucination_check.risk_level in {"low", "medium", "high"}
