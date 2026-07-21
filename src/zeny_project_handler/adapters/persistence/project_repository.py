"""Persistência do agregado de projeto e suas projeções consultáveis."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import StatusCatalogo
from zeny_project_handler.domain.project import (
    Cabo,
    ElementoProjetoType,
    Equipamento,
    EstruturaBt,
    EstruturaMt,
    Poste,
    Projeto,
    validar_projeto_com_catalogo,
)

from .catalog_repository import SqlCatalogRepository
from .domain_json import dumps_domain, loads_domain
from .errors import PersistenceConflictError, PersistenceNotFoundError
from .schema import documents, elements, pages, projects


def _digest(payload: str) -> str:
    return sha256(payload.encode("utf-8")).hexdigest()


class SqlProjectRepository:
    """Repositório de escrita do agregado Projeto."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def obter(self, project_id: UUID) -> Projeto | None:
        payload = self._session.scalar(
            select(projects.c.payload).where(projects.c.id == str(project_id))
        )
        return loads_domain(payload, Projeto) if payload is not None else None

    def listar(self) -> tuple[Projeto, ...]:
        payloads = self._session.scalars(select(projects.c.payload).order_by(projects.c.created_at))
        return tuple(loads_domain(payload, Projeto) for payload in payloads)

    def salvar(self, project: Projeto) -> None:
        catalog = SqlCatalogRepository(self._session).obter(project.catalogo_versao_id)
        if catalog is None:
            raise PersistenceNotFoundError("Catálogo do projeto não foi persistido")
        if catalog.status is not StatusCatalogo.PUBLICADO:
            raise PersistenceConflictError("Projeto somente pode usar catálogo publicado")
        validar_projeto_com_catalogo(project, catalog)

        payload = dumps_domain(project)
        project_id = str(project.id)
        existing_catalog_id = self._session.scalar(
            select(projects.c.catalog_id).where(projects.c.id == project_id)
        )
        now = datetime.now(UTC).isoformat()
        values = {
            "catalog_id": str(project.catalogo_versao_id),
            "name": project.nome,
            "created_at": project.criado_em.isoformat(),
            "updated_at": now,
            "content_hash": _digest(payload),
            "payload": payload,
        }
        if existing_catalog_id is None:
            self._session.execute(sqlite_insert(projects).values(id=project_id, **values))
        else:
            if existing_catalog_id != str(project.catalogo_versao_id):
                raise PersistenceConflictError(
                    "A versão de catálogo de um projeto persistido não pode ser trocada"
                )
            self._session.execute(
                update(projects).where(projects.c.id == project_id).values(**values)
            )

        self._sync_documents(project)
        self._sync_elements(project)

    def remover(self, project_id: UUID) -> bool:
        result = cast(
            CursorResult[Any],
            self._session.execute(delete(projects).where(projects.c.id == str(project_id))),
        )
        return bool(result.rowcount)

    def _sync_documents(self, project: Projeto) -> None:
        project_id = str(project.id)
        self._session.execute(
            update(documents)
            .where(documents.c.project_id == project_id)
            .values(position=-(documents.c.position + 1))
        )
        requested_ids = {str(document.id) for document in project.documentos}
        for position, document in enumerate(project.documentos):
            self._upsert_document(project_id, position, document)
            self._sync_pages(project_id, document)
        deletion = delete(documents).where(documents.c.project_id == project_id)
        if requested_ids:
            deletion = deletion.where(documents.c.id.not_in(requested_ids))
        self._session.execute(deletion)

    def _upsert_document(self, project_id: str, position: int, document: DocumentoProjeto) -> None:
        self._assert_project_owner(documents, str(document.id), project_id)
        statement = sqlite_insert(documents).values(
            id=str(document.id),
            project_id=project_id,
            position=position,
            file_name=document.nome_arquivo,
            sha256=document.sha256,
            payload=dumps_domain(document),
        )
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[documents.c.id],
                set_={
                    "position": position,
                    "file_name": document.nome_arquivo,
                    "sha256": document.sha256,
                    "payload": dumps_domain(document),
                },
            )
        )

    def _sync_pages(self, project_id: str, document: DocumentoProjeto) -> None:
        document_id = str(document.id)
        self._session.execute(
            update(pages)
            .where(pages.c.document_id == document_id)
            .values(page_number=-(pages.c.page_number + 1))
        )
        requested_ids = {str(page.id) for page in document.paginas}
        for page in document.paginas:
            self._upsert_page(project_id, document_id, page)
        deletion = delete(pages).where(pages.c.document_id == document_id)
        if requested_ids:
            deletion = deletion.where(pages.c.id.not_in(requested_ids))
        self._session.execute(deletion)

    def _upsert_page(self, project_id: str, document_id: str, page: PaginaDocumento) -> None:
        self._assert_project_owner(pages, str(page.id), project_id)
        statement = sqlite_insert(pages).values(
            id=str(page.id),
            document_id=document_id,
            project_id=project_id,
            page_number=page.numero,
            payload=dumps_domain(page),
        )
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[pages.c.id],
                set_={"page_number": page.numero, "payload": dumps_domain(page)},
            )
        )

    def _sync_elements(self, project: Projeto) -> None:
        project_id = str(project.id)
        self._session.execute(
            update(elements)
            .where(elements.c.project_id == project_id)
            .values(position=-(elements.c.position + 1))
        )
        requested_ids = {str(element.id) for element in project.elementos}
        for position, element in enumerate(project.elementos):
            self._upsert_element(project, position, element)
        deletion = delete(elements).where(elements.c.project_id == project_id)
        if requested_ids:
            deletion = deletion.where(elements.c.id.not_in(requested_ids))
        self._session.execute(deletion)

    def _upsert_element(
        self, project: Projeto, position: int, element: ElementoProjetoType
    ) -> None:
        self._assert_project_owner(elements, str(element.id), str(project.id))
        statement = sqlite_insert(elements).values(
            id=str(element.id),
            project_id=str(project.id),
            catalog_id=str(project.catalogo_versao_id),
            catalog_item_id=str(element.tipo_catalogo_id),
            position=position,
            category=element.categoria.value,
            situation=element.situacao.value,
            payload=dumps_domain(element),
        )
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[elements.c.id],
                set_={
                    "catalog_item_id": str(element.tipo_catalogo_id),
                    "position": position,
                    "category": element.categoria.value,
                    "situation": element.situacao.value,
                    "payload": dumps_domain(element),
                },
            )
        )

    def _assert_project_owner(self, table: Any, entity_id: str, project_id: str) -> None:
        owner = self._session.scalar(select(table.c.project_id).where(table.c.id == entity_id))
        if owner is not None and owner != project_id:
            raise PersistenceConflictError("Identificador já pertence a outro projeto")


