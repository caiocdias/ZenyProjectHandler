"""Relações confirmadas durante a revisão humana.

Revision ID: 0004_human_review
Revises: 0003_pdf_sources
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_human_review"
down_revision: str | None = "0003_pdf_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "confirmed_relations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("relation_type", sa.String(80), nullable=False),
        sa.Column("origin_id", sa.String(36), nullable=False),
        sa.Column("destination_id", sa.String(36), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "project_id",
            "position",
            name="uq_confirmed_relations_project_position",
        ),
        sa.UniqueConstraint("id", "project_id", name="uq_confirmed_relations_id_project"),
    )
    op.create_index(
        "ix_confirmed_relations_project",
        "confirmed_relations",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_confirmed_relations_project", table_name="confirmed_relations")
    op.drop_table("confirmed_relations")
