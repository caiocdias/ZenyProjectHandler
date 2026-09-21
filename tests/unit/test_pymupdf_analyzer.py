# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
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
    create_e01_network_service_drop_pdf,
    create_e01_span_change_pdf,
    create_e01_structure_occurrences_pdf,
    create_e01_switch_bags_pdf,
    create_e01_topology_cases_pdf,
    create_mixed_raster_text_pdf,
    create_small_raster_region_pdf,
)

from zeny_project_handler.adapters.analysis import JsonAnalysisCache, PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.analysis import pymupdf_analyzer as analyzer_module
from zeny_project_handler.adapters.analysis import pymupdf_ocr as ocr_module
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
from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.application.automatic_promotion import promover_resultado_automatico
from zeny_project_handler.domain.analysis import OrigemObjetoPdf
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import (
    EstadoRevisao,
    TipoEvidencia,
    TipoGeometria,
    TipoOrigemPdf,
)
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
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
from zeny_project_handler.ports.interpretation import SolicitacaoInterpretacao
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


class CharacterizationOcr(FakeOcr):
    def reconhecer_identificador(
        self,
        _pagina: PaginaRasterOcr,
    ) -> tuple[TrechoTextoOcr, ...]:
        return ()

    def reconhecer_rotulo_operacional(
        self,
        _pagina: PaginaRasterOcr,
    ) -> tuple[TrechoTextoOcr, ...]:
        return ()

    def reconhecer_bloco_operacional(
        self,
        _pagina: PaginaRasterOcr,
    ) -> tuple[TrechoTextoOcr, ...]:
        return ()


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


class _RecordingPixmapPage:
    def __init__(self) -> None:
        self.options: dict[str, object] = {}
        self.result = object()

    def get_pixmap(self, **options: object) -> object:
        self.options = options
        return self.result


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


