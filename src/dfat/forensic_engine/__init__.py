"""DFAT Forensic Engine — Acquisition and artefact parsing (stages 1–2)."""

from dfat.forensic_engine.acquisition import (
    DiskImageHandler,
    IntegrityChecker,
    MemoryDumpHandler,
)
from dfat.forensic_engine.normalizer import ArtefactNormalizer
from dfat.forensic_engine.orchestrator import ForensicOrchestrator
from dfat.forensic_engine.parsers import (
    BrowserHistoryParser,
    CodeInjectionParser,
    EventLogParser,
    FileSystemParser,
    NetworkArtefactParser,
    ProcessListParser,
    RegistryParser,
)

__all__ = [
    "ArtefactNormalizer",
    "BrowserHistoryParser",
    "CodeInjectionParser",
    "DiskImageHandler",
    "EventLogParser",
    "FileSystemParser",
    "ForensicOrchestrator",
    "IntegrityChecker",
    "MemoryDumpHandler",
    "NetworkArtefactParser",
    "ProcessListParser",
    "RegistryParser",
]
