# mypy: disable-error-code="no-untyped-call"
"""Envelope legado preserva decisões, geometria e procedência sem calibrar score."""

from decimal import Decimal

import pymupdf
import pytest

from zeny_project_handler.adapters.analysis.legacy_symbols import (
    observar_simbolos_legados,
    perfil_simbolos_legados,
)
from zeny_project_handler.adapters.analysis.pymupdf_symbols import _extract_symbolic_equipment
from zeny_project_handler.adapters.persistence.domain_json import dumps_domain, loads_domain
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos
from zeny_project_handler.domain.symbols import ResultadoMetodoSimbolos


def _draw_ground(page: pymupdf.Page, *, filled: bool = False, oc: int = 0) -> None:
    page.draw_line((50, 60), (65, 60), color=(0, 0, 0), oc=oc)
    for index, length in enumerate((10, 7, 4)):
        x = 65 + index * 4
        if filled:
            page.draw_rect(
                pymupdf.Rect(x - 0.1, 60 - length / 2, x + 0.1, 60 + length / 2),
                color=None,
                fill=(0, 0, 0),
                oc=oc,
            )
        else:
            page.draw_line((x, 60 - length / 2), (x, 60 + length / 2), color=(0, 0, 0), oc=oc)


@pytest.mark.parametrize("filled", [False, True])
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_adapter_preserves_legacy_candidates_for_lines_bars_rotation_and_ocg(
    filled: bool,
    rotation: int,
) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=500, height=400)
        oc = document.add_ocg("Rede MT")
        _draw_ground(page, filled=filled, oc=oc)
        page.set_rotation(rotation)
        direct = _extract_symbolic_equipment(page, 1)
        result = observar_simbolos_legados(
            page, documento_id="teste", documento_sha256="a" * 64, pagina_numero=1
        )
        repeated = observar_simbolos_legados(
            page, documento_id="teste", documento_sha256="a" * 64, pagina_numero=1
        )
    restored = loads_domain(dumps_domain(result), ResultadoMetodoSimbolos)
    assert restored == result == repeated
    assert len(direct) == len(restored.observacoes) == 1
    legacy = direct[0]
    observation = restored.observacoes[0]
    assert observation.chave_legada == legacy.chave_estavel
    assert observation.conteudo_bruto == legacy.conteudo_bruto == "ATERRAMENTO"
    assert observation.atributos == legacy.atributos_extraidos
    assert (
        observation.alternativas[0].classe == dict(legacy.atributos_extraidos)["classe_equipamento"]
    )
    assert observation.situacao is None
    assert dict(legacy.atributos_extraidos).get("situacao_projeto_forcada") is None
    assert observation.geometria.tipo is legacy.geometria.tipo
    assert observation.geometria.pontos_normalizados == legacy.geometria.pontos
    assert observation.score_bruto == Decimal("0.88")
    assert observation.alternativas[0].score_bruto == Decimal("0.88")
    assert observation.fonte.camada == "base"
    assert {primitive.camada for primitive in observation.primitivas} == {"Rede MT"}
    assert {primitive.indice for primitive in observation.primitivas} == {"0", "1", "2", "3"}
    primitives = {primitive.indice: primitive for primitive in observation.primitivas}
    assert primitives["0"].pontos_originais == (
        (Decimal(50), Decimal(60)),
        (Decimal(65), Decimal(60)),
    )
    if not filled:
        assert primitives["1"].pontos_originais == (
            (Decimal(65), Decimal(55)),
            (Decimal(65), Decimal(65)),
        )
    assert observation.fonte.origem_pdf == legacy.origem_pdf
    assert not observation.geometria.normalizacao_limitada
    assert restored.coberturas[0].estado is EstadoMetodoSimbolos.CONCLUIDO
    assert restored.completo
    assert "procedencia-nao-comprovada" in restored.perfil.perfil_referencia
    assert dict(observation.atributos)["origem_simbologia"] == "SIMBOLOGIA.pdf"
    assert observation.modelo is None and observation.template is None
    a, b, c, d, e, f = observation.geometria.transformacao.normalizada_para_original
    original_x = {point[0] for point in observation.geometria.pontos_originais}
    original_y = {point[1] for point in observation.geometria.pontos_originais}
    for point in observation.geometria.pontos_normalizados:
        recovered = a * point.x + c * point.y + e, b * point.x + d * point.y + f
        assert min(abs(recovered[0] - coordinate) for coordinate in original_x) < Decimal("0.0001")
        assert min(abs(recovered[1] - coordinate) for coordinate in original_y) < Decimal("0.0001")
    points = observation.geometria.pontos_normalizados
    assert points[0].x < points[1].x and points[0].y < points[1].y


