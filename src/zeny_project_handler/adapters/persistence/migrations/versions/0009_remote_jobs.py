"""Journal persistente dos jobs remotos.

Revision ID: 0009_remote_jobs
Revises: 0008_server_managed_uploads
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_remote_jobs"
down_revision: str | None = "0008_server_managed_uploads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(500), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("expires_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_api_jobs_project", "api_jobs", ["project_id"])
    op.create_index("ix_api_jobs_status", "api_jobs", ["status"])
    op.create_index("ix_api_jobs_expires", "api_jobs", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_api_jobs_expires", table_name="api_jobs")
    op.drop_index("ix_api_jobs_status", table_name="api_jobs")
    op.drop_index("ix_api_jobs_project", table_name="api_jobs")
    op.drop_table("api_jobs")
