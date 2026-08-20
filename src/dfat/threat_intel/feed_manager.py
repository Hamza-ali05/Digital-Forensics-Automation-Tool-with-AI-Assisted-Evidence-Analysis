"""Threat intelligence feed ingestion and consolidated artefact scanning."""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.enums import ArtefactCategory, PipelineStage, SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact
from dfat.dataset_intelligence.enums import DatasetFormat
from dfat.dataset_intelligence.models import DatasetRecord
from dfat.knowledge.ioc_database import IOCEntry
from dfat.knowledge.retriever import UnifiedRetriever
from dfat.threat_intel.mitre_mapper import MITREMapper, MITREMapping
from dfat.threat_intel.sigma_engine import SigmaEngine, SigmaMatch
from dfat.threat_intel.stix_handler import STIXHandler
from dfat.threat_intel.yara_engine import YARAEngine, YARAMatch

if TYPE_CHECKING:
    from dfat.dataset_intelligence.registry import DatasetRegistry
    from dfat.knowledge.knowledge_graph import ForensicKnowledgeGraph
    from dfat.services.audit_service import AuditService

logger = logging.getLogger(__name__)

_IOC_FORMATS = frozenset({DatasetFormat.CSV, DatasetFormat.JSON})


class FeedIngestionResult(BaseModel):
    """Outcome of ingesting a threat-intelligence dataset feed."""

    model_config = ConfigDict(frozen=False)

    dataset_id: str
    feed_type: str
    items_ingested: int = Field(ge=0)
    rules_loaded: int = Field(ge=0)
    errors: list[str] = Field(default_factory=list)
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ThreatScanResult(BaseModel):
    """Consolidated threat-intelligence findings for an artefact set."""

    model_config = ConfigDict(frozen=False)

    yara_matches: list[YARAMatch] = Field(default_factory=list)
    sigma_matches: list[SigmaMatch] = Field(default_factory=list)
    ioc_matches: list[IOCEntry] = Field(default_factory=list)
    mitre_mappings: list[MITREMapping] = Field(default_factory=list)
    total_findings: int = Field(ge=0)
    scan_duration_ms: float = Field(ge=0.0)


