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
from typing import Any, TypeVar
from uuid import uuid5

import pymupdf

from zeny_project_handler.adapters.pdf.errors import PdfProtegidoError
from zeny_project_handler.domain.analysis import DiagnosticoAnalise, EvidenciaDocumento
from zeny_project_handler.domain.enums import TipoEvidencia
from zeny_project_handler.domain.values import GeometriaDocumento
from zeny_project_handler.ports.analysis import (
    CacheAnaliseDocumentoPort,
    CandidatoEvidenciaDocumento,
    ExtracaoDocumentoNormalizada,
    MotorOcrPort,
    ResultadoAnaliseDocumento,
    SolicitacaoAnaliseDocumento,
    chave_cache_analise,
    validar_fonte_solicitacao,
)

from .pymupdf_annotations import _extract_annotations
from .pymupdf_ocr import _conditional_ocr
from .pymupdf_page_extractors import (
    _extract_forms,
    _extract_images,
    _extract_text,
    _extract_vectors,
)
from .pymupdf_symbols import _extract_symbolic_equipment

_READ_CHUNK_SIZE = 1024 * 1024
T = TypeVar("T")


class PyMuPdfDocumentAnalyzer:
    """Converte recursos PDF nativos em evidências independentes da biblioteca."""

    nome = "pymupdf-nativo"
    versao = "1.9.0"

    def __init__(
        self,
        *,
        cache: CacheAnaliseDocumentoPort | None = None,
        motor_ocr: MotorOcrPort | None = None,
    ) -> None:
        self._cache = cache
        self._motor_ocr = motor_ocr

    @property
    def assinatura_capacidade(self) -> str:
        payload = json.dumps(
            {
                "analisador": self.nome,
                "versao": self.versao,
                "ocr": self._ocr_runtime.assinatura,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(payload.encode("utf-8")).hexdigest()

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

    def _load_or_extract(
        self,
        source: Path,
        cache_key: str,
        request: SolicitacaoAnaliseDocumento,
    ) -> tuple[ExtracaoDocumentoNormalizada, bool, tuple[DiagnosticoAnalise, ...]]:
        cached, cache_diagnostics = self._read_cache(cache_key)
        if cached is not None:
            return cached, True, cache_diagnostics
        extraction = _extract_document(source, request, self._ocr_runtime.motor)
        _verify_source(source, request.fonte.sha256, request.fonte.tamanho_bytes)
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
) -> ExtracaoDocumentoNormalizada:
    document = _open_document(source, request.senha)
    candidates: list[CandidatoEvidenciaDocumento] = []
    diagnostics: list[DiagnosticoAnalise] = []
    try:
        if document.page_count != len(request.documento.paginas):
            raise ValueError("Quantidade de páginas diverge do documento importado")
        for page_index in range(document.page_count):
            page_candidates, page_diagnostics = _extract_page(
                document,
                document.load_page(page_index),
                page_index + 1,
                request,
                ocr_engine,
            )
            candidates.extend(page_candidates)
            diagnostics.extend(page_diagnostics)
    finally:
        document.close()
    _ensure_unique_candidate_keys(candidates)
    return ExtracaoDocumentoNormalizada(
        candidatos=tuple(candidates), diagnosticos=tuple(diagnostics)
    )


def _extract_page(
    document: Any,
    page: Any,
    page_number: int,
    request: SolicitacaoAnaliseDocumento,
    ocr_engine: MotorOcrPort | None,
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
    candidates.extend(ocr_candidates)
    diagnostics.extend(ocr_diagnostics)
    return tuple(candidates), tuple(diagnostics)


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
                atributos_extraidos=candidate.atributos_extraidos,
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
class _OcrRuntime:
    motor: MotorOcrPort | None
    assinatura: str
    diagnosticos: tuple[DiagnosticoAnalise, ...] = ()
