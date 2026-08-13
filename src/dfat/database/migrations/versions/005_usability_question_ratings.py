"""Add per-question usability Likert columns for Tobin-comparable analysis.

Revision ID: 005
Revises: 004
Create Date: 2026-08-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add optional Q1/Q4/comparative rating columns to usability_records."""
    op.add_column(
        "usability_records",
        sa.Column("q1_rating", sa.Integer(), nullable=True),
    )
    op.add_column(
        "usability_records",
        sa.Column("q4_rating", sa.Integer(), nullable=True),
    )
    op.add_column(
        "usability_records",
        sa.Column("comparative_rating", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Remove optional per-question usability columns."""
    op.drop_column("usability_records", "comparative_rating")
    op.drop_column("usability_records", "q4_rating")
    op.drop_column("usability_records", "q1_rating")
