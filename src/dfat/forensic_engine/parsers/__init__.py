"""DFAT Forensic Parsers — Disk, registry, browser, and event-log parsers."""

from dfat.forensic_engine.parsers.base import BaseParser
from dfat.forensic_engine.parsers.browser import BrowserHistoryParser
from dfat.forensic_engine.parsers.disk_access import DiskImageAccessor, FileEntry
from dfat.forensic_engine.parsers.eventlog import EventLogParser
from dfat.forensic_engine.parsers.filesystem import FileSystemParser
from dfat.forensic_engine.parsers.memory.injection import CodeInjectionParser
from dfat.forensic_engine.parsers.memory.network import NetworkArtefactParser
from dfat.forensic_engine.parsers.memory.process import ProcessListParser
from dfat.forensic_engine.parsers.memory.registry_mem import MemoryRegistryParser
from dfat.forensic_engine.parsers.registry import RegistryParser

__all__ = [
    "BaseParser",
    "BrowserHistoryParser",
    "CodeInjectionParser",
    "DiskImageAccessor",
    "EventLogParser",
    "FileEntry",
    "FileSystemParser",
    "MemoryRegistryParser",
    "NetworkArtefactParser",
    "ProcessListParser",
    "RegistryParser",
]
