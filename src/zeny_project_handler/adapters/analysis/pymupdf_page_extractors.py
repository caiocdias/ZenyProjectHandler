# mypy: disable-error-code="no-untyped-call"
"""Extratores independentes de conteúdo nativo da página PDF."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from decimal import Decimal
from hashlib import sha256
from typing import Any, cast

import pymupdf

from zeny_project_handler.domain.analysis import OrigemObjetoPdf
from zeny_project_handler.domain.enums import TipoEvidencia, TipoGeometria, TipoOrigemPdf
from zeny_project_handler.ports.analysis import (
    CandidatoEvidenciaDocumento,
    GeometriaNormalizada,
)

from .pymupdf_support import (
    _box_geometry,
    _decimal_or_zero,
    _extras,
    _normalized_points,
    _pdf_color,
    _pdf_value,
    _srgb_color,
    _stream_bytes,
    _without_consecutive_duplicates,
)


def _extract_text(page: Any, page_number: int) -> tuple[CandidatoEvidenciaDocumento, ...]:
    candidates: list[CandidatoEvidenciaDocumento] = []
    raw = cast(dict[str, Any], page.get_text("rawdict", sort=False))
    for block_index, block in enumerate(raw.get("blocks", ())):
        if int(block.get("type", -1)) != 0:
            continue
        for line_index, line in enumerate(block.get("lines", ())):
            direction = cast(tuple[float, float], tuple(line.get("dir", (1.0, 0.0))))
            for span_index, span in enumerate(line.get("spans", ())):
                text = "".join(str(char.get("c", "")) for char in span.get("chars", ()))
                if not text.strip():
                    continue
                candidates.append(
                    CandidatoEvidenciaDocumento(
                        chave_estavel=f"p{page_number}:texto:{block_index}:{line_index}:{span_index}",
                        pagina_numero=page_number,
                        tipo=TipoEvidencia.TEXTO,
                        geometria=_text_geometry(page, line, span),
                        origem_pdf=OrigemObjetoPdf(),
                        conteudo_bruto=text,
                        atributos_extraidos=_extras(
                            bloco=block_index,
                            linha=line_index,
                            fonte=str(span.get("font") or ""),
                            tamanho=Decimal(str(span.get("size", 0))),
                            cor=_srgb_color(span.get("color")),
                            opacidade=int(span.get("alpha", 255)),
                            flags=int(span.get("flags", 0)),
                            modo_escrita=int(line.get("wmode", 0)),
                            rotacao_graus=Decimal(
                                str(round(math.degrees(math.atan2(-direction[1], direction[0])), 6))
                            ),
                            quantidade_caracteres=len(text),
                        ),
                    )
                )
    return tuple(candidates)


def _text_geometry(page: Any, line: dict[str, Any], span: dict[str, Any]) -> GeometriaNormalizada:
    try:
        quad = pymupdf.recover_quad(line.get("dir", (1.0, 0.0)), span)
        points = _normalized_points(page, (quad.ul, quad.ur, quad.lr, quad.ll))
        return GeometriaNormalizada(tipo=TipoGeometria.POLIGONO, pontos=points)
    except Exception:
        return _box_geometry(page, span["bbox"])


def _extract_vectors(page: Any, page_number: int) -> tuple[CandidatoEvidenciaDocumento, ...]:
    candidates = []
    for index, drawing in enumerate(page.get_drawings(extended=True)):
        items = tuple(drawing.get("items") or ())
        command_payload = [_vector_command(item) for item in items]
        candidates.append(
            CandidatoEvidenciaDocumento(
                chave_estavel=f"p{page_number}:vetor:{index}",
                pagina_numero=page_number,
                tipo=TipoEvidencia.VETOR,
                geometria=_vector_geometry(page, drawing, items),
                origem_pdf=OrigemObjetoPdf(),
                conteudo_bruto=json.dumps(
                    command_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ),
                atributos_extraidos=_extras(
                    tipo_caminho=str(drawing.get("type") or "path"),
                    comandos=len(items),
                    operacoes=",".join(str(item[0]) for item in items),
                    cor_contorno=_pdf_color(drawing.get("color")),
                    cor_preenchimento=_pdf_color(drawing.get("fill")),
                    espessura=_decimal_or_zero(drawing.get("width")),
                    tracejado=str(drawing.get("dashes") or ""),
                    fechado=_vector_is_closed(drawing, items),
                    camada=str(drawing.get("layer") or ""),
                    sequencia=int(drawing.get("seqno", -1)),
                ),
            )
        )
    return tuple(candidates)


def _vector_geometry(
    page: Any, drawing: dict[str, Any], items: tuple[Any, ...]
) -> GeometriaNormalizada:
    raw_points = _vector_points(items)
    points = _normalized_points(page, raw_points) if raw_points else ()
    unique = _without_consecutive_duplicates(points)
    operations = {str(item[0]) for item in items}
    if _vector_is_closed(drawing, items) and len(set(unique)) >= 3:
        return GeometriaNormalizada(tipo=TipoGeometria.POLIGONO, pontos=unique)
    if operations == {"l"} and len(unique) >= 2:
        return GeometriaNormalizada(tipo=TipoGeometria.POLILINHA, pontos=unique)
    rect = drawing.get("rect") or drawing.get("scissor")
    if rect is not None:
        return _box_geometry(page, rect)
    if len(unique) >= 2:
        return GeometriaNormalizada(tipo=TipoGeometria.POLILINHA, pontos=unique)
    raise ValueError("Caminho vetorial sem geometria utilizável")


def _vector_points(items: Iterable[Any]) -> tuple[Any, ...]:
    points: list[Any] = []
    for item in items:
        operation = str(item[0])
        if operation == "l":
            points.extend(item[1:3])
        elif operation == "c":
            points.extend(item[1:5])
        elif operation == "re":
            rect = pymupdf.Rect(item[1])
            points.extend((rect.tl, rect.tr, rect.br, rect.bl))
        elif operation == "qu":
            quad = pymupdf.Quad(item[1])
            points.extend((quad.ul, quad.ur, quad.lr, quad.ll))
    return tuple(points)


def _vector_is_closed(drawing: dict[str, Any], items: tuple[Any, ...]) -> bool:
    if drawing.get("closePath"):
        return True
    points = _vector_points(items)
    return len(points) > 2 and pymupdf.Point(points[0]) == pymupdf.Point(points[-1])


def _vector_command(item: Any) -> list[object]:
    return [str(item[0]), *[_pdf_value(value) for value in item[1:]]]


def _extract_images(page: Any, page_number: int) -> tuple[CandidatoEvidenciaDocumento, ...]:
    resources = {int(raw[0]): raw for raw in page.get_images(full=True)}
    candidates = []
    for index, image in enumerate(page.get_image_info(hashes=True, xrefs=True)):
        xref = int(image.get("xref") or 0)
        resource = resources.get(xref)
        referencer = int(resource[9]) if resource is not None else 0
        name = str(resource[7]) if resource is not None else None
        digest = image.get("digest")
        digest_hex = bytes(digest).hex() if digest is not None else ""
        origin_type = TipoOrigemPdf.FORM_XOBJECT if referencer else TipoOrigemPdf.CONTEUDO_PAGINA
        candidates.append(
            CandidatoEvidenciaDocumento(
                chave_estavel=f"p{page_number}:imagem:{index}:{xref}:{digest_hex}",
                pagina_numero=page_number,
                tipo=TipoEvidencia.IMAGEM,
                geometria=_box_geometry(page, image["bbox"]),
                origem_pdf=OrigemObjetoPdf(
                    tipo=origin_type,
                    numero_objeto=xref or None,
                    nome_recurso=name,
                ),
                conteudo_bruto=digest_hex or None,
                atributos_extraidos=_extras(
                    largura_pixels=int(image.get("width", 0)),
                    altura_pixels=int(image.get("height", 0)),
                    bits_por_componente=int(image.get("bpc", 0)),
                    espaco_cor=str(image.get("cs-name") or image.get("colorspace") or ""),
                    possui_mascara=bool(image.get("has-mask", False)),
                    referenciador_xref=referencer,
                    transformacao=json.dumps(
                        _pdf_value(image.get("transform")), separators=(",", ":")
                    ),
                ),
            )
        )
    return tuple(candidates)


def _extract_forms(
    document: Any, page: Any, page_number: int
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    candidates = []
    for index, raw in enumerate(page.get_xobjects()):
        xref, name, invoker, bbox = int(raw[0]), str(raw[1]), int(raw[2]), raw[3]
        stream = _stream_bytes(document, xref)
        candidates.append(
            CandidatoEvidenciaDocumento(
                chave_estavel=f"p{page_number}:form:{index}:{xref}:{invoker}",
                pagina_numero=page_number,
                tipo=TipoEvidencia.VETOR,
                geometria=_box_geometry(page, bbox, pdf_coordinates=True),
                origem_pdf=OrigemObjetoPdf(
                    tipo=TipoOrigemPdf.FORM_XOBJECT,
                    numero_objeto=xref,
                    nome_recurso=name,
                ),
                conteudo_bruto=sha256(stream).hexdigest() if stream else None,
                atributos_extraidos=_extras(
                    referenciador_xref=invoker,
                    tamanho_stream=len(stream),
                    subtipo="Form",
                ),
            )
        )
    return tuple(candidates)
