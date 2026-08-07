"""Case lifecycle persistence port."""

from __future__ import annotations

from abc import abstractmethod
from typing import Optional

from dfat.case_management.enums import CaseStatus
from dfat.core.interfaces.repository import IRepository
from dfat.core.models.case import Case


class ICaseRepository(IRepository[Case]):
    """Persistence port for investigation case lifecycle entities."""

    @abstractmethod
    def get_by_status(self, status: CaseStatus) -> list[Case]:
        """List cases in the given lifecycle status.

        Args:
            status: Case status filter.

        Returns:
            Matching cases.
        """

    @abstractmethod
    def get_by_investigator(self, user_id: str) -> list[Case]:
        """List cases where the user is an active investigator.

        Args:
            user_id: Investigator user identifier.

        Returns:
            Matching cases.
        """

    @abstractmethod
    def update_status(self, case_id: str, new_status: CaseStatus) -> Case:
        """Update a case lifecycle status and return the updated case.

        Args:
            case_id: Case identifier.
            new_status: Target status.

        Returns:
            Updated case domain model.
        """

    @abstractmethod
    def add_evidence_id(self, case_id: str, evidence_id: str) -> None:
        """Associate an evidence record with a case.

        Args:
            case_id: Case identifier.
            evidence_id: Evidence identifier to link.
        """
