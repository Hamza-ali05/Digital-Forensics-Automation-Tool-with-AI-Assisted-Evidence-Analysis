"""Dataset intelligence registry API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from dfat.api.dependencies import get_dataset_registry, get_document_indexer, require_permission, require_role
from dfat.api.schemas.extension import (
    DatasetActionResponse,
    DatasetRecordResponse,
    DatasetScanRequest,
    DatasetScanResponse,
    DatasetStatisticsResponse,
)
from dfat.dataset_intelligence.enums import DatasetCategory, DatasetStatus
from dfat.dataset_intelligence.exceptions import DatasetNotFoundError
from dfat.dataset_intelligence.registry import DatasetRegistry
from dfat.database.models.user import UserORM
from dfat.knowledge.indexer import DocumentIndexer

router = APIRouter(prefix="/datasets", tags=["Datasets"])


def _to_dataset_response(dataset) -> DatasetRecordResponse:
    return DatasetRecordResponse(
        dataset_id=dataset.dataset_id,
        name=dataset.name,
        file_path=str(dataset.file_path),
        category=dataset.category.value,
        format=dataset.format.value,
        status=dataset.status.value,
        file_size_bytes=dataset.file_size_bytes,
        hash_sha256=dataset.hash_sha256,
        discovered_at=dataset.discovered_at,
        validated_at=dataset.validated_at,
        indexed_at=dataset.indexed_at,
        indexing_status=dataset.indexing_status.value,
        tags=list(dataset.tags),
    )


@router.post("/scan", response_model=DatasetScanResponse, status_code=status.HTTP_200_OK)
async def scan_datasets(
    body: DatasetScanRequest | None = None,
    _: UserORM = Depends(require_role(["admin"])),
    registry: DatasetRegistry = Depends(get_dataset_registry),
) -> DatasetScanResponse:
    """Trigger a dataset discovery scan (admin only)."""
    scan_path = Path(body.scan_path) if body and body.scan_path else None
    result = await registry.register_all(scan_path=scan_path)
    return DatasetScanResponse(
        scan_path=str(result.scan_path),
        datasets_found=len(result.datasets),
        new_count=result.new_count,
        updated_count=result.updated_count,
        failed_count=result.failed_count,
    )


@router.get("/statistics", response_model=DatasetStatisticsResponse)
async def dataset_statistics(
    _: UserORM = Depends(require_permission("datasets", "read")),
    registry: DatasetRegistry = Depends(get_dataset_registry),
) -> DatasetStatisticsResponse:
    """Return aggregate dataset registry statistics."""
    stats = await registry.get_statistics()
    return DatasetStatisticsResponse(statistics=stats)


@router.get("", response_model=list[DatasetRecordResponse])
async def list_datasets(
    category: Optional[DatasetCategory] = Query(default=None),
    status_filter: Optional[DatasetStatus] = Query(default=None, alias="status"),
    _: UserORM = Depends(require_permission("datasets", "read")),
    registry: DatasetRegistry = Depends(get_dataset_registry),
) -> list[DatasetRecordResponse]:
    """List registered datasets with optional filters."""
    datasets = await registry.list_datasets(category=category, status=status_filter)
    return [_to_dataset_response(item) for item in datasets]


@router.get("/{dataset_id}", response_model=DatasetRecordResponse)
async def get_dataset(
    dataset_id: str,
    _: UserORM = Depends(require_permission("datasets", "read")),
    registry: DatasetRegistry = Depends(get_dataset_registry),
) -> DatasetRecordResponse:
    """Return a single dataset record."""
    try:
        dataset = await registry.get_dataset(dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_dataset_response(dataset)


@router.post("/{dataset_id}/reindex", response_model=DatasetActionResponse)
async def reindex_dataset(
    dataset_id: str,
    _: UserORM = Depends(require_role(["admin"])),
    indexer: DocumentIndexer = Depends(get_document_indexer),
) -> DatasetActionResponse:
    """Re-index a dataset into the vector store (admin only)."""
    try:
        result = await indexer.reindex_dataset(dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return DatasetActionResponse(
        dataset_id=dataset_id,
        action="reindex",
        message=(
            f"Indexed {result.documents_indexed} documents "
            f"into collection {result.collection}"
        ),
    )


@router.post("/{dataset_id}/refresh", response_model=DatasetRecordResponse)
async def refresh_dataset(
    dataset_id: str,
    _: UserORM = Depends(require_role(["admin"])),
    registry: DatasetRegistry = Depends(get_dataset_registry),
) -> DatasetRecordResponse:
    """Re-validate and reprocess a dataset (admin only)."""
    try:
        dataset = await registry.refresh_dataset(dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_dataset_response(dataset)


@router.delete("/{dataset_id}", response_model=DatasetActionResponse)
async def delete_dataset(
    dataset_id: str,
    _: UserORM = Depends(require_role(["admin"])),
    registry: DatasetRegistry = Depends(get_dataset_registry),
) -> DatasetActionResponse:
    """Soft-remove a dataset from the registry (admin only)."""
    try:
        await registry.remove_dataset(dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return DatasetActionResponse(
        dataset_id=dataset_id,
        action="delete",
        message="Dataset removed from registry",
    )
