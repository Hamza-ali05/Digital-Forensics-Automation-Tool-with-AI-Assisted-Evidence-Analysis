"""Unit tests for LLM artefact classification pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.ai_engine.classification import (
    ClassificationPromptBuilder,
    ClassificationResponseParser,
    DefaultConfidenceScorer,
    LLMArtefactClassifier,
)
from dfat.ai_engine.llm.client import LLMResponse
from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.preprocessing import ArtefactBatcher, ArtefactSerializer
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact


def _artefact(artefact_id: str, category: ArtefactCategory) -> Artefact:
    return Artefact(
        artefact_id=artefact_id,
        category=category,
        source_evidence_id="ev-1",
        raw_data={"name": artefact_id, "detail": "x" * 20},
    )


def _builder(max_tokens: int = 80) -> ClassificationPromptBuilder:
    serializer = ArtefactSerializer()
    return ClassificationPromptBuilder(
        templates=ForensicPromptTemplates(),
        serializer=serializer,
        batcher=ArtefactBatcher(max_tokens_per_batch=max_tokens, serializer=serializer),
    )


def test_batched_prompts_respect_token_limits() -> None:
    builder = _builder(max_tokens=50)
    artefacts = [
        _artefact(f"a-{i}", ArtefactCategory.FILESYSTEM_METADATA) for i in range(20)
    ]
    prompts = builder.build_batched_prompts(artefacts)
    assert len(prompts) >= 2
    for prompt in prompts:
        assert "Do not fabricate" in prompt or "do not fabricate" in prompt.lower()
        assert "---END---" in prompt


@pytest.mark.asyncio
async def test_classify_falls_back_to_informational_on_parse_failure(
    mock_audit_logger: MagicMock,
) -> None:
    artefacts = [
        _artefact("art-1", ArtefactCategory.INJECTED_CODE),
        _artefact("art-2", ArtefactCategory.NETWORK_CONNECTION),
    ]
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=LLMResponse(text="not-json-at-all", model="llama3")
    )
    classifier = LLMArtefactClassifier(
        ollama_client=ollama,
        prompt_builder=_builder(max_tokens=5000),
        response_parser=ClassificationResponseParser(),
        confidence_scorer=DefaultConfidenceScorer(),
        audit_logger=mock_audit_logger,
        config=LLMConfig(model="llama3"),
    )

    results = await classifier.classify(artefacts)

    assert len(results) == 2
    assert all(r.suspicion_level is SuspicionLevel.INFORMATIONAL for r in results)
    assert all(
        r.reasoning
        in {
            "Classification failed — insufficient AI confidence.",
            "Not classified by AI",
        }
        for r in results
    )
    mock_audit_logger.log_action.assert_called()
    details = mock_audit_logger.log_action.call_args.kwargs["details"]
    assert details["artefact_count"] == 2
    assert details["model"] == "llama3"
    assert "duration_ms" in details
    assert "prompt" not in details
    assert "raw_data" not in details


@pytest.mark.asyncio
async def test_classify_parses_valid_json_array(
    mock_audit_logger: MagicMock,
) -> None:
    artefacts = [_artefact("art-1", ArtefactCategory.INJECTED_CODE)]
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=LLMResponse(
            text=(
                '[{"artefact_id":"art-1","suspicion_level":"HIGH",'
                '"reasoning":"RWX region with MZ header",'
                '"ioc_indicators":["MZ header"]}]'
            ),
            model="llama3",
            prompt_tokens=10,
            completion_tokens=5,
        )
    )
    classifier = LLMArtefactClassifier(
        ollama_client=ollama,
        prompt_builder=_builder(),
        response_parser=ClassificationResponseParser(),
        confidence_scorer=DefaultConfidenceScorer(),
        audit_logger=mock_audit_logger,
        config=LLMConfig(),
    )

    results = await classifier.classify(artefacts)

    assert len(results) == 1
    assert results[0].suspicion_level is SuspicionLevel.HIGH
    assert results[0].ioc_indicators == ["MZ header"]
    assert results[0].confidence > 0.5


@pytest.mark.asyncio
async def test_classify_parses_valid_json(mock_audit_logger: MagicMock) -> None:
    """Alias for valid JSON classification parsing."""
    await test_classify_parses_valid_json_array(mock_audit_logger)


@pytest.mark.asyncio
async def test_classify_handles_malformed_json(mock_audit_logger: MagicMock) -> None:
    """Alias for malformed JSON → INFORMATIONAL fallback."""
    await test_classify_falls_back_to_informational_on_parse_failure(mock_audit_logger)


@pytest.mark.asyncio
async def test_classify_defaults_unclassified_to_informational(
    mock_audit_logger: MagicMock,
) -> None:
    """Verify artefacts omitted from the LLM response default to INFORMATIONAL."""
    artefacts = [
        _artefact("art-1", ArtefactCategory.INJECTED_CODE),
        _artefact("art-2", ArtefactCategory.NETWORK_CONNECTION),
    ]
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=LLMResponse(
            text=(
                '[{"artefact_id":"art-1","suspicion_level":"HIGH",'
                '"reasoning":"Injected","ioc_indicators":[]}]'
            ),
            model="llama3",
        )
    )
    classifier = LLMArtefactClassifier(
        ollama_client=ollama,
        prompt_builder=_builder(max_tokens=5000),
        response_parser=ClassificationResponseParser(),
        confidence_scorer=DefaultConfidenceScorer(),
        audit_logger=mock_audit_logger,
        config=LLMConfig(),
    )
    results = await classifier.classify(artefacts)
    by_id = {item.artefact_id: item for item in results}
    assert by_id["art-1"].suspicion_level is SuspicionLevel.HIGH
    assert by_id["art-2"].suspicion_level is SuspicionLevel.INFORMATIONAL


@pytest.mark.asyncio
async def test_classify_discards_hallucinated_ids(
    mock_audit_logger: MagicMock,
) -> None:
    """Verify hallucinated artefact IDs from the model are discarded."""
    artefacts = [_artefact("art-1", ArtefactCategory.INJECTED_CODE)]
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=LLMResponse(
            text=(
                "["
                '{"artefact_id":"art-1","suspicion_level":"HIGH",'
                '"reasoning":"Real","ioc_indicators":[]},'
                '{"artefact_id":"art-hallucinated","suspicion_level":"CRITICAL",'
                '"reasoning":"Fake","ioc_indicators":[]}'
                "]"
            ),
            model="llama3",
        )
    )
    classifier = LLMArtefactClassifier(
        ollama_client=ollama,
        prompt_builder=_builder(),
        response_parser=ClassificationResponseParser(),
        confidence_scorer=DefaultConfidenceScorer(),
        audit_logger=mock_audit_logger,
        config=LLMConfig(),
    )
    results = await classifier.classify(artefacts)
    ids = {item.artefact_id for item in results}
    assert "art-1" in ids
    assert "art-hallucinated" not in ids


def test_classify_batches_large_sets() -> None:
    """Alias: large sets produce multiple classification prompts."""
    test_batched_prompts_respect_token_limits()
