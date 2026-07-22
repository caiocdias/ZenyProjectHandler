from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from tests.pdf_fixtures import (
    create_analysis_pdf,
    create_dense_vector_text_pdf,
    create_mixed_raster_text_pdf,
)

from zeny_project_handler.adapters.analysis import JsonAnalysisCache, PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.analysis import pymupdf_analyzer as analyzer_module
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.domain.enums import TipoEvidencia, TipoOrigemPdf
from zeny_project_handler.ports.analysis import (
    AnalisadorDocumentoPort,
    ConfiguracaoAnaliseDocumento,
    PaginaRasterOcr,
    ResultadoAnaliseDocumento,
    SolicitacaoAnaliseDocumento,
    TrechoTextoOcr,
)
from zeny_project_handler.ports.pdf import ReferenciaFontePdf


class FakeOcr:
    nome = "ocr-falso"
    versao = "1.0"

    def __init__(self) -> None:
        self.pages: list[PaginaRasterOcr] = []

    def reconhecer(self, pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]:
        self.pages.append(pagina)
        return (
            TrechoTextoOcr(
                texto="POSTE DIGITALIZADO",
                caixa_normalizada=(0.1, 0.2, 0.8, 0.35),
                confianca=0.91,
            ),
        )


class FakeAnalyzer:
    nome = "fake"
    versao = "1"

    def analisar(self, _request: SolicitacaoAnaliseDocumento) -> ResultadoAnaliseDocumento:
        return ResultadoAnaliseDocumento(evidencias=(), diagnosticos=(), cache_utilizado=False)


class OtherFakeOcr(FakeOcr):
    nome = "outro-ocr"


def _request(path: Path) -> SolicitacaoAnaliseDocumento:
    inspection = PyMuPdfReader().inspecionar(path)
    project_id = uuid4()
    return SolicitacaoAnaliseDocumento(
        projeto_id=project_id,
        documento=inspection.documento,
        fonte=ReferenciaFontePdf(
            documento_id=inspection.documento.id,
            projeto_id=project_id,
            caminho_canonico=path,
            sha256=inspection.documento.sha256,
            tamanho_bytes=inspection.tamanho_bytes,
            modificado_em_ns=inspection.modificado_em_ns,
        ),
        execucao_id=uuid4(),
        criada_em=datetime(2026, 7, 21, 14, tzinfo=UTC),
    )


def _assert_contract(
    analyzer: AnalisadorDocumentoPort, request: SolicitacaoAnaliseDocumento
) -> None:
    assert isinstance(analyzer.nome, str)
    assert isinstance(analyzer.versao, str)
    result = analyzer.analisar(request)
    assert isinstance(result, ResultadoAnaliseDocumento)


def test_real_and_fake_analyzers_follow_the_same_contract(tmp_path: Path) -> None:
    request = _request(create_analysis_pdf(tmp_path / "contract.pdf"))

    _assert_contract(FakeAnalyzer(), request)
    _assert_contract(
        PyMuPdfDocumentAnalyzer(motor_ocr=FakeOcr(), cache=JsonAnalysisCache(tmp_path / "cache")),
        request,
    )


