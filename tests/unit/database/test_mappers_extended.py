"""Extended ORM/domain mapper round-trip tests."""

from __future__ import annotations

from datetime import UTC, datetime

from dfat.case_management.enums import CaseStatus, CustodyAction, EvidenceStatus
from dfat.core.enums import ArtefactCategory, EvidenceType, HashAlgorithm, SuspicionLevel
from dfat.core.models.artefact import Artefact, RankedArtefact
from dfat.core.models.case import Case, CaseInvestigator
from dfat.core.models.evidence import CaseMetadata, MemoryDump
from dfat.database.mappers import (
    artefact_domain_to_orm,
    artefact_orm_to_domain,
    case_domain_to_orm,
    case_orm_to_domain,
    custody_domain_to_orm,
    custody_orm_to_domain,
    evidence_domain_to_orm,
    evidence_metadata_domain_to_orm,
    evidence_metadata_orm_to_domain,
    evidence_orm_to_domain,
    evidence_status_domain_to_orm,
    evidence_status_orm_to_domain,
)
from dfat.database.models.case_orm import CaseInvestigatorORM
from dfat.evidence_management.models import (
    ChainOfCustodyRecord,
    EvidenceMetadataRecord,
    EvidenceStatusChange,
    HashSet,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def test_case_round_trip_with_investigators_and_nullable_json() -> None:
    # Arrange
    investigator = CaseInvestigator(
        user_id="u1",
        username="alice",
        full_name="Alice",
        role="lead",
        assigned_at=NOW,
    )
    case = Case(
        metadata=CaseMetadata(
            case_id="case-1",
            case_name="Mapper",
            investigator="Alice",
            created_at=NOW,
            description=None,
        ),
        status=CaseStatus.OPEN,
        investigators=[investigator],
        lead_investigator_id="u1",
        notes=[],
        tags=[],
    )
    orm = case_domain_to_orm(case, created_by_user_id="u1")
    orm.investigators = [
        CaseInvestigatorORM(
            id="assignment-1",
            case_id="case-1",
            user_id="u1",
            role="lead",
            assigned_at=NOW,
            is_active=True,
        )
    ]

    # Act
    restored = case_orm_to_domain(
        orm, investigator_usernames={"u1": ("alice", "Alice")}
    )

    # Assert
    assert restored.case_id == case.case_id
    assert restored.metadata.description is None
    assert restored.notes == restored.tags == []
    assert restored.investigators == [investigator]


def test_custody_mapper_round_trip() -> None:
    # Arrange
    record = ChainOfCustodyRecord(
        record_id="custody-1",
        evidence_id="ev-1",
        action=CustodyAction.ACQUIRED,
        performed_by_user_id="u1",
        performed_by_name="Alice",
        timestamp=NOW,
        reason="acquired",
        hash_at_action="a" * 64,
        notes=None,
    )

    # Act
    restored = custody_orm_to_domain(custody_domain_to_orm(record, entry_number=7))

    # Assert
    assert restored.model_dump(exclude={"entry_number"}) == record.model_dump(
        exclude={"entry_number"}
    )
    assert restored.entry_number == 7


def test_evidence_metadata_and_status_round_trips() -> None:
    # Arrange
    metadata = EvidenceMetadataRecord(
        evidence_id="ev-1",
        mime_type="application/octet-stream",
        mime_detected_from="extension",
        file_extension=".dd",
        file_size_bytes=0,
        hash_set=HashSet(
            md5="0" * 32,
            sha1="1" * 40,
            sha256="2" * 64,
            computed_at=NOW,
            file_size_bytes=0,
        ),
        is_valid_format=True,
        validation_notes=[],
        extracted_at=NOW,
    )
    status = EvidenceStatusChange(
        evidence_id="ev-1",
        previous_status=None,
        new_status=EvidenceStatus.REGISTERED,
        changed_by_user_id="u1",
        changed_at=NOW,
        reason="registered",
    )

    # Act
    metadata_orm = evidence_metadata_domain_to_orm(metadata)
    metadata_orm.created_at = NOW
    restored_metadata = evidence_metadata_orm_to_domain(metadata_orm)
    restored_status = evidence_status_orm_to_domain(
        evidence_status_domain_to_orm(status)
    )

    # Assert
    assert restored_metadata.validation_notes == []
    assert restored_metadata.hash_set == metadata.hash_set
    assert restored_status == status


def test_artefact_mapper_detects_ranked_vs_plain_and_empty_json() -> None:
    # Arrange
    plain = Artefact(
        artefact_id="art-plain",
        category=ArtefactCategory.REGISTRY_KEY,
        source_evidence_id="ev-1",
        raw_data={},
        parsed_at=NOW,
        source_path=None,
        metadata={},
    )
    ranked_payload = plain.model_dump()
    ranked_payload["artefact_id"] = "art-ranked"
    ranked = RankedArtefact(
        **ranked_payload,
        suspicion_level=SuspicionLevel.HIGH,
        relevance_score=0.75,
        classification_reasoning=None,
    )

    # Act
    restored_plain = artefact_orm_to_domain(artefact_domain_to_orm(plain, "ev-1"))
    restored_ranked = artefact_orm_to_domain(artefact_domain_to_orm(ranked, "ev-1"))

    # Assert
    assert type(restored_plain) is Artefact
    assert restored_plain.raw_data == restored_plain.metadata == {}
    assert isinstance(restored_ranked, RankedArtefact)
    assert restored_ranked.relevance_score == 0.75


def test_memory_dump_mapper_round_trip(tmp_path) -> None:
    # Arrange
    memory = MemoryDump(
        evidence_id="mem-1",
        file_path=tmp_path / "memory.raw",
        evidence_type=EvidenceType.MEMORY_DUMP,
        original_hash="f" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=0,
        case=CaseMetadata(case_id="case-1", case_name="Memory", investigator="Alice"),
        volatility_profile=None,
    )

    # Act
    restored = evidence_orm_to_domain(evidence_domain_to_orm(memory))

    # Assert
    assert isinstance(restored, MemoryDump)
    assert restored.evidence_id == memory.evidence_id
    assert restored.volatility_profile is None
