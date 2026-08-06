"""Forensic orchestrator — Stage 1–2 routing, parsing, and normalisation."""

from __future__ import annotations

from pathlib import Path

from dfat.core.enums import EvidenceType, PipelineStage
from dfat.core.exceptions import ParsingError, UnsupportedFormatError
from dfat.core.interfaces.parser import IArtefactParser
from dfat.core.models.artefact import ArtefactSet
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.core.validators import (
    SUPPORTED_DISK_EXTENSIONS,
    SUPPORTED_MEMORY_EXTENSIONS,
)
from dfat.forensic_engine.acquisition.image_handler import DiskImageHandler
from dfat.forensic_engine.acquisition.integrity import IntegrityChecker
from dfat.forensic_engine.acquisition.memory_handler import MemoryDumpHandler
from dfat.forensic_engine.normalizer import ArtefactNormalizer
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.shared.timing import PerformanceTimer

_DISK_ONLY = {".dd", ".e01", ".img", ".001"}
_MEMORY_ONLY = {".vmem", ".dmp", ".mem"}


class ForensicOrchestrator:
    """Route evidence to parsers and produce a unified artefact set."""

    def __init__(
        self,
        parsers: list[IArtefactParser],
        normalizer: ArtefactNormalizer,
        integrity_checker: IntegrityChecker,
        disk_handler: DiskImageHandler,
        memory_handler: MemoryDumpHandler,
        audit_logger: ForensicAuditLogger,
    ) -> None:
        """Initialise the forensic orchestrator.

        Args:
            parsers: Registered artefact parsers.
            normalizer: Artefact merge/dedup service.
            integrity_checker: Evidence integrity service.
            disk_handler: Disk image acquisition handler.
            memory_handler: Memory dump acquisition handler.
            audit_logger: ACPO-compliant forensic audit logger.
        """
        self._parsers = parsers
        self._normalizer = normalizer
        self._integrity_checker = integrity_checker
        self._disk_handler = disk_handler
        self._memory_handler = memory_handler
        self._audit_logger = audit_logger

    def process_evidence(
        self,
        evidence_path: Path,
        case: CaseMetadata,
    ) -> tuple[EvidenceImage, ArtefactSet]:
        """Acquire evidence, run matching parsers, and normalise results.

        Individual parser failures are logged and skipped (graceful degradation).

        Args:
            evidence_path: Path to disk image or memory dump.
            case: Case metadata to associate with the evidence.

        Returns:
            Tuple of loaded evidence metadata and normalised artefact set.

        Raises:
            UnsupportedFormatError: If the extension is not supported.
        """
        with PerformanceTimer() as total_timer:
            evidence_type = self._detect_evidence_type(evidence_path)
            self._audit_logger.log_action(
                stage=PipelineStage.PARSING,
                action="ORCHESTRATOR_START",
                evidence_id="pending",
                details={
                    "path": str(evidence_path),
                    "evidence_type": evidence_type.value,
                },
            )

            with PerformanceTimer() as load_timer:
                if evidence_type is EvidenceType.DISK_IMAGE:
                    evidence = self._disk_handler.load_image(evidence_path, case)
                else:
                    evidence = self._memory_handler.load_dump(evidence_path, case)

            self._integrity_checker.verify_integrity(
                evidence.file_path,
                evidence.original_hash,
                evidence.evidence_id,
            )

            selected = [
                parser
                for parser in self._parsers
                if evidence_type in parser.supported_evidence_types()
            ]
            self._audit_logger.log_action(
                stage=PipelineStage.PARSING,
                action="PARSERS_SELECTED",
                evidence_id=evidence.evidence_id,
                details={
                    "parsers": [parser.parser_name for parser in selected],
                    "load_seconds": load_timer.elapsed_seconds,
                },
            )

            parser_results: list[ArtefactSet] = []
            for parser in selected:
                with PerformanceTimer() as parser_timer:
                    try:
                        result = parser.parse(evidence)
                        parser_results.append(result)
                        self._audit_logger.log_action(
                            stage=PipelineStage.PARSING,
                            action="PARSER_SUCCESS",
                            evidence_id=evidence.evidence_id,
                            details={
                                "parser": parser.parser_name,
                                "artefact_count": result.total_count,
                                "duration_seconds": parser_timer.elapsed_seconds,
                            },
                        )
                    except (ParsingError, ImportError, Exception) as exc:
                        self._audit_logger.log_action(
                            stage=PipelineStage.PARSING,
                            action="PARSER_FAILURE",
                            evidence_id=evidence.evidence_id,
                            details={
                                "parser": parser.parser_name,
                                "error_type": type(exc).__name__,
                                "error": str(exc),
                                "duration_seconds": parser_timer.elapsed_seconds,
                            },
                        )
                        continue

            artefact_set = self._normalizer.normalize(
                parser_results,
                evidence.evidence_id,
            )
            self._audit_logger.log_action(
                stage=PipelineStage.PARSING,
                action="ORCHESTRATOR_COMPLETE",
                evidence_id=evidence.evidence_id,
                hash_before=evidence.original_hash,
                hash_after=evidence.original_hash,
                details={
                    "artefact_count": artefact_set.total_count,
                    "categories": [c.value for c in artefact_set.categories_present],
                    "duration_seconds": total_timer.elapsed_seconds,
                },
            )
            return evidence, artefact_set

    def _detect_evidence_type(self, evidence_path: Path) -> EvidenceType:
        """Infer evidence type from the file extension.

        Args:
            evidence_path: Path to the evidence file.

        Returns:
            Detected evidence type.

        Raises:
            UnsupportedFormatError: If the extension is unsupported.
        """
        extension = evidence_path.suffix.lower()
        if extension in _MEMORY_ONLY:
            return EvidenceType.MEMORY_DUMP
        if extension in _DISK_ONLY:
            return EvidenceType.DISK_IMAGE
        if extension == ".raw":
            # Shared extension: treat as memory dump by default.
            return EvidenceType.MEMORY_DUMP
        if extension in {e.lower() for e in SUPPORTED_DISK_EXTENSIONS}:
            return EvidenceType.DISK_IMAGE
        if extension in {e.lower() for e in SUPPORTED_MEMORY_EXTENSIONS}:
            return EvidenceType.MEMORY_DUMP
        raise UnsupportedFormatError(
            f"Unsupported evidence extension: {extension}",
            context={"path": str(evidence_path)},
        )