class SqlDocumentRepository:
    """Projeção de leitura dos documentos pertencentes aos projetos."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def obter(self, document_id: UUID) -> DocumentoProjeto | None:
        payload = self._session.scalar(
            select(documents.c.payload).where(documents.c.id == str(document_id))
        )
        return loads_domain(payload, DocumentoProjeto) if payload is not None else None

    def listar_do_projeto(self, project_id: UUID) -> tuple[DocumentoProjeto, ...]:
        payloads = self._session.scalars(
            select(documents.c.payload)
            .where(documents.c.project_id == str(project_id))
            .order_by(documents.c.position)
        )
        return tuple(loads_domain(payload, DocumentoProjeto) for payload in payloads)


class SqlElementRepository:
    """Projeção de leitura dos elementos confirmados."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def obter(self, element_id: UUID) -> ElementoProjetoType | None:
        payload = self._session.scalar(
            select(elements.c.payload).where(elements.c.id == str(element_id))
        )
        if payload is None:
            return None
        return cast(
            ElementoProjetoType,
            loads_domain(payload, (Poste, EstruturaMt, EstruturaBt, Cabo, Equipamento)),
        )

    def listar_do_projeto(self, project_id: UUID) -> tuple[ElementoProjetoType, ...]:
        payloads = self._session.scalars(
            select(elements.c.payload)
            .where(elements.c.project_id == str(project_id))
            .order_by(elements.c.position)
        )
        expected_types = (Poste, EstruturaMt, EstruturaBt, Cabo, Equipamento)
        return tuple(
            cast(ElementoProjetoType, loads_domain(payload, expected_types)) for payload in payloads
        )
