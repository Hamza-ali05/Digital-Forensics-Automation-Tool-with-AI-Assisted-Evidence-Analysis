#!/usr/bin/env python3
"""Verify Prompt 11 dataset intelligence, knowledge, ML, and threat-intel components."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _record(results: list[str], ok: bool, message: str) -> None:
    results.append(f"{'[PASS]' if ok else '[FAIL]'} {message}")
    if not ok:
        raise AssertionError(message)


async def verify_dataset_intelligence(results: list[str]) -> None:
    from dfat.dataset_intelligence.classifier import DatasetClassifier
    from dfat.dataset_intelligence.enums import DatasetCategory, DatasetFormat, DatasetStatus
    from dfat.dataset_intelligence.models import DatasetRecord
    from dfat.dataset_intelligence.scanner import DatasetScanner

    _record(results, hasattr(DatasetScanner, "scan"), "DatasetScanner.scan exists")
    _record(results, hasattr(DatasetClassifier, "classify"), "DatasetClassifier.classify exists")

    classifier = DatasetClassifier()
    sample = DatasetRecord(
        name="dfrws.json",
        file_path=Path("/datasets/dfrws/challenge.json"),
        category=DatasetCategory.USER_UPLOADED,
        format=DatasetFormat.JSON,
        status=DatasetStatus.DISCOVERED,
        file_size_bytes=10,
        hash_sha256="a" * 64,
        parent_directory="/datasets/dfrws",
    )
    classified = classifier.classify(sample)
    _record(results, classified.category == DatasetCategory.BENCHMARK, "Classifier maps DFRWS datasets")


async def verify_knowledge(results: list[str]) -> None:
    from dfat.knowledge.embeddings import LocalEmbeddingEngine
    from dfat.knowledge.indexer import DocumentIndexer
    from dfat.knowledge.ioc_database import IOCKnowledgeBase
    from dfat.knowledge.retriever import UnifiedRetriever
    from dfat.knowledge.vector_store import ForensicVectorStore

    _record(results, hasattr(LocalEmbeddingEngine, "embed_text"), "LocalEmbeddingEngine.embed_text exists")
    _record(results, hasattr(ForensicVectorStore, "add_documents"), "ForensicVectorStore.add_documents exists")
    _record(results, hasattr(IOCKnowledgeBase, "search"), "IOCKnowledgeBase.search exists")
    _record(results, hasattr(UnifiedRetriever, "retrieve"), "UnifiedRetriever.retrieve exists")
    _record(results, hasattr(DocumentIndexer, "index_dataset"), "DocumentIndexer.index_dataset exists")


async def verify_rag(results: list[str]) -> None:
    from dfat.knowledge.rag.context_builder import RAGContextBuilder
    from dfat.knowledge.rag.rag_analyzer import RAGEnhancedAnalyzer

    _record(results, hasattr(RAGContextBuilder, "build_classification_context_with_sources"), "RAG context builder exists")
    _record(results, hasattr(RAGEnhancedAnalyzer, "analyze_async"), "RAGEnhancedAnalyzer.analyze_async exists")


async def verify_ml(results: list[str]) -> None:
    from dfat.ml.feature_engineering import ForensicFeatureExtractor
    from dfat.ml.model_registry import ModelRegistry
    from dfat.ml.predictor import MLPredictor
    from dfat.ml.trainer import ModelTrainer

    _record(results, hasattr(ForensicFeatureExtractor, "extract_all"), "ForensicFeatureExtractor.extract_all exists")
    _record(results, hasattr(ModelTrainer, "train"), "ModelTrainer.train exists")
    _record(results, hasattr(ModelRegistry, "register"), "ModelRegistry.register exists")
    _record(results, hasattr(MLPredictor, "predict"), "MLPredictor.predict exists")


async def verify_threat_intel(results: list[str]) -> None:
    from dfat.threat_intel.feed_manager import ThreatFeedManager
    from dfat.threat_intel.mitre_mapper import MITREMapper
    from dfat.threat_intel.sigma_engine import SigmaEngine
    from dfat.threat_intel.yara_engine import YARAEngine

    _record(results, hasattr(YARAEngine, "scan_artefact"), "YARAEngine.scan_artefact exists")
    _record(results, hasattr(SigmaEngine, "match_process"), "SigmaEngine.match_process exists")
    _record(results, hasattr(MITREMapper, "map_artefact"), "MITREMapper.map_artefact exists")
    _record(results, hasattr(ThreatFeedManager, "scan_artefacts_against_intel"), "ThreatFeedManager scan exists")


async def verify_research_objectives(results: list[str]) -> None:
    """Re-run the frozen RQ1-RQ5 verifier as a subprocess (same as make verify-rqs)."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(REPO_ROOT / "scripts" / "verify_research_objectives.py"),
        cwd=str(REPO_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    text = (stdout or b"").decode("utf-8", errors="replace")
    passed = proc.returncode == 0 and "OVERALL: PASS" in text
    _record(results, passed, "Existing research objectives RQ1-RQ5 still pass")


async def main() -> int:
    results: list[str] = []
    print("DFAT Prompt 11 Dataset Intelligence Verification")
    print("=" * 72)
    try:
        await verify_dataset_intelligence(results)
        await verify_knowledge(results)
        await verify_rag(results)
        await verify_ml(results)
        await verify_threat_intel(results)
        await verify_research_objectives(results)
    except AssertionError:
        pass

    for line in results:
        print(f"  {line}")

    passed = all(line.startswith("[PASS]") for line in results)
    summary = {
        "passed": passed,
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": results,
    }
    reports = REPO_ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "dataset_intelligence_verification.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print("=" * 72)
    print(f"OVERALL: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
