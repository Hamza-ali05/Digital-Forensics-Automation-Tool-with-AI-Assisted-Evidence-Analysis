"""DFAT Core Interfaces — Abstract ports implemented by engines and infrastructure."""

from dfat.core.interfaces.analyzer import IArtefactAnalyzer
from dfat.core.interfaces.case_repository import ICaseRepository
from dfat.core.interfaces.evaluator import IEvaluator
from dfat.core.interfaces.parser import IArtefactParser
from dfat.core.interfaces.reporter import IReportGenerator
from dfat.core.interfaces.repository import (
    IArtefactRepository,
    IEvidenceRepository,
    IReportRepository,
    IRepository,
)

__all__ = [
    "IArtefactAnalyzer",
    "IArtefactParser",
    "IArtefactRepository",
    "ICaseRepository",
    "IEvaluator",
    "IEvidenceRepository",
    "IReportGenerator",
    "IReportRepository",
    "IRepository",
]
