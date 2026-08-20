"""Structured IOC knowledge base for dataset-sourced threat intelligence lookups."""

from __future__ import annotations

import asyncio
import csv
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import aiosqlite
from pydantic import BaseModel, ConfigDict, Field

from dfat.dataset_intelligence.enums import DatasetFormat
from dfat.dataset_intelligence.models import DatasetRecord

_STIX_VALUE_PATTERN = re.compile(r"=\s*['\"]([^'\"]+)['\"]")
_HASH_TYPES = {"hash", "file_hash", "sha256", "sha1", "md5"}
_IP_TYPES = {"ip", "ip_address", "ipv4", "ipv6"}
_DOMAIN_TYPES = {"domain", "hostname", "fqdn", "url"}
_PROCESS_TYPES = {"process", "process_name", "binary", "filename"}
_REGISTRY_TYPES = {"registry", "registry_key", "key_path"}


class IOCEntry(BaseModel):
    """Structured indicator-of-compromise record sourced from threat datasets."""

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    ioc_id: str = Field(default_factory=lambda: str(uuid4()))
    ioc_type: str
    value: str
    source_dataset: str
    confidence: str
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    mitre_techniques: list[str] = Field(default_factory=list)
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class IOCKnowledgeBase:
    """SQLite-backed IOC store for fast lookup during pipeline triage."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        if self._db_path.suffix != ".db":
            self._db_path = self._db_path / "ioc_knowledge.db"
        self._initialised = False

    async def ingest_from_dataset(self, dataset: DatasetRecord) -> int:
        """Parse IOC data from a dataset file and persist structured entries."""
        await self._ensure_schema()
        entries = await asyncio.to_thread(self._parse_dataset, dataset)
        if not entries:
            return 0
        await self._insert_entries(entries)
        return len(entries)

    async def add_entries(self, entries: list[IOCEntry]) -> int:
        """Persist already-parsed IOC entries discovered during pipeline runs."""
        if not entries:
            return 0
        await self._ensure_schema()
        await self._insert_entries(entries)
        return len(entries)

    async def lookup_hash(self, hash_value: str) -> list[IOCEntry]:
        return await self._lookup_by_type(_HASH_TYPES, hash_value)

    async def lookup_ip(self, ip_address: str) -> list[IOCEntry]:
        return await self._lookup_by_type(_IP_TYPES, ip_address)

    async def lookup_domain(self, domain: str) -> list[IOCEntry]:
        return await self._lookup_by_type(_DOMAIN_TYPES, domain)

    async def lookup_process_name(self, name: str) -> list[IOCEntry]:
        return await self._lookup_by_type(_PROCESS_TYPES, name)

    async def lookup_registry_key(self, key_path: str) -> list[IOCEntry]:
        return await self._lookup_by_type(_REGISTRY_TYPES, key_path)

    async def search(
        self,
        query: str,
        ioc_type: Optional[str] = None,
    ) -> list[IOCEntry]:
        """Search IOC values by substring with optional type filtering."""
        await self._ensure_schema()
        normalized_query = self._normalize_value(query)
        async with aiosqlite.connect(self._db_path) as db:
            if ioc_type is not None:
                cursor = await db.execute(
                    """
                    SELECT * FROM ioc_entries
                    WHERE value_normalized LIKE ?
                      AND ioc_type = ?
                    ORDER BY ingested_at DESC
                    """,
                    (f"%{normalized_query}%", ioc_type.lower()),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT * FROM ioc_entries
                    WHERE value_normalized LIKE ?
                       OR description LIKE ?
                    ORDER BY ingested_at DESC
                    """,
                    (f"%{normalized_query}%", f"%{query}%"),
                )
            rows = await cursor.fetchall()
        return [self._row_to_entry(row) for row in rows]

    async def get_statistics(self) -> dict[str, Any]:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            total_cursor = await db.execute("SELECT COUNT(*) FROM ioc_entries")
            total = int((await total_cursor.fetchone())[0])
            type_cursor = await db.execute(
                """
                SELECT ioc_type, COUNT(*)
                FROM ioc_entries
                GROUP BY ioc_type
                ORDER BY COUNT(*) DESC
                """
            )
            by_type = {row[0]: int(row[1]) for row in await type_cursor.fetchall()}
            source_cursor = await db.execute(
                """
                SELECT source_dataset, COUNT(*)
                FROM ioc_entries
                GROUP BY source_dataset
                ORDER BY COUNT(*) DESC
                """
            )
            by_source = {row[0]: int(row[1]) for row in await source_cursor.fetchall()}
        return {
            "total_count": total,
            "by_type": by_type,
            "by_source_dataset": by_source,
            "database_path": str(self._db_path),
        }

    async def export_all(self) -> list[IOCEntry]:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM ioc_entries ORDER BY ingested_at DESC"
            )
            rows = await cursor.fetchall()
        return [self._row_to_entry(row) for row in rows]

    async def _lookup_by_type(self, ioc_types: set[str], value: str) -> list[IOCEntry]:
        await self._ensure_schema()
        normalized = self._normalize_value(value)
        placeholders = ", ".join("?" for _ in ioc_types)
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                f"""
                SELECT * FROM ioc_entries
                WHERE value_normalized = ?
                  AND ioc_type IN ({placeholders})
                ORDER BY ingested_at DESC
                """,
                (normalized, *sorted(ioc_types)),
            )
            rows = await cursor.fetchall()
        return [self._row_to_entry(row) for row in rows]

    async def _ensure_schema(self) -> None:
        if self._initialised:
            return
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS ioc_entries (
                    ioc_id TEXT PRIMARY KEY,
                    ioc_type TEXT NOT NULL,
                    value TEXT NOT NULL,
                    value_normalized TEXT NOT NULL,
                    source_dataset TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    description TEXT,
                    tags_json TEXT NOT NULL,
                    mitre_techniques_json TEXT NOT NULL,
                    first_seen TEXT,
                    last_seen TEXT,
                    ingested_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_ioc_value ON ioc_entries(value_normalized)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_ioc_type_value ON ioc_entries(ioc_type, value_normalized)"
            )
            await db.commit()
        self._initialised = True

    async def _insert_entries(self, entries: list[IOCEntry]) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.executemany(
                """
                INSERT OR REPLACE INTO ioc_entries (
                    ioc_id, ioc_type, value, value_normalized, source_dataset,
                    confidence, description, tags_json, mitre_techniques_json,
                    first_seen, last_seen, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        entry.ioc_id,
                        entry.ioc_type.lower(),
                        entry.value,
                        self._normalize_value(entry.value),
                        entry.source_dataset,
                        entry.confidence,
                        entry.description,
                        json.dumps(entry.tags),
                        json.dumps(entry.mitre_techniques),
                        entry.first_seen.isoformat() if entry.first_seen else None,
                        entry.last_seen.isoformat() if entry.last_seen else None,
                        entry.ingested_at.isoformat(),
                    )
                    for entry in entries
                ],
            )
            await db.commit()

    def _parse_dataset(self, dataset: DatasetRecord) -> list[IOCEntry]:
        path = Path(dataset.file_path)
        if dataset.format is DatasetFormat.CSV:
            return self._parse_csv(path, dataset.name)
        if dataset.format in {DatasetFormat.JSON, DatasetFormat.STIX_BUNDLE}:
            return self._parse_json(path, dataset.name)
        return []

    def _parse_csv(self, path: Path, source_dataset: str) -> list[IOCEntry]:
        entries: list[IOCEntry] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                entry = self._entry_from_mapping(row, source_dataset)
                if entry is not None:
                    entries.append(entry)
        return entries

    def _parse_json(self, path: Path, source_dataset: str) -> list[IOCEntry]:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if isinstance(payload, dict) and payload.get("type") == "bundle":
            return self._parse_stix_bundle(payload, source_dataset)

        records: list[dict[str, Any]]
        if isinstance(payload, list):
            records = [item for item in payload if isinstance(item, dict)]
        elif isinstance(payload, dict):
            candidate = payload.get("iocs") or payload.get("indicators") or payload.get("objects")
            if isinstance(candidate, list):
                records = [item for item in candidate if isinstance(item, dict)]
            else:
                records = [payload]
        else:
            records = []

        entries: list[IOCEntry] = []
        for record in records:
            if record.get("type") == "bundle":
                entries.extend(self._parse_stix_bundle(record, source_dataset))
                continue
            if record.get("type") in {"indicator", "malware", "ipv4-addr", "domain-name", "file"}:
                entries.extend(self._parse_stix_object(record, source_dataset))
                continue
            entry = self._entry_from_mapping(record, source_dataset)
            if entry is not None:
                entries.append(entry)
        return entries

    def _parse_stix_bundle(
        self,
        payload: dict[str, Any],
        source_dataset: str,
    ) -> list[IOCEntry]:
        entries: list[IOCEntry] = []
        for obj in payload.get("objects", []):
            if isinstance(obj, dict):
                entries.extend(self._parse_stix_object(obj, source_dataset))
        return entries

    def _parse_stix_object(
        self,
        obj: dict[str, Any],
        source_dataset: str,
    ) -> list[IOCEntry]:
        entries: list[IOCEntry] = []
        obj_type = str(obj.get("type", "")).lower()
        description = obj.get("description") or obj.get("name")
        tags = [str(label) for label in obj.get("labels", []) if label]
        techniques = self._extract_mitre_techniques(obj)
        confidence = "medium"
        first_seen = self._parse_datetime(obj.get("first_seen") or obj.get("created"))
        last_seen = self._parse_datetime(obj.get("last_seen") or obj.get("modified"))

        if obj_type == "indicator" and obj.get("pattern"):
            for value in _STIX_VALUE_PATTERN.findall(str(obj["pattern"])):
                ioc_type = self._infer_type_from_value(value)
                entries.append(
                    IOCEntry(
                        ioc_type=ioc_type,
                        value=value,
                        source_dataset=source_dataset,
                        confidence=confidence,
                        description=description,
                        tags=tags,
                        mitre_techniques=techniques,
                        first_seen=first_seen,
                        last_seen=last_seen,
                    )
                )
            return entries

        mapping = {
            "ipv4-addr": ("ip", obj.get("value")),
            "domain-name": ("domain", obj.get("value")),
            "file": ("hash", self._extract_file_hash(obj)),
            "malware": ("process", obj.get("name")),
        }
        if obj_type in mapping:
            ioc_type, value = mapping[obj_type]
            if value:
                entries.append(
                    IOCEntry(
                        ioc_type=ioc_type,
                        value=str(value),
                        source_dataset=source_dataset,
                        confidence=confidence,
                        description=description,
                        tags=tags,
                        mitre_techniques=techniques,
                        first_seen=first_seen,
                        last_seen=last_seen,
                    )
                )
        return entries

    def _entry_from_mapping(
        self,
        row: dict[str, Any],
        source_dataset: str,
    ) -> IOCEntry | None:
        lowered = {str(key).lower(): value for key, value in row.items() if value not in (None, "")}
        ioc_type = self._first_value(lowered, ("ioc_type", "type", "indicator_type", "category"))
        value = self._first_value(
            lowered,
            ("value", "indicator", "ioc", "observable", "hash", "ip", "domain", "process_name", "registry_key"),
        )

        if value is None:
            for key_group, inferred_type in (
                (("hash", "hash_sha256", "sha256", "sha1", "md5", "file_hash"), "hash"),
                (("ip", "ip_address", "destination_ip", "source_ip"), "ip"),
                (("domain", "hostname", "fqdn", "url"), "domain"),
                (("process_name", "process", "binary"), "process"),
                (("registry_key", "registry", "key_path"), "registry"),
            ):
                candidate = self._first_value(lowered, key_group)
                if candidate is not None:
                    value = candidate
                    ioc_type = ioc_type or inferred_type
                    break

        if value is None:
            return None

        ioc_type = str(ioc_type or self._infer_type_from_value(str(value))).lower()
        tags = self._parse_list(lowered.get("tags"))
        techniques = self._parse_list(
            lowered.get("mitre_techniques") or lowered.get("techniques") or lowered.get("attack_patterns")
        )
        return IOCEntry(
            ioc_type=ioc_type,
            value=str(value),
            source_dataset=source_dataset,
            confidence=str(lowered.get("confidence") or "medium").lower(),
            description=lowered.get("description") or lowered.get("summary"),
            tags=tags,
            mitre_techniques=techniques,
            first_seen=self._parse_datetime(lowered.get("first_seen")),
            last_seen=self._parse_datetime(lowered.get("last_seen")),
        )

    @staticmethod
    def _first_value(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any | None:
        for key in keys:
            if key in mapping:
                return mapping[key]
        return None

    @staticmethod
    def _parse_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item]
        if isinstance(value, str):
            if value.startswith("["):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return [str(item) for item in parsed if item]
                except json.JSONDecodeError:
                    pass
            return [part.strip() for part in value.split(",") if part.strip()]
        return [str(value)]

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _extract_mitre_techniques(obj: dict[str, Any]) -> list[str]:
        techniques: list[str] = []
        for ref in obj.get("external_references", []):
            if not isinstance(ref, dict):
                continue
            source = str(ref.get("source_name", "")).lower()
            external_id = ref.get("external_id")
            if source == "mitre-attack" and external_id:
                techniques.append(str(external_id))
        kill_chain = obj.get("kill_chain_phases")
        if isinstance(kill_chain, list):
            for phase in kill_chain:
                if isinstance(phase, dict) and phase.get("phase_name"):
                    techniques.append(str(phase["phase_name"]))
        return techniques

    @staticmethod
    def _extract_file_hash(obj: dict[str, Any]) -> str | None:
        hashes = obj.get("hashes")
        if isinstance(hashes, dict):
            for key in ("SHA-256", "SHA256", "MD5", "SHA-1", "SHA1"):
                if hashes.get(key):
                    return str(hashes[key])
        return obj.get("name")

    @staticmethod
    def _infer_type_from_value(value: str) -> str:
        lowered = value.lower()
        if re.fullmatch(r"(?:[0-9a-f]{32}|[0-9a-f]{40}|[0-9a-f]{64})", lowered):
            return "hash"
        if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", value):
            return "ip"
        if "." in value and not value.startswith("\\"):
            return "domain"
        if "\\" in value:
            return "registry"
        return "process"

    @staticmethod
    def _normalize_value(value: str) -> str:
        return value.strip().lower()

    @staticmethod
    def _row_to_entry(row: Any) -> IOCEntry:
        return IOCEntry(
            ioc_id=row[0],
            ioc_type=row[1],
            value=row[2],
            source_dataset=row[4],
            confidence=row[5],
            description=row[6],
            tags=json.loads(row[7] or "[]"),
            mitre_techniques=json.loads(row[8] or "[]"),
            first_seen=datetime.fromisoformat(row[9]) if row[9] else None,
            last_seen=datetime.fromisoformat(row[10]) if row[10] else None,
            ingested_at=datetime.fromisoformat(row[11]),
        )
