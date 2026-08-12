"""Snapshots imutáveis do registro configurável de regras.

Revision ID: 0006_compliance_rule_registry
Revises: 0005_import_commits
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_compliance_rule_registry"
down_revision: str | None = "0005_import_commits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compliance_rule_revisions",
        sa.Column("revision_id", sa.String(36), primary_key=True),
        sa.Column("registry_id", sa.String(36), nullable=False),
        sa.Column("registry_version", sa.String(160), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("signature", sa.String(64), nullable=False, unique=True),
        sa.Column("canonical_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_index(
        "uq_compliance_rule_revisions_active",
        "compliance_rule_revisions",
        ["active"],
        unique=True,
        sqlite_where=sa.text("active = 1"),
    )
    op.create_index(
        "ix_compliance_rule_revisions_created_at",
        "compliance_rule_revisions",
        ["created_at"],
    )
    op.create_table(
        "compliance_rule_numbers",
        sa.Column("rule_id", sa.String(240), primary_key=True),
        sa.Column("number", sa.Integer(), nullable=False, unique=True),
        sa.Column("assigned_at", sa.String(40), nullable=False),
    )
    op.execute(
        """
        CREATE TRIGGER trg_compliance_rule_revisions_immutable_update
        BEFORE UPDATE ON compliance_rule_revisions
        WHEN OLD.revision_id != NEW.revision_id
          OR OLD.registry_id != NEW.registry_id
          OR OLD.registry_version != NEW.registry_version
          OR OLD.schema_version != NEW.schema_version
          OR OLD.signature != NEW.signature
          OR OLD.canonical_json != NEW.canonical_json
          OR OLD.created_at != NEW.created_at
        BEGIN
            SELECT RAISE(ABORT, 'revisao de regras imutavel');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_compliance_rule_revisions_immutable_delete
        BEFORE DELETE ON compliance_rule_revisions
        BEGIN
            SELECT RAISE(ABORT, 'revisao de regras imutavel');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_compliance_rule_numbers_immutable_update
        BEFORE UPDATE ON compliance_rule_numbers
        BEGIN
            SELECT RAISE(ABORT, 'numero de regra imutavel');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_compliance_rule_numbers_immutable_delete
        BEFORE DELETE ON compliance_rule_numbers
        BEGIN
            SELECT RAISE(ABORT, 'numero de regra imutavel');
        END
        """
    )


def downgrade() -> None:
    for trigger in (
        "trg_compliance_rule_numbers_immutable_delete",
        "trg_compliance_rule_numbers_immutable_update",
        "trg_compliance_rule_revisions_immutable_delete",
        "trg_compliance_rule_revisions_immutable_update",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.drop_table("compliance_rule_numbers")
    op.drop_index(
        "ix_compliance_rule_revisions_created_at",
        table_name="compliance_rule_revisions",
    )
    op.drop_index(
        "uq_compliance_rule_revisions_active",
        table_name="compliance_rule_revisions",
    )
    op.drop_table("compliance_rule_revisions")
