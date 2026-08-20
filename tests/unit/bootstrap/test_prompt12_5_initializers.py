"""Unit tests for Prompt 12.5 initializers (dataset, knowledge, AI, threat-intel, evaluation)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dfat.bootstrap.ai_initializer import AIInitializer
from dfat.bootstrap.dataset_initializer import DatasetInitializer
from dfat.bootstrap.evaluation_initializer import EvaluationInitializer
from dfat.bootstrap.knowledge_initializer import KnowledgeInitializer
from dfat.bootstrap.models import InitPhase, InitStatus
from dfat.bootstrap.threat_intel_initializer import ThreatIntelInitializer
from dfat.settings import load_settings


def _settings():
    return load_settings(env="development")


# --- DatasetInitializer ---


@pytest.mark.asyncio
async def test_dataset_initializer_empty_directory() -> None:
    mock_registry = AsyncMock()
    scan_result = MagicMock()
    scan_result.datasets = []
    scan_result.new_count = 0
    scan_result.updated_count = 0
    scan_result.failed_count = 0
    scan_result.scan_path = "/data/datasets"
    mock_registry.register_all.return_value = scan_result

    result = await DatasetInitializer(mock_registry, _settings()).initialize()

    assert result.phase == InitPhase.DATASET_DISCOVERY
    assert result.status == InitStatus.COMPLETED
    assert result.details["total_discovered"] == 0


@pytest.mark.asyncio
async def test_dataset_initializer_exception_degrades() -> None:
    mock_registry = AsyncMock()
    mock_registry.register_all.side_effect = RuntimeError("scan failed")

    result = await DatasetInitializer(mock_registry, _settings()).initialize()

    assert result.status == InitStatus.DEGRADED
    assert "dataset_discovery" in result.degraded_capabilities


# --- KnowledgeInitializer ---


@pytest.mark.asyncio
async def test_knowledge_initializer_completes_with_mocks() -> None:
    vs = MagicMock()
    ee = MagicMock(_model_name="all-MiniLM-L6-v2")
    indexer = MagicMock()
    ioc_kb = MagicMock()
    ioc_kb.get_statistics.return_value = {"total_count": 42}
    graph = MagicMock(_graph=MagicMock(nodes=[1, 2, 3]))

    with patch("dfat.bootstrap.knowledge_initializer.chromadb", create=True):
        result = await KnowledgeInitializer(vs, ee, indexer, ioc_kb, graph, _settings()).initialize()

    assert result.phase == InitPhase.KNOWLEDGE_BASE
    assert result.status == InitStatus.COMPLETED
    assert result.details["embedding_model"] == "all-MiniLM-L6-v2"


@pytest.mark.asyncio
async def test_knowledge_initializer_degrades_without_chromadb() -> None:
    vs = MagicMock()
    ee = MagicMock(_model_name="test")
    indexer = MagicMock()
    ioc_kb = MagicMock()
    ioc_kb.get_statistics.return_value = {"total_count": 0}
    graph = MagicMock(_graph=MagicMock(nodes=[]))

    with patch.dict("sys.modules", {"chromadb": None}):
        result = await KnowledgeInitializer(vs, ee, indexer, ioc_kb, graph, _settings()).initialize()

    assert result.status == InitStatus.DEGRADED
    assert "vector_store" in result.degraded_capabilities


# --- AIInitializer ---


@pytest.mark.asyncio
async def test_ai_initializer_ollama_healthy() -> None:
    llm = AsyncMock()
    health = MagicMock(is_healthy=True, model_name="llama3", response_time_ms=200.0, error=None)
    llm.check_health.return_value = health
    rag = MagicMock(_retriever=MagicMock(), _context_builder=MagicMock())
    rule_based = MagicMock()
    predictor = MagicMock()
    registry = MagicMock()
    registry.list_models.return_value = [
        MagicMock(model_name="MalwareClassifier", version="1"),
    ]
    retrainer = MagicMock(_settings=MagicMock())

    result = await AIInitializer(
        llm, rag, rule_based, predictor, registry, retrainer, _settings()
    ).initialize()

    assert result.phase == InitPhase.LLM_SERVICE
    assert result.status == InitStatus.COMPLETED
    assert result.details["capabilities"]["llm"] is True
    assert result.details["capabilities"]["rag"] is True
    assert result.details["capabilities"]["ml"] is True
    assert result.details["capabilities"]["fallback"] is True


@pytest.mark.asyncio
async def test_ai_initializer_ollama_unhealthy_degrades() -> None:
    llm = AsyncMock()
    health = MagicMock(is_healthy=False, model_name="", response_time_ms=0, error="refused")
    llm.check_health.return_value = health

    result = await AIInitializer(
        llm, None, MagicMock(), None, None, None, _settings()
    ).initialize()

    assert result.status == InitStatus.DEGRADED
    assert "llm_service" in result.degraded_capabilities
    assert result.details["capabilities"]["fallback"] is True


# --- ThreatIntelInitializer ---


@pytest.mark.asyncio
async def test_threat_intel_loads_rules(tmp_path: Path) -> None:
    yara_engine = MagicMock()
    yara_engine.load_rules.return_value = 3
    sigma_engine = MagicMock()
    sigma_engine.load_rules.return_value = 5
    mitre = MagicMock(_techniques={"T1055": {}, "T1547": {}})

    result = await ThreatIntelInitializer(
        MagicMock(), yara_engine, sigma_engine, mitre, _settings()
    ).initialize()

    assert result.phase == InitPhase.THREAT_INTELLIGENCE
    assert result.status == InitStatus.COMPLETED
    assert result.details["yara_rules_loaded"] == 3
    assert result.details["sigma_rules_loaded"] == 5


@pytest.mark.asyncio
async def test_threat_intel_degrades_without_rules() -> None:
    yara_engine = MagicMock()
    yara_engine.load_rules.return_value = 0
    sigma_engine = MagicMock()
    sigma_engine.load_rules.return_value = 0
    mitre = MagicMock(_techniques={})

    result = await ThreatIntelInitializer(
        MagicMock(), yara_engine, sigma_engine, mitre, _settings()
    ).initialize()

    assert result.status == InitStatus.DEGRADED
    assert "yara_rules" in result.degraded_capabilities
    assert "sigma_rules" in result.degraded_capabilities


# --- EvaluationInitializer ---


@pytest.mark.asyncio
async def test_evaluation_reports_available_datasets() -> None:
    loader = MagicMock()
    loader.list_all_datasets.return_value = {
        "dfrws": ["dfrws-2024-challenge"],
        "cfreds": [],
    }

    result = await EvaluationInitializer(loader, _settings()).initialize()

    assert result.phase == InitPhase.EVALUATION
    assert result.status == InitStatus.COMPLETED
    assert result.details["total_available"] == 1


@pytest.mark.asyncio
async def test_evaluation_degrades_when_no_datasets() -> None:
    loader = MagicMock()
    loader.list_all_datasets.return_value = {"dfrws": [], "cfreds": []}

    result = await EvaluationInitializer(loader, _settings()).initialize()

    assert result.status == InitStatus.DEGRADED
    assert "benchmark_datasets" in result.degraded_capabilities
