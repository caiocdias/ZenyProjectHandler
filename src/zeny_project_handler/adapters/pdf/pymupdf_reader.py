"""Leitura somente leitura e tolerante a falhas usando PyMuPDF."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from types import TracebackType
from typing import Any, TypeVar, cast
from uuid import UUID, uuid4

import pymupdf

from zeny_project_handler.domain.documents import VALID_ROTATIONS, DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.values import CaixaPagina
from zeny_project_handler.ports.pdf import (
    RGB_BYTES_PER_PIXEL,
    VIEWER_BYTES_PER_PIXEL_ESTIMATE,
    AnotacaoPdf,
    DiagnosticoPdf,
    FormXObjectPdf,
    FragmentoTextoPdf,
    GraficoVetorialPdf,
    GrupoConteudoOpcionalPdf,
    ImagemIncorporadaPdf,
    InspecaoPdf,
    InventarioPaginaPdf,
    OrcamentoRenderizacaoPdf,
    PaginaPdfRenderizada,
    PdfRectangle,
    PlanoRenderizacaoPdf,
    SessaoLeituraPdfPort,
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
FileHasher = Callable[[Path], str]


@dataclass(frozen=True, slots=True)
class _SourceMetadata:
    size: int
    modified_ns: int
    changed_ns: int
    device: int
    inode: int


class PyMuPdfReader:
    """Inspeciona conteúdo nativo e renderiza sem chamar qualquer API de gravação."""

    adapter_name = f"PyMuPDF {pymupdf.__version__}"

    def __init__(self, *, file_hasher: FileHasher | None = None) -> None:
        self._file_hasher = file_hasher or _file_sha256

    def abrir_sessao(
        self,
        caminho: Path,
        *,
        senha: str | None = None,
        documento_id: UUID | None = None,
        sha256_esperado: str | None = None,
    ) -> SessaoLeituraPdfPort:
        source = _validated_path(caminho)
        inspection, metadata = self._inspect_verified_source(
            source,
            password=senha,
            document_id=documento_id,
        )
        if sha256_esperado is not None and inspection.documento.sha256 != sha256_esperado:
            raise PdfOrigemAlteradaError("O conteúdo do PDF não corresponde ao hash registrado")
        return PyMuPdfSession(
            source=source,
            inspection=inspection,
            metadata=metadata,
            password=senha,
        )

    def inspecionar(
        self,
        caminho: Path,
        *,
        senha: str | None = None,
        documento_id: UUID | None = None,
    ) -> InspecaoPdf:
        source = _validated_path(caminho)
        inspection, _metadata = self._inspect_verified_source(
            source,
            password=senha,
            document_id=documento_id,
        )
        return inspection

    def _inspect_verified_source(
        self,
        source: Path,
        *,
        password: str | None,
        document_id: UUID | None,
    ) -> tuple[InspecaoPdf, _SourceMetadata]:
        initial_metadata = _source_metadata(source)
        digest = self._file_hasher(source)
        _require_same_metadata(source, initial_metadata, "durante a leitura da identidade")
        document = _open_document(source, password)
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
                id=document_id or uuid4(),
                nome_arquivo=source.name,
                sha256=digest,
                paginas=tuple(item.pagina for item in pages),
                tamanho_bytes=initial_metadata.size,
                versao_pdf=_optional_string(metadata.get("format")),
                produtor=_optional_string(metadata.get("producer")),
            )
        finally:
            document.close()

        final_metadata = _require_same_metadata(source, initial_metadata, "durante a inspeção")
        return InspecaoPdf(
            documento=project_document,
            caminho_origem=source,
            tamanho_bytes=final_metadata.size,
            modificado_em_ns=final_metadata.modified_ns,
            adaptador=self.adapter_name,
            paginas=pages,
            grupos_conteudo_opcional=ocgs,
            diagnosticos=tuple(diagnostics),
        ), final_metadata

    def renderizar_pagina(
        self,
        caminho: Path,
        pagina_numero: int,
        *,
        dpi: int,
        orcamento: OrcamentoRenderizacaoPdf,
        rotacao_adicional_graus: int = 0,
        recorte_normalizado: PdfRectangle | None = None,
        senha: str | None = None,
        sha256_esperado: str | None = None,
    ) -> PaginaPdfRenderizada:
        source = _validated_path(caminho)
        _validate_render_parameters(dpi, rotacao_adicional_graus, recorte_normalizado)
        if sha256_esperado is not None and self._file_hasher(source) != sha256_esperado:
            raise PdfOrigemAlteradaError("O conteúdo do PDF não corresponde ao hash registrado")
        return _render_page(
            source,
            pagina_numero,
            dpi=dpi,
            rotation=rotacao_adicional_graus,
            normalized_clip=recorte_normalizado,
            budget=orcamento,
            password=senha,
        )

    def planejar_renderizacao(
        self,
        caminho: Path,
        pagina_numero: int,
        *,
        dpi: int,
        orcamento: OrcamentoRenderizacaoPdf,
        rotacao_adicional_graus: int = 0,
        recorte_normalizado: PdfRectangle | None = None,
        senha: str | None = None,
        sha256_esperado: str | None = None,
    ) -> PlanoRenderizacaoPdf:
        source = _validated_path(caminho)
        _validate_render_parameters(dpi, rotacao_adicional_graus, recorte_normalizado)
        if sha256_esperado is not None and self._file_hasher(source) != sha256_esperado:
            raise PdfOrigemAlteradaError("O conteúdo do PDF não corresponde ao hash registrado")
        return _plan_page(
            source,
            pagina_numero,
            dpi=dpi,
            rotation=rotacao_adicional_graus,
            normalized_clip=recorte_normalizado,
            budget=orcamento,
            password=senha,
        )

    def renderizar_miniatura(
        self,
        caminho: Path,
        pagina_numero: int,
        *,
        dpi: int = 36,
        orcamento: OrcamentoRenderizacaoPdf,
        senha: str | None = None,
        sha256_esperado: str | None = None,
    ) -> PaginaPdfRenderizada:
        return self.renderizar_pagina(
            caminho,
            pagina_numero,
            dpi=dpi,
            orcamento=orcamento,
            senha=senha,
            sha256_esperado=sha256_esperado,
        )

    def verificar_origem(self, inspecao: InspecaoPdf) -> None:
        source = _validated_path(inspecao.caminho_origem)
        current_stat = source.stat()
        if (
            current_stat.st_size != inspecao.tamanho_bytes
            or self._file_hasher(source) != inspecao.documento.sha256
        ):
            raise PdfOrigemAlteradaError("O PDF foi alterado depois da inspeção")


class PyMuPdfSession:
    """Sessão curta que guarda identidade, mas nenhum handle de arquivo ou documento."""

    def __init__(
        self,
        *,
        source: Path,
        inspection: InspecaoPdf,
        metadata: _SourceMetadata,
        password: str | None,
    ) -> None:
        self._source: Path | None = source
        self._inspection: InspecaoPdf | None = inspection
        self._metadata: _SourceMetadata | None = metadata
        self._password = password
        self._invalidated = False

    @property
    def inspecao(self) -> InspecaoPdf:
        if self._inspection is None:
            raise PdfOrigemAlteradaError(self._unavailable_message())
        return self._inspection

    def planejar_renderizacao(
        self,
        pagina_numero: int,
        *,
        dpi: int,
        orcamento: OrcamentoRenderizacaoPdf,
        rotacao_adicional_graus: int = 0,
        recorte_normalizado: PdfRectangle | None = None,
    ) -> PlanoRenderizacaoPdf:
        source, metadata = self._active_source()
        _validate_render_parameters(dpi, rotacao_adicional_graus, recorte_normalizado)
        self._verify_metadata(source, metadata)
        try:
            return _plan_page(
                source,
                pagina_numero,
                dpi=dpi,
                rotation=rotacao_adicional_graus,
                normalized_clip=recorte_normalizado,
                budget=orcamento,
                password=self._password,
            )
        finally:
            self._verify_metadata(source, metadata)

    def renderizar_pagina(
        self,
        pagina_numero: int,
        *,
        dpi: int,
        orcamento: OrcamentoRenderizacaoPdf,
        rotacao_adicional_graus: int = 0,
        recorte_normalizado: PdfRectangle | None = None,
    ) -> PaginaPdfRenderizada:
        source, metadata = self._active_source()
        _validate_render_parameters(dpi, rotacao_adicional_graus, recorte_normalizado)
        self._verify_metadata(source, metadata)
        try:
            return _render_page(
                source,
                pagina_numero,
                dpi=dpi,
                rotation=rotacao_adicional_graus,
                normalized_clip=recorte_normalizado,
                budget=orcamento,
                password=self._password,
            )
        finally:
            self._verify_metadata(source, metadata)

    def fechar(self) -> None:
        self._source = None
        self._inspection = None
        self._metadata = None
        self._password = None

    def __enter__(self) -> PyMuPdfSession:
        self._active_source()
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.fechar()

    def _active_source(self) -> tuple[Path, _SourceMetadata]:
        if self._source is None or self._metadata is None:
            raise PdfOrigemAlteradaError(self._unavailable_message())
        return self._source, self._metadata

    def _verify_metadata(self, source: Path, expected: _SourceMetadata) -> None:
        try:
            _require_same_metadata(source, expected, "depois da abertura da sessão")
        except (PdfArquivoInvalidoError, PdfOrigemAlteradaError):
            self._invalidated = True
            self.fechar()
            raise PdfOrigemAlteradaError(
                "O PDF foi alterado; abra e inspecione o documento novamente"
            ) from None

    def _unavailable_message(self) -> str:
        if self._invalidated:
            return "A sessão foi invalidada; inspecione o PDF novamente"
        return "A sessão de leitura do PDF já foi encerrada"


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


def _source_metadata(path: Path) -> _SourceMetadata:
    try:
        result = path.stat()
    except OSError as error:
        raise PdfArquivoInvalidoError("Não foi possível consultar o arquivo PDF") from error
    return _SourceMetadata(
        size=result.st_size,
        modified_ns=result.st_mtime_ns,
        changed_ns=result.st_ctime_ns,
        device=result.st_dev,
        inode=result.st_ino,
    )


def _require_same_metadata(
    path: Path,
    expected: _SourceMetadata,
    operation: str,
) -> _SourceMetadata:
    current = _source_metadata(path)
    if current != expected:
        raise PdfOrigemAlteradaError(f"O PDF foi alterado {operation}")
    return current


def _render_page(
    source: Path,
    page_number: int,
    *,
    dpi: int,
    rotation: int,
    normalized_clip: PdfRectangle | None,
    budget: OrcamentoRenderizacaoPdf,
    password: str | None,
) -> PaginaPdfRenderizada:
    document = _open_document(source, password)
    try:
        if not 1 <= page_number <= document.page_count:
            raise PdfPaginaInvalidaError("Número de página fora do documento")
        page = document.load_page(page_number - 1)
        plan = _plan_rendering(
            page,
            page_number=page_number,
            dpi=dpi,
            rotation=rotation,
            normalized_clip=normalized_clip,
            budget=budget,
        )
        matrix = _render_matrix(plan.dpi_efetivo, rotation)
        pixmap = page.get_pixmap(
            matrix=matrix,
            colorspace=pymupdf.csRGB,
            alpha=False,
            clip=_normalized_clip(page, plan.recorte_normalizado),
            annots=True,
        )
        if (pixmap.width, pixmap.height) != (plan.largura_pixels, plan.altura_pixels):
            raise PdfPaginaInvalidaError(
                "O raster produzido não corresponde ao planejamento de memória"
            )
        buffer = cast(memoryview, pixmap.samples_mv)
        if len(buffer) != pixmap.stride * pixmap.height:
            raise PdfPaginaInvalidaError("O buffer RGB produzido possui tamanho inesperado")
        return PaginaPdfRenderizada(
            pagina_numero=page_number,
            stride=pixmap.stride,
            dados_rgb=buffer,
            plano=plan,
            _dono_buffer=pixmap,
        )
    except PdfPaginaInvalidaError:
        raise
    except Exception as error:
        raise PdfPaginaInvalidaError("Não foi possível rasterizar a página solicitada") from error
    finally:
        document.close()


def _plan_page(
    source: Path,
    page_number: int,
    *,
    dpi: int,
    rotation: int,
    normalized_clip: PdfRectangle | None,
    budget: OrcamentoRenderizacaoPdf,
    password: str | None,
) -> PlanoRenderizacaoPdf:
    document = _open_document(source, password)
    try:
        if not 1 <= page_number <= document.page_count:
            raise PdfPaginaInvalidaError("Número de página fora do documento")
        return _plan_rendering(
            document.load_page(page_number - 1),
            page_number=page_number,
            dpi=dpi,
            rotation=rotation,
            normalized_clip=normalized_clip,
            budget=budget,
        )
    except PdfPaginaInvalidaError:
        raise
    except Exception as error:
        raise PdfPaginaInvalidaError(
            "Não foi possível planejar a rasterização solicitada"
        ) from error
    finally:
        document.close()


def _plan_rendering(
    page: Any,
    *,
    page_number: int,
    dpi: int,
    rotation: int,
    normalized_clip: PdfRectangle | None,
    budget: OrcamentoRenderizacaoPdf,
) -> PlanoRenderizacaoPdf:
    canonical_clip = normalized_clip or (0.0, 0.0, 1.0, 1.0)
    requested = _raster_dimensions(page, dpi, rotation, canonical_clip)
    if _dimensions_fit_budget(requested[0], requested[1], budget):
        effective_dpi = dpi
        effective = requested
    else:
        effective_dpi = _largest_dpi_within_budget(
            page,
            requested_dpi=dpi,
            rotation=rotation,
            normalized_clip=canonical_clip,
            budget=budget,
        )
        effective = _raster_dimensions(page, effective_dpi, rotation, canonical_clip)
    width, height, page_width, page_height, origin_x, origin_y = effective
    pixels = width * height
    return PlanoRenderizacaoPdf(
        pagina_numero=page_number,
        dpi_solicitado=dpi,
        dpi_efetivo=effective_dpi,
        rotacao_adicional_graus=rotation,
        recorte_normalizado=canonical_clip,
        largura_pixels=width,
        altura_pixels=height,
        largura_pagina_pixels=page_width,
        altura_pagina_pixels=page_height,
        origem_x_pixels=origin_x,
        origem_y_pixels=origin_y,
        largura_solicitada_pixels=requested[0],
        altura_solicitada_pixels=requested[1],
        bytes_rgb_estimados=pixels * RGB_BYTES_PER_PIXEL,
        bytes_pico_estimados=pixels * VIEWER_BYTES_PER_PIXEL_ESTIMATE,
    )


def _largest_dpi_within_budget(
    page: Any,
    *,
    requested_dpi: int,
    rotation: int,
    normalized_clip: PdfRectangle,
    budget: OrcamentoRenderizacaoPdf,
) -> int:
    minimum_dpi = 1
    minimum = _raster_dimensions(page, minimum_dpi, rotation, normalized_clip)
    if not _dimensions_fit_budget(minimum[0], minimum[1], budget):
        raise PdfPaginaInvalidaError(
            "O orçamento é insuficiente até para a menor prévia da região solicitada"
        )
    lower, upper = minimum_dpi, requested_dpi - 1
    while lower < upper:
        candidate = (lower + upper + 1) // 2
        dimensions = _raster_dimensions(page, candidate, rotation, normalized_clip)
        if _dimensions_fit_budget(dimensions[0], dimensions[1], budget):
            lower = candidate
        else:
            upper = candidate - 1
    return lower


def _dimensions_fit_budget(
    width: int,
    height: int,
    budget: OrcamentoRenderizacaoPdf,
) -> bool:
    pixels = width * height
    return budget.comporta(
        pixels=pixels,
        bytes_estimados=pixels * VIEWER_BYTES_PER_PIXEL_ESTIMATE,
    )


def _raster_dimensions(
    page: Any,
    dpi: int,
    rotation: int,
    normalized_clip: PdfRectangle,
) -> tuple[int, int, int, int, int, int]:
    matrix = _render_matrix(dpi, rotation)
    page_bounds = (page.rect * matrix).irect
    clip = _normalized_clip(page, normalized_clip)
    clip_bounds = (clip * matrix).irect
    return (
        int(clip_bounds.width),
        int(clip_bounds.height),
        int(page_bounds.width),
        int(page_bounds.height),
        int(clip_bounds.x0 - page_bounds.x0),
        int(clip_bounds.y0 - page_bounds.y0),
    )


def _render_matrix(dpi: int, rotation: int) -> Any:
    return pymupdf.Matrix(dpi / 72, dpi / 72).prerotate(  # type: ignore[no-untyped-call]
        rotation
    )


def _open_document(path: Path, password: str | None) -> Any:
    try:
        document = pymupdf.open(filename=str(path))  # type: ignore[no-untyped-call]
    except Exception as error:
        raise PdfArquivoInvalidoError("O arquivo não é um PDF válido ou está corrompido") from error
    if not document.is_pdf or document.page_count < 1:
        document.close()  # type: ignore[no-untyped-call]
        raise PdfArquivoInvalidoError("O arquivo não contém um documento PDF paginado")
    if document.needs_pass:
        authenticated = bool(
            password and document.authenticate(password) > 0  # type: ignore[no-untyped-call]
        )
        if not authenticated:
            document.close()  # type: ignore[no-untyped-call]
            raise PdfProtegidoError(senha_fornecida=bool(password))
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
    if not 18 <= dpi <= 600:
        raise PdfPaginaInvalidaError("DPI visual deve estar entre 18 e 600")
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