def _geometry_bounds(
    geometry: GeometriaDocumento,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    xs = [point.x for point in geometry.pontos]
    ys = [point.y for point in geometry.pontos]
    return min(xs), min(ys), max(xs), max(ys)


def _geometries_overlap(left: GeometriaDocumento, right: GeometriaDocumento) -> bool:
    left_x0, left_y0, left_x1, left_y1 = _geometry_bounds(left)
    right_x0, right_y0, right_x1, right_y1 = _geometry_bounds(right)
    return (
        left_x0 <= right_x1 and right_x0 <= left_x1 and left_y0 <= right_y1 and right_y0 <= left_y1
    )


def test_real_and_fake_analyzers_follow_the_same_contract(tmp_path: Path) -> None:
    request = _request(create_analysis_pdf(tmp_path / "contract.pdf"))

    _assert_contract(FakeAnalyzer(), request)
    _assert_contract(
        PyMuPdfDocumentAnalyzer(motor_ocr=FakeOcr(), cache=JsonAnalysisCache(tmp_path / "cache")),
        request,
    )


def test_semantic_ocr_raster_never_includes_pdf_annotations() -> None:
    page = _RecordingPixmapPage()

    result = ocr_module._semantic_page_pixmap(page, dpi=300, annots=True)

    assert result is page.result
    assert page.options["annots"] is False
    assert page.options["dpi"] == 300


def test_native_extraction_preserves_geometry_provenance_and_properties(tmp_path: Path) -> None:
    request = _request(create_analysis_pdf(tmp_path / "features.pdf"))
    ocr = FakeOcr()

    result = PyMuPdfDocumentAnalyzer(motor_ocr=ocr).analisar(request)

    assert {item.tipo for item in result.evidencias} == set(TipoEvidencia)
    # Annotation text no longer inflates the native-character threshold on page 1.
    assert [page.pagina_numero for page in ocr.pages] == [1, 2]
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
    shx_evidence = tuple(
        item for item in result.evidencias if item.origem_pdf.subtipo_anotacao == "Square"
    )
    assert shx_evidence
    assert all(
        dict(item.atributos_extraidos).get("anotacao_tecnica") is True for item in shx_evidence
    )
    assert any(
        item.tipo is TipoEvidencia.IMAGEM
        and item.origem_pdf.tipo is TipoOrigemPdf.APARENCIA_ANOTACAO
        and item.origem_pdf.nome_recurso == "ImAppearance"
        for item in result.evidencias
    )
    assert any(item.origem_pdf.tipo is TipoOrigemPdf.FORM_XOBJECT for item in result.evidencias)
    ocr_evidence = next(
        item
        for item in result.evidencias
        if item.tipo is TipoEvidencia.OCR and item.pagina_id == request.documento.paginas[1].id
    )
    assert ocr_evidence.pagina_id == request.documento.paginas[1].id
    assert dict(ocr_evidence.atributos_extraidos)["confianca"] == Decimal("0.91")


def test_e01_structure_fixture_extracts_each_raw_occurrence(tmp_path: Path) -> None:
    path = create_e01_structure_occurrences_pdf(tmp_path / "e01-structures.pdf")

    result = PyMuPdfDocumentAnalyzer().analisar(_request(path))

    texts = [item.conteudo_bruto for item in result.evidencias if item.tipo is TipoEvidencia.TEXTO]
    assert {"N(2)", "N-(4 CAA)", "CM3(1)", "CM3(2)"} <= set(texts)
    assert texts.count("S3R") == 2
    s3r_occurrences = [item for item in result.evidencias if item.conteudo_bruto == "S3R"]
    assert s3r_occurrences[0].geometria != s3r_occurrences[1].geometria
    assert not result.diagnosticos


def test_e01_switch_fixture_extracts_bagged_and_unbagged_inputs(tmp_path: Path) -> None:
    path = create_e01_switch_bags_pdf(tmp_path / "e01-switches.pdf")

    result = PyMuPdfDocumentAnalyzer().analisar(_request(path))

    switches = {
        label: sorted(
            (item for item in result.evidencias if item.conteudo_bruto == label),
            key=lambda item: min(point.y for point in item.geometria.pontos),
        )
        for label in ("100A-10KA-2H", "100A-10KA-5H")
    }
    bags = [
        item
        for item in result.evidencias
        if item.tipo is TipoEvidencia.VETOR
        and dict(item.atributos_extraidos).get("cor_contorno") == "#8C0033"
    ]
    assert all(len(occurrences) == 2 for occurrences in switches.values())
    assert len(bags) == 4
    for occurrences in switches.values():
        assert any(_geometries_overlap(occurrences[0].geometria, bag.geometria) for bag in bags)
        assert not any(_geometries_overlap(occurrences[1].geometria, bag.geometria) for bag in bags)
    rotated = switches["100A-10KA-5H"][0]
    assert abs(Decimal(str(dict(rotated.atributos_extraidos)["rotacao_graus"]))) == Decimal(90)
    assert any(item.conteudo_bruto == "280835-300A-12T" for item in result.evidencias)
    assert any(item.conteudo_bruto == "321 m" for item in result.evidencias)


def test_e01_span_change_fixture_extracts_superseded_and_current_measurements(
    tmp_path: Path,
) -> None:
    path = create_e01_span_change_pdf(tmp_path / "e01-span-change.pdf")

    result = PyMuPdfDocumentAnalyzer().analisar(_request(path))

    measurements = {
        item.conteudo_bruto: item
        for item in result.evidencias
        if item.conteudo_bruto in {"321 m", "269 m", "42 m"}
    }
    red_lines = [
        item
        for item in result.evidencias
        if item.tipo is TipoEvidencia.VETOR
        and dict(item.atributos_extraidos).get("cor_contorno") == "#8C0033"
    ]
    assert set(measurements) == {"321 m", "269 m", "42 m"}
    assert len(red_lines) == 2
    assert any(
        _geometries_overlap(measurements["321 m"].geometria, line.geometria) for line in red_lines
    )
    assert not any(
        _geometries_overlap(measurements["269 m"].geometria, line.geometria) for line in red_lines
    )
    assert not any(
        _geometries_overlap(measurements["42 m"].geometria, line.geometria) for line in red_lines
    )


def test_e01_network_fixture_extracts_distinct_network_drop_and_standard(
    tmp_path: Path,
) -> None:
    path = create_e01_network_service_drop_pdf(tmp_path / "e01-network-drop.pdf")

    result = PyMuPdfDocumentAnalyzer().analisar(_request(path))

    texts = {item.conteudo_bruto for item in result.evidencias if item.tipo is TipoEvidencia.TEXTO}
    vector_colors = {
        dict(item.atributos_extraidos).get("cor_contorno")
        for item in result.evidencias
        if item.tipo is TipoEvidencia.VETOR
    }
    assert {
        "P2 POSTE DA REDE",
        "ESTRUTURA CM1",
        "RAMAL R1-ENTREGA",
        "PADRAO",
        "LEGENDA: PADRAO DE COR",
    } <= texts
    assert {"#1A731A", "#262626", "#8C0033"} <= vector_colors


def test_e01_topology_fixture_extracts_complete_incomplete_and_true_controls(
    tmp_path: Path,
) -> None:
    path = create_e01_topology_cases_pdf(tmp_path / "e01-topologies.pdf")
    request = _request(path)

    result = PyMuPdfDocumentAnalyzer().analisar(request)

    page_ids = [page.id for page in request.documento.paginas]
    page_texts = {
        page_id: {
            item.conteudo_bruto
            for item in result.evidencias
            if item.pagina_id == page_id and item.tipo is TipoEvidencia.TEXTO
        }
        for page_id in page_ids
    }
    green_line_counts = {
        page_id: sum(
            1
            for item in result.evidencias
            if item.pagina_id == page_id
            and item.tipo is TipoEvidencia.VETOR
            and dict(item.atributos_extraidos).get("cor_contorno") == "#1A731A"
            and dict(item.atributos_extraidos).get("operacoes") == "l"
        )
        for page_id in page_ids
    }
    assert "TOPOLOGIA COMPLETA" in page_texts[page_ids[0]]
    assert "MESMA TECNOLOGIA" in page_texts[page_ids[0]]
    assert green_line_counts[page_ids[0]] == 2
    assert "TOPOLOGIA INCOMPLETA" in page_texts[page_ids[1]]
    assert "EXTREMIDADE AUSENTE" in page_texts[page_ids[1]]
    assert green_line_counts[page_ids[1]] == 1
    assert {"FIM REAL", "TRECHO RESOLVIDO"} <= page_texts[page_ids[2]]
    assert green_line_counts[page_ids[2]] == 1
    assert {"TRANSICAO REAL", "REDE NUA", "REDE ISOLADA"} <= page_texts[page_ids[3]]
    assert green_line_counts[page_ids[3]] == 2


@pytest.mark.parametrize(
    ("builder", "filename"),
    (
        (create_e01_structure_occurrences_pdf, "structures.pdf"),
        (create_e01_switch_bags_pdf, "switches.pdf"),
        (create_e01_span_change_pdf, "span-change.pdf"),
        (create_e01_network_service_drop_pdf, "network-drop.pdf"),
        (create_e01_topology_cases_pdf, "topologies.pdf"),
    ),
)
def test_e01_fixtures_are_sanitized_and_self_contained(
    tmp_path: Path,
    builder: Callable[[Path], Path],
    filename: str,
) -> None:
    result = PyMuPdfDocumentAnalyzer().analisar(_request(builder(tmp_path / filename)))

    combined_text = "\n".join(item.conteudo_bruto or "" for item in result.evidencias)
    assert not re.search(r"(?<!\d)\d{10}(?!\d)", combined_text)
    assert not re.search(r"\b(?:NS|TELEFONE|ASSINATURA|COORDENADA)\b", combined_text, re.I)
    assert "CEMIG" not in combined_text.upper()
    assert not any(item.tipo is TipoEvidencia.IMAGEM for item in result.evidencias)
    assert all(item.origem_pdf.tipo is TipoOrigemPdf.CONTEUDO_PAGINA for item in result.evidencias)
    assert not result.diagnosticos


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
        ("ATERRAMENTO", None),
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


@pytest.mark.parametrize("shape", ["ellipse", "curved_glyph", "angular_glyph"])
def test_vector_letters_near_network_line_are_not_equipment(shape: str) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=500, height=400)
        page.draw_line((50, 60), (90, 60), color=(0, 0.5, 0))
        for x in (96, 99, 102, 105):
            if shape == "ellipse":
                page.draw_oval(pymupdf.Rect(x, 57, x + 1, 63), color=None, fill=(0, 0.5, 0))
            elif shape == "curved_glyph":
                page.draw_bezier(
                    (x, 57), (x + 1, 59), (x + 1, 61), (x, 63), color=None, fill=(0, 0.5, 0)
                )
            else:
                page.draw_polyline([(x, 57), (x + 1, 60), (x, 63)], color=None, fill=(0, 0.5, 0))
        assert _extract_symbolic_equipment(page, 1) == ()


