"""LLM-independent AI quality tests for parsing, scoring, and hallucination."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.ai_engine.caching import AIResponseCache, DEFAULT_TTL_SECONDS
from dfat.ai_engine.classification import (
    ClassificationPromptBuilder,
    ClassificationResponseParser,
    DefaultConfidenceScorer,
    LLMArtefactClassifier,
)
from dfat.ai_engine.classification.models import ClassificationResult
from dfat.ai_engine.explanation.confidence import ConfidenceScorer
from dfat.ai_engine.llm.client import LLMResponse
from dfat.ai_engine.llm.config import LLMConfig, PROMPT_VERSION
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.optimization import PromptOptimizer
from dfat.ai_engine.preprocessing import ArtefactBatcher, ArtefactSerializer
from dfat.ai_engine.validation import HallucinationGuard
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.forensic_engine.processing.ioc_detector import IOCMatch
from dfat.forensic_engine.processing.relationship_mapper import RelationshipMap
from dfat.forensic_engine.triage.scoring import ScoringEngine

_VALID_IDS = ("art-crit-001", "art-high-001", "art-info-001")


def _predefined_artefacts() -> list[Artefact]:
    """Return a fixed artefact set with expected suspicion characteristics."""
    return [
        Artefact(
            artefact_id=_VALID_IDS[0],
            category=ArtefactCategory.INJECTED_CODE,
            source_evidence_id="ev-quality",
            raw_data={
                "process_name": "malware.exe",
                "protection": "RWX",
                "mz_header": True,
                "suspicious_indicators": ["MZ", "RWX"],
            },
        ),
        Artefact(
            artefact_id=_VALID_IDS[1],
            category=ArtefactCategory.NETWORK_CONNECTION,
            source_evidence_id="ev-quality",
            raw_data={
                "remote_address": "203.0.113.9",
                "remote_port": 4444,
                "protocol": "tcp",
            },
        ),
        Artefact(
            artefact_id=_VALID_IDS[2],
            category=ArtefactCategory.FILESYSTEM_METADATA,
            source_evidence_id="ev-quality",
            raw_data={"path": "/Windows/Temp/readme.txt", "size": 128},
        ),
    ]


_CANNED_CLASSIFICATION = """[
  {
    "artefact_id": "art-crit-001",
    "suspicion_level": "CRITICAL",
    "reasoning": "Artefact art-crit-001 shows an RWX region with an MZ header consistent with injected code.",
    "ioc_indicators": ["MZ header", "RWX"]
  },
  {
    "artefact_id": "art-high-001",
    "suspicion_level": "HIGH",
    "reasoning": "Artefact art-high-001 opened a TCP session to 203.0.113.9:4444, a common C2 port.",
    "ioc_indicators": ["203.0.113.9:4444"]
  },
  {
    "artefact_id": "art-info-001",
    "suspicion_level": "INFORMATIONAL",
    "reasoning": "Artefact art-info-001 is a small Temp readme without indicators of compromise.",
    "ioc_indicators": []
  }
]
"""


def _cached_classifier(audit_logger: MagicMock, cache: AIResponseCache) -> LLMArtefactClassifier:
    generate_calls = {"n": 0}

    async def _generate(prompt: str, system: str | None = None, temperature: float | None = None) -> LLMResponse:
        temp = 0.1 if temperature is None else temperature
        cached = await cache.get(prompt, "llama3", temp)
        if cached is not None:
            return cached.response
        generate_calls["n"] += 1
        response = LLMResponse(text=_CANNED_CLASSIFICATION, model="llama3")
        await cache.put(prompt, "llama3", temp, response)
        return response

    ollama = MagicMock()
    ollama.generate = AsyncMock(side_effect=_generate)
    ollama.generate_calls = generate_calls
    serializer = ArtefactSerializer()
    return LLMArtefactClassifier(
        ollama_client=ollama,
        prompt_builder=ClassificationPromptBuilder(
            templates=ForensicPromptTemplates(),
            serializer=serializer,
            batcher=ArtefactBatcher(max_tokens_per_batch=8000, serializer=serializer),
        ),
        response_parser=ClassificationResponseParser(),
        confidence_scorer=DefaultConfidenceScorer(),
        audit_logger=audit_logger,
        config=LLMConfig(model="llama3", temperature=0.1),
    )


@pytest.mark.quality
async def test_classification_consistency(mock_audit_logger: MagicMock) -> None:
    """Same artefacts yield the same classifications after a cache hit."""
    artefacts = _predefined_artefacts()
    cache = AIResponseCache(ttl_seconds=DEFAULT_TTL_SECONDS)
    classifier = _cached_classifier(mock_audit_logger, cache)

    first = await classifier.classify(artefacts)
    second = await classifier.classify(artefacts)

    assert len(first) == len(second) == 3
    assert [item.model_dump() for item in first] == [item.model_dump() for item in second]
    assert all(item.prompt_version == PROMPT_VERSION for item in first)
    assert first[0].suspicion_level is SuspicionLevel.CRITICAL
    stats = await cache.get_stats()
    assert stats.total_hits >= 1
    assert classifier._ollama.generate_calls["n"] == 1  # type: ignore[attr-defined]


@pytest.mark.quality
def test_scoring_consistency() -> None:
    """Rule-based scores are deterministic for the same artefact set."""
    artefacts = _predefined_artefacts()
    artefact_set = ArtefactSet(
        evidence_id="ev-quality",
        artefacts=artefacts,
        categories_present=[item.category for item in artefacts],
    )
    iocs = [
        IOCMatch(
            artefact_id=_VALID_IDS[0],
            ioc_type="process",
            indicator="malware.exe",
            confidence="high",
            description="injected binary",
            matched_rule="quality.injected_mz",
        )
    ]
    graph = RelationshipMap()
    engine = ScoringEngine()
    first = engine.score(artefact_set, iocs, graph)
    second = engine.score(artefact_set, iocs, graph)
    assert [(item.artefact.artefact_id, item.score, item.suspicion_level) for item in first] == [
        (item.artefact.artefact_id, item.score, item.suspicion_level)
        for item in second
    ]
    by_id = {item.artefact.artefact_id: item for item in first}
    assert by_id[_VALID_IDS[0]].score > by_id[_VALID_IDS[2]].score


@pytest.mark.quality
def test_confidence_calibration() -> None:
    """Specific, ID-referenced reasoning scores higher than vague output."""
    scorer = ConfidenceScorer()
    artefact = _predefined_artefacts()[0]
    high_quality = ClassificationResult(
        artefact_id=artefact.artefact_id,
        suspicion_level=SuspicionLevel.CRITICAL,
        reasoning=(
            "Artefact art-crit-001 contains an MZ header in an RWX VAD region, "
            "which is a strong injected-code indicator."
        ),
        ioc_indicators=["MZ header", "RWX"],
        raw_llm_response=_CANNED_CLASSIFICATION,
        prompt_version=PROMPT_VERSION,
    )
    vague = ClassificationResult(
        artefact_id=artefact.artefact_id,
        suspicion_level=SuspicionLevel.INFORMATIONAL,
        reasoning="Maybe bad [UNCERTAIN].",
        ioc_indicators=[],
        prompt_version=PROMPT_VERSION,
    )
    high_score = scorer.score_classification(high_quality, artefact)
    low_score = scorer.score_classification(vague, artefact)
    assert high_score > 0.6
    assert low_score < 0.5
    assert high_score > low_score


@pytest.mark.quality
def test_hallucination_detection_accuracy() -> None:
    """Known fabricated artefact IDs are detected at greater than 90% recall."""
    guard = HallucinationGuard(
        valid_artefact_ids=set(_VALID_IDS),
        valid_categories={item.value for item in ArtefactCategory},
        valid_suspicion_levels={item.value for item in SuspicionLevel},
        known_facts={"203.0.113.9"},
    )
    injected = [f"art-hall-{index:02d}" for index in range(20)]
    detected = 0
    for fake_id in injected:
        report = guard.check_response(
            f"Artefact {fake_id} is definitely linked to {_VALID_IDS[0]} via injection."
        )
        if fake_id in report.hallucinated_ids:
            detected += 1
    recall = detected / len(injected)
    assert recall > 0.9, f"hallucinated-id recall was {recall:.2f} (need > 0.90)"


@pytest.mark.quality
def test_prompt_optimizer_fits_context_window() -> None:
    """Optimized prompts stay within the requested token budget."""
    artefacts = _predefined_artefacts()
    serializer = ArtefactSerializer()
    raw = serializer.serialize_for_classification(artefacts)
    bloated = raw + "\n" + "\n".join(
        f"[art-pad-{i}] filesystem_metadata | blob={'y' * 200} suspicion_level=informational"
        for i in range(40)
    )
    prompt = ForensicPromptTemplates().render("classification", artefact_text=bloated)
    optimizer = PromptOptimizer()
    budget = 250
    fitted = optimizer.optimize_for_context_window(prompt, max_tokens=budget)
    assert optimizer.estimate_tokens(fitted) <= budget
    assert "Do not fabricate" in fitted
    assert "art-crit-001" in fitted
