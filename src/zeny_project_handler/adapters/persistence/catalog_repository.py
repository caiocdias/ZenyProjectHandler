"""Persistência versionada do catálogo técnico."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from zeny_project_handler.adapters.catalog.json_catalog import catalogo_de_dict, catalogo_para_dict
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import StatusCatalogo

from .errors import PersistenceConflictError
from .schema import catalog_items, catalog_versions


def _catalog_payload(catalog: CatalogoTecnico) -> tuple[str, str]:
    payload = json.dumps(
        catalogo_para_dict(catalog),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return payload, sha256(payload.encode("utf-8")).hexdigest()


class SqlCatalogRepository:
    """Repositório que impede alteração ou remoção de versões publicadas."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def obter(self, catalog_id: UUID) -> CatalogoTecnico | None:
        payload = self._session.scalar(
            select(catalog_versions.c.payload).where(catalog_versions.c.id == str(catalog_id))
        )
        if payload is None:
            return None
        raw = cast(dict[str, Any], json.loads(payload))
        return catalogo_de_dict(raw)

    def listar(self) -> tuple[CatalogoTecnico, ...]:
        payloads = self._session.scalars(
            select(catalog_versions.c.payload).order_by(catalog_versions.c.created_at)
        )
        return tuple(catalogo_de_dict(cast(dict[str, Any], json.loads(item))) for item in payloads)

    def salvar(self, catalog: CatalogoTecnico) -> None:
        payload, content_hash = _catalog_payload(catalog)
        catalog_id = str(catalog.id)
        existing = self._session.execute(
            select(catalog_versions.c.status, catalog_versions.c.content_hash).where(
                catalog_versions.c.id == catalog_id
            )
        ).one_or_none()
        if existing is not None:
            status, stored_hash = existing
            if stored_hash == content_hash:
                return
            if status != StatusCatalogo.RASCUNHO.value:
                raise PersistenceConflictError("Catálogo publicado ou arquivado é imutável")
            self._replace_draft(catalog, payload, content_hash)
            return
        self._insert_new(catalog, payload, content_hash)

    def remover_rascunho(self, catalog_id: UUID) -> bool:
        result = cast(
            CursorResult[Any],
            self._session.execute(
                delete(catalog_versions).where(
                    catalog_versions.c.id == str(catalog_id),
                    catalog_versions.c.status == StatusCatalogo.RASCUNHO.value,
                )
            ),
        )
        return bool(result.rowcount)

    def _insert_new(self, catalog: CatalogoTecnico, payload: str, content_hash: str) -> None:
        storage_status = (
            StatusCatalogo.RASCUNHO
            if catalog.status is StatusCatalogo.PUBLICADO
            else catalog.status
        )
        self._session.execute(
            insert(catalog_versions).values(
                id=str(catalog.id),
                version=catalog.versao,
                schema_version=catalog.versao_schema,
                status=storage_status.value,
                created_at=catalog.criado_em.isoformat(),
                published_at=(
                    catalog.publicado_em.isoformat() if catalog.publicado_em is not None else None
                ),
                content_hash=content_hash,
                payload=payload,
            )
        )
        self._insert_items(catalog)
        if storage_status is not catalog.status:
            self._session.execute(
                update(catalog_versions)
                .where(catalog_versions.c.id == str(catalog.id))
                .values(status=catalog.status.value)
            )

    def _replace_draft(self, catalog: CatalogoTecnico, payload: str, content_hash: str) -> None:
        catalog_id = str(catalog.id)
        self._session.execute(delete(catalog_items).where(catalog_items.c.catalog_id == catalog_id))
        self._session.execute(
            update(catalog_versions)
            .where(catalog_versions.c.id == catalog_id)
            .values(
                version=catalog.versao,
                schema_version=catalog.versao_schema,
                status=StatusCatalogo.RASCUNHO.value,
                created_at=catalog.criado_em.isoformat(),
                published_at=(
                    catalog.publicado_em.isoformat() if catalog.publicado_em is not None else None
                ),
                content_hash=content_hash,
                payload=payload,
            )
        )
        self._insert_items(catalog)
        if catalog.status is not StatusCatalogo.RASCUNHO:
            self._session.execute(
                update(catalog_versions)
                .where(catalog_versions.c.id == catalog_id)
                .values(status=catalog.status.value)
            )

    def _insert_items(self, catalog: CatalogoTecnico) -> None:
        self._session.execute(
            insert(catalog_items),
            [
                {
                    "catalog_id": str(catalog.id),
                    "item_id": str(item.id),
                    "category": item.categoria.value,
                    "code": item.codigo,
                    "active": item.ativo,
                }
                for item in catalog.itens
            ],
        )
