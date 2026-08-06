"""Repository ports for persistence of evidence, artefacts, and reports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, Optional, TypeVar

from dfat.core.models.artefact import ArtefactSet
from dfat.core.models.evidence import EvidenceImage
from dfat.core.models.report import ForensicReport

T = TypeVar("T")


class IRepository(ABC, Generic[T]):
    """Generic persistence port for domain entities."""

    @abstractmethod
    def save(self, entity: T) -> str:
        """Persist an entity and return its identifier.

        Args:
            entity: Domain entity to store.

        Returns:
            Persisted entity identifier.
        """

    @abstractmethod
    def get(self, entity_id: str) -> Optional[T]:
        """Retrieve an entity by identifier.

        Args:
            entity_id: Entity identifier.

        Returns:
            Entity if found; otherwise None.
        """

    @abstractmethod
    def list_all(self) -> list[T]:
        """List all persisted entities.

        Returns:
            List of stored entities.
        """

    @abstractmethod
    def delete(self, entity_id: str) -> bool:
        """Delete an entity by identifier.

        Args:
            entity_id: Entity identifier.

        Returns:
            True if deleted; False if not found.
        """


class IEvidenceRepository(IRepository[EvidenceImage]):
    """Persistence port for evidence metadata."""


class IArtefactRepository(IRepository[ArtefactSet]):
    """Persistence port for artefact sets."""


class IReportRepository(IRepository[ForensicReport]):
    """Persistence port for forensic reports."""
