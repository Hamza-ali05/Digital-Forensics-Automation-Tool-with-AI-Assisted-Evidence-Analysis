"""Analysis pipeline coordination services."""

from __future__ import annotations

import asyncio

from dfat.core.enums import PipelineStage
from dfat.core.exceptions import EvidenceNotFoundError
from dfat.core.models.artefact import ArtefactSet
from dfat.core.models.pipeline import AuditEntry, PipelineState
from dfat.core.models.report import ForensicReport
from dfat.database.repositories.artefact_repo import SQLAlchemyArtefactRepository
from dfat.database.repositories.audit_repo import SQLAlchemyAuditRepository
from dfat.database.repositories.evidence_repo import SQLAlchemyEvidenceRepository
from dfat.database.repositories.report_repo import SQLAlchemyReportRepository
from dfat.forensic_engine.acquisition.integrity import IntegrityChecker
from dfat.pipeline import PipelineOrchestrator


class AnalysisService:
    """Business logic coordinating forensic analysis pipeline runs."""

    def __init__(
        self,
        pipeline_orchestrator: PipelineOrchestrator,
        evidence_repo: SQLAlchemyEvidenceRepository,
        artefact_repo: SQLAlchemyArtefactRepository,
        report_repo: SQLAlchemyReportRepository,
        audit_repo: SQLAlchemyAuditRepository,
        integrity_checker: IntegrityChecker,
    ) -> None:
        """Initialise the analysis service.

        Args:
            pipeline_orchestrator: Top-level pipeline orchestrator.
            evidence_repo: Evidence repository.
            artefact_repo: Artefact repository.
            report_repo: Report repository.
            audit_repo: Database audit repository.
            integrity_checker: Hash verification service.
        """
        self._pipeline = pipeline_orchestrator
        self._evidence_repo = evidence_repo
        self._artefact_repo = artefact_repo
        self._report_repo = report_repo
        self._audit_repo = audit_repo
        self._integrity_checker = integrity_checker

    async def run_full_analysis(
        self,
        evidence_id: str,
        user_id: str,
        use_fallback: bool = False,
    ) -> ForensicReport:
        """Run the full pipeline for registered evidence.

        Args:
            evidence_id: Registered evidence identifier.
            user_id: Acting investigator user ID.
            use_fallback: Force rule-based triage.

        Returns:
            Persisted forensic report.
        """
        evidence = await self._evidence_repo.get(evidence_id)
        if evidence is None:
            raise EvidenceNotFoundError(
                f"Evidence not found: {evidence_id}",
                context={"evidence_id": evidence_id},
            )
        await asyncio.to_thread(
            self._integrity_checker.verify_integrity,
            evidence.file_path,
            evidence.original_hash,
            evidence.evidence_id,
        )
        report = await asyncio.to_thread(
            self._pipeline.run_full_pipeline,
            evidence.file_path,
            evidence.case,
            use_fallback=use_fallback,
        )
        # Pipeline caches artefacts under the acquisition evidence ID.
        pipeline_evidence_id = report.json_report.evidence_id
        artefact_set = self._pipeline._artefact_cache.get(pipeline_evidence_id)  # noqa: SLF001
        if artefact_set is None:
            artefact_set = ArtefactSet(
                evidence_id=pipeline_evidence_id,
                artefacts=[],
                categories_present=[],
            )
        await self._artefact_repo.save(artefact_set)
        await self._report_repo.save(report)
        await self._audit(
            action="ANALYSIS_COMPLETED",
            evidence_id=evidence_id,
            user_id=user_id,
            details={
                "report_id": report.report_id,
                "pipeline_evidence_id": pipeline_evidence_id,
                "use_fallback": use_fallback,
                "duration_seconds": report.pipeline_duration_seconds,
            },
        )
        return report

    async def run_parse_only(self, evidence_id: str, user_id: str) -> ArtefactSet:
        """Run acquisition and parsing only.

        Args:
            evidence_id: Registered evidence identifier.
            user_id: Acting investigator user ID.

        Returns:
            Parsed artefact set.
        """
        evidence = await self._evidence_repo.get(evidence_id)
        if evidence is None:
            raise EvidenceNotFoundError(
                f"Evidence not found: {evidence_id}",
                context={"evidence_id": evidence_id},
            )
        await asyncio.to_thread(
            self._integrity_checker.verify_integrity,
            evidence.file_path,
            evidence.original_hash,
            evidence.evidence_id,
        )
        artefact_set = await asyncio.to_thread(
            self._pipeline.run_parse_only,
            evidence.file_path,
            evidence.case,
        )
        await self._artefact_repo.save(artefact_set)
        await self._audit(
            action="PARSE_ONLY_COMPLETED",
            evidence_id=evidence_id,
            user_id=user_id,
            details={
                "artefact_count": artefact_set.total_count,
                "pipeline_evidence_id": artefact_set.evidence_id,
            },
        )
        return artefact_set

    async def get_analysis_status(self, pipeline_id: str) -> PipelineState:
        """Return pipeline state for a run ID."""
        state = self._pipeline.get_pipeline_state(pipeline_id)
        if state is None:
            raise EvidenceNotFoundError(
                f"Pipeline not found: {pipeline_id}",
                context={"pipeline_id": pipeline_id},
            )
        return state

    async def _audit(
        self,
        *,
        action: str,
        evidence_id: str,
        user_id: str,
        details: dict,
    ) -> None:
        """Append a database audit entry."""
        entry_number = await self._audit_repo.get_latest_entry_number() + 1
        entry = AuditEntry(
            entry_number=entry_number,
            stage=PipelineStage.AI_TRIAGE,
            action=action,
            evidence_id=evidence_id,
            details=details,
        )
        await self._audit_repo.log_entry(entry, user_id=user_id)
