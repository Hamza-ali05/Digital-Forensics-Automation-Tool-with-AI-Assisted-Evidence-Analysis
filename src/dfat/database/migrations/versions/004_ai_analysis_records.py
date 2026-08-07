"""AI analysis records table.

Revision ID: 004
Revises: 003
Create Date: 2026-08-07
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the ``ai_analysis_records`` table."""
    op.create_table(
        "ai_analysis_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.Column("analysis_type", sa.String(length=30), nullable=False),
        sa.Column("model_used", sa.String(length=100), nullable=False),
        sa.Column(
            "prompt_version",
            sa.String(length=20),
            nullable=False,
            server_default="1.0.0",
        ),
        sa.Column(
            "input_artefact_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "output_token_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "confidence_score",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "duration_ms",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("hallucination_risk", sa.String(length=20), nullable=True),
        sa.Column(
            "cache_hit",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_ai_analysis_records_job_id",
        "ai_analysis_records",
        ["job_id"],
    )
    op.create_index(
        "ix_ai_analysis_records_evidence_id",
        "ai_analysis_records",
        ["evidence_id"],
    )
    op.create_index(
        "ix_ai_analysis_records_analysis_type",
        "ai_analysis_records",
        ["analysis_type"],
    )
    op.create_index(
        "ix_ai_analysis_evidence_type",
        "ai_analysis_records",
        ["evidence_id", "analysis_type"],
    )


def downgrade() -> None:
    """Drop the ``ai_analysis_records`` table."""
    op.drop_index("ix_ai_analysis_evidence_type", table_name="ai_analysis_records")
    op.drop_index(
        "ix_ai_analysis_records_analysis_type",
        table_name="ai_analysis_records",
    )
    op.drop_index(
        "ix_ai_analysis_records_evidence_id",
        table_name="ai_analysis_records",
    )
    op.drop_index("ix_ai_analysis_records_job_id", table_name="ai_analysis_records")
    op.drop_table("ai_analysis_records")