def test_adapter_identity_changes_when_source_page_or_document_changes() -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=500, height=400)
        _draw_ground(page)
        original = observar_simbolos_legados(
            page, documento_id="teste", documento_sha256="a" * 64, pagina_numero=1
        )
        variants = tuple(
            observar_simbolos_legados(
                page, documento_id=identifier, documento_sha256=digest, pagina_numero=number
            )
            for identifier, digest, number in (
                ("teste", "a" * 64, 2),
                ("teste", "b" * 64, 1),
                ("outro", "a" * 64, 1),
            )
        )
    assert len({original.observacoes[0].id, *(item.observacoes[0].id for item in variants)}) == 4
    assert all(item.perfil.assinatura() == original.perfil.assinatura() for item in variants)
    assert original.perfil == perfil_simbolos_legados()


@pytest.mark.parametrize("shape", ["blank", "ellipse", "curved_glyph", "angular_glyph"])
def test_legacy_negative_controls_remain_non_detection_without_negative_evidence(
    shape: str,
) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=500, height=400)
        if shape != "blank":
            page.draw_line((50, 60), (90, 60), color=(0, 0.5, 0))
            for x in (96, 99, 102, 105):
                if shape == "ellipse":
                    page.draw_oval(pymupdf.Rect(x, 57, x + 1, 63), color=None, fill=(0, 0.5, 0))
                elif shape == "curved_glyph":
                    page.draw_bezier(
                        (x, 57), (x + 1, 59), (x + 1, 61), (x, 63), color=None, fill=(0, 0.5, 0)
                    )
                else:
                    page.draw_polyline(
                        [(x, 57), (x + 1, 60), (x, 63)], color=None, fill=(0, 0.5, 0)
                    )
        result = observar_simbolos_legados(
            page, documento_id="negativo", documento_sha256="a" * 64, pagina_numero=1
        )
    assert result.observacoes == ()
    restored = loads_domain(dumps_domain(result), ResultadoMetodoSimbolos)
    assert restored.coberturas[0].estado is EstadoMetodoSimbolos.NAO_DETECCAO
    assert not restored.coberturas[0].estado.comprova_ausencia
    assert restored.completo


def test_adapter_abstains_when_crop_hides_required_symbol_primitives() -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=500, height=400)
        _draw_ground(page, filled=True)
        page.set_cropbox(pymupdf.Rect(70, 0, 500, 400))
        direct = _extract_symbolic_equipment(page, 1)
        result = observar_simbolos_legados(
            page, documento_id="crop", documento_sha256="a" * 64, pagina_numero=1
        )
    # E03 preserved the legacy off-page signature. E04 must not claim a visible
    # complete symbol when the crop hides its stem and two of the three bars.
    assert direct == ()
    assert result.observacoes == ()
    assert result.coberturas[0].estado is EstadoMetodoSimbolos.NAO_DETECCAO
    assert not result.coberturas[0].estado.comprova_ausencia
    assert loads_domain(dumps_domain(result), ResultadoMetodoSimbolos) == result


def test_e04_adapter_separates_occurrences_in_one_drawing_and_roundtrips() -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=500, height=400)
        shape = page.new_shape()
        for x in (50, 150):
            shape.draw_line((x, 60), (x + 15, 60))
            for index, length in enumerate((10, 7, 4)):
                bar_x = x + 15 + index * 4
                shape.draw_line((bar_x, 60 - length / 2), (bar_x, 60 + length / 2))
        shape.finish(color=(0, 0, 0), closePath=False)
        shape.commit()
        result = observar_simbolos_legados(
            page, documento_id="grouped", documento_sha256="b" * 64, pagina_numero=1
        )
        ablated = observar_simbolos_legados(
            page,
            documento_id="grouped",
            documento_sha256="b" * 64,
            pagina_numero=1,
            normalizations=frozenset(),
        )
    assert len(result.observacoes) == 2
    assert ablated.observacoes == ()
    assert ablated.coberturas[0].estado is EstadoMetodoSimbolos.NAO_DETECCAO
    assert ablated.perfil.assinatura() != result.perfil.assinatura()
    assert loads_domain(dumps_domain(result), ResultadoMetodoSimbolos) == result
    assert len({observation.id for observation in result.observacoes}) == 2
    observations = sorted(
        result.observacoes, key=lambda item: item.geometria.pontos_originais[0][0]
    )
    for observation, expected_x in zip(observations, (50, 150), strict=True):
        xs = [point[0] for point in observation.geometria.pontos_originais]
        assert min(xs) == expected_x
        assert max(xs) == expected_x + 23
        assert observation.situacao is None
        assert len(observation.primitivas) == 1
        primitive_xs = [point[0] for point in observation.primitivas[0].pontos_originais]
        assert min(primitive_xs) == expected_x
        assert max(primitive_xs) == expected_x + 23


def test_e04_profile_signatures_record_only_executed_normalizations() -> None:
    full = perfil_simbolos_legados()
    ablated = perfil_simbolos_legados(normalizations=frozenset({"styles"}))
    assert full.assinatura() != ablated.assinatura()
    assert dict(full.parametros)["maximum_primitive_length"] is None
    assert dict(ablated.parametros)["maximum_primitive_length"] == Decimal(60)
    assert dict(ablated.parametros)["normalizacoes_vetoriais"] == "styles"
    with pytest.raises(ValueError, match="Normalização"):
        perfil_simbolos_legados(normalizations=frozenset({"invented"}))
