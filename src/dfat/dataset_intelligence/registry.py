"""Dataset registry orchestration over scanning, enrichment, and persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from dfat.core.enums import PipelineStage
from dfat.dataset_intelligence.enums import DatasetCategory, DatasetStatus
from dfat.dataset_intelligence.exceptions import DatasetNotFoundError
from dfat.dataset_intelligence.models import DatasetRecord, DatasetScanResult
from dfat.database.repositories.dataset_repo import DatasetRepository


class DatasetRegistry:
    """Persist and refresh dataset intelligence records."""

    def __init__(
        self,
        dataset_repo: DatasetRepository,
        scanner,
        classifier,
        validator,
        preprocessor,
        audit_service,
    ) -> None:
        self._dataset_repo = dataset_repo
        self._scanner = scanner
        self._classifier = classifier
        self._validator = validator
        self._preprocessor = preprocessor
        self._audit_service = audit_service

    async def register_all(self, scan_path: Optional[Path] = None) -> DatasetScanResult:
        """Scan, classify, validate, preprocess, and persist discovered datasets."""
        scan_result = await self._scanner.scan(scan_path)
        persisted: list[DatasetRecord] = []
        skipped_duplicates = 0

        for dataset in scan_result.datasets:
            existing = await self._dataset_repo.get_by_hash(dataset.hash_sha256)
            if existing is not None:
                skipped_duplicates += 1
                await self._dataset_repo.update_file_timestamps(
                    existing.dataset_id,
                    last_seen_at=datetime.now(UTC),
                    file_modified_at=self._file_modified_at(dataset.file_path),
                )
                persisted.append(existing)
                continue

            processed = await self._process_dataset(dataset)
            await self._dataset_repo.save(processed)
            persisted.append(processed)

        result = scan_result.model_copy(update={  # type: ignore[call-arg]
            "datasets": persisted,
            "new_count": max(len(persisted) - skipped_duplicates, 0),
            "updated_count": skipped_duplicates,
        })
        await self._audit_service.log_action(
            stage=PipelineStage.EVALUATION,
            action="DATASET_REGISTER_ALL_COMPLETED",
            evidence_id="dataset_registry",
            details={
                "scan_path": str(scan_result.scan_path),
                "persisted_count": len(persisted),
                "new_count": result.new_count,
                "updated_count": result.updated_count,
                "failed_count": result.failed_count,
            },
        )
        return result

    async def register_single(self, file_path: Path) -> DatasetRecord:
        """Register a single dataset file."""
        scanned = await self._scanner.scan_single(file_path)
        existing = await self._dataset_repo.get_by_hash(scanned.hash_sha256)
        if existing is not None:
            await self._dataset_repo.update_file_timestamps(
                existing.dataset_id,
                last_seen_at=datetime.now(UTC),
                file_modified_at=self._file_modified_at(existing.file_path),
            )
            return existing

        processed = await self._process_dataset(scanned)
        await self._dataset_repo.save(processed)
        await self._audit_service.log_action(
            stage=PipelineStage.EVALUATION,
            action="DATASET_REGISTERED",
            evidence_id=processed.dataset_id,
            details={"file_path": str(processed.file_path), "hash_sha256": processed.hash_sha256},
        )
        return processed

    async def get_dataset(self, dataset_id: str) -> DatasetRecord:
        """Return a dataset by identifier."""
        dataset = await self._dataset_repo.get(dataset_id)
        if dataset is None:
            raise DatasetNotFoundError(f"Dataset not found: {dataset_id}")
        return dataset

    async def list_datasets(
        self,
        category: Optional[DatasetCategory] = None,
        status: Optional[DatasetStatus] = None,
    ) -> list[DatasetRecord]:
        """List datasets with optional category/status filters."""
        return await self._dataset_repo.list_datasets(category=category, status=status)

    async def get_statistics(self) -> dict[str, object]:
        """Return aggregate dataset statistics."""
        return await self._dataset_repo.get_statistics()

    async def refresh_dataset(self, dataset_id: str) -> DatasetRecord:
        """Re-scan, re-validate, and re-preprocess a persisted dataset."""
        current = await self.get_dataset(dataset_id)
        rescanned = await self._scanner.scan_single(current.file_path)
        rescanned.dataset_id = current.dataset_id
        rescanned.discovered_at = current.discovered_at
        rescanned.update_history = [
            *current.update_history,
            {
                "action": "refresh",
                "refreshed_at": datetime.now(UTC),
                "previous_hash_sha256": current.hash_sha256,
            },
        ]
        processed = await self._process_dataset(rescanned)
        await self._dataset_repo.save(processed)
        await self._audit_service.log_action(
            stage=PipelineStage.EVALUATION,
            action="DATASET_REFRESHED",
            evidence_id=processed.dataset_id,
            details={"file_path": str(processed.file_path)},
        )
        return processed

    async def remove_dataset(self, dataset_id: str) -> None:
        """Soft-remove a dataset from active registry queries."""
        removed = await self._dataset_repo.soft_delete(dataset_id)
        if not removed:
            raise DatasetNotFoundError(f"Dataset not found: {dataset_id}")
        await self._audit_service.log_action(
            stage=PipelineStage.EVALUATION,
            action="DATASET_REMOVED",
            evidence_id=dataset_id,
            details={"soft_deleted": True},
        )

    async def _process_dataset(self, dataset: DatasetRecord) -> DatasetRecord:
        dataset = self._classifier.classify(dataset)
        dataset = await self._validator.validate(dataset)
        if dataset.status is DatasetStatus.FAILED:
            return dataset
        dataset.validated_at = datetime.now(UTC)
        dataset = await self._preprocessor.preprocess(dataset)
        dataset.indexed_at = datetime.now(UTC)
        dataset.metadata = {
            **dataset.metadata,
            "last_seen_at": datetime.now(UTC),
            "file_modified_at": self._file_modified_at(dataset.file_path),
            "is_deleted": False,
        }
        return dataset

    @staticmethod
    def _file_modified_at(file_path: Path) -> datetime | None:
        try:
            return datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC)
        except OSError:
            return None
