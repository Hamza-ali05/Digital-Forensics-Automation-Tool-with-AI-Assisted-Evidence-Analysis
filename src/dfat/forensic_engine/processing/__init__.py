"""DFAT Forensic Engine — post-parse artefact processing helpers."""

from dfat.forensic_engine.processing.categoriser import ArtefactCategoriser
from dfat.forensic_engine.processing.correlator import ArtefactCorrelator
from dfat.forensic_engine.processing.deduplicator import ArtefactDeduplicator
from dfat.forensic_engine.processing.ioc_detector import (
    EXTERNAL_PORT_INDICATORS,
    IOCDetector,
    IOCMatch,
    SUSPICIOUS_EXTENSIONS,
    SUSPICIOUS_PROCESSES,
    SUSPICIOUS_REGISTRY_PATHS,
)
from dfat.forensic_engine.processing.relationship_mapper import (
    RelationshipMap,
    RelationshipMapper,
)
from dfat.forensic_engine.processing.standardiser import ArtefactStandardiser
from dfat.forensic_engine.processing.timeline import (
    Timeline,
    TimelineEntry,
    TimelineGenerator,
    TimelineWindow,
)

__all__ = [
    "EXTERNAL_PORT_INDICATORS",
    "ArtefactCategoriser",
    "ArtefactCorrelator",
    "ArtefactDeduplicator",
    "ArtefactStandardiser",
    "IOCDetector",
    "IOCMatch",
    "RelationshipMap",
    "RelationshipMapper",
    "SUSPICIOUS_EXTENSIONS",
    "SUSPICIOUS_PROCESSES",
    "SUSPICIOUS_REGISTRY_PATHS",
    "Timeline",
    "TimelineEntry",
    "TimelineGenerator",
    "TimelineWindow",
]
