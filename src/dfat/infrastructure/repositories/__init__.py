"""DFAT Repositories — File/JSON-backed evidence, artefact, and report repositories."""

from dfat.infrastructure.repositories.artefact_repo import JSONArtefactRepository
from dfat.infrastructure.repositories.evidence_repo import FileSystemEvidenceRepository
from dfat.infrastructure.repositories.report_repo import FileSystemReportRepository

__all__ = [
    "FileSystemEvidenceRepository",
    "FileSystemReportRepository",
    "JSONArtefactRepository",
]