def test_filled_rectangular_bars_still_identify_grounding() -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=500, height=400)
        page.draw_line((50, 60), (65, 60), color=(0, 0, 0))
        for index, length in enumerate((10, 7, 4)):
            x = 65 + index * 4
            page.draw_rect(
                pymupdf.Rect(x - 0.1, 60 - length / 2, x + 0.1, 60 + length / 2),
                color=None,
                fill=(0, 0, 0),
            )
        symbols = _extract_symbolic_equipment(page, 1)
        assert len(symbols) == 1
        assert symbols[0].conteudo_bruto == "ATERRAMENTO"


@pytest.mark.parametrize("kind", ("ATERRAMENTO", "PARA RAIOS MT", "PARA RAIOS BT"))
@pytest.mark.parametrize("scale", (0.3, 1.0, 5.0))
@pytest.mark.parametrize("angle", (0.0, 31.0, 90.0, 153.0))
@pytest.mark.parametrize("packing", ("separate", "grouped", "fragmented"))
def test_e04_vector_symbols_preserve_class_and_full_geometry(
    kind: str, scale: float, angle: float, packing: str
) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        expected = _draw_e04_symbol(
            page, kind=kind, origin=(200, 120), scale=scale, angle=angle, packing=packing
        )

        symbols = _extract_symbolic_equipment(page, 1)

        assert len(symbols) == 1
        assert symbols[0].conteudo_bruto == kind
        _assert_e04_bounds(page, symbols[0], expected)
        assert dict(symbols[0].atributos_extraidos)["confianca"] == Decimal("0.88")


@pytest.mark.parametrize("kind", ("ATERRAMENTO", "PARA RAIOS MT"))
@pytest.mark.parametrize("angle", (0.0, 37.0, 90.0))
def test_e04_filled_rotated_bars_preserve_class_and_geometry(kind: str, angle: float) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        expected = _draw_e04_symbol(page, kind=kind, origin=(120, 120), angle=angle, filled=True)

        symbols = _extract_symbolic_equipment(page, 1)

        assert len(symbols) == 1
        assert symbols[0].conteudo_bruto == kind
        _assert_e04_bounds(page, symbols[0], expected)


def test_e04_bt_body_from_four_separate_strokes_is_recovered() -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        corners = ((95, 88.5), (104, 88.5), (104, 91.5), (95, 91.5))
        page.draw_line((80, 90), (95, 90), color=(0, 0.5, 0))
        for first, second in zip(corners, (*corners[1:], corners[0]), strict=True):
            page.draw_line(first, second, color=(0, 0.5, 0))
        page.draw_line((95, 86.5), (104, 93.5), color=(0, 0.5, 0))

        symbols = _extract_symbolic_equipment(page, 1)

        assert len(symbols) == 1
        assert symbols[0].conteudo_bruto == "PARA RAIOS BT"
        _assert_e04_bounds(page, symbols[0], ((80, 86.5), (104, 93.5)))


@pytest.mark.parametrize("rotation", (0, 90, 180, 270))
def test_e04_page_rotation_keeps_symbol_in_display_coordinates(rotation: int) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        expected = _draw_e04_symbol(page, kind="ATERRAMENTO", origin=(80, 90))
        page.set_rotation(rotation)

        symbols = _extract_symbolic_equipment(page, 2)

        assert len(symbols) == 1
        assert symbols[0].pagina_numero == 2
        _assert_e04_bounds(page, symbols[0], expected)


@pytest.mark.parametrize("kind", ("ATERRAMENTO", "PARA RAIOS MT", "PARA RAIOS BT"))
def test_e04_nearby_symbols_keep_distinct_identity_and_source_support(kind: str) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        expected = [
            _draw_e04_symbol(page, kind=kind, origin=(80, y), packing="grouped") for y in (90, 101)
        ]

        symbols = _extract_symbolic_equipment(page, 1)

        assert len(symbols) == 2
        assert len({item.chave_estavel for item in symbols}) == 2
        assert all(item.conteudo_bruto == kind for item in symbols)
        for symbol, bounds in zip(
            sorted(symbols, key=lambda item: min(point.y for point in item.geometria.pontos)),
            expected,
            strict=True,
        ):
            _assert_e04_bounds(page, symbol, bounds)
        supports = [
            set(str(dict(item.atributos_extraidos)["vetores_origem"]).split(","))
            for item in symbols
        ]
        assert supports[0].isdisjoint(supports[1])


@pytest.mark.parametrize("kind", ("ATERRAMENTO", "PARA RAIOS MT"))
def test_e04_interleaved_nearby_symbols_preserve_both_occurrences(kind: str) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        expected = [
            _draw_e04_symbol(page, kind=kind, origin=(x, 100), packing="grouped") for x in (80, 94)
        ]

        symbols = _extract_symbolic_equipment(page, 1)

        assert len(symbols) == 2
        assert all(item.conteudo_bruto == kind for item in symbols)
        assert len({item.chave_estavel for item in symbols}) == 2
        for symbol, bounds in zip(
            sorted(symbols, key=lambda item: min(point.x for point in item.geometria.pontos)),
            expected,
            strict=True,
        ):
            _assert_e04_bounds(page, symbol, bounds)


