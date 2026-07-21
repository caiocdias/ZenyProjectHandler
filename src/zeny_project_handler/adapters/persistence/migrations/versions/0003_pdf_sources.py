"""Referência local, verificável e removível para a origem de cada PDF.

Revision ID: 0003_pdf_sources
Revises: 0002_integrity
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_pdf_sources"
down_revision: str | None = "0002_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_sources",
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("canonical_path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("modified_at_ns", sa.String(24), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id", "project_id"],
            ["documents.id", "documents.project_id"],
            ondelete="CASCADE",
            name="fk_document_sources_document_project",
        ),
    )
    op.create_index("ix_document_sources_project", "document_sources", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_document_sources_project", table_name="document_sources")
    op.drop_table("document_sources")
