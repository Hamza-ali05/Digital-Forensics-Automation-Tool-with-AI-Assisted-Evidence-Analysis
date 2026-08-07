"""Unit tests for investigator Q&A assistance (Prompt 5.14)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.ai_engine.assistance import InvestigatorQAAssistant
from dfat.ai_engine.explanation import InMemoryResponseCache
from dfat.ai_engine.llm.client import LLMResponse
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.preprocessing import ArtefactSerializer, TokenTruncator
from dfat.ai_engine.validation import AIResponseValidator
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact


def _artefact(artefact_id: str) -> Artefact:
    return Artefact(
        artefact_id=artefact_id,
        category=ArtefactCategory.INJECTED_CODE,
        source_evidence_id="ev-1",
        raw_data={"pid": 1, "name": artefact_id, "detail": "x" * 50},
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
async def test_answer_references_artefact_ids_and_runs_hallucination_check(
    mock_audit_logger: MagicMock,
) -> None:
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
    assert result.hallucination_check is not None
    assert result.hallucination_check.risk_level in {"low", "medium", "high"}
    assert result.model_used == "llama3"
    mock_audit_logger.log_action.assert_called()


@pytest.mark.asyncio
async def test_conversation_history_uses_chat(
    mock_audit_logger: MagicMock,
) -> None:
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
async def test_context_is_truncated_to_fit_window(
    mock_audit_logger: MagicMock,
) -> None:
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=LLMResponse(text="Insufficient detail on art-1.", model="llama3")
    )
    guard = AIResponseValidator.default_guard({"art-1"})
    truncator = TokenTruncator(max_tokens=80)
    assistant = InvestigatorQAAssistant(
        ollama_client=ollama,
        templates=ForensicPromptTemplates(),
        serializer=ArtefactSerializer(),
        hallucination_guard=guard,
        response_cache=InMemoryResponseCache(),
        audit_logger=mock_audit_logger,
        truncator=truncator,
    )
    huge = [
        Artefact(
            artefact_id=f"art-{i}",
            category=ArtefactCategory.FILESYSTEM_METADATA,
            source_evidence_id="ev-1",
            raw_data={"path": "/x/" + ("y" * 200), "name": f"f{i}"},
        )
        for i in range(30)
    ]
    huge[0] = _artefact("art-1")
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=huge,
        categories_present=[ArtefactCategory.FILESYSTEM_METADATA],
    )

    await assistant.ask("Summarise findings", artefact_set)

    prompt = ollama.generate.await_args.args[0]
    assert "TRUNCATED" in prompt or len(prompt) < 5000


@pytest.mark.asyncio
async def test_suggest_questions_from_ranked(mock_audit_logger: MagicMock) -> None:
    ranked = [
        RankedArtefact(
            **_artefact("art-1").model_dump(),
            suspicion_level=SuspicionLevel.CRITICAL,
            relevance_score=0.9,
        ),
        RankedArtefact(
            **_artefact("art-2").model_dump(),
            suspicion_level=SuspicionLevel.HIGH,
            relevance_score=0.8,
        ),
    ]
    assistant = _assistant(mock_audit_logger, MagicMock())
    questions = await assistant.suggest_questions(ranked)
    assert 3 <= len(questions) <= 5
    assert any("art-1" in q for q in questions)