def test_e04_long_fragmented_fence_is_not_grounding_or_arrester() -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        shape = page.new_shape()
        for x in range(50, 350, 15):
            shape.draw_line((x, 100), (x + 15, 100))
        for x in range(50, 351, 15):
            shape.draw_line((x, 94), (x, 106))
        shape.finish(color=(0, 0.5, 0), closePath=False)
        shape.commit()

        assert _extract_symbolic_equipment(page, 1) == ()


@pytest.mark.parametrize("angle", (0.0, 37.0))
@pytest.mark.parametrize("bar_offsets", ((15.0, 19.0, 23.0, 27.0), (15.0, 18.0, 21.0, 24.0, 27.0)))
def test_e04_mt_equal_terminal_bars_preserve_legacy_true_positive(
    angle: float, bar_offsets: tuple[float, ...]
) -> None:
    theta = math.radians(angle)

    def point(x: float, y: float) -> tuple[float, float]:
        return 80 + x * math.cos(theta) - y * math.sin(theta), 100 + x * math.sin(
            theta
        ) + y * math.cos(theta)

    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        points = [point(0, 0), point(15, 0)]
        page.draw_line(points[0], points[1], color=(0, 0.5, 0))
        for x in bar_offsets:
            points.extend((point(x, -4), point(x, 4)))
            page.draw_line(points[-2], points[-1], color=(0, 0.5, 0))

        symbols = _extract_symbolic_equipment(page, 1)

        assert len(symbols) == 1
        assert symbols[0].conteudo_bruto == "PARA RAIOS MT"
        _assert_e04_bounds(page, symbols[0], tuple(points))


@pytest.mark.parametrize(
    ("kind", "bar_lengths", "terminal_offset"),
    (
        ("ATERRAMENTO", (15.0, 9.0, 3.0), 15.0),
        ("PARA RAIOS MT", (15.0, 6.0, 15.0, 6.0), 15.0),
        ("ATERRAMENTO", (10.0, 7.0, 4.0), 14.5),
        ("PARA RAIOS MT", (10.0, 7.0, 4.0, 7.0), 14.5),
    ),
    ids=("ground-wide", "mt-wide", "ground-overlap", "mt-overlap"),
)
@pytest.mark.parametrize("angle", (0.0, 37.0, 131.0))
@pytest.mark.parametrize("scale", (0.5, 1.0, 3.0))
def test_e04_wide_and_overlapping_terminal_bars_preserve_legacy_classes(
    kind: str,
    bar_lengths: tuple[float, ...],
    terminal_offset: float,
    angle: float,
    scale: float,
) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        points = _draw_e04_symbol(
            page,
            kind=kind,
            origin=(200, 120),
            scale=scale,
            angle=angle,
            bar_lengths=bar_lengths,
            terminal_offset=terminal_offset,
            bar_gap=3.0,
        )

        symbols = _extract_symbolic_equipment(page, 1)

        assert len(symbols) == 1
        assert symbols[0].conteudo_bruto == kind
        _assert_e04_bounds(page, symbols[0], points)


@pytest.mark.parametrize("outline", ("curve", "polygon", "fragmented_polygon"))
def test_e04_circular_outline_does_not_add_a_fourth_grounding_bar(outline: str) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        points = _draw_e04_symbol(page, kind="ATERRAMENTO", origin=(200, 120))
        if outline == "curve":
            page.draw_circle((212, 120), 15, color=(0, 0.5, 0), width=0.5)
        else:
            ring = [
                (
                    212 + 15 * math.cos(math.radians(angle)),
                    120 + 15 * math.sin(math.radians(angle)),
                )
                for angle in range(0, 360, 10)
            ]
            if outline == "polygon":
                page.draw_polyline([*ring, ring[0]], color=(0, 0.5, 0), width=0.5)
            else:
                for first, second in zip(ring, (*ring[1:], ring[0]), strict=True):
                    page.draw_line(first, second, color=(0, 0.5, 0), width=0.5)

        symbols = _extract_symbolic_equipment(page, 1)

        assert len(symbols) == 1
        assert symbols[0].conteudo_bruto == "ATERRAMENTO"
        _assert_e04_bounds(page, symbols[0], points)
        assert set(str(dict(symbols[0].atributos_extraidos)["vetores_origem"]).split(",")) == {
            "0",
            "1",
            "2",
            "3",
        }


@pytest.mark.parametrize("fragmented_bar", (0, 1, 2))
@pytest.mark.parametrize("bar_tilt", (0.0, 10.0))
def test_e04_fragments_and_reconstructed_bar_are_one_physical_bar(
    fragmented_bar: int, bar_tilt: float
) -> None:
    with pymupdf.open() as document:
        document.new_page(width=400, height=300)
        document.new_page(width=400, height=300)
        reference_page, page = document[0], document[1]
        points: list[tuple[float, float]] = [(100, 120), (115, 120)]
        theta = math.radians(bar_tilt)
        for target, fragmented in ((reference_page, False), (page, True)):
            target.draw_line((100, 120), (115, 120), color=(0, 0.5, 0))
            for index, length in enumerate((10, 7, 4)):
                center = (115.0 + 4 * index, 120.0)
                start = (
                    center[0] - length / 2 * math.sin(theta),
                    center[1] - length / 2 * math.cos(theta),
                )
                end = (
                    center[0] + length / 2 * math.sin(theta),
                    center[1] + length / 2 * math.cos(theta),
                )
                points.extend((start, end))
                segments = (
                    ((start, center), (center, end))
                    if fragmented and index == fragmented_bar
                    else ((start, end),)
                )
                for first, second in segments:
                    target.draw_line(first, second, color=(0, 0.5, 0))

        reference = _extract_symbolic_equipment(reference_page, 1)
        symbols = _extract_symbolic_equipment(page, 2)

        assert len(reference) == len(symbols) == 1
        assert symbols[0].conteudo_bruto == reference[0].conteudo_bruto == "ATERRAMENTO"
        assert _extract_symbolic_equipment(page, 2) == symbols
        _assert_e04_bounds(page, symbols[0], tuple(points))
        assert json.loads(str(dict(symbols[0].atributos_extraidos)["primitives_origem"])) == [
            [index, 0] for index in range(5)
        ]


