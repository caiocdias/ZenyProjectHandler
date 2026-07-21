"""Schema inicial da persistência local.

Revision ID: 0001_initial
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("published_at", sa.String(40)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_table(
        "catalog_items",
        sa.Column(
            "catalog_id",
            sa.String(36),
            sa.ForeignKey("catalog_versions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("item_id", sa.String(36), primary_key=True),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("code", sa.String(160), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("catalog_id", "item_id", name="uq_catalog_items_catalog_item"),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "catalog_id",
            sa.String(36),
            sa.ForeignKey("catalog_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.UniqueConstraint("id", "catalog_id", name="uq_projects_id_catalog"),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(260), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.UniqueConstraint("project_id", "position", name="uq_documents_project_position"),
        sa.UniqueConstraint("id", "project_id", name="uq_documents_id_project"),
    )
    op.create_table(
        "pages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id", "project_id"],
            ["documents.id", "documents.project_id"],
            ondelete="CASCADE",
            name="fk_pages_document_project",
        ),
        sa.UniqueConstraint("id", "project_id", name="uq_pages_id_project"),
        sa.UniqueConstraint("document_id", "page_number", name="uq_pages_document_number"),
    )
    op.create_table(
        "elements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("catalog_id", sa.String(36), nullable=False),
        sa.Column("catalog_item_id", sa.String(36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("situation", sa.String(20), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id", "catalog_id"],
            ["projects.id", "projects.catalog_id"],
            ondelete="CASCADE",
            name="fk_elements_project_catalog",
        ),
        sa.ForeignKeyConstraint(
            ["catalog_id", "catalog_item_id"],
            ["catalog_items.catalog_id", "catalog_items.item_id"],
            ondelete="RESTRICT",
            name="fk_elements_catalog_item",
        ),
        sa.UniqueConstraint("project_id", "position", name="uq_elements_project_position"),
        sa.UniqueConstraint("id", "project_id", name="uq_elements_id_project"),
    )
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("method", sa.String(160), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("started_at", sa.String(40), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.UniqueConstraint("id", "project_id", name="uq_analysis_runs_id_project"),
    )
    op.create_table(
        "evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("execution_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("page_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["execution_id", "project_id"],
            ["analysis_runs.id", "analysis_runs.project_id"],
            ondelete="CASCADE",
            name="fk_evidence_execution_project",
        ),
        sa.ForeignKeyConstraint(
            ["page_id", "project_id"],
            ["pages.id", "pages.project_id"],
            ondelete="RESTRICT",
            name="fk_evidence_page_project",
        ),
        sa.UniqueConstraint("id", "project_id", name="uq_evidence_id_project"),
    )
    op.create_table(
        "proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("execution_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("review_state", sa.String(20), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["execution_id", "project_id"],
            ["analysis_runs.id", "analysis_runs.project_id"],
            ondelete="CASCADE",
            name="fk_proposals_execution_project",
        ),
        sa.UniqueConstraint("id", "project_id", name="uq_proposals_id_project"),
    )
    op.create_table(
        "proposal_evidence",
        sa.Column("proposal_id", sa.String(36), primary_key=True),
        sa.Column("evidence_id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.ForeignKeyConstraint(
            ["proposal_id", "project_id"],
            ["proposals.id", "proposals.project_id"],
            ondelete="CASCADE",
            name="fk_proposal_evidence_proposal_project",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "project_id"],
            ["evidence.id", "evidence.project_id"],
            ondelete="RESTRICT",
            name="fk_proposal_evidence_evidence_project",
        ),
    )
    op.create_table(
        "review_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("proposal_id", sa.String(36), nullable=False, unique=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("confirmed_element_id", sa.String(36)),
        sa.Column("decided_at", sa.String(40), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["proposal_id", "project_id"],
            ["proposals.id", "proposals.project_id"],
            ondelete="CASCADE",
            name="fk_review_decisions_proposal_project",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_element_id", "project_id"],
            ["elements.id", "elements.project_id"],
            ondelete="RESTRICT",
            name="fk_review_decisions_element_project",
        ),
    )


def downgrade() -> None:
    for table_name in (
        "review_decisions",
        "proposal_evidence",
        "proposals",
        "evidence",
        "analysis_runs",
        "elements",
        "pages",
        "documents",
        "projects",
        "catalog_items",
        "catalog_versions",
    ):
        op.drop_table(table_name)
