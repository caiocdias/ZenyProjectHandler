# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pymupdf
import pytest
from tests.pdf_fixtures import (
    create_analysis_pdf,
    create_dense_vector_text_pdf,
    create_mixed_raster_text_pdf,
    create_small_raster_region_pdf,
)

from zeny_project_handler.adapters.analysis import JsonAnalysisCache, PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.analysis import pymupdf_analyzer as analyzer_module
from zeny_project_handler.adapters.analysis.pymupdf_ocr import (
    _deduplicate_tiled_candidates,
    _extract_marked_equipment_labels,
    _extract_point_identifiers,
    _normalize_equipment_ocr_text,
    _normalize_operational_label_text,
)
from zeny_project_handler.adapters.analysis.pymupdf_symbols import (
    _extract_symbolic_equipment,
)
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.domain.analysis import OrigemObjetoPdf
from zeny_project_handler.domain.enums import TipoEvidencia, TipoGeometria, TipoOrigemPdf
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ports.analysis import (
    AnalisadorDocumentoPort,
    CandidatoEvidenciaDocumento,
    CapacidadeMotorOcr,
    ConfiguracaoAnaliseDocumento,
    GeometriaNormalizada,
    IdentidadeDadosTreinadosOcr,
    PaginaRasterOcr,
    ResultadoAnaliseDocumento,
    ResultadoConsultaCapacidadeOcr,
    SolicitacaoAnaliseDocumento,
    TrechoTextoOcr,
)
from zeny_project_handler.ports.pdf import ReferenciaFontePdf


class FakeOcr:
    nome = "ocr-falso"

    def __init__(
        self,
        *,
        version: str = "1.0",
        languages: tuple[str, ...] = ("por", "eng"),
        traineddata_digests: tuple[str, ...] = ("1" * 64, "2" * 64),
        oem: int = 3,
    ) -> None:
        self.pages: list[PaginaRasterOcr] = []
        self._capability = CapacidadeMotorOcr(
            implementacao=self.nome,
            versao=version,
            idiomas=languages,
            dados_treinados=tuple(
                IdentidadeDadosTreinadosOcr(idioma=language, sha256=digest)
                for language, digest in zip(languages, traineddata_digests, strict=True)
            ),
            parametros=(("oem", oem), ("preprocessamento", "fake-v1")),
        )

    def consultar_capacidade(self) -> ResultadoConsultaCapacidadeOcr:
        return ResultadoConsultaCapacidadeOcr(capacidade=self._capability)

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
    assinatura_capacidade = "fake-capability-v1"

    def analisar(self, _request: SolicitacaoAnaliseDocumento) -> ResultadoAnaliseDocumento:
        return ResultadoAnaliseDocumento(evidencias=(), diagnosticos=(), cache_utilizado=False)


class OtherFakeOcr(FakeOcr):
    nome = "outro-ocr"


class FakeTargetedOcr:
    def __init__(self) -> None:
        self._labels = iter(("CM2(1)", "S1N", "11-300"))

    def reconhecer_identificador(
        self,
        _pagina: PaginaRasterOcr,
    ) -> tuple[TrechoTextoOcr, ...]:
        return (
            TrechoTextoOcr(
                texto="P7",
                caixa_normalizada=(0.1, 0.1, 0.9, 0.9),
                confianca=0.95,
            ),
        )

    def reconhecer_rotulo_operacional(
        self,
        _pagina: PaginaRasterOcr,
    ) -> tuple[TrechoTextoOcr, ...]:
        return (
            TrechoTextoOcr(
                texto=next(self._labels),
                caixa_normalizada=(0.1, 0.1, 0.9, 0.9),
                confianca=0.95,
            ),
        )


class FakeBlockTargetedOcr(FakeTargetedOcr):
    def reconhecer_bloco_operacional(
        self,
        _pagina: PaginaRasterOcr,
    ) -> tuple[TrechoTextoOcr, ...]:
        return tuple(
            TrechoTextoOcr(
                texto=text,
                caixa_normalizada=(0.1, index * 0.2, 0.9, index * 0.2 + 0.1),
                confianca=0.95,
            )
            for index, text in enumerate(("U3(1)", "S3R", "11-300"))
        )


