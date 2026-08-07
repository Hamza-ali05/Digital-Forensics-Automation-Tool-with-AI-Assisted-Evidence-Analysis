"""Case and evidence management schema.

Revision ID: 002
Revises: 001
Create Date: 2026-08-06
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create case/custody/evidence-management tables and alter evidence_records."""
    op.create_table(
        "cases",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("case_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="created",
        ),
        sa.Column("lead_investigator_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closure_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("tags", sa.Text(), nullable=False, server_default="[]"),
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
        sa.ForeignKeyConstraint(["lead_investigator_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
    )
    op.create_index("ix_cases_status", "cases", ["status"])

    op.create_table(
        "case_investigators",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="member"),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
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
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("case_id", "user_id", name="uq_case_investigators_case_user"),
    )
    op.create_index("ix_case_investigators_case_id", "case_investigators", ["case_id"])
    op.create_index("ix_case_investigators_user_id", "case_investigators", ["user_id"])

    op.create_table(
        "chain_of_custody",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("performed_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("performed_by_name", sa.String(length=255), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("hash_at_action", sa.String(length=128), nullable=False),
        sa.Column(
            "location",
            sa.String(length=255),
            nullable=False,
            server_default="DFAT Local System",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("entry_number", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_records.id"]),
        sa.ForeignKeyConstraint(["performed_by_user_id"], ["users.id"]),
    )
    op.create_index("ix_chain_of_custody_evidence_id", "chain_of_custody", ["evidence_id"])
    op.create_index(
        "ix_custody_evidence_entry",
        "chain_of_custody",
        ["evidence_id", "entry_number"],
    )

    op.create_table(
        "evidence_status_history",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.Column("previous_status", sa.String(length=30), nullable=True),
        sa.Column("new_status", sa.String(length=30), nullable=False),
        sa.Column("changed_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_records.id"]),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"]),
    )
    op.create_index(
        "ix_evidence_status_history_evidence_id",
        "evidence_status_history",
        ["evidence_id"],
    )

    op.create_table(
        "evidence_metadata",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("mime_detected_from", sa.String(length=50), nullable=False),
        sa.Column("file_extension", sa.String(length=20), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hash_md5", sa.String(length=32), nullable=False),
        sa.Column("hash_sha1", sa.String(length=40), nullable=False),
        sa.Column("hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("hash_computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_valid_format",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "validation_notes",
            sa.Text(),
            nullable=False,
            server_default="[]",
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
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_records.id"]),
        sa.UniqueConstraint("evidence_id", name="uq_evidence_metadata_evidence_id"),
    )
    op.create_index("ix_evidence_metadata_evidence_id", "evidence_metadata", ["evidence_id"])

    # Additive columns on evidence_records (case_id already exists from revision 001).
    with op.batch_alter_table("evidence_records") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=30),
                nullable=True,
                server_default="registered",
            )
        )
        batch_op.add_column(sa.Column("hash_md5", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("hash_sha1", sa.String(length=40), nullable=True))


def downgrade() -> None:
    """Drop case/evidence-management tables and reverse evidence_records alters."""
    with op.batch_alter_table("evidence_records") as batch_op:
        batch_op.drop_column("hash_sha1")
        batch_op.drop_column("hash_md5")
        batch_op.drop_column("status")

    op.drop_index("ix_evidence_metadata_evidence_id", table_name="evidence_metadata")
    op.drop_table("evidence_metadata")

    op.drop_index(
        "ix_evidence_status_history_evidence_id",
        table_name="evidence_status_history",
    )
    op.drop_table("evidence_status_history")

    op.drop_index("ix_custody_evidence_entry", table_name="chain_of_custody")
    op.drop_index("ix_chain_of_custody_evidence_id", table_name="chain_of_custody")
    op.drop_table("chain_of_custody")

    op.drop_index("ix_case_investigators_user_id", table_name="case_investigators")
    op.drop_index("ix_case_investigators_case_id", table_name="case_investigators")
    op.drop_table("case_investigators")

    op.drop_index("ix_cases_status", table_name="cases")
    op.drop_table("cases")
