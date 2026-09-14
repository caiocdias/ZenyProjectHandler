# mypy: disable-error-code="no-untyped-call"
"""Compare local annotation appearances without changing the source or semantic raster."""

from __future__ import annotations

import base64
import json
import re
from hashlib import sha256
from io import BytesIO
from typing import Any

import pymupdf
from PIL import Image, ImageChops

from zeny_project_handler.domain.analysis import OrigemObjetoPdf
from zeny_project_handler.domain.enums import TipoEvidencia, TipoOrigemPdf
from zeny_project_handler.ports.analysis import (
    CandidatoEvidenciaDocumento,
    MotorOcrPort,
    PaginaRasterOcr,
)

from .pymupdf_annotations import _annotation_info, _is_technical_annotation
from .pymupdf_support import _box_geometry

POLICY_VERSION = "1"
_CODE = re.compile(r"(?:[ABC]+N\s*-\s*\d+\s*\(\s*\d+\s*\)|\bN[1-4]\b)", re.I)


def extract_revision_appearances(
    page: Any,
    page_number: int,
    source_hash: str,
    candidates: tuple[CandidatoEvidenciaDocumento, ...],
    engine: MotorOcrPort | None,
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    """Record changed technical labels as candidates, never as approved drawing text.

    Pixel difference is evidence of overlap, not proof of an author's authority.
    Comments without a changed label produce no conflict and no semantic evidence.
    """
    annotations = tuple(page.annots() or ())
    results: list[CandidatoEvidenciaDocumento] = []
    seen: set[tuple[int, str]] = set()
    for candidate in candidates:
        if candidate.origem_pdf.tipo is not TipoOrigemPdf.CONTEUDO_PAGINA:
            continue
        if candidate.tipo not in {TipoEvidencia.TEXTO, TipoEvidencia.OCR}:
            continue
        codes = _CODE.findall(candidate.conteudo_bruto or "")
        if not codes:
            continue
        points = candidate.geometria.pontos
        rect = pymupdf.Rect(
            float(min(p.x for p in points)) * page.rect.width,
            float(min(p.y for p in points)) * page.rect.height,
            float(max(p.x for p in points)) * page.rect.width,
            float(max(p.y for p in points)) * page.rect.height,
        )
        for annotation in annotations:
            subtype = str(annotation.type[1])
            if _is_technical_annotation(subtype, _annotation_info(page, annotation.xref)):
                continue
            if not rect.intersects(annotation.rect * page.rotation_matrix):
                continue
            key = (annotation.xref, " ".join(codes))
            if key in seen:
                continue
            # Verify actual pixels on the label, rather than the annotation's bounding box alone.
            base = page.get_pixmap(clip=rect, dpi=300, alpha=False, annots=False)
            visible = page.get_pixmap(clip=rect, dpi=300, alpha=False, annots=True)
            diff = ImageChops.difference(
                Image.frombytes("RGB", (base.width, base.height), base.samples),
                Image.frombytes("RGB", (visible.width, visible.height), visible.samples),
            )
            changed = diff.getbbox()
            if changed is None:
                continue
            mask = BytesIO()
            diff.convert("L").point(lambda value: 255 if value else 0).save(mask, format="PNG")
            seen.add(key)
            affected = [a for a in annotations if rect.intersects(a.rect * page.rotation_matrix)]
            clip = pymupdf.Rect(rect)
            for related in affected:
                clip |= related.rect * page.rotation_matrix
                seen.add((related.xref, " ".join(codes)))
            clip += (-2, -2, 2, 2)
            clip &= page.rect
            # Memory is bounded per crop. Larger presentation objects use a lower DPI.
            dpi = min(1200, max(72, int(72 * (4_000_000 / (clip.width * clip.height)) ** 0.5)))
            base = page.get_pixmap(clip=clip, dpi=dpi, alpha=False, annots=False)
            visible = page.get_pixmap(clip=clip, dpi=dpi, alpha=False, annots=True)
            text = None
            ocr_failed = False
            if engine is not None:
                try:
                    readings = engine.reconhecer(
                        PaginaRasterOcr(
                            pagina_numero=page_number,
                            largura_pixels=visible.width,
                            altura_pixels=visible.height,
                            stride=visible.stride,
                            dados_rgb=visible.samples,
                            dpi=dpi,
                        )
                    )
                    text = " ".join(item.texto for item in readings)
                except Exception:
                    ocr_failed = True
            xrefs = sorted(
                a.xref for a in annotations if clip.intersects(a.rect * page.rotation_matrix)
            )
            payload = {
                "policy_version": POLICY_VERSION,
                "source_sha256": source_hash,
                "page_number": page_number,
                "annotation_xrefs": xrefs,
                "base_text": candidate.conteudo_bruto,
                "visible_text": text,
                "base_codes": codes,
                "visible_codes": _CODE.findall(text or ""),
                "classification": "candidata_revisao_tecnica",
                "authority": "nao_comprovada",
                "decision": None,
                "effective_value": None,
                "ocr_failed": ocr_failed,
                "operation_review_pending": any(code.upper() == "N4" for code in codes),
                "representation_xrefs": _representation_xrefs(candidates, xrefs),
                "annotation_details": [
                    {
                        "xref": a.xref,
                        "type": a.type[1],
                        "colors": a.colors,
                        "opacity": a.opacity,
                        "vertices": a.vertices,
                    }
                    for a in affected
                ],
                "changed_pixels_box": list(changed),
                "changed_pixels_mask_png": base64.b64encode(mask.getvalue()).decode("ascii"),
                "changed_pixels_dpi": 300,
                "changed_pixels_roi": [rect.x0, rect.y0, rect.x1, rect.y1],
                "base_raster_sha256": sha256(base.samples).hexdigest(),
                "visible_raster_sha256": sha256(visible.samples).hexdigest(),
                "base_png": base64.b64encode(base.tobytes("png")).decode("ascii"),
                "visible_png": base64.b64encode(visible.tobytes("png")).decode("ascii"),
            }
            identity = (
                f"{source_hash}:{page_number}:{xrefs}:"
                f"{payload['base_raster_sha256']}:{payload['visible_raster_sha256']}"
            )
            payload["group_id"] = sha256(identity.encode()).hexdigest()
            results.append(
                CandidatoEvidenciaDocumento(
                    chave_estavel=f"p{page_number}:revisao:{payload['group_id']}",
                    pagina_numero=page_number,
                    tipo=TipoEvidencia.VETOR,
                    geometria=_box_geometry(page, rect * page.derotation_matrix),
                    origem_pdf=OrigemObjetoPdf(
                        tipo=TipoOrigemPdf.APARENCIA_ANOTACAO,
                        numero_objeto=annotation.xref,
                        subtipo_anotacao=subtype,
                    ),
                    conteudo_bruto=None,
                    atributos_extraidos=(
                        ("revisao_tecnica", json.dumps(payload, ensure_ascii=False)),
                    ),
                )
            )
    return tuple({item.chave_estavel: item for item in results}.values())


def _representation_xrefs(
    candidates: tuple[CandidatoEvidenciaDocumento, ...],
    xrefs: list[int],
) -> list[int]:
    images = [
        item
        for item in candidates
        if item.tipo is TipoEvidencia.IMAGEM
        and item.origem_pdf.tipo is TipoOrigemPdf.APARENCIA_ANOTACAO
    ]
    digests = {
        item.conteudo_bruto
        for item in images
        if dict(item.atributos_extraidos).get("anotacao_xref") in xrefs
    }
    return sorted(
        {
            int(str(dict(item.atributos_extraidos)["anotacao_xref"]))
            for item in images
            if item.conteudo_bruto in digests
        }
    )
