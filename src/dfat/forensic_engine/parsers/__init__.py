"""DFAT Forensic Parsers — Disk, registry, browser, and event-log parsers."""

from dfat.forensic_engine.parsers.browser import BrowserHistoryParser
from dfat.forensic_engine.parsers.eventlog import EventLogParser
from dfat.forensic_engine.parsers.filesystem import FileSystemParser
from dfat.forensic_engine.parsers.registry import RegistryParser
from dfat.forensic_engine.parsers.base import BaseParser
from dfat.forensic_engine.parsers.memory.injection import CodeInjectionParser
from dfat.forensic_engine.parsers.memory.network import NetworkArtefactParser
from dfat.forensic_engine.parsers.memory.process import ProcessListParser

__all__ = [
    "BaseParser",
    "BrowserHistoryParser",
    "CodeInjectionParser",
    "EventLogParser",
    "FileSystemParser",
    "NetworkArtefactParser",
    "ProcessListParser",
    "RegistryParser",
]