def test_e04_grouped_stem_turning_into_half_bar_preserves_open_t_junction() -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        shape = page.new_shape()
        shape.draw_polyline(((100, 120), (115, 120), (115, 115)))
        shape.draw_line((115, 120), (115, 125))
        shape.draw_line((119, 116.5), (119, 123.5))
        shape.draw_line((123, 118), (123, 122))
        shape.finish(color=(0, 0.5, 0), width=0.5, closePath=False)
        shape.commit()

        symbols = _extract_symbolic_equipment(page, 1)

        assert len(symbols) == 1
        assert symbols[0].conteudo_bruto == "ATERRAMENTO"
        _assert_e04_bounds(page, symbols[0], ((100, 115), (123, 125)))
        assert dict(symbols[0].atributos_extraidos)["vetores_origem"] == "0"


@pytest.mark.parametrize("kind", ("ATERRAMENTO", "PARA RAIOS MT"))
@pytest.mark.parametrize("shortening", (0.5, 1.0))
@pytest.mark.parametrize("angle", (0.0, 37.0))
def test_e04_contained_redundant_stem_keeps_one_symbol_and_all_sources(
    kind: str, shortening: float, angle: float
) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        points = _draw_e04_symbol(page, kind=kind, origin=(100, 120), angle=angle)
        theta = math.radians(angle)
        page.draw_line(
            (100 + shortening * math.cos(theta), 120 + shortening * math.sin(theta)),
            (100 + 15 * math.cos(theta), 120 + 15 * math.sin(theta)),
            color=(0, 0.5, 0),
            width=0.5,
        )

        symbols = _extract_symbolic_equipment(page, 1)

        assert len(symbols) == 1
        assert symbols[0].conteudo_bruto == kind
        assert _extract_symbolic_equipment(page, 1) == symbols
        _assert_e04_bounds(page, symbols[0], points)
        drawing_count = 5 if kind == "ATERRAMENTO" else 6
        assert json.loads(str(dict(symbols[0].atributos_extraidos)["primitives_origem"])) == [
            [index, 0] for index in range(drawing_count)
        ]


def test_e04_redundant_stems_with_fragmented_terminal_bar_are_coalesced() -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        segments = (
            ((80, 100), (95, 100)),
            ((81, 100), (95, 100)),
            ((95, 95), (95, 100)),
            ((95, 100), (95, 105)),
            ((99, 96.5), (99, 103.5)),
            ((103, 98), (103, 102)),
        )
        for first, second in segments:
            page.draw_line(first, second, color=(0, 0.5, 0), width=0.5)

        symbols = _extract_symbolic_equipment(page, 1)

        assert len(symbols) == 1
        assert symbols[0].conteudo_bruto == "ATERRAMENTO"
        _assert_e04_bounds(page, symbols[0], ((80, 95), (103, 105)))
        assert json.loads(str(dict(symbols[0].atributos_extraidos)["primitives_origem"])) == [
            [index, 0] for index in range(6)
        ]


@pytest.mark.parametrize(
    "kinds", (("ATERRAMENTO", "PARA RAIOS MT"), ("PARA RAIOS MT", "ATERRAMENTO"))
)
@pytest.mark.parametrize("angle", (0.0, 37.0))
def test_e04_collinear_ground_and_mt_neighbors_keep_separate_boxes_and_support(
    kinds: tuple[str, str], angle: float
) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        theta = math.radians(angle)
        expected = {
            kind: _draw_e04_symbol(
                page,
                kind=kind,
                origin=(100 + offset * math.cos(theta), 120 + offset * math.sin(theta)),
                angle=angle,
                packing="grouped",
            )
            for kind, offset in zip(kinds, (0, 14), strict=True)
        }

        symbols = _extract_symbolic_equipment(page, 1)

        assert len(symbols) == 2
        assert {symbol.conteudo_bruto for symbol in symbols} == set(kinds)
        assert len({symbol.chave_estavel for symbol in symbols}) == 2
        for symbol in symbols:
            assert symbol.conteudo_bruto is not None
            _assert_e04_bounds(page, symbol, expected[symbol.conteudo_bruto])
            assert dict(symbol.atributos_extraidos)["vetores_origem"] == str(
                kinds.index(symbol.conteudo_bruto)
            )


@pytest.mark.parametrize("angle", (0.0, 37.0))
def test_e04_shared_stem_start_with_distinct_terminals_keeps_two_grounds(angle: float) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        expected = [
            _draw_e04_symbol(
                page,
                kind="ATERRAMENTO",
                origin=(100, 120),
                scale=scale,
                angle=angle,
                packing="grouped",
            )
            for scale in (1.0, 7.0 / 3.0)
        ]

        symbols = _extract_symbolic_equipment(page, 1)

        assert len(symbols) == 2
        assert all(symbol.conteudo_bruto == "ATERRAMENTO" for symbol in symbols)
        assert len({symbol.chave_estavel for symbol in symbols}) == 2
        ordered = sorted(symbols, key=lambda item: max(point.x for point in item.geometria.pontos))
        for index, (symbol, points) in enumerate(zip(ordered, expected, strict=True)):
            _assert_e04_bounds(page, symbol, points)
            assert dict(symbol.atributos_extraidos)["vetores_origem"] == str(index)


@pytest.mark.parametrize("angle", (0.0, 37.0))
def test_e04_ground_stem_does_not_borrow_opposite_mt_terminal_bars(angle: float) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        theta = math.radians(angle)
        expected = {}
        for kind, start, lengths in (
            ("ATERRAMENTO", 15.0, (15.0, 9.0, 3.0)),
            ("PARA RAIOS MT", 40.0, (15.0, 6.0, 15.0, 6.0)),
        ):
            expected[kind] = _draw_e04_symbol(
                page,
                kind=kind,
                origin=(100 + start * math.cos(theta), 120 + start * math.sin(theta)),
                angle=180 + angle,
                packing="grouped",
                bar_lengths=lengths,
                bar_gap=3,
            )

        symbols = _extract_symbolic_equipment(page, 1)

        assert len(symbols) == 2
        assert {symbol.conteudo_bruto for symbol in symbols} == set(expected)
        for symbol in symbols:
            assert symbol.conteudo_bruto is not None
            _assert_e04_bounds(page, symbol, expected[symbol.conteudo_bruto])
            assert dict(symbol.atributos_extraidos)["vetores_origem"] == (
                "0" if symbol.conteudo_bruto == "ATERRAMENTO" else "1"
            )


