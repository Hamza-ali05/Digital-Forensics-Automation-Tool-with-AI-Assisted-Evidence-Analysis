"""Catalog of DFAT database indexes and helpers to apply missing ones.

Compound indexes named here match common repository query patterns:
case-filtered evidence, category/triage artefact lookups, ordered custody
chains, status timelines, audit trails, job listings, and benchmark history.

``CREATE INDEX IF NOT EXISTS`` is used throughout so applying the catalog is
idempotent on both Alembic-managed and ``create_all`` databases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


@dataclass(frozen=True)
class IndexDefinition:
    """Documented SQL index on a persistence table.

    Attributes:
        name: Unique index identifier (SQLite index names are database-wide).
        table: Target table name.
        columns: Ordered column names that form the index key.
        purpose: Query pattern this index is intended to accelerate.
        added_in: Alembic revision that introduced the index (``001``/``002``
            for indexes created with the original schema).
    """

    name: str
    table: str
    columns: tuple[str, ...]
    purpose: str
    added_in: str


# Compound indexes already present on the schema before revision 006.
_EXISTING_COMPOUND_INDEXES: tuple[IndexDefinition, ...] = (
    IndexDefinition(
        name="ix_artefact_evidence_category",
        table="artefact_records",
        columns=("evidence_id", "category"),
        purpose="category-filtered artefact queries for a single evidence item",
        added_in="001",
    ),
    IndexDefinition(
        name="ix_custody_evidence_entry",
        table="chain_of_custody",
        columns=("evidence_id", "entry_number"),
        purpose="ordered chain-of-custody queries by evidence",
        added_in="002",
    ),
    IndexDefinition(
        name="ix_audit_evidence_timestamp",
        table="audit_log",
        columns=("evidence_id", "timestamp"),
        purpose="audit trail queries by evidence identifier",
        added_in="001",
    ),
)

# Compound indexes added by revision 006 for remaining common query patterns.
NEW_COMPOUND_INDEXES: tuple[IndexDefinition, ...] = (
    IndexDefinition(
        name="ix_evidence_records_case_status",
        table="evidence_records",
        columns=("case_id", "status"),
        purpose="case-filtered evidence inventory queries by status",
        added_in="006",
    ),
    IndexDefinition(
        name="ix_artefact_evidence_suspicion",
        table="artefact_records",
        columns=("evidence_id", "suspicion_level"),
        purpose="triage queries ranking artefacts within an evidence item",
        added_in="006",
    ),
    IndexDefinition(
        name="ix_evidence_status_history_evidence_changed",
        table="evidence_status_history",
        columns=("evidence_id", "changed_at"),
        purpose="evidence status timeline queries ordered by change time",
        added_in="006",
    ),
    IndexDefinition(
        name="ix_audit_user_timestamp",
        table="audit_log",
        columns=("user_id", "timestamp"),
        purpose="user-scoped audit trail queries ordered by timestamp",
        added_in="006",
    ),
    IndexDefinition(
        name="ix_pipeline_jobs_status_created",
        table="pipeline_jobs",
        columns=("status", "created_at"),
        purpose="pipeline job listing filtered by status and creation time",
        added_in="006",
    ),
    IndexDefinition(
        name="ix_benchmark_dataset_evaluated",
        table="benchmark_records",
        columns=("dataset_name", "evaluated_at"),
        purpose="benchmark result history by dataset ordered by evaluation time",
        added_in="006",
    ),
)

COMPOUND_INDEXES: tuple[IndexDefinition, ...] = (
    *_EXISTING_COMPOUND_INDEXES,
    *NEW_COMPOUND_INDEXES,
)


def create_index_sql(index: IndexDefinition) -> str:
    """Return idempotent ``CREATE INDEX`` SQL for ``index``.

    Args:
        index: Index definition to materialise.

    Returns:
        SQLite-compatible ``CREATE INDEX IF NOT EXISTS`` statement.
    """
    columns = ", ".join(index.columns)
    return f"CREATE INDEX IF NOT EXISTS {index.name} ON {index.table} ({columns})"


def drop_index_sql(index: IndexDefinition) -> str:
    """Return idempotent ``DROP INDEX`` SQL for ``index``.

    Args:
        index: Index definition to remove.

    Returns:
        SQLite-compatible ``DROP INDEX IF EXISTS`` statement.
    """
    return f"DROP INDEX IF EXISTS {index.name}"


def create_index_statements(
    indexes: Sequence[IndexDefinition] | None = None,
) -> list[str]:
    """Return ``CREATE INDEX IF NOT EXISTS`` statements for ``indexes``.

    Args:
        indexes: Index catalog subset. Defaults to every compound index.

    Returns:
        Ordered SQL statements.
    """
    selected = COMPOUND_INDEXES if indexes is None else tuple(indexes)
    return [create_index_sql(index) for index in selected]


async def apply_indexes(
    engine: AsyncEngine,
    *,
    indexes: Sequence[IndexDefinition] | None = None,
) -> list[str]:
    """Apply catalogued indexes using ``CREATE INDEX IF NOT EXISTS``.

    Args:
        engine: Async SQLAlchemy engine bound to the target database.
        indexes: Optional subset to apply. Defaults to all compound indexes.

    Returns:
        SQL statements that were executed.
    """
    statements = create_index_statements(indexes)
    async with engine.begin() as connection:
        for statement in statements:
            await connection.execute(text(statement))
    return statements


async def _main() -> None:
    """Apply catalogued indexes to the configured DFAT database."""
    from dfat.database.engine import DatabaseEngine
    from dfat.settings import load_settings

    settings = load_settings()
    engine = DatabaseEngine(database_url=settings.database.url, echo=False)
    try:
        applied = await apply_indexes(engine.engine)
        for statement in applied:
            print(statement)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main())
