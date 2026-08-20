"""Add dataset registry persistence tables.

Revision ID: 007
Revises: 006
Create Date: 2026-08-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create dataset intelligence registry table and indexes."""
    op.create_table(
        "dataset_records",
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("format", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parent_directory", sa.String(length=1024), nullable=False),
        sa.Column("is_nested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("nested_depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "associated_research_objectives_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "supported_forensic_modules_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("indexing_status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("preprocessing_history_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("update_history_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id"),
        sa.UniqueConstraint("file_path"),
    )
    op.create_index(op.f("ix_dataset_records_category"), "dataset_records", ["category"], unique=False)
    op.create_index(op.f("ix_dataset_records_category_status"), "dataset_records", ["category", "status"], unique=False)
    op.create_index(op.f("ix_dataset_records_dataset_id"), "dataset_records", ["dataset_id"], unique=False)
    op.create_index(op.f("ix_dataset_records_format"), "dataset_records", ["format"], unique=False)
    op.create_index(op.f("ix_dataset_records_format_status"), "dataset_records", ["format", "status"], unique=False)
    op.create_index(op.f("ix_dataset_records_hash_active"), "dataset_records", ["hash_sha256", "is_deleted"], unique=False)
    op.create_index(op.f("ix_dataset_records_hash_sha256"), "dataset_records", ["hash_sha256"], unique=False)
    op.create_index(op.f("ix_dataset_records_is_deleted"), "dataset_records", ["is_deleted"], unique=False)
    op.create_index(op.f("ix_dataset_records_status"), "dataset_records", ["status"], unique=False)


def downgrade() -> None:
    """Drop dataset intelligence registry table and indexes."""
    op.drop_index(op.f("ix_dataset_records_status"), table_name="dataset_records")
    op.drop_index(op.f("ix_dataset_records_is_deleted"), table_name="dataset_records")
    op.drop_index(op.f("ix_dataset_records_hash_sha256"), table_name="dataset_records")
    op.drop_index(op.f("ix_dataset_records_hash_active"), table_name="dataset_records")
    op.drop_index(op.f("ix_dataset_records_format_status"), table_name="dataset_records")
    op.drop_index(op.f("ix_dataset_records_format"), table_name="dataset_records")
    op.drop_index(op.f("ix_dataset_records_dataset_id"), table_name="dataset_records")
    op.drop_index(op.f("ix_dataset_records_category_status"), table_name="dataset_records")
    op.drop_index(op.f("ix_dataset_records_category"), table_name="dataset_records")
    op.drop_table("dataset_records")
