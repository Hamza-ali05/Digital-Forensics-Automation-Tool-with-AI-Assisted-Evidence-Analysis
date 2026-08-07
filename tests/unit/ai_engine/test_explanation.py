"""Unit tests for per-artefact explanation generation (Prompt 5.10)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.ai_engine.explanation import (
    ArtefactExplainer,
    InMemoryResponseCache,
)
from dfat.ai_engine.llm.client import LLMResponse
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.preprocessing import ArtefactSerializer
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import RankedArtefact


def _ranked(artefact_id: str, level: SuspicionLevel) -> RankedArtefact:
    return RankedArtefact(
        artefact_id=artefact_id,
        category=ArtefactCategory.INJECTED_CODE,
        source_evidence_id="ev-1",
        raw_data={"pid": 1, "name": artefact_id},
        suspicion_level=level,
        relevance_score=0.9,
        classification_reasoning="test reason",
    )


def _explainer(
    mock_audit_logger: MagicMock,
    ollama: MagicMock,
    cache: InMemoryResponseCache | None = None,
) -> ArtefactExplainer:
    return ArtefactExplainer(
        ollama_client=ollama,
        templates=ForensicPromptTemplates(),
        serializer=ArtefactSerializer(),
        response_cache=cache if cache is not None else InMemoryResponseCache(),
        audit_logger=mock_audit_logger,
    )


@pytest.mark.asyncio
async def test_explanations_are_cached(mock_audit_logger: MagicMock) -> None:
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=LLMResponse(
            text=(
                "1. What this artefact represents\nInjected code region.\n"
                "2. Why it was classified at this level\nRWX + MZ.\n"
                "3. What investigative action it suggests\n- Dump the process\n"
                "4. Any related artefacts to examine\nNone"
            ),
            model="llama3",
        )
    )
    cache = InMemoryResponseCache()
    explainer = _explainer(mock_audit_logger, ollama, cache)
    artefact = _ranked("art-1", SuspicionLevel.CRITICAL)

    first = await explainer.explain_artefact(artefact)
    second = await explainer.explain_artefact(artefact)

    assert first.artefact_id == "art-1"
    assert second.explanation_text == first.explanation_text
    assert ollama.generate.await_count == 1
    assert len(cache) == 1


@pytest.mark.asyncio
async def test_batch_only_explains_high_plus_by_default(
    mock_audit_logger: MagicMock,
) -> None:
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=LLMResponse(text="Injected code explanation.", model="llama3")
    )
    explainer = _explainer(mock_audit_logger, ollama)
    artefacts = [
        _ranked("crit", SuspicionLevel.CRITICAL),
        _ranked("high", SuspicionLevel.HIGH),
        _ranked("low", SuspicionLevel.LOW),
        _ranked("info", SuspicionLevel.INFORMATIONAL),
    ]

    results = await explainer.explain_batch(artefacts, max_concurrent=2)

    assert len(results) == 2
    assert {item.artefact_id for item in results} == {"crit", "high"}
    assert ollama.generate.await_count == 2


@pytest.mark.asyncio
async def test_batch_respects_concurrency_limit(
    mock_audit_logger: MagicMock,
) -> None:
    started = 0
    max_in_flight = 0
    lock = asyncio.Lock()

    async def _slow_generate(*_args, **_kwargs):
        nonlocal started, max_in_flight
        async with lock:
            started += 1
            max_in_flight = max(max_in_flight, started)
        await asyncio.sleep(0.05)
        async with lock:
            started -= 1
        return LLMResponse(text="ok", model="llama3")

    ollama = MagicMock()
    ollama.generate = AsyncMock(side_effect=_slow_generate)
    explainer = _explainer(mock_audit_logger, ollama)
    artefacts = [_ranked(f"a-{i}", SuspicionLevel.HIGH) for i in range(6)]

    await explainer.explain_batch(artefacts, max_concurrent=2)

    assert getattr(explainer, "_last_max_in_flight", 0) <= 2
    assert max_in_flight <= 2
