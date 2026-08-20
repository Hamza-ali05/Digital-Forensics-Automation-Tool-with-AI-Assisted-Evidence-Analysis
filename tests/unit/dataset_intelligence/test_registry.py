"""Unit tests for DatasetRegistry."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.dataset_intelligence.enums import DatasetCategory, DatasetFormat, DatasetStatus
from dfat.dataset_intelligence.exceptions import DatasetNotFoundError
from dfat.dataset_intelligence.models import DatasetRecord, DatasetScanResult
from dfat.dataset_intelligence.registry import DatasetRegistry


def _dataset(dataset_id: str = "ds-1", hash_sha256: str = "a" * 64) -> DatasetRecord:
    return DatasetRecord(
        dataset_id=dataset_id,
        name="sample.csv",
        file_path=Path("/data/sample.csv"),
        category=DatasetCategory.USER_UPLOADED,
        format=DatasetFormat.CSV,
        status=DatasetStatus.DISCOVERED,
        file_size_bytes=10,
        hash_sha256=hash_sha256,
        parent_directory="/data",
    )


@pytest.fixture
def registry() -> DatasetRegistry:
    repo = AsyncMock()
    repo.get_by_hash = AsyncMock(return_value=None)
    repo.save = AsyncMock()
    repo.get = AsyncMock()
    repo.update_file_timestamps = AsyncMock()
    repo.soft_delete = AsyncMock(return_value=True)
    scanner = AsyncMock()
    scanner.scan = AsyncMock(
        return_value=DatasetScanResult(
            scan_path=Path("/data"),
            discovered_count=1,
            new_count=1,
            updated_count=0,
            failed_count=0,
            duration_seconds=0.1,
            datasets=[_dataset()],
        )
    )
    classifier = MagicMock()
    classifier.classify = MagicMock(side_effect=lambda item: item)
    validator = AsyncMock()
    validator.validate = AsyncMock(side_effect=lambda item: item)
    preprocessor = AsyncMock()
    preprocessor.preprocess = AsyncMock(side_effect=lambda item: item)
    audit = AsyncMock()
    audit.log_action = AsyncMock()
    return DatasetRegistry(repo, scanner, classifier, validator, preprocessor, audit)


@pytest.mark.asyncio
async def test_register_all_persists_new_dataset(registry: DatasetRegistry) -> None:
    result = await registry.register_all()

    assert result.new_count == 1
    registry._dataset_repo.save.assert_awaited_once()
    registry._classifier.classify.assert_called()
    registry._validator.validate.assert_awaited()
    registry._preprocessor.preprocess.assert_awaited()


@pytest.mark.asyncio
async def test_register_all_skips_duplicate_hash(registry: DatasetRegistry) -> None:
    existing = _dataset(dataset_id="existing")
    registry._dataset_repo.get_by_hash = AsyncMock(return_value=existing)

    result = await registry.register_all()

    assert result.updated_count == 1
    assert result.new_count == 0
    registry._dataset_repo.save.assert_not_awaited()
    registry._dataset_repo.update_file_timestamps.assert_awaited()


@pytest.mark.asyncio
async def test_get_dataset_missing_raises(registry: DatasetRegistry) -> None:
    registry._dataset_repo.get = AsyncMock(return_value=None)
    with pytest.raises(DatasetNotFoundError):
        await registry.get_dataset("missing-id")


@pytest.mark.asyncio
async def test_remove_dataset_soft_deletes(registry: DatasetRegistry) -> None:
    record = _dataset()
    registry._dataset_repo.get = AsyncMock(return_value=record)

    await registry.remove_dataset(record.dataset_id)

    registry._dataset_repo.soft_delete.assert_awaited_once_with(record.dataset_id)
