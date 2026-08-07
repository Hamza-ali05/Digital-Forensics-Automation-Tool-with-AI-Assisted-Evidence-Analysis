"""Stage 1 — acquire and verify forensic evidence for pipeline processing."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from dfat.case_management.enums import EvidenceStatus
from dfat.core.enums import PipelineStage
from dfat.core.exceptions import EvidenceNotFoundError, IntegrityVerificationError
from dfat.core.models.pipeline import StageResult
from dfat.evidence_management.custody_service import ChainOfCustodyService
from dfat.evidence_management.exceptions import InvalidEvidenceTransitionError
from dfat.evidence_management.models import HashSet
from dfat.pipeline.evidence_loader import EvidenceLoader, LoadedEvidence
from dfat.pipeline.progress_tracker import ProgressNotFoundError, ProgressTracker
from dfat.pipeline.stage_interface import IPipelineStage, PipelineContext
from dfat.services.audit_service import AuditService
from dfat.services.evidence_management_service import EvidenceManagementService

logger = logging.getLogger(__name__)


class AcquisitionStage(IPipelineStage):
    """Load, verify, and open evidence for downstream parsing stages."""

    def __init__(
        self,
        evidence_loader: EvidenceLoader,
        evidence_management_service: EvidenceManagementService,
        custody_service: ChainOfCustodyService,
        progress_tracker: ProgressTracker,
        audit_service: AuditService,
    ) -> None:
        """Initialise the acquisition stage.

        Args:
            evidence_loader: Opens evidence into parser-ready handler contexts.
            evidence_management_service: Integrity verification and status transitions.
            custody_service: Chain-of-custody recorder (ACCESSED actions).
            progress_tracker: Job/stage progress tracker.
            audit_service: Dual-write audit trail service.
        """
        self._loader = evidence_loader
        self._evidence_mgmt = evidence_management_service
        self._custody = custody_service
        self._progress = progress_tracker
        self._audit = audit_service

    @property
    def stage_name(self) -> PipelineStage:
        """Return ``PipelineStage.ACQUISITION``."""
        return PipelineStage.ACQUISITION

    @property
    def description(self) -> str:
        """Return a human-readable description of this stage."""
        return "Acquire and verify forensic evidence for analysis"

    async def validate_preconditions(self, context: PipelineContext) -> bool:
        """Require a job with a non-empty evidence identifier."""
        return bool(context.job.evidence_id)

    async def execute(self, context: PipelineContext) -> StageResult:
        """Verify integrity, record custody, load evidence, and update context.

        Steps:
            1. Load evidence metadata by ``job.evidence_id``.
            2. Verify integrity via ``EvidenceManagementService``.
            3. Record an ACCESSED custody action (if not already recorded by verify).
            4. Load evidence via ``EvidenceLoader``.
            5. Transition evidence status to ``PROCESSING``.
            6. Store loaded evidence on the pipeline context.
            7. Return ``StageResult``.

        Args:
            context: Shared pipeline context.

        Returns:
            ``StageResult`` for the acquisition stage.
        """
        started = time.perf_counter()
        errors: list[str] = []
        job = context.job
        evidence_id = job.evidence_id
        user_id = job.user_id
        user_name = str(context.metadata.get("user_name") or user_id)

        self._ensure_progress_job(job.job_id)
        self._progress.start_stage(job.job_id, self.stage_name, parser_count=0)

        await self._audit.log_action(
            stage=self.stage_name,
            action="ACQUISITION_STAGE_STARTED",
            evidence_id=evidence_id,
            user_id=user_id,
            details={"job_id": job.job_id, "case_id": job.case_id},
        )

        try:
            # 1. Load evidence metadata
            detail = await self._evidence_mgmt.get_evidence_detail(evidence_id)
            evidence = detail["evidence"]

            # 2. Verify integrity (also records ACCESSED when verification passes)
            verification = await self._evidence_mgmt.verify_evidence(
                evidence_id,
                user_id,
                user_name,
            )
            if not verification.get("integrity_verified"):
                discrepancies = verification.get("discrepancies") or {}
                sha = discrepancies.get("sha256") or {}
                raise IntegrityVerificationError(
                    f"Evidence integrity verification failed: {evidence_id}",
                    expected_hash=str(sha.get("expected") or evidence.original_hash),
                    actual_hash=str(sha.get("actual") or ""),
                    context={"evidence_id": evidence_id},
                )

            # 3. Ensure ACCESSED custody is recorded (verify_evidence usually does this)
            if verification.get("custody_record") is None:
                await self._custody.record_access(
                    evidence_id,
                    evidence.file_path,
                    user_id,
                    user_name,
                    reason="Pipeline acquisition stage access",
                )

            # 4. Load evidence into handler context
            hash_set = self._hash_set_from_verification(verification)
            loaded: LoadedEvidence = await self._loader.load_evidence(
                evidence,
                hash_set=hash_set,
            )

            # 5. Transition status to PROCESSING
            await self._transition_to_processing(evidence_id, user_id)

            # 6. Store on context
            context.evidence = loaded.evidence
            context.metadata["loaded_evidence"] = {
                "evidence_id": loaded.evidence.evidence_id,
                "evidence_type": loaded.evidence_type.value,
                "integrity_verified": loaded.integrity_verified,
                "loaded_at": loaded.loaded_at.isoformat(),
                "handler_keys": sorted(loaded.handler_context.keys()),
            }
            context.metadata["handler_context"] = loaded.handler_context
            context.metadata["acquisition_verification"] = {
                key: value
                for key, value in verification.items()
                if key != "custody_record"
            }

            duration = time.perf_counter() - started
            context.stage_timings[self.stage_name.value] = duration
            self._progress.complete_stage(job.job_id, self.stage_name, artefacts_found=0)

            await self._audit.log_action(
                stage=self.stage_name,
                action="ACQUISITION_STAGE_COMPLETED",
                evidence_id=evidence_id,
                user_id=user_id,
                details={
                    "job_id": job.job_id,
                    "integrity_verified": loaded.integrity_verified,
                    "evidence_type": loaded.evidence_type.value,
                },
            )

            return StageResult(
                stage=self.stage_name,
                success=True,
                duration_seconds=duration,
                output_data={
                    "evidence_id": evidence_id,
                    "evidence_type": loaded.evidence_type.value,
                    "integrity_verified": loaded.integrity_verified,
                    "path": str(loaded.evidence.file_path),
                },
                errors=errors,
            )
        except Exception as exc:  # noqa: BLE001 — stage-level failure
            duration = time.perf_counter() - started
            errors.append(str(exc))
            logger.exception("Acquisition stage failed for job %s", job.job_id)
            await self._audit.log_action(
                stage=self.stage_name,
                action="ACQUISITION_STAGE_FAILED",
                evidence_id=evidence_id,
                user_id=user_id,
                details={"job_id": job.job_id, "error": str(exc)},
            )
            return StageResult(
                stage=self.stage_name,
                success=False,
                duration_seconds=duration,
                output_data=None,
                errors=errors,
            )

    async def _transition_to_processing(self, evidence_id: str, user_id: str) -> None:
        """Move evidence to ``PROCESSING``, tolerating an already-active state."""
        try:
            await self._evidence_mgmt.transition_evidence_status(
                evidence_id,
                EvidenceStatus.PROCESSING,
                user_id,
                reason="Pipeline acquisition stage started processing",
            )
        except InvalidEvidenceTransitionError as exc:
            detail = await self._evidence_mgmt.get_evidence_detail(evidence_id)
            current = detail.get("status")
            if current == EvidenceStatus.PROCESSING.value or current == EvidenceStatus.PROCESSING:
                logger.info(
                    "Evidence %s already in PROCESSING; continuing acquisition",
                    evidence_id,
                )
                return
            raise EvidenceNotFoundError(
                f"Cannot transition evidence {evidence_id} to PROCESSING: {exc}",
                context={
                    "evidence_id": evidence_id,
                    "current_status": current,
                },
            ) from exc

    @staticmethod
    def _hash_set_from_verification(verification: dict[str, Any]) -> Optional[HashSet]:
        """Rebuild a ``HashSet`` from verification payload when available."""
        raw = verification.get("hash_set")
        if not isinstance(raw, dict):
            return None
        try:
            return HashSet.model_validate(raw)
        except Exception:  # noqa: BLE001
            return None

    def _ensure_progress_job(self, job_id: str) -> None:
        """Ensure progress tracking has been initialised for ``job_id``."""
        try:
            self._progress.get_progress(job_id)
        except ProgressNotFoundError:
            self._progress.start_job(job_id, total_stages=5)
