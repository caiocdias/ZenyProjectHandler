"""Versão otimista, idempotência HTTP e uploads gerenciados.

Revision ID: 0008_server_managed_uploads
Revises: 0007_compliance_executions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_server_managed_uploads"
down_revision: str | None = "0007_compliance_executions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "api_idempotency_records",
        sa.Column("idempotency_key", sa.String(200), primary_key=True),
        sa.Column("operation", sa.String(120), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(36), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "api_uploads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_id", sa.String(36), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("pending_relative_path", sa.String(120), nullable=True),
        sa.Column("password_attempts_remaining", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_api_uploads_project", "api_uploads", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_api_uploads_project", table_name="api_uploads")
    op.drop_table("api_uploads")
    op.drop_table("api_idempotency_records")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("version")
