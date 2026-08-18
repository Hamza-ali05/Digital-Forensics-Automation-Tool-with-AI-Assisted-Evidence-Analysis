"""Dual-output report builder combining JSON and narrative layers."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Optional, Union

from dfat import __version__
from dfat.ai_engine.llm.config import PROMPT_VERSION
from dfat.ai_engine.summarization.summarizer import SummaryResult
from dfat.core.enums import PipelineStage
from dfat.core.interfaces.reporter import IReportGenerator
from dfat.core.interfaces.repository import IReportRepository
from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.core.models.evidence import CaseMetadata
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport
from dfat.reporting.integrity import ReportIntegrityVerifier
from dfat.reporting.json_layer import StructuredJSONExporter
from dfat.reporting.narrative import NarrativeAssembler
from dfat.services.audit_service import AuditService


class DualOutputReportBuilder(IReportGenerator):
    """Build, persist, and audit dual-output forensic reports."""

    def __init__(
        self,
        json_exporter: StructuredJSONExporter,
        narrative_assembler: NarrativeAssembler,
        integrity_verifier: ReportIntegrityVerifier,
        report_repo: IReportRepository,
        audit_service: AuditService,
    ) -> None:
        """Initialise the dual-output report builder.

        Args:
            json_exporter: Structured JSON exporter.
            narrative_assembler: Narrative assembler.
            integrity_verifier: Report integrity / audit-metadata helper.
            report_repo: Report persistence repository.
            audit_service: Dual-write forensic audit service.
        """
        self._json_exporter = json_exporter
        self._narrative_assembler = narrative_assembler
        self._integrity_verifier = integrity_verifier
        self._report_repo = report_repo
        self._audit_service = audit_service
        self._context_user_id: Optional[str] = None
        self._context_pipeline_job_id: Optional[str] = None
        self._context_custody_chain_length: int = 0

    def generate_json_report(
        self,
        artefact_set: ArtefactSet,
        ranked: list[RankedArtefact],
        case: CaseMetadata,
        timings: dict[str, float],
        ai_metadata: Optional[dict[str, Any]] = None,
        evidence_hash: str = "",
    ) -> JSONReport:
        """Generate the machine-readable JSON report layer.

        Args:
            artefact_set: Parsed artefact collection.
            ranked: Triaged ranked artefacts.
            case: Case metadata for the report envelope.
            timings: Pipeline stage timings in seconds.
            ai_metadata: Optional AI analysis metadata block.
            evidence_hash: Hash of the input evidence image/file.

        Returns:
            Structured JSON report.
        """
        report = self._json_exporter.export(
            artefact_set=artefact_set,
            ranked_artefacts=ranked,
            case=case,
            stage_timings=timings,
            ai_metadata=ai_metadata,
            evidence_hash=evidence_hash,
        )
        self._emit_audit(
            action="JSON_REPORT_GENERATED",
            evidence_id=report.evidence_id,
            details={
                "report_id": report.report_id,
                "integrity_hash": report.integrity_hash,
                "artefact_count": len(report.artefact_data),
                "schema_version": report.schema_version,
            },
        )
        return report

    def generate_narrative_report(
        self,
        summary_result: SummaryResult,
        llm_model: str,
        params: dict[str, Any],
        ranked: list[RankedArtefact],
        case: CaseMetadata,
        confidence: float,
    ) -> NarrativeReport:
        """Generate the human-readable narrative report.

        Args:
            summary_result: Structured LLM (or fallback) summary.
            llm_model: Local model identifier used for generation.
            params: Generation parameter snapshot.
            ranked: Triaged ranked artefacts for statistics/findings.
            case: Case metadata for the narrative header.
            confidence: Narrative confidence score in ``[0.0, 1.0]``.

        Returns:
            Narrative report artefact.
        """
        merged_params = dict(params or {})
        merged_params.setdefault("prompt_version", summary_result.prompt_version)
        merged_params.setdefault("confidence_score", confidence)
        merged_params.setdefault("evidence_id", ranked[0].source_evidence_id if ranked else "unknown")

        report = self._narrative_assembler.assemble(
            summary_result=summary_result,
            llm_model=llm_model,
            generation_params=merged_params,
            ranked_artefacts=list(ranked),
            case=case,
            confidence_score=float(confidence),
        )
        self._emit_audit(
            action="NARRATIVE_GENERATED",
            evidence_id=report.evidence_id,
            details={
                "report_id": report.report_id,
                "llm_model": report.llm_model_used,
                "confidence_score": float(confidence),
            },
        )
        return report

    def generate_full_report(
        self,
        case: CaseMetadata,
        json_report: JSONReport,
        narrative_report: NarrativeReport,
        duration: float,
        timings: dict[str, float],
    ) -> ForensicReport:
        """Combine JSON and narrative outputs into a full forensic report.

        Args:
            case: Case metadata associated with the report.
            json_report: Machine-readable report component.
            narrative_report: Human-readable report component.
            duration: End-to-end pipeline duration in seconds.
            timings: Per-stage timing map in seconds.

        Returns:
            Combined dual-output forensic report.
        """
        document = {
            "schema_version": json_report.schema_version,
            "report_id": json_report.report_id,
            "evidence_id": json_report.evidence_id,
            "integrity_hash": json_report.integrity_hash,
            "artefacts": json_report.artefact_data,
            "generated_at": json_report.generated_at.isoformat(),
        }
        enriched = self._integrity_verifier.embed_audit_metadata(
            document,
            user_id=self._context_user_id or "system",
            pipeline_job_id=self._context_pipeline_job_id or "",
            evidence_custody_chain_length=self._context_custody_chain_length,
            tool_version=str(__version__),
        )
        audit_metadata = dict(enriched.get("audit_metadata") or {})

        report = ForensicReport(
            case=case,
            json_report=json_report,
            narrative_report=narrative_report,
            pipeline_duration_seconds=duration,
            stage_timings=dict(timings),
            audit_metadata=audit_metadata,
        )
        # Persistence is performed by async callers (ReportingStage) so that
        # async SQLAlchemy repositories are correctly awaited.
        self._emit_audit(
            action="REPORT_GENERATED",
            evidence_id=json_report.evidence_id,
            details={
                "report_id": report.report_id,
                "json_report_id": json_report.report_id,
                "narrative_report_id": narrative_report.report_id,
                "integrity_hash": json_report.integrity_hash,
                "duration_seconds": duration,
                "audit_metadata": audit_metadata,
            },
        )
        return report

    async def persist_report(self, report: ForensicReport) -> str:
        """Persist ``report`` via the configured repository (await-safe)."""
        result = self._report_repo.save(report)
        if hasattr(result, "__await__"):
            return await result  # type: ignore[misc]
        return str(result)

    def build_complete_report(
        self,
        case: CaseMetadata,
        artefact_set: ArtefactSet,
        ranked: Optional[list[RankedArtefact]] = None,
        summary_result: Optional[Union[SummaryResult, str]] = None,
        llm_model: str = "",
        generation_params: Optional[dict[str, Any]] = None,
        stage_timings: Optional[dict[str, float]] = None,
        confidence: float = 0.0,
        evidence_hash: str = "",
        pipeline_job_id: str = "",
        user_id: str = "system",
        *,
        ai_metadata: Optional[dict[str, Any]] = None,
        custody_chain_length: int = 0,
        ranked_artefacts: Optional[list[RankedArtefact]] = None,
        summary_text: Optional[str] = None,
    ) -> ForensicReport:
        """Build JSON + narrative reports and return the combined result.

        This is the primary API used by ``ReportingStage``.

        Args:
            case: Case metadata.
            artefact_set: Parsed artefact set.
            ranked: Triaged ranked artefacts.
            summary_result: Structured summary or plain summary text.
            llm_model: Model identifier.
            generation_params: Generation parameter snapshot.
            stage_timings: Pipeline stage timings.
            confidence: Narrative confidence score.
            evidence_hash: Input evidence integrity hash.
            pipeline_job_id: Pipeline job identifier for audit metadata.
            user_id: Acting user identifier for audit metadata.
            ai_metadata: Optional AI metadata for the JSON layer.
            custody_chain_length: Custody-chain entry count for audit metadata.
            ranked_artefacts: Alias for ``ranked``.
            summary_text: Alias for a bare summary string.

        Returns:
            Persisted ``ForensicReport``.
        """
        ranked_list = list(
            ranked_artefacts
            if ranked_artefacts is not None
            else (ranked if ranked is not None else [])
        )
        params = dict(generation_params or {})
        timings = dict(stage_timings or {})
        self._context_user_id = user_id
        self._context_pipeline_job_id = pipeline_job_id
        self._context_custody_chain_length = int(custody_chain_length)

        if summary_result is None and summary_text is None:
            raise ValueError("build_complete_report requires summary_result or summary_text")

        resolved_summary = self._resolve_summary_result(
            summary_result=summary_result if summary_result is not None else "",
            summary_text=summary_text,
            llm_model=llm_model,
            generation_params=params,
            confidence=confidence,
        )
        resolved_confidence = float(
            confidence if confidence else resolved_summary.confidence_score
        )

        json_report = self.generate_json_report(
            artefact_set=artefact_set,
            ranked=ranked_list,
            case=case,
            timings=timings,
            ai_metadata=ai_metadata,
            evidence_hash=evidence_hash,
        )
        narrative = self.generate_narrative_report(
            summary_result=resolved_summary,
            llm_model=llm_model or resolved_summary.model_used,
            params=params,
            ranked=ranked_list,
            case=case,
            confidence=resolved_confidence,
        )
        duration = float(sum(float(value) for value in timings.values()))
        return self.generate_full_report(
            case=case,
            json_report=json_report,
            narrative_report=narrative,
            duration=duration,
            timings=timings,
        )

    def _emit_audit(
        self,
        action: str,
        evidence_id: str,
        details: dict[str, Any],
    ) -> None:
        """Emit an audit entry via ``AuditService`` (sync- or async-safe)."""
        result = self._audit_service.log_action(
            stage=PipelineStage.REPORTING,
            action=action,
            evidence_id=evidence_id,
            user_id=self._context_user_id,
            details=details,
        )
        if inspect.iscoroutine(result):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(result)
            else:
                loop.create_task(result)

    @staticmethod
    def _resolve_summary_result(
        summary_result: Union[SummaryResult, str],
        summary_text: Optional[str],
        llm_model: str,
        generation_params: dict[str, Any],
        confidence: float,
    ) -> SummaryResult:
        """Normalise string/SummaryResult inputs into a ``SummaryResult``."""
        if isinstance(summary_result, SummaryResult):
            if summary_text and not summary_result.executive_summary.strip():
                return summary_result.model_copy(
                    update={
                        "executive_summary": summary_text,
                        "full_text": summary_text,
                    }
                )
            return summary_result

        text = summary_text if summary_text is not None else str(summary_result)
        prompt_version = str(
            generation_params.get("prompt_version") or PROMPT_VERSION
        )
        return SummaryResult(
            full_text=text,
            executive_summary=text,
            key_findings=list(generation_params.get("key_findings") or []),
            timeline_narrative=generation_params.get("timeline_narrative"),
            iocs_identified=list(generation_params.get("iocs_identified") or []),
            recommended_actions=list(
                generation_params.get("recommended_actions") or []
            ),
            model_used=llm_model,
            prompt_version=prompt_version,
            generation_params=dict(generation_params),
            confidence_score=float(
                confidence or generation_params.get("confidence_score") or 0.0
            ),
        )
