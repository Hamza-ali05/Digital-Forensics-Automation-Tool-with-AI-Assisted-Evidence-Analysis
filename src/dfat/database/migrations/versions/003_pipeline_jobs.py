"""Pipeline jobs table.

Revision ID: 003
Revises: 002
Create Date: 2026-08-07
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the ``pipeline_jobs`` table."""
    op.create_table(
        "pipeline_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="queued",
        ),
        sa.Column(
            "mode",
            sa.String(length=30),
            nullable=False,
            server_default="full",
        ),
        sa.Column(
            "use_fallback_analyzer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_duration_seconds", sa.Float(), nullable=True),
        sa.Column("current_stage", sa.String(length=50), nullable=True),
        sa.Column(
            "stage_executions",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "artefact_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("report_id", sa.String(length=36), nullable=True),
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
    op.create_index("ix_pipeline_jobs_evidence_id", "pipeline_jobs", ["evidence_id"])
    op.create_index("ix_pipeline_jobs_case_id", "pipeline_jobs", ["case_id"])
    op.create_index("ix_pipeline_jobs_user_id", "pipeline_jobs", ["user_id"])
    op.create_index("ix_pipeline_jobs_status", "pipeline_jobs", ["status"])


def downgrade() -> None:
    """Drop the ``pipeline_jobs`` table."""
    op.drop_index("ix_pipeline_jobs_status", table_name="pipeline_jobs")
    op.drop_index("ix_pipeline_jobs_user_id", table_name="pipeline_jobs")
    op.drop_index("ix_pipeline_jobs_case_id", table_name="pipeline_jobs")
    op.drop_index("ix_pipeline_jobs_evidence_id", table_name="pipeline_jobs")
    op.drop_table("pipeline_jobs")
