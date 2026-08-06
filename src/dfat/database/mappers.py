"""ORM ↔ domain Pydantic mapper utilities.

ORM models are used only by the repository layer. Domain models remain free of
database dependencies.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from dfat.core.enums import (
    ArtefactCategory,
    EvidenceType,
    HashAlgorithm,
    PipelineStage,
    SuspicionLevel,
)
from dfat.core.models.artefact import Artefact, RankedArtefact
from dfat.core.models.evaluation import BenchmarkResult, UsabilityResponse
from dfat.core.models.evidence import CaseMetadata, EvidenceImage, MemoryDump
from dfat.core.models.pipeline import AuditEntry
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport
from dfat.database.models.artefact_orm import ArtefactRecordORM
from dfat.database.models.audit_orm import AuditLogRecordORM
from dfat.database.models.evaluation_orm import BenchmarkRecordORM, UsabilityRecordORM
from dfat.database.models.evidence_orm import EvidenceRecordORM
from dfat.database.models.report_orm import ReportRecordORM


def _dumps(payload: Any) -> str:
    """Serialise a JSON-compatible payload to a text column value."""
    return json.dumps(payload, default=str, sort_keys=True)


def _loads(raw: str, default: Any = None) -> Any:
    """Deserialise a JSON text column value."""
    if not raw:
        return {} if default is None else default
    return json.loads(raw)


def evidence_orm_to_domain(orm: EvidenceRecordORM) -> EvidenceImage:
    """Convert an evidence ORM row to a domain ``EvidenceImage`` / ``MemoryDump``.

    Args:
        orm: Evidence ORM record.

    Returns:
        Domain evidence model (``MemoryDump`` when a Volatility profile is set).
    """
    case = CaseMetadata(
        case_id=orm.case_id,
        case_name=orm.case_name,
        investigator=orm.investigator,
        description=orm.description,
    )
    common: dict[str, Any] = {
        "evidence_id": orm.id,
        "file_path": Path(orm.file_path),
        "evidence_type": EvidenceType(orm.evidence_type),
        "original_hash": orm.original_hash,
        "hash_algorithm": HashAlgorithm(orm.hash_algorithm),
        "file_size_bytes": orm.file_size_bytes,
        "acquired_at": orm.acquired_at,
        "case": case,
    }
    if orm.volatility_profile is not None or orm.evidence_type == EvidenceType.MEMORY_DUMP.value:
        return MemoryDump(**common, volatility_profile=orm.volatility_profile)
    return EvidenceImage(**common)


def evidence_domain_to_orm(
    domain: EvidenceImage,
    *,
    registered_by: Optional[str] = None,
) -> EvidenceRecordORM:
    """Convert a domain evidence model to an ORM row.

    Args:
        domain: Domain evidence image or memory dump.
        registered_by: Optional registering user ID.

    Returns:
        Evidence ORM record (not yet persisted).
    """
    volatility_profile: Optional[str] = None
    if isinstance(domain, MemoryDump):
        volatility_profile = domain.volatility_profile
    return EvidenceRecordORM(
        id=domain.evidence_id,
        case_id=domain.case.case_id,
        case_name=domain.case.case_name,
        investigator=domain.case.investigator,
        file_path=str(domain.file_path),
        evidence_type=domain.evidence_type.value,
        original_hash=domain.original_hash,
        hash_algorithm=domain.hash_algorithm.value,
        file_size_bytes=domain.file_size_bytes,
        acquired_at=domain.acquired_at,
        volatility_profile=volatility_profile,
        description=domain.case.description,
        registered_by=registered_by,
    )


def artefact_orm_to_domain(orm: ArtefactRecordORM) -> Artefact:
    """Convert an artefact ORM row to a domain ``Artefact`` / ``RankedArtefact``.

    Args:
        orm: Artefact ORM record.

    Returns:
        Domain artefact (ranked when triage fields are present).
    """
    base: dict[str, Any] = {
        "artefact_id": orm.id,
        "category": ArtefactCategory(orm.category),
        "source_evidence_id": orm.evidence_id,
        "raw_data": _loads(orm.raw_data, default={}),
        "parsed_at": orm.parsed_at,
        "source_path": orm.source_path,
        "metadata": _loads(orm.metadata_json, default={}),
    }
    if orm.suspicion_level is not None and orm.relevance_score is not None:
        return RankedArtefact(
            **base,
            suspicion_level=SuspicionLevel(orm.suspicion_level),
            relevance_score=orm.relevance_score,
            classification_reasoning=orm.classification_reasoning,
        )
    return Artefact(**base)


def artefact_domain_to_orm(
    domain: Artefact,
    evidence_id: str,
) -> ArtefactRecordORM:
    """Convert a domain artefact to an ORM row.

    Args:
        domain: Domain artefact or ranked artefact.
        evidence_id: Parent evidence record ID.

    Returns:
        Artefact ORM record (not yet persisted).
    """
    suspicion: Optional[str] = None
    relevance: Optional[float] = None
    reasoning: Optional[str] = None
    if isinstance(domain, RankedArtefact):
        suspicion = domain.suspicion_level.value
        relevance = domain.relevance_score
        reasoning = domain.classification_reasoning
    return ArtefactRecordORM(
        id=domain.artefact_id,
        evidence_id=evidence_id,
        category=domain.category.value,
        source_path=domain.source_path,
        raw_data=_dumps(domain.raw_data),
        parsed_at=domain.parsed_at,
        suspicion_level=suspicion,
        relevance_score=relevance,
        classification_reasoning=reasoning,
        metadata_json=_dumps(domain.metadata),
    )


def report_orm_to_domain(orm: ReportRecordORM) -> ForensicReport:
    """Convert a report ORM row to a domain ``ForensicReport``.

    Args:
        orm: Report ORM record.

    Returns:
        Domain forensic report.
    """
    envelope = _loads(orm.json_report_data, default={})
    if isinstance(envelope, dict) and "json_report" in envelope:
        case_data = envelope.get("case", {})
        json_data = envelope.get("json_report", {})
        narrative_meta = envelope.get("narrative_report", {})
    else:
        case_data = {"case_id": orm.case_id, "case_name": "Unknown", "investigator": "Unknown"}
        json_data = envelope if isinstance(envelope, dict) else {}
        narrative_meta = {}

    case = CaseMetadata.model_validate(
        {
            "case_id": case_data.get("case_id", orm.case_id),
            "case_name": case_data.get("case_name", "Unknown"),
            "investigator": case_data.get("investigator", "Unknown"),
            "description": case_data.get("description"),
            "created_at": case_data.get("created_at"),
        }
        if case_data.get("created_at") is not None
        else {
            "case_id": case_data.get("case_id", orm.case_id),
            "case_name": case_data.get("case_name", "Unknown"),
            "investigator": case_data.get("investigator", "Unknown"),
            "description": case_data.get("description"),
        }
    )
    json_report = JSONReport.model_validate(
        {
            **json_data,
            "evidence_id": json_data.get("evidence_id", orm.evidence_id),
            "integrity_hash": json_data.get("integrity_hash", orm.integrity_hash),
            "schema_version": json_data.get("schema_version", orm.schema_version),
        }
    )
    narrative = NarrativeReport(
        report_id=str(narrative_meta.get("report_id", orm.id)),
        evidence_id=orm.evidence_id,
        summary_text=orm.narrative_text,
        llm_model_used=orm.llm_model_used,
        generation_parameters=_loads(orm.generation_parameters, default={}),
        generated_at=narrative_meta.get("generated_at", json_report.generated_at),
    )
    return ForensicReport(
        report_id=orm.id,
        case=case,
        json_report=json_report,
        narrative_report=narrative,
        pipeline_duration_seconds=orm.pipeline_duration_seconds,
        stage_timings=_loads(orm.stage_timings, default={}),
    )


def report_domain_to_orm(domain: ForensicReport) -> ReportRecordORM:
    """Convert a domain forensic report to an ORM row.

    Args:
        domain: Domain forensic report.

    Returns:
        Report ORM record (not yet persisted).
    """
    envelope = {
        "case": domain.case.model_dump(mode="json"),
        "json_report": domain.json_report.model_dump(mode="json"),
        "narrative_report": {
            "report_id": domain.narrative_report.report_id,
            "generated_at": domain.narrative_report.generated_at.isoformat(),
        },
    }
    return ReportRecordORM(
        id=domain.report_id,
        case_id=domain.case.case_id,
        evidence_id=domain.json_report.evidence_id,
        json_report_data=_dumps(envelope),
        narrative_text=domain.narrative_report.summary_text,
        llm_model_used=domain.narrative_report.llm_model_used,
        generation_parameters=_dumps(domain.narrative_report.generation_parameters),
        integrity_hash=domain.json_report.integrity_hash,
        schema_version=domain.json_report.schema_version,
        pipeline_duration_seconds=domain.pipeline_duration_seconds,
        stage_timings=_dumps(domain.stage_timings),
    )


def benchmark_orm_to_domain(orm: BenchmarkRecordORM) -> BenchmarkResult:
    """Convert a benchmark ORM row to a domain ``BenchmarkResult``.

    Args:
        orm: Benchmark ORM record.

    Returns:
        Domain benchmark result.
    """
    return BenchmarkResult(
        benchmark_id=orm.id,
        dataset_name=orm.dataset_name,
        precision=orm.precision_val,
        recall=orm.recall_val,
        f1_score=orm.f1_score,
        time_to_triage_seconds=orm.time_to_triage_seconds,
        artefacts_expected=orm.artefacts_expected,
        artefacts_recovered=orm.artefacts_recovered,
        false_positives=orm.false_positives,
        false_negatives=orm.false_negatives,
        evaluated_at=orm.evaluated_at,
    )


def benchmark_domain_to_orm(
    domain: BenchmarkResult,
    *,
    evidence_id: Optional[str] = None,
) -> BenchmarkRecordORM:
    """Convert a domain benchmark result to an ORM row.

    Args:
        domain: Domain benchmark result.
        evidence_id: Optional related evidence ID.

    Returns:
        Benchmark ORM record (not yet persisted).
    """
    return BenchmarkRecordORM(
        id=domain.benchmark_id,
        dataset_name=domain.dataset_name,
        evidence_id=evidence_id,
        precision_val=domain.precision,
        recall_val=domain.recall,
        f1_score=domain.f1_score,
        time_to_triage_seconds=domain.time_to_triage_seconds,
        artefacts_expected=domain.artefacts_expected,
        artefacts_recovered=domain.artefacts_recovered,
        false_positives=domain.false_positives,
        false_negatives=domain.false_negatives,
        evaluated_at=domain.evaluated_at,
    )


def usability_orm_to_domain(orm: UsabilityRecordORM) -> UsabilityResponse:
    """Convert a usability ORM row to a domain ``UsabilityResponse``.

    Args:
        orm: Usability ORM record.

    Returns:
        Domain usability response.
    """
    return UsabilityResponse(
        response_id=orm.id,
        participant_id=orm.participant_id,
        usefulness_rating=orm.usefulness_rating,
        accuracy_rating=orm.accuracy_rating,
        clarity_rating=orm.clarity_rating,
        free_text_feedback=orm.free_text_feedback,
        submitted_at=orm.submitted_at,
    )


def usability_domain_to_orm(domain: UsabilityResponse) -> UsabilityRecordORM:
    """Convert a domain usability response to an ORM row.

    Args:
        domain: Domain usability response.

    Returns:
        Usability ORM record (not yet persisted).
    """
    return UsabilityRecordORM(
        id=domain.response_id,
        participant_id=domain.participant_id,
        usefulness_rating=domain.usefulness_rating,
        accuracy_rating=domain.accuracy_rating,
        clarity_rating=domain.clarity_rating,
        free_text_feedback=domain.free_text_feedback,
        submitted_at=domain.submitted_at,
    )


def audit_orm_to_domain(orm: AuditLogRecordORM) -> AuditEntry:
    """Convert an audit ORM row to a domain ``AuditEntry``.

    Args:
        orm: Audit log ORM record.

    Returns:
        Domain audit entry.
    """
    return AuditEntry(
        entry_number=orm.entry_number,
        timestamp=orm.timestamp,
        stage=PipelineStage(orm.stage),
        action=orm.action,
        evidence_id=orm.evidence_id or "",
        hash_before=orm.hash_before,
        hash_after=orm.hash_after,
        details=_loads(orm.details, default={}),
    )


def audit_domain_to_orm(
    domain: AuditEntry,
    *,
    user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> AuditLogRecordORM:
    """Convert a domain audit entry to an ORM row.

    Args:
        domain: Domain audit entry.
        user_id: Optional acting user ID.
        ip_address: Optional client IP.

    Returns:
        Audit ORM record (not yet persisted).
    """
    return AuditLogRecordORM(
        entry_number=domain.entry_number,
        timestamp=domain.timestamp,
        stage=domain.stage.value,
        action=domain.action,
        evidence_id=domain.evidence_id or None,
        user_id=user_id,
        hash_before=domain.hash_before,
        hash_after=domain.hash_after,
        details=_dumps(domain.details),
        ip_address=ip_address,
    )
