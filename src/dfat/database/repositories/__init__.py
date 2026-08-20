"""SQLAlchemy-backed repository implementations for DFAT persistence."""

from dfat.database.repositories.artefact_repo import SQLAlchemyArtefactRepository
from dfat.database.repositories.audit_repo import SQLAlchemyAuditRepository
from dfat.database.repositories.base_repo import SQLAlchemyRepository
from dfat.database.repositories.case_repo import SQLAlchemyCaseRepository
from dfat.database.repositories.custody_repo import CustodyRepository
from dfat.database.repositories.dataset_repo import DatasetRepository
from dfat.database.repositories.evaluation_repo import (
    SQLAlchemyBenchmarkRepository,
    SQLAlchemyUsabilityRepository,
)
from dfat.database.repositories.evidence_repo import SQLAlchemyEvidenceRepository
from dfat.database.repositories.evidence_status_repo import (
    EvidenceMetadataRepository,
    EvidenceStatusRepository,
)
from dfat.database.repositories.pipeline_repo import SQLAlchemyPipelineRepository
from dfat.database.repositories.report_repo import SQLAlchemyReportRepository
from dfat.database.repositories.session_repo import SessionRepository
from dfat.database.repositories.user_repo import SQLAlchemyUserRepository

__all__ = [
    "CustodyRepository",
    "DatasetRepository",
    "EvidenceMetadataRepository",
    "EvidenceStatusRepository",
    "SQLAlchemyArtefactRepository",
    "SQLAlchemyAuditRepository",
    "SQLAlchemyBenchmarkRepository",
    "SQLAlchemyCaseRepository",
    "SQLAlchemyEvidenceRepository",
    "SQLAlchemyPipelineRepository",
    "SQLAlchemyReportRepository",
    "SQLAlchemyRepository",
    "SQLAlchemyUsabilityRepository",
    "SQLAlchemyUserRepository",
    "SessionRepository",
]
