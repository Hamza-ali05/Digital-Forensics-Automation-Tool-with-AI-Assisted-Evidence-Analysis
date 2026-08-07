"""DFAT Database — Async SQLAlchemy persistence layer."""

from dfat.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from dfat.database.engine import DatabaseEngine, engine_factory, get_async_session
from dfat.database.models import (  # noqa: F401 — register ORM tables on Base.metadata
    AIAnalysisRecordORM,
    ArtefactRecordORM,
    AuditLogRecordORM,
    BenchmarkRecordORM,
    CaseInvestigatorORM,
    CaseORM,
    ChainOfCustodyORM,
    EvidenceMetadataORM,
    EvidenceRecordORM,
    EvidenceStatusHistoryORM,
    ReportRecordORM,
    RoleORM,
    SessionORM,
    UsabilityRecordORM,
    UserORM,
)

__all__ = [
    "AIAnalysisRecordORM",
    "ArtefactRecordORM",
    "AuditLogRecordORM",
    "Base",
    "BenchmarkRecordORM",
    "CaseInvestigatorORM",
    "CaseORM",
    "ChainOfCustodyORM",
    "DatabaseEngine",
    "EvidenceMetadataORM",
    "EvidenceRecordORM",
    "EvidenceStatusHistoryORM",
    "ReportRecordORM",
    "RoleORM",
    "SessionORM",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "UsabilityRecordORM",
    "UserORM",
    "engine_factory",
    "get_async_session",
]
