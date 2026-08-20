"""Post-pipeline hooks that index completed analyses into knowledge stores."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from dfat.core.enums import PipelineStage
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact
from dfat.core.models.report import ForensicReport
from dfat.knowledge.ioc_database import IOCEntry, IOCKnowledgeBase
from dfat.knowledge.knowledge_graph import ForensicKnowledgeGraph
from dfat.pipeline.models import PipelineJob

if TYPE_CHECKING:
    from dfat.knowledge.indexer import DocumentIndexer
    from dfat.services.audit_service import AuditService

logger = logging.getLogger(__name__)

_IOC_FIELDS: tuple[tuple[str, str], ...] = (
    ("remote_address", "ip"),
    ("local_address", "ip"),
    ("destination_ip", "ip"),
    ("domain", "domain"),
    ("hostname", "domain"),
    ("url", "domain"),
    ("hash_sha256", "hash"),
    ("hash", "hash"),
    ("name", "process"),
    ("process_name", "process"),
    ("key_path", "registry"),
)


class PipelineKnowledgeHooks:
    """Index pipeline results into knowledge repositories for future RAG retrieval.

    Invoked after the forensic report is generated so indexing does not affect
    pipeline stage timings or benchmark measurements.
    """

    def __init__(
        self,
        indexer: DocumentIndexer,
        knowledge_graph: ForensicKnowledgeGraph,
        ioc_db: IOCKnowledgeBase,
        audit_service: AuditService,
    ) -> None:
        self._indexer = indexer
        self._graph = knowledge_graph
        self._ioc_db = ioc_db
        self._audit = audit_service

    async def on_pipeline_complete(
        self,
        job: PipelineJob,
        artefact_set: ArtefactSet,
        ranked: list[RankedArtefact],
        report: ForensicReport,
    ) -> None:
        """Index artefacts, relationships, and IOCs after a successful pipeline run."""
        artefacts_indexed = 0
        graph_edges = 0
        iocs_stored = 0
        errors: list[str] = []

        try:
            artefacts_indexed = await self._indexer.index_artefact_set(
                artefact_set,
                job.case_id,
            )
        except Exception as exc:  # noqa: BLE001 — hook must not fail the pipeline
            errors.append(f"vector_index: {exc}")
            logger.warning("Knowledge vector indexing failed for job %s: %s", job.job_id, exc)

        iocs = self._extract_iocs(job, artefact_set, ranked)

        try:
            graph_set = self._graph_artefact_set(artefact_set, ranked)
            graph_edges += self._graph.add_artefact_relationships(graph_set)
            if iocs:
                graph_edges += self._graph.add_ioc_relationships(iocs)
            self._graph.save()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"knowledge_graph: {exc}")
            logger.warning("Knowledge graph update failed for job %s: %s", job.job_id, exc)

        try:
            iocs_stored = await self._ioc_db.add_entries(iocs)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"ioc_store: {exc}")
            logger.warning("IOC knowledge store failed for job %s: %s", job.job_id, exc)

        await self._audit.log_action(
            stage=PipelineStage.EVALUATION,
            action="KNOWLEDGE_BASE_UPDATED",
            evidence_id=job.evidence_id,
            user_id=job.user_id,
            details={
                "job_id": job.job_id,
                "case_id": job.case_id,
                "report_id": report.report_id,
                "artefacts_indexed": artefacts_indexed,
                "graph_edges_added": graph_edges,
                "iocs_stored": iocs_stored,
                "errors": errors,
            },
        )

    @staticmethod
    def _graph_artefact_set(
        artefact_set: ArtefactSet,
        ranked: list[RankedArtefact],
    ) -> ArtefactSet:
        artefacts: list[Artefact] = list(ranked) if ranked else list(artefact_set.artefacts)
        return ArtefactSet(
            evidence_id=artefact_set.evidence_id,
            artefacts=artefacts,
            categories_present=artefact_set.categories_present,
            extraction_timestamp=artefact_set.extraction_timestamp,
        )

    def _extract_iocs(
        self,
        job: PipelineJob,
        artefact_set: ArtefactSet,
        ranked: list[RankedArtefact],
    ) -> list[IOCEntry]:
        source = f"pipeline:{job.job_id}"
        artefacts: list[Artefact] = list(ranked) if ranked else list(artefact_set.artefacts)
        entries: list[IOCEntry] = []
        seen: set[tuple[str, str]] = set()

        for artefact in artefacts:
            for ioc_type, value, confidence, description in self._indicators_from_artefact(artefact):
                key = (ioc_type, value.lower())
                if key in seen:
                    continue
                seen.add(key)
                entries.append(
                    IOCEntry(
                        ioc_type=ioc_type,
                        value=value,
                        source_dataset=source,
                        confidence=confidence,
                        description=description,
                        tags=["pipeline", job.case_id],
                    )
                )
        return entries

    @staticmethod
    def _indicators_from_artefact(artefact: Artefact) -> list[tuple[str, str, str, str]]:
        raw: dict[str, Any] = artefact.raw_data if isinstance(artefact.raw_data, dict) else {}
        metadata: dict[str, Any] = artefact.metadata if isinstance(artefact.metadata, dict) else {}
        indicators: list[tuple[str, str, str, str]] = []
        confidence = "medium"
        if isinstance(artefact, RankedArtefact):
            level = artefact.suspicion_level.value
            if level in {"critical", "high"}:
                confidence = "high"
            elif level in {"low", "informational"}:
                confidence = "low"

        for key, ioc_type in _IOC_FIELDS:
            value = raw.get(key)
            if value:
                indicators.append(
                    (
                        ioc_type,
                        str(value),
                        confidence,
                        f"Extracted {ioc_type} from artefact {artefact.artefact_id}",
                    )
                )

        for bag in (raw, metadata):
            extra = bag.get("ioc_indicators") or bag.get("suspicious_indicators")
            if isinstance(extra, list):
                for item in extra:
                    text = str(item).strip()
                    if text:
                        indicators.append(
                            (
                                "indicator",
                                text,
                                confidence,
                                f"Listed indicator on artefact {artefact.artefact_id}",
                            )
                        )
        return indicators
