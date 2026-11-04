# mypy: disable-error-code="no-untyped-call"
"""Orquestração da extração nativa PyMuPDF e materialização das evidências."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, TypeVar
from uuid import uuid5

import pymupdf

from zeny_project_handler.adapters.pdf.errors import PdfProtegidoError
from zeny_project_handler.application.errors import FluxoMvpCanceladoError
from zeny_project_handler.application.method_reconciliation import (
    READING_KEY,
    reading_data,
    reconcile_readings,
)
from zeny_project_handler.domain.analysis import DiagnosticoAnalise, EvidenciaDocumento
from zeny_project_handler.domain.enums import TipoEvidencia
from zeny_project_handler.domain.values import GeometriaDocumento
from zeny_project_handler.ports.analysis import (
    CacheAnaliseDocumentoPort,
    CandidatoEvidenciaDocumento,
    ExtracaoDocumentoNormalizada,
    ExtratorComplementarPort,
    MotorOcrPort,
    ResultadoAnaliseDocumento,
    SolicitacaoAnaliseDocumento,
    chave_cache_analise,
    validar_fonte_solicitacao,
)

from .drawing_model.glyph_table import TabelaGlifos, carregar_tabela_glifos
from .drawing_model.model import VERSAO_MODELO_DESENHO
from .pymupdf_annotations import _extract_annotations
from .pymupdf_glyph_text import (
    GlifosDaPagina,
    _resolver_cobertura,
    diagnostico_divergencia,
    eh_texto_de_glifo,
    ler_glifos_da_pagina,
)
from .pymupdf_ocr import _conditional_ocr
from .pymupdf_page_extractors import (
    _extract_forms,
    _extract_images,
    _extract_text,
    _extract_vectors,
)
from .pymupdf_revisions import extract_revision_appearances
from .pymupdf_symbols import _extract_symbolic_equipment

_READ_CHUNK_SIZE = 1024 * 1024
T = TypeVar("T")
_NO_GLYPHS = GlifosDaPagina((), (), ())


class PyMuPdfDocumentAnalyzer:
    """Converte recursos PDF nativos em evidências independentes da biblioteca."""

    nome = "pymupdf-nativo"
    versao = "1.21.0"

    def __init__(
        self,
        *,
        cache: CacheAnaliseDocumentoPort | None = None,
        motor_ocr: MotorOcrPort | None = None,
        complementar: ExtratorComplementarPort | None = None,
        tabela_glifos: TabelaGlifos | Literal["pacote"] | None = None,
    ) -> None:
        """`tabela_glifos`: None desativa a leitura de texto por contorno de glifo; "pacote"
        carrega a tabela empacotada na primeira análise (ausente ou inválida, a leitura fica
        desativada com diagnóstico, como o OCR indisponível)."""
        self._cache = cache
        self._motor_ocr = motor_ocr
        self._complementar = complementar
        self._tabela_glifos = tabela_glifos

    @property
    def assinatura_capacidade(self) -> str:
        payload = json.dumps(self._capacidade(), sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode("utf-8")).hexdigest()

    def _capacidade(self) -> dict[str, str | None]:
        return {
            "analisador": self.nome,
            "versao": self.versao,
            "ocr": self._ocr_runtime.assinatura,
            "complementar": self._complementar.assinatura_capacidade
            if self._complementar
            else None,
            "tabela_glifos": self._glyph_runtime.assinatura,
            "modelo_desenho": VERSAO_MODELO_DESENHO,
        }

    def analisar(self, solicitacao: SolicitacaoAnaliseDocumento) -> ResultadoAnaliseDocumento:
        source = validar_fonte_solicitacao(solicitacao).expanduser().resolve(strict=True)
        _verify_source(source, solicitacao.fonte.sha256, solicitacao.fonte.tamanho_bytes)
        cache_key = chave_cache_analise(
            documento_sha256=solicitacao.documento.sha256,
            configuracao=solicitacao.configuracao,
            analisador=self.assinatura_capacidade,
        )
        extraction, cache_used, runtime_diagnostics = self._load_or_extract(
            source, cache_key, solicitacao
        )
        evidence = _materialize_evidence(
            extraction.candidatos,
            solicitacao,
            method=self.nome,
            version=self.versao,
            capability_signature=self.assinatura_capacidade,
        )
        return ResultadoAnaliseDocumento(
            evidencias=evidence,
            diagnosticos=(
                *self._ocr_runtime.diagnosticos,
                *self._glyph_runtime.diagnosticos,
                *extraction.diagnosticos,
                *runtime_diagnostics,
            ),
            cache_utilizado=cache_used,
        )

    @cached_property
    def _ocr_runtime(self) -> _OcrRuntime:
        if self._motor_ocr is None:
            return _OcrRuntime(motor=None, assinatura="ausente")
        try:
            result = self._motor_ocr.consultar_capacidade()
        except Exception:
            diagnostic = _ocr_capability_diagnostic()
            return _OcrRuntime(
                motor=None,
                assinatura=f"indisponivel:{diagnostic.codigo}",
                diagnosticos=(diagnostic,),
            )
        if result.capacidade is None:
            codes = ",".join(item.codigo for item in result.diagnosticos)
            return _OcrRuntime(
                motor=None,
                assinatura=f"indisponivel:{codes}",
                diagnosticos=result.diagnosticos,
            )
        return _OcrRuntime(
            motor=self._motor_ocr,
            assinatura=result.capacidade.assinatura(),
            diagnosticos=result.diagnosticos,
        )

    @cached_property
    def _glyph_runtime(self) -> _GlyphRuntime:
        if isinstance(self._tabela_glifos, TabelaGlifos):
            return _GlyphRuntime(self._tabela_glifos, self._tabela_glifos.sha256)
        if self._tabela_glifos is None:
            return _GlyphRuntime(None, "desativada")
        try:
            table = carregar_tabela_glifos()
        except Exception:
            diagnostic = _glyph_table_diagnostic()
            return _GlyphRuntime(None, f"indisponivel:{diagnostic.codigo}", (diagnostic,))
        return _GlyphRuntime(table, table.sha256)

    def _load_or_extract(
        self,
        source: Path,
        cache_key: str,
        request: SolicitacaoAnaliseDocumento,
    ) -> tuple[ExtracaoDocumentoNormalizada, bool, tuple[DiagnosticoAnalise, ...]]:
        _check_cancelled(request)
        cached, cache_diagnostics = self._read_cache(cache_key)
        if cached is not None:
            return cached, True, cache_diagnostics
        extraction = _extract_document(
            source, request, self._ocr_runtime.motor, self._glyph_runtime.tabela
        )
        if self._complementar is not None:
            try:
                auxiliary = self._complementar.extrair(request)
                extraction = ExtracaoDocumentoNormalizada(
                    candidatos=(
                        *extraction.candidatos,
                        *reconcile_readings(
                            _without_glyph_text(extraction.candidatos), auxiliary.candidatos
                        ),
                    ),
                    diagnosticos=(*extraction.diagnosticos, *auxiliary.diagnosticos),
                )
            except Exception as error:
                extraction = ExtracaoDocumentoNormalizada(
                    candidatos=extraction.candidatos,
                    diagnosticos=(
                        *extraction.diagnosticos,
                        DiagnosticoAnalise(
                            codigo="analysis.complementary.failed",
                            extrator="complementar",
                            mensagem=(
                                f"Verificação incompleta; base preservada: {type(error).__name__}"
                            ),
                        ),
                    ),
                )
        _verify_source(source, request.fonte.sha256, request.fonte.tamanho_bytes)
        _check_cancelled(request)
        write_diagnostics = self._write_cache(cache_key, extraction)
        return extraction, False, (*cache_diagnostics, *write_diagnostics)

    def _read_cache(
        self, cache_key: str
    ) -> tuple[ExtracaoDocumentoNormalizada | None, tuple[DiagnosticoAnalise, ...]]:
        if self._cache is None:
            return None, ()
        try:
            return self._cache.obter(cache_key), ()
        except Exception:
            return None, (_cache_diagnostic("analise.cache_leitura_falhou"),)

    def _write_cache(
        self, cache_key: str, extraction: ExtracaoDocumentoNormalizada
    ) -> tuple[DiagnosticoAnalise, ...]:
        if self._cache is None:
            return ()
        if any(
            (item.codigo.startswith("analise.") and item.codigo.endswith("falhou"))
            or item.codigo.startswith("analysis.complementary.")
            for item in extraction.diagnosticos
        ):
            # A transient runtime failure must be retried on the next analysis.
            return ()
        try:
            self._cache.salvar(cache_key, extraction)
            return ()
        except Exception:
            return (_cache_diagnostic("analise.cache_gravacao_falhou"),)


def _cache_diagnostic(code: str) -> DiagnosticoAnalise:
    return DiagnosticoAnalise(
        codigo=code,
        mensagem="O cache derivado não pôde ser usado; a análise nativa permanece válida.",
        extrator="cache",
    )


def _glyph_table_diagnostic() -> DiagnosticoAnalise:
    return DiagnosticoAnalise(
        codigo="analise.tabela_glifos_indisponivel",
        mensagem=(
            "A tabela de glifos empacotada está ausente ou inválida; "
            "a leitura de texto por contorno de glifo foi desativada."
        ),
        extrator="texto_glifos",
    )


def _without_glyph_text(
    candidates: tuple[CandidatoEvidenciaDocumento, ...],
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    return tuple(item for item in candidates if not eh_texto_de_glifo(item))


def _ocr_capability_diagnostic() -> DiagnosticoAnalise:
    return DiagnosticoAnalise(
        codigo="analise.ocr_capacidade_falhou",
        mensagem="A capacidade do motor OCR não pôde ser consultada; o OCR foi desativado.",
        extrator="ocr-capacidade",
    )


def _extract_document(
    source: Path,
    request: SolicitacaoAnaliseDocumento,
    ocr_engine: MotorOcrPort | None,
    glyph_table: TabelaGlifos | None = None,
) -> ExtracaoDocumentoNormalizada:
    document = _open_document(source, request.senha)
    candidates: list[CandidatoEvidenciaDocumento] = []
    diagnostics: list[DiagnosticoAnalise] = []
    try:
        if document.page_count != len(request.documento.paginas):
            raise ValueError("Quantidade de páginas diverge do documento importado")
        for page_index in range(document.page_count):
            _check_cancelled(request)
            page_candidates, page_diagnostics = _extract_page(
                document,
                document.load_page(page_index),
                page_index + 1,
                request,
                ocr_engine,
                glyph_table,
            )
            candidates.extend(page_candidates)
            diagnostics.extend(page_diagnostics)
            if request.progresso is not None:
                request.progresso(
                    page_index + 1,
                    document.page_count,
                    f"Extração nativa: página {page_index + 1}/{document.page_count}",
                )
        _check_cancelled(request)
    finally:
        document.close()
    _ensure_unique_candidate_keys(candidates)
    return ExtracaoDocumentoNormalizada(
        candidatos=tuple(candidates), diagnosticos=tuple(diagnostics)
    )


def _check_cancelled(request: SolicitacaoAnaliseDocumento) -> None:
    if request.cancelado is not None and request.cancelado():
        raise FluxoMvpCanceladoError(
            "Extração documental cancelada entre páginas; use Retomar análise para continuar"
        )


def _extract_page(
    document: Any,
    page: Any,
    page_number: int,
    request: SolicitacaoAnaliseDocumento,
    ocr_engine: MotorOcrPort | None,
    glyph_table: TabelaGlifos | None = None,
) -> tuple[tuple[CandidatoEvidenciaDocumento, ...], tuple[DiagnosticoAnalise, ...]]:
    config = request.configuracao
    candidates: list[CandidatoEvidenciaDocumento] = []
    diagnostics: list[DiagnosticoAnalise] = []
    text_candidates: tuple[CandidatoEvidenciaDocumento, ...] = ()
    image_candidates: tuple[CandidatoEvidenciaDocumento, ...] = ()
    vector_candidates: tuple[CandidatoEvidenciaDocumento, ...] = ()
    extractors: tuple[
        tuple[bool, str, Callable[[], tuple[CandidatoEvidenciaDocumento, ...]]], ...
    ] = (
        (config.extrair_texto, "texto", lambda: _extract_text(page, page_number)),
        (config.extrair_vetores, "vetores", lambda: _extract_vectors(page, page_number)),
        (config.extrair_imagens, "imagens", lambda: _extract_images(page, page_number)),
        (
            config.extrair_forms_xobjects,
            "forms_xobjects",
            lambda: _extract_forms(document, page, page_number),
        ),
        (
            config.extrair_anotacoes,
            "anotacoes",
            lambda: _extract_annotations(
                document,
                page,
                page_number,
                config.profundidade_maxima_xobject,
            ),
        ),
    )
    for enabled, name, extractor in extractors:
        if not enabled:
            continue
        extracted, found = _safe_extract(name, page_number, extractor)
        if name == "texto":
            text_candidates = extracted
        elif name == "vetores":
            vector_candidates = extracted
        elif name == "imagens":
            image_candidates = extracted
        candidates.extend(extracted)
        diagnostics.extend(found)
    if config.extrair_vetores:
        symbolic_candidates, symbolic_diagnostics = _safe_extract(
            "simbolos_vetoriais",
            page_number,
            lambda: _extract_symbolic_equipment(page, page_number),
        )
        candidates.extend(symbolic_candidates)
        diagnostics.extend(symbolic_diagnostics)
    glyphs = _NO_GLYPHS
    if glyph_table is not None and config.extrair_texto:
        glyphs, glyph_diagnostics = _page_glyphs(page, page_number, glyph_table, text_candidates)
        diagnostics.extend(glyph_diagnostics)
    # Glyph text is a reading of vectors, not native text: it never suppresses the OCR.
    native_characters = sum(
        len(item.conteudo_bruto or "")
        for item in text_candidates
        if item.tipo is TipoEvidencia.TEXTO
    )
    image_coverage = max((_geometry_area(item) for item in image_candidates), default=Decimal(0))
    ocr_candidates, ocr_diagnostics = _conditional_ocr(
        page,
        page_number,
        request,
        ocr_engine,
        native_characters,
        image_coverage,
        len(vector_candidates),
        image_candidates,
    )
    ocr_candidates, glyphs, coverage_diagnostics = _cover_glyphs_by_ocr(
        ocr_candidates, glyphs, page_number
    )
    candidates.extend(ocr_candidates)
    diagnostics.extend(ocr_diagnostics)
    diagnostics.extend(coverage_diagnostics)
    if config.extrair_anotacoes:
        # Failure to compare the source must fail the analysis, not approve hidden values.
        revisions = extract_revision_appearances(
            page, page_number, request.fonte.sha256, tuple(candidates), ocr_engine
        )
        candidates.extend(revisions)
        if any(
            json.loads(str(dict(item.atributos_extraidos)["revisao_tecnica"])).get("ocr_failed")
            for item in revisions
        ):
            diagnostics.append(
                DiagnosticoAnalise(
                    codigo="analise.ocr_revisoes_falhou",
                    extrator="ocr_revisoes",
                    pagina_numero=page_number,
                    mensagem="OCR da revisão falhou; comparação preservada e decisão pendente.",
                )
            )
    # Revisions and the complementary reconciliation never see glyph text.
    candidates.extend(glyphs.candidatos)
    return tuple(candidates), tuple(diagnostics)


def _page_glyphs(
    page: Any,
    page_number: int,
    table: TabelaGlifos,
    text_candidates: tuple[CandidatoEvidenciaDocumento, ...],
) -> tuple[GlifosDaPagina, tuple[DiagnosticoAnalise, ...]]:
    """Glyph text of the page minus the texts fully covered by agreeing native text."""

    def read() -> tuple[GlifosDaPagina]:
        glyphs = ler_glifos_da_pagina(page, page_number, table)
        native = tuple(item for item in text_candidates if item.tipo is TipoEvidencia.TEXTO)
        coverage = _resolver_cobertura(native, glyphs.textos, nativo=True)
        return (glyphs.apenas(coverage.glifos),)

    found, failures = _safe_extract("texto_glifos", page_number, read)
    if not found:
        return _NO_GLYPHS, failures
    return found[0], found[0].diagnosticos


def _cover_glyphs_by_ocr(
    ocr_candidates: tuple[CandidatoEvidenciaDocumento, ...],
    glyphs: GlifosDaPagina,
    page_number: int,
) -> tuple[tuple[CandidatoEvidenciaDocumento, ...], GlifosDaPagina, tuple[DiagnosticoAnalise, ...]]:
    """OCR stays the reserve: compare it with the glyph text glyph by glyph."""
    if not glyphs.candidatos or not ocr_candidates:
        return ocr_candidates, glyphs, ()
    readings = tuple(item for item in ocr_candidates if item.tipo is TipoEvidencia.OCR)
    coverage = _resolver_cobertura(readings, glyphs.textos)
    kept = {item.chave_estavel for item in coverage.mantidos}
    remaining = tuple(
        item
        for item in ocr_candidates
        if item.tipo is not TipoEvidencia.OCR or item.chave_estavel in kept
    )
    diagnostics = (
        (diagnostico_divergencia(page_number, coverage.divergentes),)
        if coverage.divergentes
        else ()
    )
    return remaining, glyphs.apenas(coverage.glifos), diagnostics


def _geometry_area(candidate: CandidatoEvidenciaDocumento) -> Decimal:
    x_values = [point.x for point in candidate.geometria.pontos]
    y_values = [point.y for point in candidate.geometria.pontos]
    return (max(x_values) - min(x_values)) * (max(y_values) - min(y_values))


def _safe_extract(
    name: str,
    page_number: int,
    extractor: Callable[[], tuple[T, ...]],
) -> tuple[tuple[T, ...], tuple[DiagnosticoAnalise, ...]]:
    try:
        return extractor(), ()
    except Exception:
        return (), (
            DiagnosticoAnalise(
                codigo=f"analise.{name}_falhou",
                mensagem=(
                    f"O extrator de {name} falhou nesta página; "
                    "os demais resultados foram mantidos."
                ),
                extrator=name,
                pagina_numero=page_number,
            ),
        )


def _materialize_evidence(
    candidates: tuple[CandidatoEvidenciaDocumento, ...],
    request: SolicitacaoAnaliseDocumento,
    *,
    method: str,
    version: str,
    capability_signature: str,
) -> tuple[EvidenciaDocumento, ...]:
    page_ids = {page.numero: page.id for page in request.documento.paginas}
    evidence = []
    for candidate in candidates:
        page_id = page_ids.get(candidate.pagina_numero)
        if page_id is None:
            raise ValueError("Candidato referencia página inexistente")
        geometry = GeometriaDocumento(
            pagina_id=page_id,
            tipo=candidate.geometria.tipo,
            pontos=candidate.geometria.pontos,
        )
        attributes = candidate.atributos_extraidos
        data = reading_data(attributes)
        if data is not None:
            data["alternatives"] = [
                {
                    **alternative,
                    "evidence_id": str(uuid5(request.execucao_id, alternative["evidence_key"])),
                    "extraction_version": version,
                    "extraction_capability": capability_signature,
                }
                for alternative in data.get("alternatives", [])
            ]
            attributes = (
                *((key, value) for key, value in attributes if key != READING_KEY),
                (READING_KEY, json.dumps(data, ensure_ascii=False, sort_keys=True)),
            )
        evidence.append(
            EvidenciaDocumento(
                id=uuid5(request.execucao_id, candidate.chave_estavel),
                execucao_id=request.execucao_id,
                pagina_id=page_id,
                tipo=candidate.tipo,
                geometria=geometry,
                metodo=method,
                versao_metodo=version,
                parametros=(
                    *request.configuracao.parametros(),
                    ("assinatura_capacidade_analisador", capability_signature),
                ),
                conteudo_bruto=candidate.conteudo_bruto,
                criada_em=request.criada_em,
                origem_pdf=candidate.origem_pdf,
                atributos_extraidos=attributes,
            )
        )
    return tuple(evidence)


def _open_document(source: Path, password: str | None) -> Any:
    document = pymupdf.open(filename=str(source))
    if not document.is_pdf or document.page_count < 1:
        document.close()
        raise ValueError("A origem não é um PDF paginado válido")
    if document.needs_pass:
        authenticated = bool(password and document.authenticate(password) > 0)
        if not authenticated:
            document.close()
            raise PdfProtegidoError(senha_fornecida=bool(password))
    return document


def _verify_source(source: Path, expected_hash: str, expected_size: int) -> None:
    if not source.is_file() or source.stat().st_size != expected_size:
        raise ValueError("A origem PDF foi removida ou alterada")
    if _file_sha256(source) != expected_hash:
        raise ValueError("O conteúdo da origem PDF foi alterado")


def _file_sha256(source: Path) -> str:
    digest = sha256()
    with source.open("rb") as stream:
        while chunk := stream.read(_READ_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_unique_candidate_keys(candidates: list[CandidatoEvidenciaDocumento]) -> None:
    keys = [candidate.chave_estavel for candidate in candidates]
    if len(keys) != len(set(keys)):
        raise ValueError("Extração gerou chaves de evidência duplicadas")


@dataclass(frozen=True, slots=True)
class _GlyphRuntime:
    tabela: TabelaGlifos | None
    assinatura: str
    diagnosticos: tuple[DiagnosticoAnalise, ...] = ()


@dataclass(frozen=True, slots=True)
class _OcrRuntime:
    motor: MotorOcrPort | None
    assinatura: str
    diagnosticos: tuple[DiagnosticoAnalise, ...] = ()