class FakeEquipmentMarkerOcr:
    def __init__(self) -> None:
        self._labels = iter(("100A/10KA/2H", "100A/2KA/2H"))

    def reconhecer_bloco_operacional(
        self,
        _pagina: PaginaRasterOcr,
    ) -> tuple[TrechoTextoOcr, ...]:
        return (
            TrechoTextoOcr(
                texto=next(self._labels),
                caixa_normalizada=(0.1, 0.1, 0.9, 0.9),
                confianca=0.92,
            ),
        )


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


def test_vector_symbols_identify_grounding_and_surge_arresters_with_situation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "simbolos-vetoriais.pdf"
    document = pymupdf.open()
    try:
        page = document.new_page(width=500, height=400)
        _draw_ground_family(page, x=50, y=60, bars=3, color=(0, 0, 0))
        _draw_ground_family(page, x=50, y=170, bars=4, color=(0, 0.5, 0))
        _draw_bt_arrester(page, x=50, y=280, color=(1, 0, 0))

        direct = _extract_symbolic_equipment(page, 1)
        document.save(path)
    finally:
        document.close()

    assert {
        (
            item.conteudo_bruto,
            dict(item.atributos_extraidos)["situacao_projeto_forcada"],
        )
        for item in direct
    } == {
        ("ATERRAMENTO", "EXISTENTE"),
        ("PARA RAIOS MT", "INSTALAR"),
        ("PARA RAIOS BT", "REMOVER"),
    }
    assert all(
        dict(item.atributos_extraidos)["origem_simbologia"] == "SIMBOLOGIA.pdf" for item in direct
    )
    assert all(item.tipo is TipoEvidencia.VETOR for item in direct)

    request = replace(
        _request(path),
        configuracao=ConfiguracaoAnaliseDocumento(habilitar_ocr_condicional=False),
    )
    result = PyMuPdfDocumentAnalyzer().analisar(request)
    symbolic = tuple(
        item
        for item in result.evidencias
        if dict(item.atributos_extraidos).get("reconhecido_por_simbologia") is True
    )

    assert {item.conteudo_bruto for item in symbolic} == {
        "ATERRAMENTO",
        "PARA RAIOS MT",
        "PARA RAIOS BT",
    }
    assert not result.diagnosticos


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


@pytest.mark.parametrize(
    ("version", "languages", "traineddata_digests", "oem"),
    (
        ("1.1", ("por", "eng"), ("1" * 64, "2" * 64), 3),
        ("1.0", ("eng",), ("2" * 64,), 3),
        ("1.0", ("por", "eng"), ("3" * 64, "2" * 64), 3),
        ("1.0", ("por", "eng"), ("1" * 64, "2" * 64), 1),
    ),
    ids=("version", "language", "traineddata", "adapter-configuration"),
)
def test_ocr_capability_changes_invalidate_derived_cache(
    tmp_path: Path,
    version: str,
    languages: tuple[str, ...],
    traineddata_digests: tuple[str, ...],
    oem: int,
) -> None:
    request = _request(create_analysis_pdf(tmp_path / "capability-cache.pdf"))
    cache = JsonAnalysisCache(tmp_path / "cache")

    baseline = PyMuPdfDocumentAnalyzer(motor_ocr=FakeOcr(), cache=cache).analisar(request)
    changed = PyMuPdfDocumentAnalyzer(
        motor_ocr=FakeOcr(
            version=version,
            languages=languages,
            traineddata_digests=traineddata_digests,
            oem=oem,
        ),
        cache=cache,
    ).analisar(request)

    assert not baseline.cache_utilizado
    assert not changed.cache_utilizado


def test_relevant_raster_triggers_ocr_even_with_native_text(tmp_path: Path) -> None:
    request = _request(create_mixed_raster_text_pdf(tmp_path / "mixed.pdf"))
    ocr = FakeOcr()

    result = PyMuPdfDocumentAnalyzer(motor_ocr=ocr).analisar(request)

    assert [page.pagina_numero for page in ocr.pages] == [1]
    assert any(item.tipo is TipoEvidencia.OCR for item in result.evidencias)


