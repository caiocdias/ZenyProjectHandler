"""Schema relacional usado como índice íntegro dos agregados persistidos."""

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)

catalog_versions = Table(
    "catalog_versions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("status", String(20), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("published_at", String(40)),
    Column("content_hash", String(64), nullable=False),
    Column("payload", Text, nullable=False),
)

catalog_items = Table(
    "catalog_items",
    metadata,
    Column(
        "catalog_id",
        String(36),
        ForeignKey("catalog_versions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("item_id", String(36), primary_key=True),
    Column("category", String(30), nullable=False),
    Column("code", String(160), nullable=False),
    Column("active", Boolean, nullable=False),
    UniqueConstraint("catalog_id", "item_id", name="uq_catalog_items_catalog_item"),
)

projects = Table(
    "projects",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "catalog_id",
        String(36),
        ForeignKey("catalog_versions.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("name", String(240), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("payload", Text, nullable=False),
    UniqueConstraint("id", "catalog_id", name="uq_projects_id_catalog"),
)

documents = Table(
    "documents",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("project_id", String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
    Column("position", Integer, nullable=False),
    Column("file_name", String(260), nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("payload", Text, nullable=False),
    UniqueConstraint("project_id", "position", name="uq_documents_project_position"),
    UniqueConstraint("id", "project_id", name="uq_documents_id_project"),
)

document_sources = Table(
    "document_sources",
    metadata,
    Column(
        "document_id",
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("project_id", String(36), nullable=False),
    Column("canonical_path", Text, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("modified_at_ns", String(24), nullable=False),
    ForeignKeyConstraint(
        ["document_id", "project_id"],
        ["documents.id", "documents.project_id"],
        ondelete="CASCADE",
        name="fk_document_sources_document_project",
    ),
)

pages = Table(
    "pages",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "document_id", String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    ),
    Column("project_id", String(36), nullable=False),
    Column("page_number", Integer, nullable=False),
    Column("payload", Text, nullable=False),
    ForeignKeyConstraint(
        ["document_id", "project_id"],
        ["documents.id", "documents.project_id"],
        ondelete="CASCADE",
        name="fk_pages_document_project",
    ),
    UniqueConstraint("id", "project_id", name="uq_pages_id_project"),
    UniqueConstraint("document_id", "page_number", name="uq_pages_document_number"),
)

elements = Table(
    "elements",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("project_id", String(36), nullable=False),
    Column("catalog_id", String(36), nullable=False),
    Column("catalog_item_id", String(36), nullable=False),
    Column("position", Integer, nullable=False),
    Column("category", String(30), nullable=False),
    Column("situation", String(20), nullable=False),
    Column("payload", Text, nullable=False),
    ForeignKeyConstraint(
        ["project_id", "catalog_id"],
        ["projects.id", "projects.catalog_id"],
        ondelete="CASCADE",
        name="fk_elements_project_catalog",
    ),
    ForeignKeyConstraint(
        ["catalog_id", "catalog_item_id"],
        ["catalog_items.catalog_id", "catalog_items.item_id"],
        ondelete="RESTRICT",
        name="fk_elements_catalog_item",
    ),
    UniqueConstraint("project_id", "position", name="uq_elements_project_position"),
    UniqueConstraint("id", "project_id", name="uq_elements_id_project"),
)

confirmed_relations = Table(
    "confirmed_relations",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("project_id", String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
    Column("position", Integer, nullable=False),
    Column("relation_type", String(80), nullable=False),
    Column("origin_id", String(36), nullable=False),
    Column("destination_id", String(36), nullable=False),
    Column("payload", Text, nullable=False),
    UniqueConstraint("project_id", "position", name="uq_confirmed_relations_project_position"),
    UniqueConstraint("id", "project_id", name="uq_confirmed_relations_id_project"),
)

analysis_runs = Table(
    "analysis_runs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("project_id", String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
    Column("method", String(160), nullable=False),
    Column("state", String(20), nullable=False),
    Column("started_at", String(40), nullable=False),
    Column("payload", Text, nullable=False),
    UniqueConstraint("id", "project_id", name="uq_analysis_runs_id_project"),
)

evidence = Table(
    "evidence",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("execution_id", String(36), nullable=False),
    Column("project_id", String(36), nullable=False),
    Column("page_id", String(36), nullable=False),
    Column("kind", String(20), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("payload", Text, nullable=False),
    ForeignKeyConstraint(
        ["execution_id", "project_id"],
        ["analysis_runs.id", "analysis_runs.project_id"],
        ondelete="CASCADE",
        name="fk_evidence_execution_project",
    ),
    ForeignKeyConstraint(
        ["page_id", "project_id"],
        ["pages.id", "pages.project_id"],
        ondelete="RESTRICT",
        name="fk_evidence_page_project",
    ),
    UniqueConstraint("id", "project_id", name="uq_evidence_id_project"),
)

proposals = Table(
    "proposals",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("execution_id", String(36), nullable=False),
    Column("project_id", String(36), nullable=False),
    Column("kind", String(20), nullable=False),
    Column("review_state", String(20), nullable=False),
    Column("payload", Text, nullable=False),
    ForeignKeyConstraint(
        ["execution_id", "project_id"],
        ["analysis_runs.id", "analysis_runs.project_id"],
        ondelete="CASCADE",
        name="fk_proposals_execution_project",
    ),
    UniqueConstraint("id", "project_id", name="uq_proposals_id_project"),
)

proposal_evidence = Table(
    "proposal_evidence",
    metadata,
    Column("proposal_id", String(36), primary_key=True),
    Column("evidence_id", String(36), primary_key=True),
    Column("project_id", String(36), nullable=False),
    ForeignKeyConstraint(
        ["proposal_id", "project_id"],
        ["proposals.id", "proposals.project_id"],
        ondelete="CASCADE",
        name="fk_proposal_evidence_proposal_project",
    ),
    ForeignKeyConstraint(
        ["evidence_id", "project_id"],
        ["evidence.id", "evidence.project_id"],
        ondelete="RESTRICT",
        name="fk_proposal_evidence_evidence_project",
    ),
)

review_decisions = Table(
    "review_decisions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("proposal_id", String(36), nullable=False, unique=True),
    Column("project_id", String(36), nullable=False),
    Column("confirmed_element_id", String(36)),
    Column("decided_at", String(40), nullable=False),
    Column("payload", Text, nullable=False),
    ForeignKeyConstraint(
        ["proposal_id", "project_id"],
        ["proposals.id", "proposals.project_id"],
        ondelete="CASCADE",
        name="fk_review_decisions_proposal_project",
    ),
    ForeignKeyConstraint(
        ["confirmed_element_id", "project_id"],
        ["elements.id", "elements.project_id"],
        ondelete="RESTRICT",
        name="fk_review_decisions_element_project",
    ),
)
