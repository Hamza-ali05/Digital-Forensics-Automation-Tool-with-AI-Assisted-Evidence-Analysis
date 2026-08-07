"""Shared base class for forensic artefact parsers."""

from __future__ import annotations

import importlib
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Optional

from dfat.core.enums import ArtefactCategory, EvidenceType, PipelineStage
from dfat.core.exceptions import ParsingError
from dfat.core.interfaces.parser import IArtefactParser
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.core.models.evidence import EvidenceImage
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.shared.constants import MAX_ARTEFACTS_PER_CATEGORY


class BaseParser(IArtefactParser, ABC):
    """Template-method base for concrete ``IArtefactParser`` implementations.

    Subclasses implement ``_do_parse``, ``parser_name``, and typically
    override ``supported_categories`` / ``supported_evidence_types``.
    """

    #: Exception type used when ``_safe_parse`` wraps unexpected failures.
    _parse_error_class: type[ParsingError] = ParsingError

    def __init__(
        self,
        audit_logger: ForensicAuditLogger,
        max_artefacts: int = MAX_ARTEFACTS_PER_CATEGORY,
    ) -> None:
        """Initialise the parser.

        Args:
            audit_logger: ACPO-compliant forensic audit logger.
            max_artefacts: Maximum artefacts retained for a single parse.
        """
        self._audit_logger = audit_logger
        self._max_artefacts = max(0, max_artefacts)

    def supported_categories(self) -> list[ArtefactCategory]:
        """Return artefact categories this parser can produce."""
        return []

    def supported_evidence_types(self) -> list[EvidenceType]:
        """Return evidence types this parser can process."""
        return []

    def parse(self, evidence: EvidenceImage) -> ArtefactSet:
        """Template method: log start → ``_do_parse`` → log complete.

        Args:
            evidence: Evidence image or dump metadata to parse.

        Returns:
            Normalised artefact set extracted from the evidence.
        """
        self._log_parse_start(evidence.evidence_id)
        started = time.perf_counter()
        artefacts = self._safe_parse(
            lambda: self._do_parse(evidence),
            evidence.evidence_id,
            error_class=self._parse_error_class,
        )
        if not isinstance(artefacts, list):
            artefacts = []
        artefacts = self._truncate(artefacts)
        duration = time.perf_counter() - started
        result = self._to_artefact_set(evidence.evidence_id, artefacts)
        self._log_parse_complete(evidence.evidence_id, len(artefacts), duration)
        return result

    @abstractmethod
    def _do_parse(self, evidence: EvidenceImage) -> list[Artefact]:
        """Extract artefacts from ``evidence`` (subclass implementation).

        Args:
            evidence: Evidence metadata to parse.

        Returns:
            List of extracted artefacts (may be truncated by the template).
        """

    def _create_artefact(
        self,
        category: ArtefactCategory,
        raw_data: dict[str, Any],
        evidence_id: str,
        source_path: Optional[str] = None,
    ) -> Artefact:
        """Factory creating an ``Artefact`` with UUID and current timestamp.

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

    def _log_parse_start(self, evidence_id: str) -> None:
        """Log parser start."""
        self._audit_logger.log_action(
            stage=PipelineStage.PARSING,
            action="PARSE_START",
            evidence_id=evidence_id,
            details={"parser": self.parser_name},
        )

    def _log_parse_complete(
        self,
        evidence_id: str,
        count: int,
        duration: float,
    ) -> None:
        """Log successful parser completion with duration."""
        self._audit_logger.log_action(
            stage=PipelineStage.PARSING,
            action="PARSE_COMPLETE",
            evidence_id=evidence_id,
            details={
                "parser": self.parser_name,
                "artefact_count": count,
                "duration_seconds": duration,
            },
        )

    def _log_parse_end(self, evidence_id: str, count: int) -> None:
        """Backward-compatible alias for completion logging without duration."""
        self._log_parse_complete(evidence_id, count, duration=0.0)

    def _log_parse_error(self, evidence_id: str, error: str) -> None:
        """Log parser failure.

        Args:
            evidence_id: Source evidence identifier.
            error: Error message string.
        """
        self._audit_logger.log_action(
            stage=PipelineStage.PARSING,
            action="PARSE_ERROR",
            evidence_id=evidence_id,
            details={
                "parser": self.parser_name,
                "error": error,
            },
        )

    def _check_limit(self, current_count: int) -> bool:
        """Return ``True`` when ``current_count`` is under the artefact cap."""
        return current_count < self._max_artefacts

    def _safe_import(self, module_name: str, install_hint: str) -> Any:
        """Import ``module_name`` or raise ``ImportError`` with ``install_hint``.

        Args:
            module_name: Dotted module path to import.
            install_hint: Human-readable install guidance for the error message.

        Returns:
            Imported module object.

        Raises:
            ImportError: If the module cannot be imported.
        """
        try:
            return importlib.import_module(module_name)
        except ImportError as exc:
            raise ImportError(install_hint) from exc

    def _safe_parse(
        self,
        parse_func: Callable[[], Any],
        evidence_id: str,
        error_class: type = ParsingError,
    ) -> Any:
        """Run ``parse_func``, converting unexpected errors to ``error_class``.

        ``ImportError`` and existing ``ParsingError`` subclasses are re-raised.
        Other exceptions are logged and wrapped.

        Args:
            parse_func: Zero-argument callable performing the parse work.
            evidence_id: Evidence identifier for audit correlation.
            error_class: DFAT exception type used for wrapping.

        Returns:
            Result of ``parse_func``.
        """
        try:
            return parse_func()
        except ImportError:
            raise
        except ParsingError:
            raise
        except Exception as exc:  # noqa: BLE001 — bridge third-party errors
            self._log_parse_error(evidence_id, str(exc))
            raise error_class(
                f"{self.parser_name} failed: {exc}",
                context={"evidence_id": evidence_id, "error": str(exc)},
            ) from exc

    def _empty_set(self, evidence_id: str) -> ArtefactSet:
        """Return an empty artefact set for the evidence."""
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
        """Build an ``ArtefactSet`` from a list of artefacts."""
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
        """Enforce ``max_artefacts`` on the collected list."""
        if len(artefacts) <= self._max_artefacts:
            return artefacts
        return artefacts[: self._max_artefacts]
