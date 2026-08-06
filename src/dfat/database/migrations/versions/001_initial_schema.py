"""Initial DFAT schema with default RBAC roles.

Revision ID: 001
Revises: None
Create Date: 2026-08-06
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROLE_SEEDS: list[dict[str, object]] = [
    {
        "id": "role-admin",
        "name": "admin",
        "description": "Full system administrator",
        "permissions": '{"all": true}',
        "is_active": True,
    },
    {
        "id": "role-investigator",
        "name": "investigator",
        "description": "Lead forensic investigator with full analysis access",
        "permissions": (
            '{"evidence": ["create","read","update","delete"],'
            '"analysis": ["create","read"],'
            '"reports": ["create","read"],'
            '"evaluation": ["create","read"]}'
        ),
        "is_active": True,
    },
    {
        "id": "role-analyst",
        "name": "analyst",
        "description": "Forensic analyst with read and analysis access",
        "permissions": (
            '{"evidence": ["read"],'
            '"analysis": ["create","read"],'
            '"reports": ["read"],'
            '"evaluation": ["read"]}'
        ),
        "is_active": True,
    },
    {
        "id": "role-viewer",
        "name": "viewer",
        "description": "Read-only access to reports",
        "permissions": '{"reports": ["read"],"evaluation": ["read"]}',
        "is_active": True,
    },
]


def upgrade() -> None:
    """Create all DFAT tables and seed default roles."""
    op.create_table(
        "roles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("permissions", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
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
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "failed_login_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_jti", sa.String(length=36), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("token_jti"),
    )
    op.create_index("ix_user_sessions_token_jti", "user_sessions", ["token_jti"], unique=True)

    op.create_table(
        "evidence_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("case_name", sa.String(length=255), nullable=False),
        sa.Column("investigator", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("evidence_type", sa.String(length=50), nullable=False),
        sa.Column("original_hash", sa.String(length=128), nullable=False),
        sa.Column("hash_algorithm", sa.String(length=20), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("volatility_profile", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("registered_by", sa.String(length=36), nullable=True),
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
        sa.ForeignKeyConstraint(["registered_by"], ["users.id"]),
    )
    op.create_index("ix_evidence_records_case_id", "evidence_records", ["case_id"])

    op.create_table(
        "artefact_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("source_path", sa.String(length=1024), nullable=True),
        sa.Column("raw_data", sa.Text(), nullable=False),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("suspicion_level", sa.String(length=20), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("classification_reasoning", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
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
    )
    op.create_index("ix_artefact_records_evidence_id", "artefact_records", ["evidence_id"])
    op.create_index("ix_artefact_records_category", "artefact_records", ["category"])
    op.create_index(
        "ix_artefact_evidence_category",
        "artefact_records",
        ["evidence_id", "category"],
    )

    op.create_table(
        "report_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.Column("json_report_data", sa.Text(), nullable=False),
        sa.Column("narrative_text", sa.Text(), nullable=False),
        sa.Column("llm_model_used", sa.String(length=100), nullable=False),
        sa.Column("generation_parameters", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("integrity_hash", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.String(length=20), nullable=False),
        sa.Column("pipeline_duration_seconds", sa.Float(), nullable=False),
        sa.Column("stage_timings", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("generated_by", sa.String(length=36), nullable=True),
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
        sa.ForeignKeyConstraint(["generated_by"], ["users.id"]),
    )
    op.create_index("ix_report_records_case_id", "report_records", ["case_id"])

    op.create_table(
        "benchmark_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("dataset_name", sa.String(length=255), nullable=False),
        sa.Column("evidence_id", sa.String(length=36), nullable=True),
        sa.Column("precision_val", sa.Float(), nullable=False),
        sa.Column("recall_val", sa.Float(), nullable=False),
        sa.Column("f1_score", sa.Float(), nullable=False),
        sa.Column("time_to_triage_seconds", sa.Float(), nullable=False),
        sa.Column("artefacts_expected", sa.Integer(), nullable=False),
        sa.Column("artefacts_recovered", sa.Integer(), nullable=False),
        sa.Column("false_positives", sa.Integer(), nullable=False),
        sa.Column("false_negatives", sa.Integer(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
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

    op.create_table(
        "usability_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("usefulness_rating", sa.Integer(), nullable=False),
        sa.Column("accuracy_rating", sa.Integer(), nullable=False),
        sa.Column("clarity_rating", sa.Integer(), nullable=False),
        sa.Column("free_text_feedback", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
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

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("entry_number", sa.Integer(), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("evidence_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("hash_before", sa.String(length=128), nullable=True),
        sa.Column("hash_after", sa.String(length=128), nullable=True),
        sa.Column("details", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
    )
    op.create_index("ix_audit_log_entry_number", "audit_log", ["entry_number"])
    op.create_index(
        "ix_audit_evidence_timestamp",
        "audit_log",
        ["evidence_id", "timestamp"],
    )

    roles_table = sa.table(
        "roles",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("permissions", sa.Text),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(roles_table, _ROLE_SEEDS)


def downgrade() -> None:
    """Drop all DFAT tables in reverse dependency order."""
    op.drop_index("ix_audit_evidence_timestamp", table_name="audit_log")
    op.drop_index("ix_audit_log_entry_number", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_table("usability_records")
    op.drop_table("benchmark_records")

    op.drop_index("ix_report_records_case_id", table_name="report_records")
    op.drop_table("report_records")

    op.drop_index("ix_artefact_evidence_category", table_name="artefact_records")
    op.drop_index("ix_artefact_records_category", table_name="artefact_records")
    op.drop_index("ix_artefact_records_evidence_id", table_name="artefact_records")
    op.drop_table("artefact_records")

    op.drop_index("ix_evidence_records_case_id", table_name="evidence_records")
    op.drop_table("evidence_records")

    op.drop_index("ix_user_sessions_token_jti", table_name="user_sessions")
    op.drop_table("user_sessions")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_roles_name", table_name="roles")
    op.drop_table("roles")