def test_missing_ocr_engine_preserves_all_native_extractors(tmp_path: Path) -> None:
    request = _request(create_analysis_pdf(tmp_path / "without-tesseract.pdf"))

    result = PyMuPdfDocumentAnalyzer().analisar(request)

    assert {TipoEvidencia.TEXTO, TipoEvidencia.VETOR, TipoEvidencia.IMAGEM} <= {
        item.tipo for item in result.evidencias
    }
    assert not any(item.tipo is TipoEvidencia.OCR for item in result.evidencias)
    assert any(item.codigo == "analise.ocr_indisponivel" for item in result.diagnosticos)


def test_small_raster_region_triggers_localized_ocr_on_text_rich_page(
    tmp_path: Path,
) -> None:
    request = _request(create_small_raster_region_pdf(tmp_path / "small-region.pdf"))
    ocr = FakeOcr()

    result = PyMuPdfDocumentAnalyzer(motor_ocr=ocr).analisar(request)

    assert len(ocr.pages) == 1
    assert ocr.pages[0].largura_pixels < 200 * 200 / 72
    evidence = next(item for item in result.evidencias if item.tipo is TipoEvidencia.OCR)
    assert min(point.x for point in evidence.geometria.pontos) >= Decimal("0.7")
    assert min(point.y for point in evidence.geometria.pontos) >= Decimal("0.6")


def test_dense_vector_page_triggers_ocr_even_with_native_text(tmp_path: Path) -> None:
    request = _request(create_dense_vector_text_pdf(tmp_path / "dense-vectors.pdf"))
    ocr = FakeOcr()

    result = PyMuPdfDocumentAnalyzer(motor_ocr=ocr).analisar(request)

    assert [page.pagina_numero for page in ocr.pages] == [1] * 9
    assert all(page.dpi == 450 for page in ocr.pages)
    assert any(item.tipo is TipoEvidencia.OCR for item in result.evidencias)


def test_targeted_ocr_reads_each_green_operational_label_below_point() -> None:
    document = pymupdf.open()
    try:
        page = document.new_page(width=1000, height=1000)
        page.draw_oval(
            pymupdf.Rect(100, 100, 114, 110),
            color=(0.5, 0, 0),
        )
        for rectangle in (
            pymupdf.Rect(98, 111, 116, 116),
            pymupdf.Rect(101, 117, 112, 122),
            pymupdf.Rect(97, 123, 117, 129),
        ):
            page.draw_rect(rectangle, color=(0, 0.5, 0))

        candidates = _extract_point_identifiers(
            page,
            1,
            FakeTargetedOcr(),
            1200,
        )
    finally:
        document.close()

    assert [item.conteudo_bruto for item in candidates] == [
        "P7",
        "CM2(1)",
        "S1N",
        "11-300",
    ]
    assert all(item.tipo is TipoEvidencia.OCR for item in candidates)
    assert {dict(item.atributos_extraidos).get("motor_ocr") for item in candidates[1:]} == {
        "tesseract-rotulo-operacional-localizado"
    }


def test_targeted_ocr_falls_back_to_unboxed_dark_block_below_point() -> None:
    document = pymupdf.open()
    try:
        page = document.new_page(width=1000, height=1000)
        page.draw_oval(
            pymupdf.Rect(100, 100, 114, 110),
            color=(0.5, 0, 0),
        )

        candidates = _extract_point_identifiers(
            page,
            1,
            FakeBlockTargetedOcr(),
            1200,
        )
    finally:
        document.close()

    assert [item.conteudo_bruto for item in candidates] == [
        "P7",
        "U3(1)",
        "S3R",
        "11-300",
    ]
    assert {dict(item.atributos_extraidos).get("motor_ocr") for item in candidates[1:]} == {
        "tesseract-bloco-operacional-localizado"
    }