def test_native_extraction_preserves_geometry_provenance_and_properties(tmp_path: Path) -> None:
    request = _request(create_analysis_pdf(tmp_path / "features.pdf"))
    ocr = FakeOcr()

    result = PyMuPdfDocumentAnalyzer(motor_ocr=ocr).analisar(request)

    assert {item.tipo for item in result.evidencias} == set(TipoEvidencia)
    assert [page.pagina_numero for page in ocr.pages] == [2]
    assert not result.diagnosticos
    assert all(
        0 <= point.x <= 1 and 0 <= point.y <= 1
        for evidence in result.evidencias
        for point in evidence.geometria.pontos
    )

    text = next(item for item in result.evidencias if item.conteudo_bruto == "POSTE P1")
    assert dict(text.atributos_extraidos)["tamanho"] == 10
    rotated = next(item for item in result.evidencias if item.conteudo_bruto == "MT")
    rotation = dict(rotated.atributos_extraidos)["rotacao_graus"]
    assert isinstance(rotation, Decimal)
    assert abs(rotation) == 90

    vectors = [item for item in result.evidencias if item.tipo is TipoEvidencia.VETOR]
    assert any(dict(item.atributos_extraidos).get("cor_contorno") == "#00FF00" for item in vectors)
    assert any("c" in str(dict(item.atributos_extraidos).get("operacoes")) for item in vectors)
    assert any(dict(item.atributos_extraidos).get("fechado") is True for item in vectors)

    annotation_subtypes = {
        item.origem_pdf.subtipo_anotacao
        for item in result.evidencias
        if item.origem_pdf.tipo is TipoOrigemPdf.ANOTACAO
    }
    assert {"Stamp", "FreeText", "Square", "Text", "Popup"} <= annotation_subtypes
    assert any(
        item.tipo is TipoEvidencia.IMAGEM
        and item.origem_pdf.tipo is TipoOrigemPdf.APARENCIA_ANOTACAO
        and item.origem_pdf.nome_recurso == "ImAppearance"
        for item in result.evidencias
    )
    assert any(item.origem_pdf.tipo is TipoOrigemPdf.FORM_XOBJECT for item in result.evidencias)
    ocr_evidence = next(item for item in result.evidencias if item.tipo is TipoEvidencia.OCR)
    assert ocr_evidence.pagina_id == request.documento.paginas[1].id
    assert dict(ocr_evidence.atributos_extraidos)["confianca"] == Decimal("0.91")


def test_same_input_and_configuration_are_reproducible_from_cache(tmp_path: Path) -> None:
    request = _request(create_analysis_pdf(tmp_path / "reproducible.pdf"))
    analyzer = PyMuPdfDocumentAnalyzer(
        motor_ocr=FakeOcr(), cache=JsonAnalysisCache(tmp_path / "cache")
    )

    first = analyzer.analisar(request)
    second = analyzer.analisar(request)

    assert not first.cache_utilizado
    assert second.cache_utilizado
    assert second.evidencias == first.evidencias
    assert second.diagnosticos == first.diagnosticos

    different_engine = OtherFakeOcr()
    third = PyMuPdfDocumentAnalyzer(
        motor_ocr=different_engine, cache=JsonAnalysisCache(tmp_path / "cache")
    ).analisar(request)
    assert not third.cache_utilizado


def test_relevant_raster_triggers_ocr_even_with_native_text(tmp_path: Path) -> None:
    request = _request(create_mixed_raster_text_pdf(tmp_path / "mixed.pdf"))
    ocr = FakeOcr()

    result = PyMuPdfDocumentAnalyzer(motor_ocr=ocr).analisar(request)

    assert [page.pagina_numero for page in ocr.pages] == [1]
    assert any(item.tipo is TipoEvidencia.OCR for item in result.evidencias)


def test_dense_vector_page_triggers_ocr_even_with_native_text(tmp_path: Path) -> None:
    request = _request(create_dense_vector_text_pdf(tmp_path / "dense-vectors.pdf"))
    ocr = FakeOcr()

    result = PyMuPdfDocumentAnalyzer(motor_ocr=ocr).analisar(request)

    assert [page.pagina_numero for page in ocr.pages] == [1]
    assert any(item.tipo is TipoEvidencia.OCR for item in result.evidencias)


def test_extractor_failure_is_localized(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    request = _request(create_analysis_pdf(tmp_path / "partial.pdf"))
    request = replace(
        request,
        configuracao=ConfiguracaoAnaliseDocumento(habilitar_ocr_condicional=False),
    )

    def fail_vectors(_page: object, _page_number: int) -> tuple[object, ...]:
        raise RuntimeError("vector decoder failed")

    monkeypatch.setattr(analyzer_module, "_extract_vectors", fail_vectors)
    result = PyMuPdfDocumentAnalyzer().analisar(request)

    assert any(item.tipo is TipoEvidencia.TEXTO for item in result.evidencias)
    assert any(item.tipo is TipoEvidencia.IMAGEM for item in result.evidencias)
    assert any(item.origem_pdf.tipo is TipoOrigemPdf.ANOTACAO for item in result.evidencias)
    assert any(item.codigo == "analise.vetores_falhou" for item in result.diagnosticos)


def test_changed_source_is_rejected(tmp_path: Path) -> None:
    path = create_analysis_pdf(tmp_path / "changed.pdf")
    request = _request(path)
    path.write_bytes(path.read_bytes() + b"changed")

    with pytest.raises(ValueError, match="alterada"):
        PyMuPdfDocumentAnalyzer().analisar(request)