def test_e04_repeated_form_instances_have_distinct_keys_and_localization() -> None:
    with pymupdf.open() as source, pymupdf.open() as document:
        source_page = source.new_page(width=100, height=80)
        source_bounds = _draw_e04_symbol(
            source_page, kind="PARA RAIOS MT", origin=(30, 40), packing="grouped"
        )
        page = document.new_page(width=400, height=300)
        for x, y in ((20, 20), (180, 160)):
            page.show_pdf_page(pymupdf.Rect(x, y, x + 100, y + 80), source, 0)

        first = _extract_symbolic_equipment(page, 1)
        second = _extract_symbolic_equipment(page, 1)

        assert first == second
        assert len(first) == 2
        assert len({item.chave_estavel for item in first}) == 2
        for symbol, (x, y) in zip(first, ((20, 20), (180, 160)), strict=True):
            _assert_e04_bounds(
                page,
                symbol,
                tuple((px + x, py + y) for px, py in source_bounds),
            )


@pytest.mark.parametrize("clip_width", (70, 100))
def test_e04_inherited_form_clip_does_not_detect_invisible_symbol_bars(clip_width: int) -> None:
    with pymupdf.open() as source, pymupdf.open() as document:
        source_page = source.new_page(width=200, height=200)
        source_points = _draw_e04_symbol(source_page, kind="ATERRAMENTO", origin=(60, 100))
        page = document.new_page(width=400, height=300)
        page.show_pdf_page(
            pymupdf.Rect(20, 20, 20 + clip_width, 220),
            source,
            0,
            clip=pymupdf.Rect(0, 0, clip_width, 200),
        )

        symbols = _extract_symbolic_equipment(page, 1)

        if clip_width == 70:
            # Only a short piece of the stem is painted; all bars lie outside the Form clip.
            assert symbols == ()
        else:
            assert len(symbols) == 1
            _assert_e04_bounds(page, symbols[0], tuple((x + 20, y + 20) for x, y in source_points))


@pytest.mark.parametrize("with_ocg", (False, True))
def test_e04_annotation_appearance_is_not_reported_as_base_symbol(with_ocg: bool) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        ocg = document.add_ocg("Rede E04") if with_ocg else 0
        expected = _draw_e04_symbol(page, kind="ATERRAMENTO", origin=(80, 90), oc=ocg)
        segments: list[tuple[tuple[float, float], tuple[float, float]]] = [((80, 160), (95, 160))]
        segments.extend(
            ((95 + index * 4, 160 - length / 2), (95 + index * 4, 160 + length / 2))
            for index, length in enumerate((10, 7, 4))
        )
        for first, second in segments:
            annotation = page.add_line_annot(first, second)
            annotation.set_colors(stroke=(0, 0.5, 0))
            annotation.set_border(width=0.5)
            annotation.update()

        symbols = _extract_symbolic_equipment(page, 1)

        assert len(symbols) == 1
        _assert_e04_bounds(page, symbols[0], expected)
        styles = json.loads(str(dict(symbols[0].atributos_extraidos)["estilos_originais"]))
        assert {item["layer"] for item in styles.values()} == {"Rede E04" if with_ocg else ""}
        assert len(tuple(page.annots())) == 4


@pytest.mark.parametrize("shade", (0.0, 0.4, 0.7))
def test_e04_monochrome_symbol_is_not_automatically_existing(shade: float) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        _draw_e04_symbol(page, kind="ATERRAMENTO", origin=(80, 90), color=(shade, shade, shade))

        symbols = _extract_symbolic_equipment(page, 1)

        assert len(symbols) == 1
        attributes = dict(symbols[0].atributos_extraidos)
        assert attributes.get("situacao_projeto_forcada") is None
        assert attributes["situacao_indeterminada"] is True


def test_e04_monochrome_candidate_is_not_promoted_to_confirmed_equipment(
    tmp_path: Path, catalogo_inicial: CatalogoTecnico
) -> None:
    path = tmp_path / "monochrome.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        _draw_e04_symbol(page, kind="ATERRAMENTO", origin=(80, 90), color=(0, 0, 0))
        page.insert_text((85, 82), "P1", fontsize=6)
        document.save(path)
    request = replace(
        _request(path),
        configuracao=ConfiguracaoAnaliseDocumento(habilitar_ocr_condicional=False),
    )
    extracted = PyMuPdfDocumentAnalyzer().analisar(request)
    symbols = [
        item
        for item in extracted.evidencias
        if dict(item.atributos_extraidos).get("reconhecido_por_simbologia") is True
    ]
    assert len(symbols) == 1
    assert dict(symbols[0].atributos_extraidos).get("situacao_projeto_forcada") is None
    registry = carregar_registro_regras_inicial()
    interpreted = InterpretadorRegrasExplicitas(registry).interpretar(
        SolicitacaoInterpretacao(
            projeto_id=request.projeto_id,
            execucao_id=uuid4(),
            execucao_extracao_id=request.execucao_id,
            catalogo=catalogo_inicial,
            evidencias=extracted.evidencias,
            registro=registry,
        )
    )

    assert not interpreted.diagnosticos
    assert len(interpreted.elementos) == 1
    proposal = interpreted.elementos[0]
    assert proposal.estado_revisao is EstadoRevisao.CONFLITANTE
    assert proposal.tipo_catalogo_sugerido_id is None
    promoted = promover_resultado_automatico(
        Projeto(
            id=request.projeto_id,
            nome="E04 monochrome",
            catalogo_versao_id=catalogo_inicial.id,
            criado_em=request.criada_em,
            documentos=(request.documento,),
        ),
        catalogo_inicial,
        interpreted.elementos,
        interpreted.relacoes,
        promovido_em=request.criada_em,
    )
    assert promoted.projeto.elementos == ()
    assert promoted.decisoes == ()
    assert promoted.elementos[0].estado_revisao is not EstadoRevisao.CONFIRMADA


