"""Add compound indexes for common repository query patterns.

Revision ID: 006
Revises: 005
Create Date: 2026-08-17
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from dfat.database.indexes import NEW_COMPOUND_INDEXES, create_index_sql, drop_index_sql

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create missing compound indexes identified by query-pattern audit."""
    for index in NEW_COMPOUND_INDEXES:
        op.execute(create_index_sql(index))


def downgrade() -> None:
    """Drop compound indexes added in this revision."""
    for index in reversed(NEW_COMPOUND_INDEXES):
        op.execute(drop_index_sql(index))
