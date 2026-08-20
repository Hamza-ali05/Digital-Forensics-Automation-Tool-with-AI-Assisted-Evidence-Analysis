"""ORM ↔ domain Pydantic mapper utilities.

ORM models are used only by the repository layer. Domain models remain free of
database dependencies.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from dfat.case_management.enums import CaseStatus, CustodyAction, EvidenceStatus
from dfat.core.enums import (
    ArtefactCategory,
    EvidenceType,
    HashAlgorithm,
    PipelineStage,
    SuspicionLevel,
)
from dfat.core.models.artefact import Artefact, RankedArtefact
from dfat.core.models.case import Case, CaseInvestigator
from dfat.core.models.evaluation import BenchmarkResult, UsabilityResponse
from dfat.core.models.evidence import CaseMetadata, EvidenceImage, MemoryDump
from dfat.core.models.pipeline import AuditEntry
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport
from dfat.database.models.artefact_orm import ArtefactRecordORM
from dfat.database.models.audit_orm import AuditLogRecordORM
from dfat.database.models.case_orm import CaseInvestigatorORM, CaseORM
from dfat.database.models.custody_orm import ChainOfCustodyORM
from dfat.database.models.dataset_orm import DatasetRecordORM
from dfat.database.models.evaluation_orm import BenchmarkRecordORM, UsabilityRecordORM
from dfat.database.models.evidence_orm import EvidenceRecordORM
from dfat.database.models.evidence_status_orm import (
    EvidenceMetadataORM,
    EvidenceStatusHistoryORM,
)
from dfat.database.models.report_orm import ReportRecordORM
from dfat.evidence_management.models import (
    ChainOfCustodyRecord,
    EvidenceMetadataRecord,
    EvidenceStatusChange,
    HashSet,
)
from dfat.dataset_intelligence.enums import (
    DatasetCategory,
    DatasetFormat,
    DatasetStatus,
    IndexingStatus,
)
from dfat.dataset_intelligence.models import DatasetRecord

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
        audit_metadata=(
            envelope.get("audit_metadata", {})
            if isinstance(envelope, dict)
            else {}
        ),
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
        "audit_metadata": dict(domain.audit_metadata or {}),
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
        q1_rating=orm.q1_rating,
        q4_rating=orm.q4_rating,
        comparative_rating=orm.comparative_rating,
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
        q1_rating=domain.q1_rating,
        q4_rating=domain.q4_rating,
        comparative_rating=domain.comparative_rating,
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


def case_orm_to_domain(
    orm: CaseORM,
    *,
    evidence_ids: Optional[list[str]] = None,
    investigator_usernames: Optional[dict[str, tuple[str, str]]] = None,
) -> Case:
    """Convert a case ORM row (with investigators) to a domain ``Case``.

    Args:
        orm: Case ORM record (investigators relationship may be loaded).
        evidence_ids: Optional linked evidence IDs (from evidence_records).
        investigator_usernames: Optional map of user_id → (username, full_name).

    Returns:
        Domain case model wrapping ``CaseMetadata``.
    """
    name_map = investigator_usernames or {}
    investigators: list[CaseInvestigator] = []
    for assignment in orm.investigators:
        if not assignment.is_active:
            continue
        username, full_name = name_map.get(
            assignment.user_id,
            (assignment.user_id, assignment.user_id),
        )
        role = assignment.role if assignment.role in ("lead", "member") else "member"
        investigators.append(
            CaseInvestigator(
                user_id=assignment.user_id,
                username=username,
                full_name=full_name,
                role=role,  # type: ignore[arg-type]
                assigned_at=assignment.assigned_at,
            )
        )
    lead_name = "Unknown"
    if orm.lead_investigator_id and orm.lead_investigator_id in name_map:
        lead_name = name_map[orm.lead_investigator_id][1]
    elif investigators:
        leads = [inv for inv in investigators if inv.role == "lead"]
        lead_name = leads[0].full_name if leads else investigators[0].full_name

    metadata = CaseMetadata(
        case_id=orm.id,
        case_name=orm.case_name,
        investigator=lead_name,
        created_at=orm.created_at,
        description=orm.description,
    )
    return Case(
        metadata=metadata,
        status=CaseStatus(orm.status),
        investigators=investigators,
        lead_investigator_id=orm.lead_investigator_id,
        evidence_ids=list(evidence_ids or []),
        opened_at=orm.opened_at,
        closed_at=orm.closed_at,
        archived_at=orm.archived_at,
        closure_reason=orm.closure_reason,
        notes=list(_loads(orm.notes, default=[]) or []),
        tags=list(_loads(orm.tags, default=[]) or []),
    )


def case_domain_to_orm(
    domain: Case,
    *,
    created_by_user_id: str,
) -> CaseORM:
    """Convert a domain ``Case`` to an ORM row (investigators not included).

    Args:
        domain: Domain case model.
        created_by_user_id: User who created the case.

    Returns:
        Case ORM record (not yet persisted).
    """
    return CaseORM(
        id=domain.case_id,
        case_name=domain.case_name,
        description=domain.metadata.description,
        status=domain.status.value,
        lead_investigator_id=domain.lead_investigator_id,
        created_by_user_id=created_by_user_id,
        opened_at=domain.opened_at,
        closed_at=domain.closed_at,
        archived_at=domain.archived_at,
        closure_reason=domain.closure_reason,
        notes=_dumps(domain.notes),
        tags=_dumps(domain.tags),
        created_at=domain.metadata.created_at,
    )


def custody_orm_to_domain(orm: ChainOfCustodyORM) -> ChainOfCustodyRecord:
    """Convert a custody ORM row to a domain ``ChainOfCustodyRecord``."""
    return ChainOfCustodyRecord(
        record_id=orm.id,
        evidence_id=orm.evidence_id,
        action=CustodyAction(orm.action),
        performed_by_user_id=orm.performed_by_user_id,
        performed_by_name=orm.performed_by_name,
        timestamp=orm.timestamp,
        reason=orm.reason,
        hash_at_action=orm.hash_at_action,
        location=orm.location,
        notes=orm.notes,
        entry_number=orm.entry_number,
    )


def custody_domain_to_orm(
    domain: ChainOfCustodyRecord,
    *,
    entry_number: int,
) -> ChainOfCustodyORM:
    """Convert a domain custody record to an ORM row.

    Args:
        domain: Domain custody record.
        entry_number: Sequential custody entry number for the evidence.

    Returns:
        Custody ORM record (not yet persisted).
    """
    return ChainOfCustodyORM(
        id=domain.record_id,
        evidence_id=domain.evidence_id,
        action=domain.action.value,
        performed_by_user_id=domain.performed_by_user_id,
        performed_by_name=domain.performed_by_name,
        timestamp=domain.timestamp,
        reason=domain.reason,
        hash_at_action=domain.hash_at_action,
        location=domain.location,
        notes=domain.notes,
        entry_number=entry_number,
    )


def evidence_metadata_orm_to_domain(orm: EvidenceMetadataORM) -> EvidenceMetadataRecord:
    """Convert evidence metadata ORM to domain ``EvidenceMetadataRecord``."""
    hash_set = HashSet(
        md5=orm.hash_md5,
        sha1=orm.hash_sha1,
        sha256=orm.hash_sha256,
        computed_at=orm.hash_computed_at,
        file_size_bytes=orm.file_size_bytes,
    )
    extracted_at = orm.created_at if orm.created_at is not None else orm.hash_computed_at
    return EvidenceMetadataRecord(
        evidence_id=orm.evidence_id,
        mime_type=orm.mime_type,
        mime_detected_from=orm.mime_detected_from,
        file_extension=orm.file_extension,
        file_size_bytes=orm.file_size_bytes,
        file_created_at=orm.file_created_at,
        file_modified_at=orm.file_modified_at,
        file_accessed_at=orm.file_accessed_at,
        hash_set=hash_set,
        is_valid_format=orm.is_valid_format,
        validation_notes=list(_loads(orm.validation_notes, default=[]) or []),
        extracted_at=extracted_at,
    )


def evidence_metadata_domain_to_orm(
    domain: EvidenceMetadataRecord,
) -> EvidenceMetadataORM:
    """Convert domain evidence metadata to an ORM row."""
    return EvidenceMetadataORM(
        evidence_id=domain.evidence_id,
        mime_type=domain.mime_type,
        mime_detected_from=domain.mime_detected_from,
        file_extension=domain.file_extension,
        file_size_bytes=domain.file_size_bytes,
        file_created_at=domain.file_created_at,
        file_modified_at=domain.file_modified_at,
        file_accessed_at=domain.file_accessed_at,
        hash_md5=domain.hash_set.md5,
        hash_sha1=domain.hash_set.sha1,
        hash_sha256=domain.hash_set.sha256,
        hash_computed_at=domain.hash_set.computed_at,
        is_valid_format=domain.is_valid_format,
        validation_notes=_dumps(domain.validation_notes),
    )


def evidence_status_orm_to_domain(
    orm: EvidenceStatusHistoryORM,
) -> EvidenceStatusChange:
    """Convert a status-history ORM row to domain ``EvidenceStatusChange``."""
    previous: Optional[EvidenceStatus] = None
    if orm.previous_status:
        previous = EvidenceStatus(orm.previous_status)
    return EvidenceStatusChange(
        evidence_id=orm.evidence_id,
        previous_status=previous,
        new_status=EvidenceStatus(orm.new_status),
        changed_by_user_id=orm.changed_by_user_id,
        changed_at=orm.changed_at,
        reason=orm.reason,
    )


def evidence_status_domain_to_orm(
    domain: EvidenceStatusChange,
) -> EvidenceStatusHistoryORM:
    """Convert domain evidence status change to an ORM row."""
    return EvidenceStatusHistoryORM(
        evidence_id=domain.evidence_id,
        previous_status=(
            domain.previous_status.value if domain.previous_status is not None else None
        ),
        new_status=domain.new_status.value,
        changed_by_user_id=domain.changed_by_user_id,
        changed_at=domain.changed_at,
        reason=domain.reason,
    )


def dataset_orm_to_domain(orm: DatasetRecordORM) -> DatasetRecord:
    """Convert a dataset ORM row to domain ``DatasetRecord``."""
    return DatasetRecord(
        dataset_id=orm.dataset_id,
        name=orm.name,
        file_path=Path(orm.file_path),
        category=DatasetCategory(orm.category),
        format=DatasetFormat(orm.format),
        status=DatasetStatus(orm.status),
        file_size_bytes=orm.file_size_bytes,
        hash_sha256=orm.hash_sha256,
        mime_type=orm.mime_type,
        discovered_at=orm.discovered_at,
        validated_at=orm.validated_at,
        indexed_at=orm.indexed_at,
        parent_directory=orm.parent_directory,
        is_nested=orm.is_nested,
        nested_depth=orm.nested_depth,
        metadata=_loads(orm.metadata_json, default={}),
        tags=list(_loads(orm.tags_json, default=[]) or []),
        associated_research_objectives=list(
            _loads(orm.associated_research_objectives_json, default=[]) or []
        ),
        supported_forensic_modules=list(
            _loads(orm.supported_forensic_modules_json, default=[]) or []
        ),
        indexing_status=IndexingStatus(orm.indexing_status),
        preprocessing_history=list(_loads(orm.preprocessing_history_json, default=[]) or []),
        update_history=list(_loads(orm.update_history_json, default=[]) or []),
    )


def dataset_domain_to_orm(domain: DatasetRecord) -> DatasetRecordORM:
    """Convert domain ``DatasetRecord`` to a dataset ORM row."""
    metadata = dict(domain.metadata)
    deleted_at_raw = metadata.get("deleted_at")
    last_seen_raw = metadata.get("last_seen_at")
    file_modified_raw = metadata.get("file_modified_at")
    return DatasetRecordORM(
        dataset_id=domain.dataset_id,
        name=domain.name,
        file_path=str(domain.file_path),
        category=domain.category.value,
        format=domain.format.value,
        status=domain.status.value,
        file_size_bytes=domain.file_size_bytes,
        hash_sha256=domain.hash_sha256,
        mime_type=domain.mime_type,
        discovered_at=domain.discovered_at,
        validated_at=domain.validated_at,
        indexed_at=domain.indexed_at,
        parent_directory=domain.parent_directory,
        is_nested=domain.is_nested,
        nested_depth=domain.nested_depth,
        metadata_json=_dumps(domain.metadata),
        tags_json=_dumps(domain.tags),
        associated_research_objectives_json=_dumps(domain.associated_research_objectives),
        supported_forensic_modules_json=_dumps(domain.supported_forensic_modules),
        indexing_status=domain.indexing_status.value,
        preprocessing_history_json=_dumps(domain.preprocessing_history),
        update_history_json=_dumps(domain.update_history),
        is_deleted=bool(metadata.get("is_deleted", False)),
        deleted_at=deleted_at_raw if isinstance(deleted_at_raw, datetime) else None,
        last_seen_at=last_seen_raw if isinstance(last_seen_raw, datetime) else None,
        file_modified_at=(
            file_modified_raw if isinstance(file_modified_raw, datetime) else None
        ),
    )
