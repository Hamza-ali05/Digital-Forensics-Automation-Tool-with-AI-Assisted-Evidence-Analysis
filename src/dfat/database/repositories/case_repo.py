"""SQLAlchemy case repository implementing ``ICaseRepository``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from dfat.case_management.enums import CaseStatus
from dfat.case_management.exceptions import (
    CaseNotFoundError,
    InvestigatorAlreadyAssignedError,
)
from dfat.core.interfaces.case_repository import ICaseRepository
from dfat.core.models.case import Case, CaseInvestigator
from dfat.database.exceptions import DatabaseError
from dfat.database.mappers import case_domain_to_orm, case_orm_to_domain
from dfat.database.models.case_orm import CaseInvestigatorORM, CaseORM
from dfat.database.models.evidence_orm import EvidenceRecordORM
from dfat.database.models.user import UserORM


class SQLAlchemyCaseRepository(ICaseRepository):
    """Async SQLAlchemy implementation of the case repository port."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialise the case repository.

        Args:
            session_factory: Async SQLAlchemy session factory.
        """
        self._session_factory = session_factory

    async def save(  # type: ignore[override]
        self,
        entity: Case,
        *,
        created_by_user_id: Optional[str] = None,
    ) -> str:
        """Persist a case and return its identifier.

        Args:
            entity: Domain case model.
            created_by_user_id: Creating user (defaults to lead or ``system``).

        Returns:
            Persisted case identifier.
        """
        creator = (
            created_by_user_id
            or entity.lead_investigator_id
            or (entity.investigators[0].user_id if entity.investigators else "system")
        )
        orm = case_domain_to_orm(entity, created_by_user_id=creator)
        async with self._session_factory() as session:
            try:
                merged = await session.merge(orm)
                # Sync active investigator assignments from the domain model.
                for investigator in entity.investigators:
                    await self._upsert_investigator(
                        session,
                        case_id=merged.id,
                        investigator=investigator,
                    )
                await session.commit()
                return str(merged.id)
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to save case",
                    context={"case_id": entity.case_id, "error": str(exc)},
                ) from exc

    async def get(self, entity_id: str) -> Optional[Case]:  # type: ignore[override]
        """Load a case by identifier."""
        async with self._session_factory() as session:
            try:
                return await self._load_case(session, entity_id)
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load case",
                    context={"case_id": entity_id, "error": str(exc)},
                ) from exc

    async def list_all(self) -> list[Case]:  # type: ignore[override]
        """List all cases."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(CaseORM).options(selectinload(CaseORM.investigators))
                )
                rows = list(result.scalars().unique().all())
                return [
                    await self._to_domain(session, row) for row in rows
                ]
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to list cases",
                    context={"error": str(exc)},
                ) from exc

    async def delete(self, entity_id: str) -> bool:  # type: ignore[override]
        """Delete a case and its investigator assignments."""
        async with self._session_factory() as session:
            try:
                orm = await session.get(CaseORM, entity_id)
                if orm is None:
                    return False
                await session.delete(orm)
                await session.commit()
                return True
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to delete case",
                    context={"case_id": entity_id, "error": str(exc)},
                ) from exc

    async def get_by_status(self, status: CaseStatus) -> list[Case]:  # type: ignore[override]
        """List cases in the given lifecycle status."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(CaseORM)
                    .options(selectinload(CaseORM.investigators))
                    .where(CaseORM.status == status.value)
                )
                rows = list(result.scalars().unique().all())
                return [await self._to_domain(session, row) for row in rows]
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to list cases by status",
                    context={"status": status.value, "error": str(exc)},
                ) from exc

    async def get_by_investigator(self, user_id: str) -> list[Case]:  # type: ignore[override]
        """List cases where the user is an active investigator."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(CaseORM)
                    .options(selectinload(CaseORM.investigators))
                    .join(CaseInvestigatorORM)
                    .where(
                        CaseInvestigatorORM.user_id == user_id,
                        CaseInvestigatorORM.is_active.is_(True),
                    )
                )
                rows = list(result.scalars().unique().all())
                return [await self._to_domain(session, row) for row in rows]
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to list cases by investigator",
                    context={"user_id": user_id, "error": str(exc)},
                ) from exc

    async def update_status(  # type: ignore[override]
        self,
        case_id: str,
        new_status: CaseStatus,
    ) -> Case:
        """Update a case lifecycle status and return the updated case."""
        async with self._session_factory() as session:
            try:
                orm = await session.get(
                    CaseORM,
                    case_id,
                    options=(selectinload(CaseORM.investigators),),
                )
                if orm is None:
                    raise CaseNotFoundError(
                        f"Case not found: {case_id}",
                        case_id=case_id,
                    )
                now = datetime.now(UTC)
                orm.status = new_status.value
                if new_status is CaseStatus.OPEN and orm.opened_at is None:
                    orm.opened_at = now
                elif new_status is CaseStatus.CLOSED:
                    orm.closed_at = now
                elif new_status is CaseStatus.ARCHIVED:
                    orm.archived_at = now
                await session.commit()
                await session.refresh(orm, attribute_names=["investigators"])
                loaded = await self._load_case(session, case_id)
                assert loaded is not None
                return loaded
            except CaseNotFoundError:
                raise
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to update case status",
                    context={
                        "case_id": case_id,
                        "status": new_status.value,
                        "error": str(exc),
                    },
                ) from exc

    async def add_evidence_id(  # type: ignore[override]
        self,
        case_id: str,
        evidence_id: str,
    ) -> None:
        """Associate an evidence record with a case via ``evidence_records.case_id``."""
        async with self._session_factory() as session:
            try:
                case = await session.get(CaseORM, case_id)
                if case is None:
                    raise CaseNotFoundError(
                        f"Case not found: {case_id}",
                        case_id=case_id,
                    )
                evidence = await session.get(EvidenceRecordORM, evidence_id)
                if evidence is None:
                    raise DatabaseError(
                        "Evidence not found for case linkage",
                        context={"evidence_id": evidence_id, "case_id": case_id},
                    )
                evidence.case_id = case_id
                evidence.case_name = case.case_name
                await session.commit()
            except CaseNotFoundError:
                raise
            except DatabaseError:
                raise
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to link evidence to case",
                    context={
                        "case_id": case_id,
                        "evidence_id": evidence_id,
                        "error": str(exc),
                    },
                ) from exc

    async def add_investigator(
        self,
        case_id: str,
        investigator: CaseInvestigator,
    ) -> None:
        """Assign an investigator to a case.

        Args:
            case_id: Case identifier.
            investigator: Investigator assignment to add.

        Raises:
            CaseNotFoundError: If the case does not exist.
            InvestigatorAlreadyAssignedError: If already actively assigned.
        """
        async with self._session_factory() as session:
            try:
                case = await session.get(CaseORM, case_id)
                if case is None:
                    raise CaseNotFoundError(
                        f"Case not found: {case_id}",
                        case_id=case_id,
                    )
                existing = await session.execute(
                    select(CaseInvestigatorORM).where(
                        CaseInvestigatorORM.case_id == case_id,
                        CaseInvestigatorORM.user_id == investigator.user_id,
                        CaseInvestigatorORM.is_active.is_(True),
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    raise InvestigatorAlreadyAssignedError(
                        "Investigator already assigned to case",
                        context={
                            "case_id": case_id,
                            "user_id": investigator.user_id,
                        },
                    )
                await self._upsert_investigator(
                    session,
                    case_id=case_id,
                    investigator=investigator,
                )
                if investigator.role == "lead":
                    case.lead_investigator_id = investigator.user_id
                await session.commit()
            except (CaseNotFoundError, InvestigatorAlreadyAssignedError):
                raise
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to add investigator",
                    context={
                        "case_id": case_id,
                        "user_id": investigator.user_id,
                        "error": str(exc),
                    },
                ) from exc

    async def remove_investigator(self, case_id: str, user_id: str) -> bool:
        """Soft-remove an investigator (sets ``is_active=False``).

        Args:
            case_id: Case identifier.
            user_id: Investigator user identifier.

        Returns:
            ``True`` if an active assignment was deactivated.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(CaseInvestigatorORM).where(
                        CaseInvestigatorORM.case_id == case_id,
                        CaseInvestigatorORM.user_id == user_id,
                        CaseInvestigatorORM.is_active.is_(True),
                    )
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return False
                row.is_active = False
                row.removed_at = datetime.now(UTC)
                case = await session.get(CaseORM, case_id)
                if case is not None and case.lead_investigator_id == user_id:
                    case.lead_investigator_id = None
                await session.commit()
                return True
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to remove investigator",
                    context={
                        "case_id": case_id,
                        "user_id": user_id,
                        "error": str(exc),
                    },
                ) from exc

    async def get_investigators(self, case_id: str) -> list[CaseInvestigator]:
        """Return active investigator assignments for a case."""
        case = await self.get(case_id)
        if case is None:
            raise CaseNotFoundError(f"Case not found: {case_id}", case_id=case_id)
        return list(case.investigators)

    async def count_by_status(self) -> dict[str, int]:
        """Return a mapping of status value → case count."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(CaseORM.status, func.count())
                    .group_by(CaseORM.status)
                )
                return {str(status): int(count) for status, count in result.all()}
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to count cases by status",
                    context={"error": str(exc)},
                ) from exc

    async def _load_case(
        self,
        session: AsyncSession,
        case_id: str,
    ) -> Optional[Case]:
        """Load a single case with investigators and evidence IDs."""
        result = await session.execute(
            select(CaseORM)
            .options(selectinload(CaseORM.investigators))
            .where(CaseORM.id == case_id)
            .limit(1)
        )
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return await self._to_domain(session, orm)

    async def _to_domain(self, session: AsyncSession, orm: CaseORM) -> Case:
        """Map ORM case to domain including user names and evidence IDs."""
        user_ids = [inv.user_id for inv in orm.investigators if inv.is_active]
        if orm.lead_investigator_id:
            user_ids.append(orm.lead_investigator_id)
        name_map: dict[str, tuple[str, str]] = {}
        if user_ids:
            users = await session.execute(
                select(UserORM).where(UserORM.id.in_(set(user_ids)))
            )
            for user in users.scalars().all():
                name_map[user.id] = (user.username, user.full_name)
        evidence_result = await session.execute(
            select(EvidenceRecordORM.id).where(EvidenceRecordORM.case_id == orm.id)
        )
        evidence_ids = [str(row[0]) for row in evidence_result.all()]
        return case_orm_to_domain(
            orm,
            evidence_ids=evidence_ids,
            investigator_usernames=name_map,
        )

    async def _upsert_investigator(
        self,
        session: AsyncSession,
        *,
        case_id: str,
        investigator: CaseInvestigator,
    ) -> None:
        """Insert or reactivate an investigator assignment."""
        result = await session.execute(
            select(CaseInvestigatorORM).where(
                CaseInvestigatorORM.case_id == case_id,
                CaseInvestigatorORM.user_id == investigator.user_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.role = investigator.role
            existing.is_active = True
            existing.assigned_at = investigator.assigned_at
            existing.removed_at = None
            return
        session.add(
            CaseInvestigatorORM(
                id=str(uuid4()),
                case_id=case_id,
                user_id=investigator.user_id,
                role=investigator.role,
                assigned_at=investigator.assigned_at,
                is_active=True,
            )
        )
