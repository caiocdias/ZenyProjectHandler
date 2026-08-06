"""Comprovantes transacionais de importação recuperável.

Revision ID: 0005_import_commits
Revises: 0004_human_review
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_import_commits"
down_revision: str | None = "0004_human_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_commits",
        sa.Column("operation_id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("package_sha256", sa.String(64), nullable=False),
        sa.Column("plan_sha256", sa.String(64), nullable=False),
        sa.Column("files_sha256", sa.String(64), nullable=False),
        sa.Column("committed_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_import_commits_project", "import_commits", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_import_commits_project", table_name="import_commits")
    op.drop_table("import_commits")
