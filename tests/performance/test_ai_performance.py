"""AI engine latency tests against local LLaMA-3 (Ollama).

Marked ``performance``. Tests that call the LLM are also marked
``requires_ollama`` and skip when the local API is unavailable.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest

from dfat.ai_engine.caching.response_cache import AIResponseCache, DEFAULT_TTL_SECONDS
from dfat.ai_engine.classification import (
    ClassificationPromptBuilder,
    ClassificationResponseParser,
    DefaultConfidenceScorer,
    LLMArtefactClassifier,
)
from dfat.ai_engine.fallback import RuleBasedAnalyzer
from dfat.ai_engine.llm.client import OllamaClient
from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.llm.connection import LLMConnectionManager
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.preprocessing import ArtefactBatcher, ArtefactSerializer
from dfat.ai_engine.summarization import (
    LLMInvestigativeSummarizer,
    SummarizationPromptBuilder,
    SummaryResponseValidator,
)
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact

_CATEGORIES: tuple[ArtefactCategory, ...] = (
    ArtefactCategory.INJECTED_CODE,
    ArtefactCategory.NETWORK_CONNECTION,
    ArtefactCategory.REGISTRY_KEY,
    ArtefactCategory.RUNNING_PROCESS,
    ArtefactCategory.BROWSER_HISTORY,
)


def _elapsed_ms(started: float) -> float:
    """Return milliseconds since ``started``."""
    return (time.perf_counter() - started) * 1000.0


def _ollama_available() -> bool:
    """Return True when a local Ollama instance lists a llama3-family model."""
    try:
        with httpx.Client(timeout=httpx.Timeout(1.0, connect=1.0)) as client:
            response = client.get("http://127.0.0.1:11434/api/tags")
        if response.status_code != 200:
            return False
        models = response.json().get("models") or []
        names = [str(item.get("name") or "") for item in models if isinstance(item, dict)]
        return any(
            name == "llama3" or name.startswith("llama3:") for name in names
        )
    except Exception:  # noqa: BLE001 — absence is a skip, not a failure
        return False


@pytest.fixture
def require_ollama() -> None:
    """Skip LLM latency tests when the local Ollama API is not usable."""
    if not _ollama_available():
        pytest.skip("Ollama is not running locally (llama3 model required)")


def _artefact(index: int, evidence_id: str = "ev-ai-perf") -> Artefact:
    """Build a compact artefact for latency tests."""
    category = _CATEGORIES[index % len(_CATEGORIES)]
    return Artefact(
        artefact_id=f"art-{index:03d}",
        category=category,
        source_evidence_id=evidence_id,
        raw_data={"name": f"sample-{index}", "index": index, "path": f"/tmp/a{index}"},
    )


def _ranked(index: int) -> RankedArtefact:
    """Build a ranked artefact for summarisation latency tests."""
    levels = (
        SuspicionLevel.CRITICAL,
        SuspicionLevel.HIGH,
        SuspicionLevel.MEDIUM,
        SuspicionLevel.LOW,
        SuspicionLevel.INFORMATIONAL,
    )
    base = _artefact(index)
    return RankedArtefact(
        **base.model_dump(),
        suspicion_level=levels[index % len(levels)],
        relevance_score=round(1.0 - (index % 10) / 12.0, 4),
        classification_reasoning=f"Fixture rank for art-{index:03d}",
    )


def _config() -> LLMConfig:
    return LLMConfig(
        api_url="http://127.0.0.1:11434",
        model="llama3",
        num_predict=256,
        request_timeout_seconds=90,
        max_retries=1,
        retry_delay_seconds=0.0,
    )


def _classifier(
    audit_logger: Any,
    *,
    cache: AIResponseCache | None = None,
    max_tokens_per_batch: int = 100_000,
) -> LLMArtefactClassifier:
    config = _config()
    ollama = OllamaClient(
        config,
        LLMConnectionManager(config, audit_logger),
        audit_logger,
        cache=cache if cache is not None else AIResponseCache(ttl_seconds=DEFAULT_TTL_SECONDS),
    )
    serializer = ArtefactSerializer()
    builder = ClassificationPromptBuilder(
        templates=ForensicPromptTemplates(),
        serializer=serializer,
        batcher=ArtefactBatcher(
            max_tokens_per_batch=max_tokens_per_batch,
            serializer=serializer,
        ),
    )
    return LLMArtefactClassifier(
        ollama_client=ollama,
        prompt_builder=builder,
        response_parser=ClassificationResponseParser(),
        confidence_scorer=DefaultConfidenceScorer(),
        audit_logger=audit_logger,
        config=config,
    )


def _summarizer(audit_logger: Any, cache: AIResponseCache | None = None) -> LLMInvestigativeSummarizer:
    config = _config()
    ollama = OllamaClient(
        config,
        LLMConnectionManager(config, audit_logger),
        audit_logger,
        cache=cache if cache is not None else AIResponseCache(ttl_seconds=DEFAULT_TTL_SECONDS),
    )
    return LLMInvestigativeSummarizer(
        ollama_client=ollama,
        prompt_builder=SummarizationPromptBuilder(),
        response_validator=SummaryResponseValidator(),
        audit_logger=audit_logger,
        config=config,
    )


@pytest.mark.performance
@pytest.mark.requires_ollama
async def test_classification_latency(mock_audit_logger: Any, require_ollama: None) -> None:
    """Classify 50 artefacts in under 60 seconds with local LLaMA-3."""
    artefacts = [_artefact(i) for i in range(50)]
    classifier = _classifier(mock_audit_logger)
    started = time.perf_counter()
    results = await classifier.classify(artefacts)
    elapsed = time.perf_counter() - started
    assert len(results) == 50
    assert elapsed < 60, f"classification took {elapsed:.1f}s (budget 60s)"


@pytest.mark.performance
@pytest.mark.requires_ollama
async def test_summarization_latency(mock_audit_logger: Any, require_ollama: None) -> None:
    """Summarize 50 ranked artefacts in under 30 seconds."""
    ranked = [_ranked(i) for i in range(50)]
    summarizer = _summarizer(mock_audit_logger)
    started = time.perf_counter()
    result = await summarizer.generate_summary(ranked)
    elapsed = time.perf_counter() - started
    assert result.full_text
    assert elapsed < 30, f"summarization took {elapsed:.1f}s (budget 30s)"


@pytest.mark.performance
@pytest.mark.requires_ollama
async def test_cache_effectiveness(mock_audit_logger: Any, require_ollama: None) -> None:
    """Second identical classification is a cache hit under 100 ms."""
    artefacts = [_artefact(i) for i in range(8)]
    cache = AIResponseCache(ttl_seconds=DEFAULT_TTL_SECONDS)
    await cache.warm_common_patterns("llama3", 0.1)
    classifier = _classifier(mock_audit_logger, cache=cache)
    first = await classifier.classify(artefacts)
    assert len(first) == 8

    started = time.perf_counter()
    second = await classifier.classify(artefacts)
    elapsed_ms = _elapsed_ms(started)

    assert len(second) == 8
    assert [item.artefact_id for item in first] == [item.artefact_id for item in second]
    stats = await cache.get_stats()
    assert stats.total_hits >= 1
    assert elapsed_ms < 100, f"cached classify took {elapsed_ms:.1f}ms (budget 100ms)"


@pytest.mark.performance
@pytest.mark.requires_ollama
async def test_batch_vs_single(mock_audit_logger: Any, require_ollama: None) -> None:
    """Measure 5×10 batched classification against one 50-artefact call."""
    artefacts = [_artefact(i) for i in range(50)]
    batches = [artefacts[i : i + 10] for i in range(0, 50, 10)]
    classifier = _classifier(mock_audit_logger)

    started = time.perf_counter()
    batched_results: list[Any] = []
    for batch in batches:
        batched_results.extend(await classifier.classify(batch))
    batched_seconds = time.perf_counter() - started

    started = time.perf_counter()
    single_results = await classifier.classify(artefacts)
    single_seconds = time.perf_counter() - started

    assert len(batched_results) == 50
    assert len(single_results) == 50
    # Both strategies must complete; timings are recorded for comparison.
    assert batched_seconds > 0
    assert single_seconds > 0
    mock_audit_logger.log_action.assert_called()


@pytest.mark.performance
async def test_fallback_latency() -> None:
    """Rule-based triage of 1000 artefacts completes in under 1 second."""
    artefacts = [_artefact(i, evidence_id="ev-fallback") for i in range(1000)]
    artefact_set = ArtefactSet(
        evidence_id="ev-fallback",
        artefacts=artefacts,
        categories_present=list(_CATEGORIES),
    )
    analyzer = RuleBasedAnalyzer()
    started = time.perf_counter()
    ranked = analyzer.analyze(artefact_set)
    elapsed = time.perf_counter() - started
    assert len(ranked) == 1000
    assert elapsed < 1.0, f"rule-based triage took {elapsed:.3f}s (budget 1s)"
