"""Shared base class for forensic artefact parsers."""

from __future__ import annotations

from abc import ABC
from datetime import UTC, datetime
from typing import Any, Optional

from dfat.core.enums import ArtefactCategory, EvidenceType, PipelineStage
from dfat.core.interfaces.parser import IArtefactParser
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.shared.constants import MAX_ARTEFACTS_PER_CATEGORY


class BaseParser(IArtefactParser, ABC):
    """Shared utilities for concrete ``IArtefactParser`` implementations.

    Subclasses must implement ``parse``, ``parser_name``, and typically
    override ``supported_categories`` / ``supported_evidence_types``.
    """

    def __init__(self, audit_logger: ForensicAuditLogger) -> None:
        """Initialise the parser.

        Args:
            audit_logger: ACPO-compliant forensic audit logger.
        """
        self._audit_logger = audit_logger
        self._max_artefacts = MAX_ARTEFACTS_PER_CATEGORY

    def supported_categories(self) -> list[ArtefactCategory]:
        """Return artefact categories this parser can produce.

        Returns:
            Empty list by default; subclasses must override.
        """
        return []

    def supported_evidence_types(self) -> list[EvidenceType]:
        """Return evidence types this parser can process.

        Returns:
            Empty list by default; subclasses must override.
        """
        return []

    def _create_artefact(
        self,
        category: ArtefactCategory,
        raw_data: dict[str, Any],
        evidence_id: str,
        source_path: Optional[str] = None,
    ) -> Artefact:
        """Factory for domain ``Artefact`` instances.

        Args:
            category: Artefact category taxonomy value.
            raw_data: Parser-specific structured payload.
            evidence_id: Source evidence identifier.
            source_path: Optional path within the evidence.

        Returns:
            Newly constructed artefact.
        """
        return Artefact(
            category=category,
            source_evidence_id=evidence_id,
            raw_data=raw_data,
            parsed_at=datetime.now(UTC),
            source_path=source_path,
            metadata={"parser": self.parser_name},
        )

    def _empty_set(self, evidence_id: str) -> ArtefactSet:
        """Return an empty artefact set for the evidence.

        Args:
            evidence_id: Source evidence identifier.

        Returns:
            Empty ``ArtefactSet``.
        """
        return ArtefactSet(
            evidence_id=evidence_id,
            artefacts=[],
            categories_present=[],
        )

    def _to_artefact_set(
        self,
        evidence_id: str,
        artefacts: list[Artefact],
    ) -> ArtefactSet:
        """Build an ``ArtefactSet`` from a list of artefacts.

        Args:
            evidence_id: Source evidence identifier.
            artefacts: Extracted artefacts (already truncated if needed).

        Returns:
            Populated artefact set with categories computed.
        """
        categories = sorted(
            {artefact.category for artefact in artefacts},
            key=lambda item: item.value,
        )
        return ArtefactSet(
            evidence_id=evidence_id,
            artefacts=artefacts,
            categories_present=categories,
        )

    def _truncate(self, artefacts: list[Artefact]) -> list[Artefact]:
        """Enforce ``MAX_ARTEFACTS_PER_CATEGORY`` on the collected list.

        Args:
            artefacts: Candidate artefacts.

        Returns:
            Truncated artefact list.
        """
        if len(artefacts) <= self._max_artefacts:
            return artefacts
        return artefacts[: self._max_artefacts]

    def _log_parse_start(self, evidence_id: str) -> None:
        """Log parser start.

        Args:
            evidence_id: Source evidence identifier.
        """
        self._audit_logger.log_action(
            stage=PipelineStage.PARSING,
            action="PARSE_START",
            evidence_id=evidence_id,
            details={"parser": self.parser_name},
        )

    def _log_parse_end(self, evidence_id: str, count: int) -> None:
        """Log parser completion.

        Args:
            evidence_id: Source evidence identifier.
            count: Number of artefacts extracted.
        """
        self._audit_logger.log_action(
            stage=PipelineStage.PARSING,
            action="PARSE_END",
            evidence_id=evidence_id,
            details={"parser": self.parser_name, "artefact_count": count},
        )

    def _log_parse_error(self, evidence_id: str, error: Exception) -> None:
        """Log parser failure.

        Args:
            evidence_id: Source evidence identifier.
            error: Exception raised during parsing.
        """
        self._audit_logger.log_action(
            stage=PipelineStage.PARSING,
            action="PARSE_ERROR",
            evidence_id=evidence_id,
            details={
                "parser": self.parser_name,
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
