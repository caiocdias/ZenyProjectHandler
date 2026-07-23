# mypy: disable-error-code="no-untyped-call"
"""Extração de anotações, appearance streams e seus recursos indiretos."""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Any, cast

from zeny_project_handler.domain.analysis import OrigemObjetoPdf
from zeny_project_handler.domain.enums import TipoEvidencia, TipoOrigemPdf
from zeny_project_handler.ports.analysis import (
    CandidatoEvidenciaDocumento,
    GeometriaNormalizada,
)

from .pymupdf_support import (
    _box_geometry,
    _extras,
    _optional_string,
    _stream_bytes,
)

_XREF_PATTERN = re.compile(r"(?<!\d)(\d+)\s+\d+\s+R")
_NAMED_XREF_PATTERN = re.compile(r"/([^\s/<>{}\[\]()]+)\s+(\d+)\s+\d+\s+R")
_NUMBER_PATTERN = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")


def _extract_annotations(
    document: Any,
    page: Any,
    page_number: int,
    max_depth: int,
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    candidates: list[CandidatoEvidenciaDocumento] = []
    for index, (raw_xref, fallback_type, field_name) in enumerate(page.annot_xrefs()):
        xref = int(raw_xref)
        subtype = _annotation_subtype(document, xref, int(fallback_type))
        field_type, field_has_value = _annotation_field_data(document, xref)
        geometry = _annotation_geometry(document, page, xref)
        if geometry is None:
            continue
        info = _annotation_info(page, xref)
        content = _optional_string(info.get("content"))
        evidence_type = TipoEvidencia.TEXTO if content else TipoEvidencia.VETOR
        candidates.append(
            CandidatoEvidenciaDocumento(
                chave_estavel=f"p{page_number}:anotacao:{index}:{xref}",
                pagina_numero=page_number,
                tipo=evidence_type,
                geometria=geometry,
                origem_pdf=OrigemObjetoPdf(
                    tipo=TipoOrigemPdf.ANOTACAO,
                    numero_objeto=xref,
                    indice_anotacao=index,
                    subtipo_anotacao=subtype,
                ),
                conteudo_bruto=content,
                atributos_extraidos=_extras(
                    subtipo=subtype,
                    nome=_optional_string(info.get("name")),
                    titulo=_optional_string(info.get("title")),
                    assunto=_optional_string(info.get("subject")),
                    campo_formulario=_optional_string(field_name),
                    tipo_campo_formulario=field_type,
                    campo_formulario_preenchido=field_has_value,
                ),
            )
        )
        for appearance_xref, appearance_name in _appearance_roots(document, xref):
            candidates.extend(
                _walk_appearance(
                    document=document,
                    page_number=page_number,
                    annotation_index=index,
                    annotation_xref=xref,
                    annotation_subtype=subtype,
                    root_xref=appearance_xref,
                    root_name=appearance_name,
                    geometry=geometry,
                    max_depth=max_depth,
                )
            )
    return tuple(candidates)


def _annotation_subtype(document: Any, xref: int, fallback: int) -> str:
    kind, value = document.xref_get_key(xref, "Subtype")
    return str(value).lstrip("/") if kind == "name" and value else f"Tipo-{fallback}"


def _annotation_field_data(document: Any, xref: int) -> tuple[str | None, bool]:
    field_kind, field_type = document.xref_get_key(xref, "FT")
    value_kind, value = document.xref_get_key(xref, "V")
    normalized_type = str(field_type).lstrip("/") if field_kind == "name" and field_type else None
    has_value = value_kind not in {"null", "none"} and str(value).strip() not in {"", "null"}
    return normalized_type, has_value


def _annotation_geometry(document: Any, page: Any, xref: int) -> GeometriaNormalizada | None:
    try:
        annotation = page.load_annot(xref)
    except Exception:
        annotation = None
    if annotation is not None and annotation.rect is not None:
        return _box_geometry(page, annotation.rect)
    kind, value = document.xref_get_key(xref, "Rect")
    numbers = [float(item) for item in _NUMBER_PATTERN.findall(str(value))]
    if kind == "array" and len(numbers) == 4:
        return _box_geometry(page, numbers, pdf_coordinates=True)
    return None


def _annotation_info(page: Any, xref: int) -> dict[str, Any]:
    try:
        annotation = page.load_annot(xref)
    except Exception:
        annotation = None
    return cast(dict[str, Any], annotation.info or {}) if annotation is not None else {}


def _appearance_roots(document: Any, annotation_xref: int) -> tuple[tuple[int, str], ...]:
    _kind, raw = document.xref_get_key(annotation_xref, "AP")
    value = str(raw)
    named = tuple((int(xref), name) for name, xref in _NAMED_XREF_PATTERN.findall(value))
    if named:
        return tuple(dict.fromkeys(named))
    return tuple((int(xref), "AP") for xref in dict.fromkeys(_XREF_PATTERN.findall(value)))


def _walk_appearance(
    *,
    document: Any,
    page_number: int,
    annotation_index: int,
    annotation_xref: int,
    annotation_subtype: str,
    root_xref: int,
    root_name: str,
    geometry: GeometriaNormalizada,
    max_depth: int,
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    candidates: list[CandidatoEvidenciaDocumento] = []
    queue: list[tuple[int, str | None, int]] = [(root_xref, root_name, 0)]
    visited: set[int] = set()
    while queue:
        xref, resource_name, depth = queue.pop(0)
        if xref in visited or depth > max_depth:
            continue
        visited.add(xref)
        subtype = _object_subtype(document, xref)
        if subtype in {"Form", "Image"} or xref == root_xref:
            evidence_type = TipoEvidencia.IMAGEM if subtype == "Image" else TipoEvidencia.VETOR
            stream = _stream_bytes(document, xref)
            candidates.append(
                CandidatoEvidenciaDocumento(
                    chave_estavel=f"p{page_number}:aparencia:{annotation_xref}:{root_xref}:{xref}",
                    pagina_numero=page_number,
                    tipo=evidence_type,
                    geometria=geometry,
                    origem_pdf=OrigemObjetoPdf(
                        tipo=TipoOrigemPdf.APARENCIA_ANOTACAO,
                        numero_objeto=xref,
                        indice_anotacao=annotation_index,
                        subtipo_anotacao=annotation_subtype,
                        nome_recurso=resource_name,
                    ),
                    conteudo_bruto=sha256(stream).hexdigest() if stream else None,
                    atributos_extraidos=_extras(
                        anotacao_xref=annotation_xref,
                        aparencia_raiz_xref=root_xref,
                        profundidade=depth,
                        subtipo_objeto=subtype or "desconhecido",
                        tamanho_stream=len(stream),
                        geometria_aproximada=True,
                    ),
                )
            )
        if depth < max_depth:
            queue.extend(
                (child_xref, name, depth + 1)
                for name, child_xref in _named_references(document, xref)
            )
    return tuple(candidates)


def _named_references(document: Any, xref: int) -> tuple[tuple[str, int], ...]:
    raw = str(document.xref_object(xref, compressed=False))
    named = [(name, int(reference)) for name, reference in _NAMED_XREF_PATTERN.findall(raw)]
    named_xrefs = {reference for _name, reference in named}
    named.extend(
        ("recurso", int(reference))
        for reference in _XREF_PATTERN.findall(raw)
        if int(reference) not in named_xrefs
    )
    return tuple(dict.fromkeys(named))


def _object_subtype(document: Any, xref: int) -> str | None:
    kind, value = document.xref_get_key(xref, "Subtype")
    return str(value).lstrip("/") if kind == "name" and value else None
