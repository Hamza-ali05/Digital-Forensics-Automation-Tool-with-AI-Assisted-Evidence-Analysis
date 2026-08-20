"""Dataset preprocessing helpers for indexing and ML-oriented enrichment."""

from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path
from typing import Any

import yaml

from dfat.dataset_intelligence.enums import DatasetCategory, DatasetFormat, DatasetStatus
from dfat.dataset_intelligence.models import DatasetRecord


class DatasetPreprocessor:
    """Preprocess validated datasets into structured metadata summaries."""

    async def preprocess(self, dataset: DatasetRecord) -> DatasetRecord:
        """Run category-aware preprocessing and mark a dataset ready on success."""
        steps: list[dict[str, Any]] = []
        derived_metadata: dict[str, Any] = {}

        try:
            if dataset.category is DatasetCategory.BENCHMARK:
                derived_metadata["benchmark"] = await self._preprocess_benchmark(dataset)
                steps.append({"step": "benchmark_enrichment", "status": "completed"})
            elif dataset.category is DatasetCategory.THREAT_INTELLIGENCE:
                derived_metadata["threat_intelligence"] = await self._preprocess_threat_intel(dataset)
                steps.append({"step": "threat_intelligence_parsing", "status": "completed"})
            elif dataset.category is DatasetCategory.MACHINE_LEARNING:
                derived_metadata["machine_learning"] = await self._preprocess_ml(dataset)
                steps.append({"step": "machine_learning_normalization", "status": "completed"})
            elif dataset.category is DatasetCategory.FORENSIC_OPERATIONAL:
                derived_metadata["forensic_operational"] = await self._preprocess_forensic(dataset)
                steps.append({"step": "forensic_metadata_summary", "status": "completed"})
            else:
                derived_metadata["generic"] = await self._preprocess_generic(dataset)
                steps.append({"step": "generic_metadata_capture", "status": "completed"})
        except Exception as exc:  # noqa: BLE001
            dataset.status = DatasetStatus.FAILED
            dataset.preprocessing_history = [
                *dataset.preprocessing_history,
                {"step": "preprocess", "status": "failed", "error": str(exc)},
            ]
            dataset.metadata = {
                **dataset.metadata,
                "preprocessing_notes": [f"Preprocessing failed: {exc}"],
            }
            return dataset

        dataset.preprocessing_history = [*dataset.preprocessing_history, *steps]
        dataset.metadata = {**dataset.metadata, **derived_metadata}
        dataset.status = DatasetStatus.READY
        return dataset

    async def _preprocess_benchmark(self, dataset: DatasetRecord) -> dict[str, Any]:
        path = Path(dataset.file_path)
        normalized_identifier = self._normalise_identifier(path.stem)
        metadata: dict[str, Any] = {
            "normalized_identifier": normalized_identifier,
            "ground_truth_embedded": False,
        }

        if dataset.format is DatasetFormat.JSON:
            json_summary = await asyncio.to_thread(self._preprocess_json, path)
            metadata["json_summary"] = json_summary
            metadata["ground_truth_embedded"] = json_summary["contains_ground_truth"]
        elif dataset.format is DatasetFormat.ARCHIVE:
            archive_contents = dataset.metadata.get("archive_contents", [])
            metadata["ground_truth_embedded"] = any(
                "ground" in str(item).lower() and "truth" in str(item).lower()
                for item in archive_contents
            )
            metadata["archive_members"] = len(archive_contents)

        return metadata

    async def _preprocess_threat_intel(self, dataset: DatasetRecord) -> dict[str, Any]:
        path = Path(dataset.file_path)
        if dataset.format is DatasetFormat.YARA_RULES:
            return {"yara_summary": await asyncio.to_thread(self._preprocess_yara, path)}
        if dataset.format is DatasetFormat.SIGMA_RULES:
            return {"sigma_summary": await asyncio.to_thread(self._preprocess_sigma, path)}
        if dataset.format in {DatasetFormat.JSON, DatasetFormat.STIX_BUNDLE}:
            return {"json_summary": await asyncio.to_thread(self._preprocess_json, path)}
        return await self._preprocess_generic(dataset)

    async def _preprocess_ml(self, dataset: DatasetRecord) -> dict[str, Any]:
        path = Path(dataset.file_path)
        if dataset.format is DatasetFormat.CSV:
            return {"csv_summary": await asyncio.to_thread(self._preprocess_csv, path)}
        if dataset.format is DatasetFormat.JSON:
            return {"json_summary": await asyncio.to_thread(self._preprocess_json, path)}
        return await self._preprocess_generic(dataset)

    async def _preprocess_forensic(self, dataset: DatasetRecord) -> dict[str, Any]:
        path = Path(dataset.file_path)
        stat = await asyncio.to_thread(path.stat)
        return {
            "file_name": path.name,
            "extension": path.suffix.lower(),
            "size_bytes": stat.st_size,
            "nested_depth": dataset.nested_depth,
            "mime_type": dataset.mime_type,
            "hash_prefix": dataset.hash_sha256[:12],
        }

    async def _preprocess_generic(self, dataset: DatasetRecord) -> dict[str, Any]:
        path = Path(dataset.file_path)
        stat = await asyncio.to_thread(path.stat)
        return {
            "file_name": path.name,
            "size_bytes": stat.st_size,
            "format": dataset.format.value,
        }

    @staticmethod
    def _preprocess_csv(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            fieldnames = reader.fieldnames or []

        normalized_headers = [header.strip().lower().replace(" ", "_") for header in fieldnames]
        sample_row = rows[0] if rows else {}
        column_types = {
            header: DatasetPreprocessor._infer_value_type(sample_row.get(header))
            for header in fieldnames
        }
        feature_columns = [
            header
            for header in fieldnames
            if header.lower() not in {"label", "labels", "target", "class", "y"}
        ]

        return {
            "row_count": len(rows),
            "columns": fieldnames,
            "normalized_headers": normalized_headers,
            "column_types": column_types,
            "feature_columns": feature_columns,
        }

    @staticmethod
    def _preprocess_json(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if isinstance(payload, list):
            schema_keys = sorted(
                {
                    key
                    for item in payload
                    if isinstance(item, dict)
                    for key in item.keys()
                }
            )
            object_count = len(payload)
        elif isinstance(payload, dict):
            schema_keys = sorted(payload.keys())
            object_count = len(payload.get("objects", payload))
            if not isinstance(object_count, int):
                object_count = 1
        else:
            schema_keys = []
            object_count = 1

        searchable = json.dumps(payload).lower()
        return {
            "schema_keys": schema_keys,
            "object_count": object_count,
            "contains_ground_truth": "ground_truth" in searchable or "ground truth" in searchable,
        }

    @staticmethod
    def _preprocess_yara(path: Path) -> dict[str, Any]:
        content = path.read_text(encoding="utf-8")
        rule_names: list[str] = []
        tags: list[str] = []

        for line in content.splitlines():
            stripped = line.strip()
            if not stripped.startswith("rule "):
                continue
            declaration = stripped.removeprefix("rule ").split("{", 1)[0].strip()
            if ":" in declaration:
                name_part, tag_part = declaration.split(":", 1)
                rule_names.append(name_part.strip())
                tags.extend(part for part in tag_part.split() if part)
            else:
                rule_names.append(declaration.strip())

        return {
            "rule_count": len(rule_names),
            "rule_names": rule_names,
            "tags": DatasetPreprocessor._dedupe(tags),
        }

    @staticmethod
    def _preprocess_sigma(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)

        if isinstance(payload, list):
            title = None
            logsource = None
            detection_keys: list[str] = []
            rule_count = len(payload)
        elif isinstance(payload, dict):
            title = payload.get("title")
            logsource = payload.get("logsource")
            detection = payload.get("detection", {})
            detection_keys = sorted(detection.keys()) if isinstance(detection, dict) else []
            rule_count = 1
        else:
            title = None
            logsource = None
            detection_keys = []
            rule_count = 0

        return {
            "rule_count": rule_count,
            "title": title,
            "logsource": logsource,
            "detection_keys": detection_keys,
        }

    @staticmethod
    def _infer_value_type(value: Any) -> str:
        if value is None or value == "":
            return "empty"
        lowered = str(value).strip().lower()
        if lowered in {"true", "false"}:
            return "bool"
        try:
            int(str(value))
            return "int"
        except ValueError:
            pass
        try:
            float(str(value))
            return "float"
        except ValueError:
            pass
        return "str"

    @staticmethod
    def _normalise_identifier(value: str) -> str:
        return "_".join(part for part in value.lower().replace("-", "_").split("_") if part)

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                deduped.append(value)
        return deduped
