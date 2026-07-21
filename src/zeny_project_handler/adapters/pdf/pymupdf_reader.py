"""Leitura somente leitura e tolerante a falhas usando PyMuPDF."""

from __future__ import annotations

import re
from collections.abc import Callable
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any, TypeVar, cast
from uuid import UUID, uuid4

import pymupdf

from zeny_project_handler.domain.documents import VALID_ROTATIONS, DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.values import CaixaPagina
from zeny_project_handler.ports.pdf import (
    AnotacaoPdf,
    DiagnosticoPdf,
    FormXObjectPdf,
    FragmentoTextoPdf,
    GraficoVetorialPdf,
    GrupoConteudoOpcionalPdf,
    ImagemIncorporadaPdf,
    InspecaoPdf,
    InventarioPaginaPdf,
    PaginaPdfRenderizada,
    PdfRectangle,
)

from .errors import (
    PdfArquivoInvalidoError,
    PdfOrigemAlteradaError,
    PdfPaginaInvalidaError,
    PdfProtegidoError,
)

_XREF_PATTERN = re.compile(r"(?<!\d)(\d+)\s+\d+\s+R")
_READ_CHUNK_SIZE = 1024 * 1024
T = TypeVar("T")


class PyMuPdfReader:
    """Inspeciona conteúdo nativo e renderiza sem chamar qualquer API de gravação."""

    adapter_name = f"PyMuPDF {pymupdf.__version__}"

    def inspecionar(
        self,
        caminho: Path,
        *,
        senha: str | None = None,
        documento_id: UUID | None = None,
    ) -> InspecaoPdf:
        source = _validated_path(caminho)
        initial_stat = source.stat()
        digest = _file_sha256(source)
        document = _open_document(source, senha)
        try:
            diagnostics: list[DiagnosticoPdf] = []
            if document.is_repaired:
                diagnostics.append(
                    DiagnosticoPdf(
                        codigo="pdf.documento_reparado",
                        mensagem="O leitor reparou inconsistências estruturais durante a abertura.",
                    )
                )
            ocgs, ocg_diagnostics = _safe_extract(
                "pdf.ocg_nao_lido",
                "Não foi possível inventariar grupos de conteúdo opcional.",
                lambda: _extract_ocgs(document),
            )
            diagnostics.extend(ocg_diagnostics)
            pages = tuple(_inspect_page(document, index) for index in range(document.page_count))
            metadata = cast(dict[str, Any], document.metadata or {})
            project_document = DocumentoProjeto(
                id=documento_id or uuid4(),
                nome_arquivo=source.name,
                sha256=digest,
                paginas=tuple(item.pagina for item in pages),
                tamanho_bytes=initial_stat.st_size,
                versao_pdf=_optional_string(metadata.get("format")),
                produtor=_optional_string(metadata.get("producer")),
            )
        finally:
            document.close()

        final_stat = source.stat()
        if (
            final_stat.st_size != initial_stat.st_size
            or final_stat.st_mtime_ns != initial_stat.st_mtime_ns
            or _file_sha256(source) != digest
        ):
            raise PdfOrigemAlteradaError("O PDF foi alterado durante a inspeção")
        return InspecaoPdf(
            documento=project_document,
            caminho_origem=source,
            tamanho_bytes=final_stat.st_size,
            modificado_em_ns=final_stat.st_mtime_ns,
            adaptador=self.adapter_name,
            paginas=pages,
            grupos_conteudo_opcional=ocgs,
            diagnosticos=tuple(diagnostics),
        )

    def renderizar_pagina(
        self,
        caminho: Path,
        pagina_numero: int,
        *,
        dpi: int,
        rotacao_adicional_graus: int = 0,
        recorte_normalizado: PdfRectangle | None = None,
        senha: str | None = None,
        sha256_esperado: str | None = None,
    ) -> PaginaPdfRenderizada:
        source = _validated_path(caminho)
        _validate_render_parameters(dpi, rotacao_adicional_graus, recorte_normalizado)
        if sha256_esperado is not None and _file_sha256(source) != sha256_esperado:
            raise PdfOrigemAlteradaError("O conteúdo do PDF não corresponde ao hash registrado")
        document = _open_document(source, senha)
        try:
            if not 1 <= pagina_numero <= document.page_count:
                raise PdfPaginaInvalidaError("Número de página fora do documento")
            page = document.load_page(pagina_numero - 1)
            matrix = pymupdf.Matrix(dpi / 72, dpi / 72).prerotate(  # type: ignore[no-untyped-call]
                rotacao_adicional_graus
            )
            pixmap = page.get_pixmap(
                matrix=matrix,
                colorspace=pymupdf.csRGB,
                alpha=False,
                clip=_normalized_clip(page, recorte_normalizado),
                annots=True,
            )
            return PaginaPdfRenderizada(
                pagina_numero=pagina_numero,
                largura_pixels=pixmap.width,
                altura_pixels=pixmap.height,
                stride=pixmap.stride,
                dados_rgb=bytes(pixmap.samples),
                dpi=dpi,
                rotacao_adicional_graus=rotacao_adicional_graus,
            )
        except PdfPaginaInvalidaError:
            raise
        except Exception as error:
            raise PdfPaginaInvalidaError(
                "Não foi possível rasterizar a página solicitada"
            ) from error
        finally:
            document.close()

    def renderizar_miniatura(
        self,
        caminho: Path,
        pagina_numero: int,
        *,
        dpi: int = 36,
        senha: str | None = None,
        sha256_esperado: str | None = None,
    ) -> PaginaPdfRenderizada:
        return self.renderizar_pagina(
            caminho,
            pagina_numero,
            dpi=dpi,
            senha=senha,
            sha256_esperado=sha256_esperado,
        )

    def verificar_origem(self, inspecao: InspecaoPdf) -> None:
        source = _validated_path(inspecao.caminho_origem)
        current_stat = source.stat()
        if (
            current_stat.st_size != inspecao.tamanho_bytes
            or _file_sha256(source) != inspecao.documento.sha256
        ):
            raise PdfOrigemAlteradaError("O PDF foi alterado depois da inspeção")