def test_targeted_ocr_reads_boxed_installation_and_struck_removal() -> None:
    document = pymupdf.open()
    try:
        page = document.new_page(width=1000, height=1000)
        page.draw_rect(
            pymupdf.Rect(200, 200, 260, 206),
            color=(0.5, 0, 0),
        )
        page.draw_line(
            (100, 300),
            (150, 300),
            color=(0.5, 0, 0),
        )

        candidates = _extract_marked_equipment_labels(
            page,
            1,
            FakeEquipmentMarkerOcr(),
            1800,
        )
    finally:
        document.close()

    assert [item.conteudo_bruto for item in candidates] == [
        "100A/10KA/2H",
        "100A/2KA/2H",
    ]
    assert [dict(item.atributos_extraidos)["situacao_projeto_forcada"] for item in candidates] == [
        "INSTALAR",
        "REMOVER",
    ]
    assert {dict(item.atributos_extraidos)["motor_ocr"] for item in candidates} == {
        "tesseract-equipamento-marcado-localizado"
    }


@pytest.mark.parametrize(
    ("ocr_text", "expected"),
    [
        ("11-30C", "11-300"),
        ("11-60O", "11-600"),
        ("CM2(1)", "CM2(1)"),
        ("S1N", "S1N"),
        ('CM-50(3/8")', 'CM-50(3/8")'),
        ("CM-50(3/8)", 'CM-50(3/8")'),
        ("N-(1N2)", "N- (1N2)"),
        ("N-(4CA)", "N-(4 CA)"),
        ("N-(4/0 CAA)", "N-(4/0 CAA)"),
        ("ABN-16(16)", "ABN-16(16)"),
    ],
)
def test_targeted_ocr_normalizes_ambiguous_characters_only_in_numeric_labels(
    ocr_text: str,
    expected: str,
) -> None:
    assert _normalize_operational_label_text(ocr_text) == expected


def test_targeted_equipment_ocr_normalizes_numeric_glyph_confusion() -> None:
    assert _normalize_equipment_ocr_text("1OOA/1OKA/2H") == "100A/10KA/2H"


def test_targeted_operational_label_replaces_general_ocr_at_same_position() -> None:
    def candidate(
        text: str,
        motor: str,
        *,
        y: str,
    ) -> CandidatoEvidenciaDocumento:
        return CandidatoEvidenciaDocumento(
            chave_estavel=f"{motor}:{text}",
            pagina_numero=1,
            tipo=TipoEvidencia.OCR,
            geometria=GeometriaNormalizada(
                tipo=TipoGeometria.CAIXA,
                pontos=(
                    PontoNormalizado(Decimal("0.34"), Decimal(y)),
                    PontoNormalizado(Decimal("0.36"), Decimal(y) + Decimal("0.004")),
                ),
            ),
            origem_pdf=OrigemObjetoPdf(),
            conteudo_bruto=text,
            atributos_extraidos=(
                ("confianca", Decimal("0.90")),
                ("motor_ocr", motor),
            ),
        )

    general = candidate("M2", "tesseract-cli", y="0.65")
    composite = candidate("S4R S3R", "tesseract-cli", y="0.65")
    point = candidate(
        "P7",
        "tesseract-identificador-localizado",
        y="0.642",
    )
    targeted = candidate(
        "CM2(1)",
        "tesseract-rotulo-operacional-localizado",
        y="0.65",
    )

    selected = _deduplicate_tiled_candidates((general, composite, point, targeted))

    assert [item.conteudo_bruto for item in selected] == [
        "S4R S3R",
        "P7",
        "CM2(1)",
    ]


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


def _draw_ground_family(
    page: pymupdf.Page,
    *,
    x: float,
    y: float,
    bars: int,
    color: tuple[float, float, float],
) -> None:
    page.draw_line((x, y), (x + 15, y), color=color, width=0.5)
    lengths = (10.0, 7.0, 4.0, 7.0)
    for index in range(bars):
        center_x = x + 15 + index * 4
        length = lengths[index]
        page.draw_line(
            (center_x, y - length / 2),
            (center_x, y + length / 2),
            color=color,
            width=0.5,
        )


def _draw_bt_arrester(
    page: pymupdf.Page,
    *,
    x: float,
    y: float,
    color: tuple[float, float, float],
) -> None:
    page.draw_line((x, y), (x + 15, y), color=color, width=0.5)
    page.draw_rect(pymupdf.Rect(x + 15, y - 1.5, x + 24, y + 1.5), color=color, width=0.5)
    page.draw_line(
        (x + 15, y - 3.5),
        (x + 24, y + 3.5),
        color=color,
        width=0.5,
    )
