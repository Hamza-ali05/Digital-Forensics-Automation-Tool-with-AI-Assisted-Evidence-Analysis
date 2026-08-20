"""SQLAlchemy ORM models for DFAT persistence (Alembic auto-detect target)."""

from dfat.database.models.ai_orm import AIAnalysisRecordORM
from dfat.database.models.artefact_orm import ArtefactRecordORM
from dfat.database.models.audit_orm import AuditLogRecordORM
from dfat.database.models.case_orm import CaseInvestigatorORM, CaseORM
from dfat.database.models.custody_orm import ChainOfCustodyORM
from dfat.database.models.dataset_orm import DatasetRecordORM
from dfat.database.models.evaluation_orm import BenchmarkRecordORM, UsabilityRecordORM
from dfat.database.models.ml_orm import MLExperimentORM, MLModelRecordORM
from dfat.database.models.evidence_orm import EvidenceRecordORM
from dfat.database.models.evidence_status_orm import (
    EvidenceMetadataORM,
    EvidenceStatusHistoryORM,
)
from dfat.database.models.pipeline_orm import PipelineJobORM
from dfat.database.models.report_orm import ReportRecordORM
from dfat.database.models.session_orm import SessionORM
from dfat.database.models.user import RoleORM, UserORM

__all__ = [
    "AIAnalysisRecordORM",
    "ArtefactRecordORM",
    "AuditLogRecordORM",
    "BenchmarkRecordORM",
    "CaseInvestigatorORM",
    "CaseORM",
    "ChainOfCustodyORM",
    "DatasetRecordORM",
    "EvidenceMetadataORM",
    "EvidenceRecordORM",
    "EvidenceStatusHistoryORM",
    "MLExperimentORM",
    "MLModelRecordORM",
    "PipelineJobORM",
    "ReportRecordORM",
    "RoleORM",
    "SessionORM",
    "UsabilityRecordORM",
    "UserORM",
]