@pytest.mark.parametrize("negative", ("fence", "table", "incomplete_ground", "body_only"))
def test_e04_vector_negative_controls_do_not_create_equipment(negative: str) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        shape = page.new_shape()
        if negative == "fence":
            shape.draw_line((60, 100), (90, 100))
            for x in (60, 70, 80, 90):
                shape.draw_line((x, 95), (x, 105))
        elif negative == "table":
            shape.draw_rect(pymupdf.Rect(60, 90, 100, 110))
            for x in (70, 80, 90):
                shape.draw_line((x, 90), (x, 110))
            shape.draw_line((60, 100), (100, 100))
        elif negative == "incomplete_ground":
            shape.draw_line((60, 100), (75, 100))
            shape.draw_line((75, 95), (75, 105))
            shape.draw_line((79, 96.5), (79, 103.5))
        else:
            shape.draw_rect(pymupdf.Rect(75, 98.5, 84, 101.5))
            shape.draw_line((75, 96.5), (84, 103.5))
        shape.finish(color=(0, 0.5, 0), closePath=False)
        shape.commit()

        assert _extract_symbolic_equipment(page, 1) == ()


def test_e04_grouped_symbol_retains_drawing_and_item_provenance() -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        expected = _draw_e04_symbol(page, kind="ATERRAMENTO", origin=(80, 90), packing="grouped")

        symbols = _extract_symbolic_equipment(page, 1)

        assert len(symbols) == 1
        attributes = dict(symbols[0].atributos_extraidos)
        assert attributes["vetores_origem"] == "0"
        assert json.loads(str(attributes["primitives_origem"])) == [[0, i] for i in range(4)]
        xs, ys = zip(*expected, strict=True)
        assert json.loads(str(attributes["simbolo_limites_originais"])) == pytest.approx(
            (min(xs), min(ys), max(xs), max(ys)), abs=0.001
        )


@pytest.mark.parametrize("removed", ("grouping", "fragments", "scale", "styles"))
def test_e04_normalization_ablation_changes_only_the_requested_control(removed: str) -> None:
    normalizations = frozenset({"grouping", "fragments", "scale", "styles"})
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        _draw_e04_symbol(
            page,
            kind="ATERRAMENTO",
            origin=(120, 120),
            packing={"grouping": "grouped", "fragments": "fragmented"}.get(removed, "separate"),
            scale=0.3 if removed == "scale" else 1.0,
            color=(0.4, 0.4, 0.4) if removed == "styles" else (0, 0.5, 0),
        )

        full = _extract_symbolic_equipment(page, 1)
        explicit_full = _extract_symbolic_equipment(page, 1, normalizations=normalizations)
        ablated = _extract_symbolic_equipment(page, 1, normalizations=normalizations - {removed})

        assert full == explicit_full
        assert len(full) == 1
        assert ablated == ()


def test_e04_failed_symbol_extraction_is_retried_before_caching_complete_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "retry-symbol.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        _draw_e04_symbol(page, kind="ATERRAMENTO", origin=(80, 90))
        document.save(path)
    request = replace(
        _request(path),
        configuracao=ConfiguracaoAnaliseDocumento(habilitar_ocr_condicional=False),
    )
    extract = _extract_symbolic_equipment
    calls = 0

    def fail_once(page: pymupdf.Page, page_number: int) -> tuple[CandidatoEvidenciaDocumento, ...]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("Não foi possível preservar índices vetoriais da camada base")
        return extract(page, page_number)

    monkeypatch.setattr(analyzer_module, "_extract_symbolic_equipment", fail_once)
    analyzer = PyMuPdfDocumentAnalyzer(cache=JsonAnalysisCache(tmp_path / "cache"))
    failed = analyzer.analisar(request)
    recovered = analyzer.analisar(request)
    cached = analyzer.analisar(request)

    assert any(item.codigo == "analise.simbolos_vetoriais_falhou" for item in failed.diagnosticos)
    assert not failed.cache_utilizado
    assert not recovered.cache_utilizado
    assert calls == 2
    assert not recovered.diagnosticos
    assert any(item.conteudo_bruto == "ATERRAMENTO" for item in recovered.evidencias)
    assert cached.cache_utilizado
    assert cached.evidencias == recovered.evidencias


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


def test_conditional_ocr_preserves_partial_candidates_and_diagnostic_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request = replace(
        _request(create_analysis_pdf(tmp_path / "conditional-characterization.pdf")),
        configuracao=ConfiguracaoAnaliseDocumento(minimo_vetores_para_ocr=1),
    )

    def candidate(key: str, text: str, x: str) -> CandidatoEvidenciaDocumento:
        return CandidatoEvidenciaDocumento(
            chave_estavel=key,
            pagina_numero=3,
            tipo=TipoEvidencia.OCR,
            geometria=GeometriaNormalizada(
                tipo=TipoGeometria.CAIXA,
                pontos=(
                    PontoNormalizado(Decimal(x), Decimal("0.20")),
                    PontoNormalizado(Decimal(x) + Decimal("0.10"), Decimal("0.30")),
                ),
            ),
            origem_pdf=OrigemObjetoPdf(),
            conteudo_bruto=text,
            atributos_extraidos=(("motor_ocr", key),),
        )

    general = candidate("geral", "TEXTO GERAL", "0.10")
    linear = candidate("linear", "V1-2", "0.60")

    def general_candidates(
        *_args: object,
        **_kwargs: object,
    ) -> tuple[CandidatoEvidenciaDocumento, ...]:
        return (general,)

    def fail(*_args: object, **_kwargs: object) -> tuple[CandidatoEvidenciaDocumento, ...]:
        raise RuntimeError("falha caracterizada")

    def linear_candidates(
        *_args: object,
        **_kwargs: object,
    ) -> tuple[CandidatoEvidenciaDocumento, ...]:
        return (linear,)

    monkeypatch.setattr(ocr_module, "_extract_ocr_tiled", general_candidates)
    monkeypatch.setattr(ocr_module, "extract_vector_glyphs", lambda *_args: ((), ()))
    monkeypatch.setattr(ocr_module, "_extract_point_identifiers", fail)
    monkeypatch.setattr(ocr_module, "_extract_blue_operational_identifiers", linear_candidates)
    monkeypatch.setattr(ocr_module, "_extract_linear_operational_labels", fail)
    monkeypatch.setattr(ocr_module, "_extract_marked_equipment_labels", fail)

    candidates, diagnostics = ocr_module._conditional_ocr(
        object(),
        3,
        request,
        CharacterizationOcr(),
        native_characters=100,
        image_coverage=Decimal(0),
        vector_count=1,
        image_candidates=(),
    )

    assert [item.chave_estavel for item in candidates] == ["geral", "linear"]
    assert [item.codigo for item in diagnostics] == [
        "analise.ocr_identificadores_falhou",
        "analise.ocr_rotulos_lineares_falhou",
        "analise.ocr_equipamentos_marcados_falhou",
    ]
    assert [item.extrator for item in diagnostics] == [
        "ocr-identificadores",
        "ocr-rotulos-lineares",
        "ocr-equipamentos-marcados",
    ]
    assert all(item.pagina_numero == 3 for item in diagnostics)


