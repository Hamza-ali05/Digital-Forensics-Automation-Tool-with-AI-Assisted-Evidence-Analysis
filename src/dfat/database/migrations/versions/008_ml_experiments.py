"""Add ML experiment and model registry persistence tables.

Revision ID: 008
Revises: 007
Create Date: 2026-08-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ML experiment and model record tables."""
    op.create_table(
        "ml_experiments",
        sa.Column("experiment_id", sa.String(length=36), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("dataset_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="running"),
        sa.Column("hyperparameters_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.String(length=40), nullable=False),
        sa.Column("completed_at", sa.String(length=40), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("artifact_paths_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_id"),
    )
    op.create_index("ix_ml_experiments_experiment_id", "ml_experiments", ["experiment_id"], unique=False)
    op.create_index("ix_ml_experiments_model_name", "ml_experiments", ["model_name"], unique=False)
    op.create_index("ix_ml_experiments_model_status", "ml_experiments", ["model_name", "status"], unique=False)
    op.create_index("ix_ml_experiments_status", "ml_experiments", ["status"], unique=False)

    op.create_table(
        "ml_model_records",
        sa.Column("model_id", sa.String(length=36), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("model_path", sa.String(length=1024), nullable=False),
        sa.Column("training_dataset", sa.String(length=255), nullable=False),
        sa.Column("hyperparameters_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("feature_names_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("trained_at", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id"),
    )
    op.create_index("ix_ml_model_records_model_id", "ml_model_records", ["model_id"], unique=False)
    op.create_index("ix_ml_model_records_model_name", "ml_model_records", ["model_name"], unique=False)
    op.create_index(
        "ix_ml_model_records_name_version",
        "ml_model_records",
        ["model_name", "version"],
        unique=False,
    )


def downgrade() -> None:
    """Drop ML experiment and model record tables."""
    op.drop_index("ix_ml_model_records_name_version", table_name="ml_model_records")
    op.drop_index("ix_ml_model_records_model_name", table_name="ml_model_records")
    op.drop_index("ix_ml_model_records_model_id", table_name="ml_model_records")
    op.drop_table("ml_model_records")
    op.drop_index("ix_ml_experiments_status", table_name="ml_experiments")
    op.drop_index("ix_ml_experiments_model_status", table_name="ml_experiments")
    op.drop_index("ix_ml_experiments_model_name", table_name="ml_experiments")
    op.drop_index("ix_ml_experiments_experiment_id", table_name="ml_experiments")
    op.drop_table("ml_experiments")
