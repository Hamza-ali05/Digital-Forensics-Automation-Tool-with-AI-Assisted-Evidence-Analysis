"""Dataset intelligence domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field

from dfat.dataset_intelligence.enums import (
    DatasetCategory,
    DatasetFormat,
    DatasetStatus,
    IndexingStatus,
)


class DatasetRecord(BaseModel):
    """Single dataset registered in the dataset intelligence subsystem."""

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    dataset_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    file_path: Path
    category: DatasetCategory
    format: DatasetFormat
    status: DatasetStatus
    file_size_bytes: int = Field(ge=0)
    hash_sha256: str
    mime_type: str | None = None
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    validated_at: datetime | None = None
    indexed_at: datetime | None = None
    parent_directory: str
    is_nested: bool = False
    nested_depth: int = Field(default=0, ge=0)
    metadata: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    associated_research_objectives: list[str] = Field(default_factory=list)
    supported_forensic_modules: list[str] = Field(default_factory=list)
    indexing_status: IndexingStatus = IndexingStatus.PENDING
    preprocessing_history: list[dict] = Field(default_factory=list)
    update_history: list[dict] = Field(default_factory=list)


class DatasetCollection(BaseModel):
    """Named grouping of dataset records."""

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    collection_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    datasets: list[DatasetRecord] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_size_bytes(self) -> int:
        """Total size of datasets in the collection."""
        return sum(item.file_size_bytes for item in self.datasets)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def category_distribution(self) -> dict[str, int]:
        """Count datasets by category."""
        distribution: dict[str, int] = {}
        for dataset in self.datasets:
            distribution[dataset.category.value] = (
                distribution.get(dataset.category.value, 0) + 1
            )
        return distribution

    @computed_field  # type: ignore[prop-decorator]
    @property
    def format_distribution(self) -> dict[str, int]:
        """Count datasets by format."""
        distribution: dict[str, int] = {}
        for dataset in self.datasets:
            distribution[dataset.format.value] = (
                distribution.get(dataset.format.value, 0) + 1
            )
        return distribution


class DatasetScanResult(BaseModel):
    """Summary of a dataset-discovery scan."""

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
    )

    scan_id: str = Field(default_factory=lambda: str(uuid4()))
    scan_path: Path
    discovered_count: int = Field(ge=0)
    new_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    duration_seconds: float = Field(ge=0.0)
    scanned_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    datasets: list[DatasetRecord] = Field(default_factory=list)
