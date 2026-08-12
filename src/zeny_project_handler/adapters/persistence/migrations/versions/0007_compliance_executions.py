"""Execuções imutáveis e auditáveis de conformidade.

Revision ID: 0007_compliance_executions
Revises: 0006_compliance_rule_registry
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_compliance_executions"
down_revision: str | None = "0006_compliance_rule_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compliance_executions",
        sa.Column("sequence", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(36), nullable=False, unique=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rule_revision_id",
            sa.String(36),
            sa.ForeignKey("compliance_rule_revisions.revision_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("rule_version", sa.String(160), nullable=False),
        sa.Column("rule_signature", sa.String(64), nullable=False),
        sa.Column("session_signature", sa.String(64), nullable=False),
        sa.Column("executed_at", sa.String(40), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_compliance_executions_project",
        "compliance_executions",
        ["project_id"],
    )
    op.create_index(
        "ix_compliance_executions_rule_signature",
        "compliance_executions",
        ["rule_signature"],
    )
    op.execute(
        """
        CREATE TRIGGER trg_compliance_executions_immutable_update
        BEFORE UPDATE ON compliance_executions
        BEGIN
            SELECT RAISE(ABORT, 'execucao de conformidade imutavel');
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_compliance_executions_immutable_update")
    op.drop_index(
        "ix_compliance_executions_rule_signature",
        table_name="compliance_executions",
    )
    op.drop_index(
        "ix_compliance_executions_project",
        table_name="compliance_executions",
    )
    op.drop_table("compliance_executions")
