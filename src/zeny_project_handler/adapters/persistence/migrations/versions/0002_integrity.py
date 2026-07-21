"""Índices, data de atualização e proteção de catálogos publicados.

Revision ID: 0002_integrity
Revises: 0001_initial
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_integrity"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRIGGERS = (
    "trg_catalog_versions_published_update",
    "trg_catalog_versions_published_delete",
    "trg_catalog_items_published_insert",
    "trg_catalog_items_published_update",
    "trg_catalog_items_published_delete",
)


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "updated_at",
            sa.String(40),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_catalog_items_code", "catalog_items", ["catalog_id", "category", "code"])
    op.create_index("ix_documents_project", "documents", ["project_id"])
    op.create_index("ix_elements_project", "elements", ["project_id", "category"])
    op.create_index("ix_analysis_runs_project", "analysis_runs", ["project_id"])
    op.create_index("ix_evidence_execution", "evidence", ["execution_id"])
    op.create_index("ix_proposals_execution", "proposals", ["execution_id"])

    op.execute(
        """
        CREATE TRIGGER trg_catalog_versions_published_update
        BEFORE UPDATE ON catalog_versions
        WHEN OLD.status = 'PUBLICADO'
        BEGIN
            SELECT RAISE(ABORT, 'catalogo publicado e imutavel');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_catalog_versions_published_delete
        BEFORE DELETE ON catalog_versions
        WHEN OLD.status = 'PUBLICADO'
        BEGIN
            SELECT RAISE(ABORT, 'catalogo publicado e imutavel');
        END
        """
    )
    for operation in ("INSERT", "UPDATE", "DELETE"):
        row_alias = "NEW" if operation == "INSERT" else "OLD"
        op.execute(
            f"""
            CREATE TRIGGER trg_catalog_items_published_{operation.lower()}
            BEFORE {operation} ON catalog_items
            WHEN EXISTS (
                SELECT 1 FROM catalog_versions
                WHERE id = {row_alias}.catalog_id AND status = 'PUBLICADO'
            )
            BEGIN
                SELECT RAISE(ABORT, 'itens de catalogo publicado sao imutaveis');
            END
            """
        )


def downgrade() -> None:
    for trigger_name in _TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
    for table_name, index_name in (
        ("proposals", "ix_proposals_execution"),
        ("evidence", "ix_evidence_execution"),
        ("analysis_runs", "ix_analysis_runs_project"),
        ("elements", "ix_elements_project"),
        ("documents", "ix_documents_project"),
        ("catalog_items", "ix_catalog_items_code"),
    ):
        op.drop_index(index_name, table_name=table_name)
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("updated_at")