def _validated_path(path: Path) -> Path:
    try:
        source = path.expanduser().resolve(strict=True)
    except OSError as error:
        raise PdfArquivoInvalidoError("Arquivo PDF não encontrado") from error
    if not source.is_file() or source.suffix.casefold() != ".pdf":
        raise PdfArquivoInvalidoError("Selecione um arquivo com extensão PDF")
    return source


def _file_sha256(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(_READ_CHUNK_SIZE):
                digest.update(chunk)
    except OSError as error:
        raise PdfArquivoInvalidoError("Não foi possível ler o arquivo PDF") from error
    return digest.hexdigest()


def _open_document(path: Path, password: str | None) -> Any:
    try:
        document = pymupdf.open(filename=str(path))  # type: ignore[no-untyped-call]
    except Exception as error:
        raise PdfArquivoInvalidoError("O arquivo não é um PDF válido ou está corrompido") from error
    if not document.is_pdf or document.page_count < 1:
        document.close()  # type: ignore[no-untyped-call]
        raise PdfArquivoInvalidoError("O arquivo não contém um documento PDF paginado")
    if document.needs_pass and (
        not password or document.authenticate(password) <= 0  # type: ignore[no-untyped-call]
    ):
        document.close()  # type: ignore[no-untyped-call]
        raise PdfProtegidoError("O PDF requer uma senha válida")
    return document


def _inspect_page(document: Any, page_index: int) -> InventarioPaginaPdf:
    page = document.load_page(page_index)
    page_number = page_index + 1
    diagnostics: list[DiagnosticoPdf] = []
    text, found = _safe_extract(
        "pdf.texto_nao_lido",
        "A extração de texto falhou; os demais recursos permanecem disponíveis.",
        lambda: _extract_text(page),
        page_number,
    )
    diagnostics.extend(found)
    vectors, found = _safe_extract(
        "pdf.vetor_nao_lido",
        "A extração vetorial falhou; os demais recursos permanecem disponíveis.",
        lambda: _extract_vectors(page),
        page_number,
    )
    diagnostics.extend(found)
    images, found = _safe_extract(
        "pdf.imagem_nao_lida",
        "O inventário de imagens falhou; os demais recursos permanecem disponíveis.",
        lambda: _extract_images(page),
        page_number,
    )
    diagnostics.extend(found)
    annotations, annotation_diagnostics = _extract_annotations(document, page, page_number)
    diagnostics.extend(annotation_diagnostics)
    forms, found = _safe_extract(
        "pdf.xobject_nao_lido",
        "O inventário de Form XObjects falhou; os demais recursos permanecem disponíveis.",
        lambda: _extract_forms(page),
        page_number,
    )
    diagnostics.extend(found)
    diagnostics.extend(_mupdf_diagnostics(page_number))
    return InventarioPaginaPdf(
        pagina=_page_model(page, page_number),
        textos=text,
        vetores=vectors,
        imagens=images,
        anotacoes=annotations,
        forms_xobjects=forms,
        diagnosticos=tuple(diagnostics),
    )


def _page_model(page: Any, page_number: int) -> PaginaDocumento:
    rect = page.rect
    return PaginaDocumento(
        id=uuid4(),
        numero=page_number,
        largura_pontos=Decimal(str(rect.width)),
        altura_pontos=Decimal(str(rect.height)),
        rotacao_graus=int(page.rotation),
        media_box=_box(page.mediabox),
        crop_box=_box(page.cropbox),
        matriz_pdf_para_pagina=_matrix(page.transformation_matrix),
        matriz_rotacao_pagina=_matrix(page.rotation_matrix),
    )


def _box(rect: Any) -> CaixaPagina:
    return CaixaPagina(
        Decimal(str(rect.x0)),
        Decimal(str(rect.y0)),
        Decimal(str(rect.x1)),
        Decimal(str(rect.y1)),
    )


def _matrix(matrix: Any) -> tuple[Decimal, ...]:
    return tuple(Decimal(str(value)) for value in matrix)


def _safe_extract(
    code: str,
    message: str,
    extractor: Callable[[], tuple[T, ...]],
    page_number: int | None = None,
) -> tuple[tuple[T, ...], tuple[DiagnosticoPdf, ...]]:
    try:
        return extractor(), ()
    except Exception:
        return (), (DiagnosticoPdf(code, message, page_number),)


def _extract_text(page: Any) -> tuple[FragmentoTextoPdf, ...]:
    fragments: list[FragmentoTextoPdf] = []
    for block in page.get_text("blocks", sort=False):
        if len(block) < 7 or int(block[6]) != 0:
            continue
        text = str(block[4])
        if text:
            fragments.append(FragmentoTextoPdf(text, _rect_tuple(block[:4])))
    return tuple(fragments)


def _extract_vectors(page: Any) -> tuple[GraficoVetorialPdf, ...]:
    vectors: list[GraficoVetorialPdf] = []
    for drawing in page.get_drawings(extended=True):
        rect = drawing.get("rect")
        items = drawing.get("items") or ()
        if rect is not None:
            vectors.append(
                GraficoVetorialPdf(
                    tipo=str(drawing.get("type") or "path"),
                    caixa=_rect_tuple(rect),
                    quantidade_comandos=len(items),
                )
            )
    return tuple(vectors)


def _extract_images(page: Any) -> tuple[ImagemIncorporadaPdf, ...]:
    return tuple(
        ImagemIncorporadaPdf(
            xref=int(raw[0]),
            mascara_xref=int(raw[1]),
            largura=int(raw[2]),
            altura=int(raw[3]),
            bits_por_componente=int(raw[4]),
            espaco_cor=str(raw[5]),
            nome=str(raw[7]),
            filtro=str(raw[8]),
            referenciador_xref=int(raw[9]),
        )
        for raw in page.get_images(full=True)
    )


def _extract_annotations(
    document: Any,
    page: Any,
    page_number: int,
) -> tuple[tuple[AnotacaoPdf, ...], tuple[DiagnosticoPdf, ...]]:
    annotations: list[AnotacaoPdf] = []
    diagnostics: list[DiagnosticoPdf] = []
    try:
        references = page.annot_xrefs()
    except Exception:
        return (), (
            DiagnosticoPdf(
                "pdf.anotacao_malformada",
                "A lista de anotações da página não pôde ser lida.",
                page_number,
            ),
        )
    for xref, type_number, _field_name in references:
        try:
            subtype = _annotation_subtype(document, int(xref), int(type_number))
            appearances = _appearance_xrefs(document, int(xref))
        except Exception:
            diagnostics.append(
                DiagnosticoPdf(
                    "pdf.anotacao_malformada",
                    "Uma anotação isolada não pôde ser interpretada.",
                    page_number,
                    int(xref),
                )
            )
            continue
        try:
            rectangle = _annotation_rect(page, int(xref))
        except Exception:
            rectangle = None
            diagnostics.append(
                DiagnosticoPdf(
                    "pdf.anotacao_malformada",
                    "A geometria de uma anotação isolada não pôde ser interpretada.",
                    page_number,
                    int(xref),
                )
            )
        annotations.append(
            AnotacaoPdf(
                xref=int(xref),
                subtipo=subtype,
                caixa=rectangle,
                aparencias_xrefs=appearances,
            )
        )
    return tuple(annotations), tuple(diagnostics)


def _annotation_subtype(document: Any, xref: int, fallback_type: int) -> str:
    kind, value = document.xref_get_key(xref, "Subtype")
    if kind == "name" and value:
        return str(value).lstrip("/")
    return f"Tipo-{fallback_type}"


def _annotation_rect(page: Any, xref: int) -> PdfRectangle | None:
    annotation = page.load_annot(xref)
    return _rect_tuple(annotation.rect) if annotation is not None else None


def _appearance_xrefs(document: Any, annotation_xref: int) -> tuple[int, ...]:
    _kind, value = document.xref_get_key(annotation_xref, "AP")
    return tuple(sorted({int(match) for match in _XREF_PATTERN.findall(str(value))}))


def _extract_forms(page: Any) -> tuple[FormXObjectPdf, ...]:
    return tuple(
        FormXObjectPdf(
            xref=int(raw[0]),
            nome=str(raw[1]),
            referenciador_xref=int(raw[2]),
            caixa=_rect_tuple(raw[3]),
        )
        for raw in page.get_xobjects()
    )


def _extract_ocgs(document: Any) -> tuple[GrupoConteudoOpcionalPdf, ...]:
    return tuple(
        GrupoConteudoOpcionalPdf(
            xref=int(xref),
            nome=str(raw.get("name") or ""),
            ligado=bool(raw.get("on")),
            intencoes=tuple(str(value) for value in raw.get("intent") or ()),
        )
        for xref, raw in document.get_ocgs().items()
    )


def _mupdf_diagnostics(page_number: int) -> tuple[DiagnosticoPdf, ...]:
    raw_warnings = _raw_mupdf_warnings()
    diagnostics = []
    for warning in raw_warnings.splitlines():
        normalized = warning.casefold()
        code = "pdf.objeto_nao_suportado"
        if "font" in normalized:
            code = "pdf.fonte_ausente"
        elif "annot" in normalized:
            code = "pdf.anotacao_malformada"
        diagnostics.append(
            DiagnosticoPdf(
                codigo=code,
                mensagem=(
                    "O mecanismo PDF sinalizou um recurso localizado que pode estar incompleto."
                ),
                pagina_numero=page_number,
            )
        )
    return tuple(diagnostics)


def _raw_mupdf_warnings() -> str:
    return str(pymupdf.TOOLS.mupdf_warnings(reset=True) or "")  # type: ignore[no-untyped-call]


def _rect_tuple(rect: Any) -> PdfRectangle:
    if hasattr(rect, "x0"):
        return float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)
    values = tuple(float(value) for value in rect)
    return cast(PdfRectangle, values)


def _optional_string(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _validate_render_parameters(
    dpi: int,
    rotation: int,
    clip: PdfRectangle | None,
) -> None:
    if not 18 <= dpi <= 1200:
        raise PdfPaginaInvalidaError("DPI deve estar entre 18 e 1200")
    if rotation not in VALID_ROTATIONS:
        raise PdfPaginaInvalidaError("Rotação deve ser 0, 90, 180 ou 270 graus")
    if clip is not None:
        x0, y0, x1, y1 = clip
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise PdfPaginaInvalidaError("Recorte normalizado deve estar dentro da página")


def _normalized_clip(page: Any, clip: PdfRectangle | None) -> Any | None:
    if clip is None:
        return None
    x0, y0, x1, y1 = clip
    rect = page.rect
    return pymupdf.Rect(  # type: ignore[no-untyped-call]
        rect.x0 + x0 * rect.width,
        rect.y0 + y0 * rect.height,
        rect.x0 + x1 * rect.width,
        rect.y0 + y1 * rect.height,
    )
