"""Analysis pipeline coordination services."""

from __future__ import annotations

from dfat.core.enums import PipelineStage
from dfat.core.exceptions import EvidenceNotFoundError, ParsingError
from dfat.core.models.artefact import ArtefactSet
from dfat.core.models.pipeline import AuditEntry, PipelineState
from dfat.core.models.report import ForensicReport
from dfat.database.repositories.artefact_repo import SQLAlchemyArtefactRepository
from dfat.database.repositories.audit_repo import SQLAlchemyAuditRepository
from dfat.database.repositories.evidence_repo import SQLAlchemyEvidenceRepository
from dfat.database.repositories.report_repo import SQLAlchemyReportRepository
from dfat.forensic_engine.acquisition.integrity import IntegrityChecker
from dfat.pipeline.enums import JobStatus
from dfat.pipeline.orchestrator import PipelineOrchestrator


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
        evidence = await self._require_evidence(evidence_id)
        self._integrity_checker.verify_integrity(
            evidence.file_path,
            evidence.original_hash,
            evidence.evidence_id,
        )
        job = await self._pipeline.execute_pipeline(
            evidence_id=evidence_id,
            case_id=evidence.case.case_id,
            user_id=user_id,
            mode="full",
            use_fallback=use_fallback,
        )
        if job.status is not JobStatus.COMPLETED:
            raise ParsingError(
                f"Pipeline job failed: {job.error_message or job.status.value}",
                context={"job_id": job.job_id, "status": job.status.value},
            )
        report = self._pipeline.get_job_report(job.job_id)
        if report is None:
            raise ParsingError(
                f"Pipeline completed without a report: {job.job_id}",
                context={"job_id": job.job_id},
            )
        artefact_set = self._pipeline.get_job_artefact_set(job.job_id)
        if artefact_set is None:
            artefact_set = ArtefactSet(
                evidence_id=evidence_id,
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
                "job_id": job.job_id,
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
        evidence = await self._require_evidence(evidence_id)
        self._integrity_checker.verify_integrity(
            evidence.file_path,
            evidence.original_hash,
            evidence.evidence_id,
        )
        job = await self._pipeline.execute_pipeline(
            evidence_id=evidence_id,
            case_id=evidence.case.case_id,
            user_id=user_id,
            mode="parse-only",
        )
        if job.status is not JobStatus.COMPLETED:
            raise ParsingError(
                f"Parse-only job failed: {job.error_message or job.status.value}",
                context={"job_id": job.job_id, "status": job.status.value},
            )
        artefact_set = self._pipeline.get_job_artefact_set(job.job_id)
        if artefact_set is None:
            raise ParsingError(
                f"Parse-only completed without artefacts: {job.job_id}",
                context={"job_id": job.job_id},
            )
        await self._artefact_repo.save(artefact_set)
        await self._audit(
            action="PARSE_ONLY_COMPLETED",
            evidence_id=evidence_id,
            user_id=user_id,
            details={
                "artefact_count": artefact_set.total_count,
                "job_id": job.job_id,
            },
        )
        return artefact_set

    async def run_triage_only(
        self,
        evidence_id: str,
        user_id: str,
        use_fallback: bool = False,
    ) -> PipelineState:
        """Parse (if needed) then run triage-only; return pipeline state."""
        evidence = await self._require_evidence(evidence_id)
        if self._pipeline._artefact_cache.get(evidence_id) is None:  # noqa: SLF001
            await self.run_parse_only(evidence_id, user_id)

        job = await self._pipeline.execute_pipeline(
            evidence_id=evidence_id,
            case_id=evidence.case.case_id,
            user_id=user_id,
            mode="triage-only",
            use_fallback=use_fallback,
        )
        state = self._pipeline.get_pipeline_state(job.job_id)
        if state is None:
            raise EvidenceNotFoundError(
                f"Pipeline state missing for job: {job.job_id}",
                context={"job_id": job.job_id},
            )
        return state

    async def get_analysis_status(self, pipeline_id: str) -> PipelineState:
        """Return pipeline state for a run ID."""
        state = self._pipeline.get_pipeline_state(pipeline_id)
        if state is None:
            raise EvidenceNotFoundError(
                f"Pipeline not found: {pipeline_id}",
                context={"pipeline_id": pipeline_id},
            )
        return state

    async def _require_evidence(self, evidence_id: str):
        """Load evidence or raise ``EvidenceNotFoundError``."""
        evidence = await self._evidence_repo.get(evidence_id)
        if evidence is None:
            raise EvidenceNotFoundError(
                f"Evidence not found: {evidence_id}",
                context={"evidence_id": evidence_id},
            )
        return evidence

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