class ThreatFeedManager:
    """Ingest local threat feeds and scan artefacts against loaded intelligence."""

    def __init__(
        self,
        dataset_registry: DatasetRegistry,
        ioc_kb: IOCKnowledgeBase,
        yara_engine: YARAEngine,
        sigma_engine: SigmaEngine,
        mitre_mapper: MITREMapper,
        knowledge_graph: ForensicKnowledgeGraph,
        audit_service: AuditService,
        *,
        stix_handler: STIXHandler | None = None,
    ) -> None:
        self._dataset_registry = dataset_registry
        self._ioc_kb = ioc_kb
        self._yara = yara_engine
        self._sigma = sigma_engine
        self._mitre = mitre_mapper
        self._stix = stix_handler or STIXHandler()
        self._graph = knowledge_graph
        self._audit = audit_service

    async def ingest_feed(self, dataset: DatasetRecord) -> FeedIngestionResult:
        """Route ``dataset`` to the appropriate threat-intelligence handler."""
        errors: list[str] = []
        items_ingested = 0
        rules_loaded = 0
        feed_type = dataset.format.value

        try:
            if dataset.format is DatasetFormat.YARA_RULES:
                rules_loaded = await self._ingest_yara_rules(dataset, errors)
            elif dataset.format is DatasetFormat.SIGMA_RULES:
                rules_loaded = await self._ingest_sigma_rules(dataset, errors)
            elif dataset.format is DatasetFormat.STIX_BUNDLE:
                items_ingested = await self._ingest_stix_bundle(dataset, errors)
            elif dataset.format in _IOC_FORMATS:
                items_ingested = await self._ingest_ioc_dataset(dataset, errors)
            else:
                errors.append(f"Unsupported threat feed format: {feed_type}")
        except Exception as exc:  # noqa: BLE001 — feed-level failure
            logger.exception("Threat feed ingestion failed for %s", dataset.dataset_id)
            errors.append(str(exc))

        result = FeedIngestionResult(
            dataset_id=dataset.dataset_id,
            feed_type=feed_type,
            items_ingested=items_ingested,
            rules_loaded=rules_loaded,
            errors=errors,
        )

        await self._audit.log_action(
            stage=PipelineStage.EVALUATION,
            action="THREAT_FEED_INGESTED",
            evidence_id=dataset.dataset_id,
            details={
                "feed_type": feed_type,
                "items_ingested": items_ingested,
                "rules_loaded": rules_loaded,
                "errors": errors,
            },
        )
        return result

    async def scan_artefacts_against_intel(
        self,
        artefact_set: ArtefactSet,
    ) -> ThreatScanResult:
        """Run YARA, Sigma, IOC KB, and MITRE mapping against ``artefact_set``."""
        started = time.perf_counter()
        yara_matches: list[YARAMatch] = []
        sigma_matches: list[SigmaMatch] = []
        ioc_matches: list[IOCEntry] = []
        mitre_mappings: list[MITREMapping] = []

        for artefact in artefact_set.artefacts:
            yara_matches.extend(
                await asyncio.to_thread(self._yara.scan_artefact, artefact)
            )
            if artefact.category is ArtefactCategory.EVENT_LOG:
                sigma_matches.extend(
                    await asyncio.to_thread(self._sigma.match_event_log, artefact)
                )
            elif artefact.category in {
                ArtefactCategory.RUNNING_PROCESS,
                ArtefactCategory.INJECTED_CODE,
            }:
                sigma_matches.extend(
                    await asyncio.to_thread(self._sigma.match_process, artefact)
                )

            artefact_iocs = await self._lookup_artefact_iocs(artefact)
            ioc_matches.extend(artefact_iocs)

            ranked = RankedArtefact(
                **artefact.model_dump(),
                suspicion_level=SuspicionLevel.INFORMATIONAL,
                relevance_score=0.0,
            )
            mitre_mappings.extend(self._mitre.map_artefact(ranked))

        ioc_matches = _dedupe_ioc_matches(ioc_matches)
        mitre_mappings = _dedupe_mitre_mappings(mitre_mappings)
        duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
        total = len(yara_matches) + len(sigma_matches) + len(ioc_matches) + len(mitre_mappings)

        return ThreatScanResult(
            yara_matches=yara_matches,
            sigma_matches=sigma_matches,
            ioc_matches=ioc_matches,
            mitre_mappings=mitre_mappings,
            total_findings=total,
            scan_duration_ms=duration_ms,
        )

    async def get_intel_summary(self) -> dict[str, object]:
        """Return counts and coverage for loaded threat intelligence."""
        ioc_stats = await self._ioc_kb.get_statistics()
        tactic_coverage = {
            info["tactic"]
            for info in self._mitre.TECHNIQUE_DB.values()
        }
        return {
            "yara_rules_loaded": self._yara.get_loaded_rules_count(),
            "sigma_rules_loaded": self._sigma.get_loaded_rules_count(),
            "ioc_count": ioc_stats.get("total_count", 0),
            "ioc_by_type": ioc_stats.get("by_type", {}),
            "mitre_techniques_known": len(self._mitre.TECHNIQUE_DB),
            "mitre_tactic_coverage": sorted(tactic_coverage),
        }

    async def _ingest_yara_rules(
        self,
        dataset: DatasetRecord,
        errors: list[str],
    ) -> int:
        await self._stage_rule_file(dataset, self._yara.rules_dir, errors)
        return await asyncio.to_thread(self._yara.load_rules)

    async def _ingest_sigma_rules(
        self,
        dataset: DatasetRecord,
        errors: list[str],
    ) -> int:
        await self._stage_rule_file(dataset, self._sigma.rules_dir, errors)
        return await asyncio.to_thread(self._sigma.load_rules)

    async def _ingest_stix_bundle(
        self,
        dataset: DatasetRecord,
        errors: list[str],
    ) -> int:
        path = Path(dataset.file_path)
        if not path.is_file():
            errors.append(f"STIX bundle file missing: {path}")
            return 0
        objects = await asyncio.to_thread(self._stix.parse_bundle, path)
        entries = self._stix.extract_indicators(objects)
        if not entries:
            return 0
        for entry in entries:
            entry.source_dataset = dataset.name
        count = await self._ioc_kb.add_entries(entries)
        await asyncio.to_thread(self._graph.add_ioc_relationships, entries)
        await asyncio.to_thread(self._graph.save)
        return count

    async def _ingest_ioc_dataset(
        self,
        dataset: DatasetRecord,
        errors: list[str],
    ) -> int:
        path = Path(dataset.file_path)
        if not path.is_file():
            errors.append(f"IOC dataset file missing: {path}")
            return 0
        entries = await asyncio.to_thread(self._ioc_kb._parse_dataset, dataset)
        if not entries:
            return 0
        count = await self._ioc_kb.add_entries(entries)
        await asyncio.to_thread(self._graph.add_ioc_relationships, entries)
        await asyncio.to_thread(self._graph.save)
        return count

    async def _stage_rule_file(
        self,
        dataset: DatasetRecord,
        destination_dir: Path,
        errors: list[str],
    ) -> None:
        source = Path(dataset.file_path)
        destination_dir.mkdir(parents=True, exist_ok=True)
        if not source.exists():
            errors.append(f"Rule file missing: {source}")
            return
        if source.is_dir():
            for child in source.iterdir():
                if child.is_file():
                    target = destination_dir / child.name
                    await asyncio.to_thread(shutil.copy2, child, target)
            return
        target = destination_dir / source.name
        await asyncio.to_thread(shutil.copy2, source, target)

    async def _lookup_artefact_iocs(self, artefact: Artefact) -> list[IOCEntry]:
        matches: list[IOCEntry] = []
        for ioc_type, value in UnifiedRetriever._extract_artefact_indicators(artefact):
            if ioc_type == "hash":
                matches.extend(await self._ioc_kb.lookup_hash(value))
            elif ioc_type == "ip":
                matches.extend(await self._ioc_kb.lookup_ip(value))
            elif ioc_type == "domain":
                matches.extend(await self._ioc_kb.lookup_domain(value))
            elif ioc_type == "process":
                matches.extend(await self._ioc_kb.lookup_process_name(value))
            elif ioc_type == "registry":
                matches.extend(await self._ioc_kb.lookup_registry_key(value))
            else:
                matches.extend(await self._ioc_kb.search(value, ioc_type=ioc_type))
        return matches


def _dedupe_ioc_matches(matches: list[IOCEntry]) -> list[IOCEntry]:
    seen: set[str] = set()
    deduped: list[IOCEntry] = []
    for match in matches:
        if match.ioc_id in seen:
            continue
        seen.add(match.ioc_id)
        deduped.append(match)
    return deduped


def _dedupe_mitre_mappings(mappings: list[MITREMapping]) -> list[MITREMapping]:
    seen: set[tuple[str, str]] = set()
    deduped: list[MITREMapping] = []
    for mapping in mappings:
        key = (mapping.artefact_id, mapping.technique_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(mapping)
    return deduped
