"""Integration tests for dataset intelligence pipeline stages."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.dataset_intelligence.classifier import DatasetClassifier
from dfat.dataset_intelligence.config import DatasetIntelligenceSettings
from dfat.dataset_intelligence.enums import DatasetCategory, DatasetFormat, DatasetStatus
from dfat.dataset_intelligence.models import DatasetRecord
from dfat.dataset_intelligence.registry import DatasetRegistry
from dfat.dataset_intelligence.scanner import DatasetScanner
from dfat.knowledge.indexer import DocumentIndexer


@pytest.fixture
def dataset_dir(tmp_path: Path) -> Path:
    root = tmp_path / "datasets"
    target = root / "intel" / "ioc_feed.csv"
    target.parent.mkdir(parents=True)
    target.write_text("ioc_type,value\nhash,deadbeef\n", encoding="utf-8")
    return root


@pytest.mark.asyncio
async def test_scan_classify_validate_preprocess_chain(dataset_dir: Path) -> None:
    settings = DatasetIntelligenceSettings(datasets_dir=dataset_dir, max_dataset_size_gb=1.0)
    audit = AsyncMock()
    audit.log_action = AsyncMock()
    mime = MagicMock()
    mime.identify = MagicMock(return_value=("text/csv", "extension"))
    scanner = DatasetScanner(settings, audit, mime)
    classifier = DatasetClassifier()
    validator = AsyncMock()
    validator.validate = AsyncMock(side_effect=lambda item: item)
    preprocessor = AsyncMock()
    preprocessor.preprocess = AsyncMock(
        side_effect=lambda item: item.model_copy(update={"status": DatasetStatus.READY})
    )

    scan_result = await scanner.scan()
    assert scan_result.discovered_count == 1
    classified = classifier.classify(scan_result.datasets[0])
    validated = await validator.validate(classified)
    processed = await preprocessor.preprocess(validated)

    assert processed.format == DatasetFormat.CSV
    assert processed.status == DatasetStatus.READY


@pytest.mark.asyncio
async def test_registry_register_all_persists_discovered_dataset(dataset_dir: Path) -> None:
    settings = DatasetIntelligenceSettings(datasets_dir=dataset_dir, max_dataset_size_gb=1.0)
    audit = AsyncMock()
    audit.log_action = AsyncMock()
    mime = MagicMock()
    mime.identify = MagicMock(return_value=("text/csv", "extension"))
    scanner = DatasetScanner(settings, audit, mime)
    classifier = DatasetClassifier()
    validator = AsyncMock()
    validator.validate = AsyncMock(side_effect=lambda item: item)
    preprocessor = AsyncMock()
    preprocessor.preprocess = AsyncMock(side_effect=lambda item: item)
    repo = AsyncMock()
    repo.get_by_hash = AsyncMock(return_value=None)
    repo.save = AsyncMock()

    registry = DatasetRegistry(repo, scanner, classifier, validator, preprocessor, audit)
    result = await registry.register_all()

    assert result.new_count == 1
    repo.save.assert_awaited_once()
    saved_record = repo.save.await_args.args[0]
    assert saved_record.category in {
        DatasetCategory.THREAT_INTELLIGENCE,
        DatasetCategory.USER_UPLOADED,
        DatasetCategory.MACHINE_LEARNING,
    }


@pytest.mark.asyncio
async def test_index_dataset_writes_to_knowledge_collection(tmp_path: Path) -> None:
    csv_path = tmp_path / "ioc_feed.csv"
    csv_path.write_text("ioc_type,value,description\nhash,abc123,malware hash\n", encoding="utf-8")
    dataset = DatasetRecord(
        dataset_id="ds-index",
        name="ioc_feed.csv",
        file_path=csv_path,
        category=DatasetCategory.THREAT_INTELLIGENCE,
        format=DatasetFormat.CSV,
        status=DatasetStatus.READY,
        file_size_bytes=csv_path.stat().st_size,
        hash_sha256="d" * 64,
        parent_directory=str(tmp_path),
    )
    vector_store = AsyncMock()
    vector_store.add_documents = AsyncMock()
    embedding = MagicMock()
    audit = AsyncMock()
    audit.log_action = AsyncMock()
    indexer = DocumentIndexer(embedding, vector_store, audit)

    result = await indexer.index_dataset(dataset)

    assert result.documents_indexed >= 1
    assert result.collection == "threat_intel"
    vector_store.add_documents.assert_awaited_once()
    audit.log_action.assert_awaited()
