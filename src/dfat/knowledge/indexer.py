"""Document indexing for dataset full-text and vector retrieval."""

from __future__ import annotations

import asyncio
import csv
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from dfat.ai_engine.preprocessing.serializer import ArtefactSerializer
from dfat.core.enums import PipelineStage
from dfat.core.models.artefact import ArtefactSet
from dfat.dataset_intelligence.enums import (
    DatasetCategory,
    DatasetFormat,
    IndexingStatus,
)
from dfat.dataset_intelligence.exceptions import DatasetNotFoundError
from dfat.dataset_intelligence.models import DatasetRecord
from dfat.knowledge.embeddings import LocalEmbeddingEngine
from dfat.knowledge.vector_store import ForensicVectorStore

if TYPE_CHECKING:
    from dfat.database.repositories.dataset_repo import DatasetRepository
    from dfat.services.audit_service import AuditService


class IndexingResult(BaseModel):
    """Summary of a dataset indexing operation."""

    model_config = ConfigDict(validate_assignment=True)

    dataset_id: str
    documents_indexed: int
    chunks_created: int
    duration_seconds: float = Field(ge=0.0)
    collection: str
    indexed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DocumentIndexer:
    """Index dataset and artefact content into the forensic vector store."""

    def __init__(
        self,
        embedding_engine: LocalEmbeddingEngine,
        vector_store: ForensicVectorStore,
        audit_service: AuditService,
        dataset_repo: DatasetRepository | None = None,
    ) -> None:
        self._embedding_engine = embedding_engine
        self._vector_store = vector_store
        self._audit_service = audit_service
        self._dataset_repo = dataset_repo
        self._artefact_serializer = ArtefactSerializer()

    async def index_dataset(self, dataset: DatasetRecord) -> IndexingResult:
        """Index a dataset according to its format and update indexing status."""
        started = asyncio.get_running_loop().time()
        dataset.indexing_status = IndexingStatus.IN_PROGRESS
        collection = self._collection_for_dataset(dataset)

        try:
            documents, metadatas, ids, chunks_created = await asyncio.to_thread(
                self._build_dataset_documents,
                dataset,
            )
            if documents:
                await self._vector_store.add_documents(collection, documents, metadatas, ids)

            dataset.indexing_status = IndexingStatus.COMPLETE
            dataset.indexed_at = datetime.now(UTC)
            duration_seconds = round(asyncio.get_running_loop().time() - started, 4)
            result = IndexingResult(
                dataset_id=dataset.dataset_id,
                documents_indexed=len(documents),
                chunks_created=chunks_created,
                duration_seconds=duration_seconds,
                collection=collection,
            )
            await self._audit_service.log_action(
                stage=PipelineStage.EVALUATION,
                action="DATASET_INDEXED",
                evidence_id=dataset.dataset_id,
                details={
                    "dataset_name": dataset.name,
                    "collection": collection,
                    "documents_indexed": result.documents_indexed,
                    "chunks_created": result.chunks_created,
                    "duration_seconds": result.duration_seconds,
                },
            )
            return result
        except Exception:
            dataset.indexing_status = IndexingStatus.FAILED
            raise

    async def index_artefact_set(self, artefact_set: ArtefactSet, case_id: str) -> int:
        """Embed and index artefacts for retrieval in future investigations."""
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        ids: list[str] = []

        for artefact in artefact_set.artefacts:
            documents.append(self._artefact_serializer.serialize_artefact(artefact))
            metadatas.append(
                {
                    "case_id": case_id,
                    "evidence_id": artefact_set.evidence_id,
                    "artefact_id": artefact.artefact_id,
                    "category": artefact.category.value,
                }
            )
            ids.append(f"{case_id}:{artefact.artefact_id}")

        if documents:
            await self._vector_store.add_documents("artefacts", documents, metadatas, ids)
        return len(documents)

    async def reindex_dataset(self, dataset_id: str) -> IndexingResult:
        """Reload a dataset from persistence and index it again."""
        if self._dataset_repo is None:
            raise RuntimeError("Dataset repository is required for reindex_dataset")
        dataset = await self._dataset_repo.get(dataset_id)
        if dataset is None:
            raise DatasetNotFoundError(f"Dataset not found: {dataset_id}")
        dataset.indexing_status = IndexingStatus.STALE
        result = await self.index_dataset(dataset)
        await self._dataset_repo.save(dataset)
        return result

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        """Split text into overlapping chunks, preferring paragraph boundaries."""
        normalized = text.strip()
        if not normalized:
            return []

        chunks: list[str] = []
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
        if not paragraphs:
            paragraphs = [normalized]

        for paragraph in paragraphs:
            if len(paragraph) <= chunk_size:
                chunks.append(paragraph)
                continue
            start = 0
            while start < len(paragraph):
                end = min(start + chunk_size, len(paragraph))
                chunks.append(paragraph[start:end])
                if end >= len(paragraph):
                    break
                start = max(end - overlap, start + 1)
        return chunks

    def _build_dataset_documents(
        self,
        dataset: DatasetRecord,
    ) -> tuple[list[str], list[dict[str, Any]], list[str], int]:
        path = Path(dataset.file_path)
        base_metadata = {
            "dataset_id": dataset.dataset_id,
            "dataset_name": dataset.name,
            "format": dataset.format.value,
            "category": dataset.category.value,
        }

        if dataset.format is DatasetFormat.CSV:
            return self._index_csv(path, dataset.dataset_id, base_metadata)
        if dataset.format is DatasetFormat.STIX_BUNDLE:
            return self._index_stix(path, dataset.dataset_id, base_metadata)
        if dataset.format is DatasetFormat.JSON:
            return self._index_json(path, dataset.dataset_id, base_metadata)
        if dataset.format is DatasetFormat.YARA_RULES:
            return self._index_yara(path, dataset.dataset_id, base_metadata)
        if dataset.format is DatasetFormat.SIGMA_RULES:
            return self._index_sigma(path, dataset.dataset_id, base_metadata)
        if dataset.format is DatasetFormat.PLAIN_TEXT:
            return self._index_plain_text(path, dataset.dataset_id, base_metadata)
        if dataset.format in {DatasetFormat.DISK_IMAGE, DatasetFormat.MEMORY_DUMP}:
            return self._index_forensic_metadata(dataset, base_metadata)

        text = path.read_text(encoding="utf-8", errors="replace")
        chunks = self._chunk_text(text)
        return self._pack_chunks(dataset.dataset_id, chunks, base_metadata, kind="generic")

    def _index_csv(
        self,
        path: Path,
        dataset_id: str,
        base_metadata: dict[str, Any],
    ) -> tuple[list[str], list[dict[str, Any]], list[str], int]:
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        ids: list[str] = []

        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader):
                documents.append(json.dumps(row, sort_keys=True))
                metadatas.append({**base_metadata, "row_index": index})
                ids.append(f"{dataset_id}:row:{index}")

        return documents, metadatas, ids, len(documents)

    def _index_json(
        self,
        path: Path,
        dataset_id: str,
        base_metadata: dict[str, Any],
    ) -> tuple[list[str], list[dict[str, Any]], list[str], int]:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if isinstance(payload, list):
            documents = [json.dumps(item, sort_keys=True, default=str) for item in payload]
            metadatas = [{**base_metadata, "object_index": index} for index in range(len(documents))]
            ids = [f"{dataset_id}:object:{index}" for index in range(len(documents))]
            return documents, metadatas, ids, len(documents)

        if isinstance(payload, dict) and payload.get("type") == "bundle":
            return self._index_stix_objects(payload.get("objects", []), dataset_id, base_metadata)

        documents = [json.dumps(payload, sort_keys=True, default=str)]
        metadatas = [{**base_metadata, "object_index": 0}]
        ids = [f"{dataset_id}:object:0"]
        return documents, metadatas, ids, 1

    def _index_yara(
        self,
        path: Path,
        dataset_id: str,
        base_metadata: dict[str, Any],
    ) -> tuple[list[str], list[dict[str, Any]], list[str], int]:
        content = path.read_text(encoding="utf-8")
        rules: list[str] = []
        current: list[str] = []
        for line in content.splitlines():
            if line.strip().startswith("rule ") and current:
                rules.append("\n".join(current).strip())
                current = [line]
            else:
                current.append(line)
        if current:
            rules.append("\n".join(current).strip())

        documents = [rule for rule in rules if rule]
        metadatas = [{**base_metadata, "rule_index": index} for index in range(len(documents))]
        ids = [f"{dataset_id}:rule:{index}" for index in range(len(documents))]
        return documents, metadatas, ids, len(documents)

    def _index_sigma(
        self,
        path: Path,
        dataset_id: str,
        base_metadata: dict[str, Any],
    ) -> tuple[list[str], list[dict[str, Any]], list[str], int]:
        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)

        if isinstance(payload, list):
            documents = [yaml.safe_dump(item, sort_keys=False) for item in payload]
        else:
            documents = [yaml.safe_dump(payload, sort_keys=False)]

        metadatas = [{**base_metadata, "rule_index": index} for index in range(len(documents))]
        ids = [f"{dataset_id}:sigma:{index}" for index in range(len(documents))]
        return documents, metadatas, ids, len(documents)

    def _index_stix(
        self,
        path: Path,
        dataset_id: str,
        base_metadata: dict[str, Any],
    ) -> tuple[list[str], list[dict[str, Any]], list[str], int]:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        objects = payload.get("objects", []) if isinstance(payload, dict) else []
        return self._index_stix_objects(objects, dataset_id, base_metadata)

    def _index_stix_objects(
        self,
        objects: list[Any],
        dataset_id: str,
        base_metadata: dict[str, Any],
    ) -> tuple[list[str], list[dict[str, Any]], list[str], int]:
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        ids: list[str] = []

        for index, obj in enumerate(objects):
            if not isinstance(obj, dict):
                continue
            documents.append(json.dumps(obj, sort_keys=True, default=str))
            metadatas.append(
                {
                    **base_metadata,
                    "stix_type": obj.get("type", "unknown"),
                    "object_index": index,
                }
            )
            object_id = str(obj.get("id") or f"object-{index}")
            ids.append(f"{dataset_id}:stix:{object_id}")

        return documents, metadatas, ids, len(documents)

    def _index_plain_text(
        self,
        path: Path,
        dataset_id: str,
        base_metadata: dict[str, Any],
    ) -> tuple[list[str], list[dict[str, Any]], list[str], int]:
        text = path.read_text(encoding="utf-8", errors="replace")
        chunks = self._chunk_text(text)
        return self._pack_chunks(dataset_id, chunks, base_metadata, kind="text")

    def _index_forensic_metadata(
        self,
        dataset: DatasetRecord,
        base_metadata: dict[str, Any],
    ) -> tuple[list[str], list[dict[str, Any]], list[str], int]:
        summary = (
            f"Forensic dataset metadata\n"
            f"name: {dataset.name}\n"
            f"format: {dataset.format.value}\n"
            f"size_bytes: {dataset.file_size_bytes}\n"
            f"hash_sha256: {dataset.hash_sha256}\n"
            f"mime_type: {dataset.mime_type or 'unknown'}\n"
            f"path: {dataset.file_path}\n"
        )
        documents = [summary]
        metadatas = [{**base_metadata, "metadata_only": True}]
        ids = [f"{dataset.dataset_id}:metadata"]
        return documents, metadatas, ids, 1

    @staticmethod
    def _pack_chunks(
        dataset_id: str,
        chunks: list[str],
        base_metadata: dict[str, Any],
        *,
        kind: str,
    ) -> tuple[list[str], list[dict[str, Any]], list[str], int]:
        documents = chunks
        metadatas = [{**base_metadata, "chunk_index": index, "chunk_kind": kind} for index in range(len(chunks))]
        ids = [f"{dataset_id}:{kind}:{index}" for index in range(len(chunks))]
        return documents, metadatas, ids, len(chunks)

    @staticmethod
    def _collection_for_dataset(dataset: DatasetRecord) -> str:
        if dataset.category is DatasetCategory.BENCHMARK:
            return "benchmark"
        if dataset.category is DatasetCategory.THREAT_INTELLIGENCE:
            return "threat_intel"
        if dataset.format in {
            DatasetFormat.YARA_RULES,
            DatasetFormat.SIGMA_RULES,
            DatasetFormat.STIX_BUNDLE,
        }:
            return "threat_intel"
        return "knowledge"