def test_conditional_ocr_general_failure_short_circuits_targeted_extraction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request = replace(
        _request(create_analysis_pdf(tmp_path / "conditional-failure.pdf")),
        configuracao=ConfiguracaoAnaliseDocumento(minimo_vetores_para_ocr=1),
    )
    targeted_calls = 0

    def fail_general(
        *_args: object,
        **_kwargs: object,
    ) -> tuple[CandidatoEvidenciaDocumento, ...]:
        raise RuntimeError("falha geral")

    def targeted(
        *_args: object,
        **_kwargs: object,
    ) -> tuple[CandidatoEvidenciaDocumento, ...]:
        nonlocal targeted_calls
        targeted_calls += 1
        return ()

    monkeypatch.setattr(ocr_module, "_extract_ocr_tiled", fail_general)
    monkeypatch.setattr(ocr_module, "_extract_point_identifiers", targeted)

    candidates, diagnostics = ocr_module._conditional_ocr(
        object(),
        7,
        request,
        CharacterizationOcr(),
        native_characters=100,
        image_coverage=Decimal(0),
        vector_count=1,
        image_candidates=(),
    )

    assert candidates == ()
    assert [item.codigo for item in diagnostics] == ["analise.ocr_falhou"]
    assert diagnostics[0].pagina_numero == 7
    assert targeted_calls == 0


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


def _draw_e04_symbol(
    page: pymupdf.Page,
    *,
    kind: str,
    origin: tuple[float, float],
    scale: float = 1.0,
    angle: float = 0.0,
    packing: str = "separate",
    filled: bool = False,
    color: tuple[float, float, float] = (0, 0.5, 0),
    oc: int = 0,
    bar_lengths: tuple[float, ...] | None = None,
    terminal_offset: float = 15.0,
    bar_gap: float = 4.0,
) -> tuple[tuple[float, float], ...]:
    """Independent authorial development controls; no benchmark reference is consumed."""
    theta = math.radians(angle)

    def transform(x: float, y: float) -> tuple[float, float]:
        return (
            origin[0] + scale * (x * math.cos(theta) - y * math.sin(theta)),
            origin[1] + scale * (x * math.sin(theta) + y * math.cos(theta)),
        )

    segments = [((0.0, 0.0), (15.0, 0.0))]
    rectangles = []
    if kind == "PARA RAIOS BT":
        rectangles.append((15.0, -1.5, 24.0, 1.5))
        segments.append(((15.0, -3.5), (24.0, 3.5)))
    else:
        lengths = bar_lengths or (
            (10.0, 7.0, 4.0, 7.0) if kind == "PARA RAIOS MT" else (10.0, 7.0, 4.0)
        )
        for index, length in enumerate(lengths):
            x = terminal_offset + index * bar_gap
            if filled:
                rectangles.append((x - 0.1, -length / 2, x + 0.1, length / 2))
            else:
                segments.append(((x, -length / 2), (x, length / 2)))
    points: list[tuple[float, float]] = []
    shape = page.new_shape()
    for start, end in segments:
        points.extend((transform(*start), transform(*end)))
        pairs = [(start, end)]
        if packing == "fragmented":
            middle = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
            pairs = [(start, middle), (middle, end)]
        for first, second in pairs:
            shape.draw_line(transform(*first), transform(*second))
            if packing != "grouped":
                shape.finish(color=color, width=0.5 * scale, closePath=False, oc=oc)
                shape.commit()
                shape = page.new_shape()
    for x0, y0, x1, y1 in rectangles:
        corners = (transform(x0, y0), transform(x1, y0), transform(x1, y1), transform(x0, y1))
        points.extend(corners)
        shape.draw_quad(pymupdf.Quad(corners[0], corners[1], corners[3], corners[2]))
        if packing != "grouped":
            shape.finish(
                color=None if filled else color,
                fill=color if filled else None,
                width=0.5 * scale,
                closePath=False,
                oc=oc,
            )
            shape.commit()
            shape = page.new_shape()
    if packing == "grouped":
        shape.finish(color=color, width=0.5 * scale, closePath=False, oc=oc)
        shape.commit()
    return tuple(points)


def _assert_e04_bounds(
    page: pymupdf.Page,
    symbol: CandidatoEvidenciaDocumento,
    source_points: tuple[tuple[float, float], ...],
) -> None:
    transformed = [pymupdf.Point(point) * page.rotation_matrix for point in source_points]
    expected = (
        min(point.x for point in transformed) / page.rect.width,
        min(point.y for point in transformed) / page.rect.height,
        max(point.x for point in transformed) / page.rect.width,
        max(point.y for point in transformed) / page.rect.height,
    )
    assert symbol.geometria.tipo is TipoGeometria.CAIXA
    actual = (
        min(float(point.x) for point in symbol.geometria.pontos),
        min(float(point.y) for point in symbol.geometria.pontos),
        max(float(point.x) for point in symbol.geometria.pontos),
        max(float(point.y) for point in symbol.geometria.pontos),
    )
    assert actual == pytest.approx(expected, abs=0.00001)


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
