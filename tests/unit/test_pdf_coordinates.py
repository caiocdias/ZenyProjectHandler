from decimal import Decimal
from uuid import uuid4

import pytest

from zeny_project_handler.adapters.pdf import (
    PontoPlano,
    TransformacaoAfin,
    TransformadorCoordenadasPagina,
)
from zeny_project_handler.domain.documents import PaginaDocumento
from zeny_project_handler.domain.values import CaixaPagina, PontoNormalizado


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("dpi", [72, 144, 300])
def test_coordinate_round_trip_for_pdf_pixels_and_scene(rotation: int, dpi: int) -> None:
    page = _page(rotation)
    transformer = TransformadorCoordenadasPagina(
        page,
        dpi=dpi,
        rotacao_adicional_graus=rotation,
    )
    normalized = PontoNormalizado(Decimal("0.23"), Decimal("0.67"))

    pdf_point = transformer.normalizado_para_pdf(normalized)
    assert transformer.pdf_para_normalizado(pdf_point) == normalized

    pixel = transformer.normalizado_para_pixel(normalized)
    pixel_round_trip = transformer.pixel_para_normalizado(pixel)
    assert float(pixel_round_trip.x) == pytest.approx(float(normalized.x))
    assert float(pixel_round_trip.y) == pytest.approx(float(normalized.y))

    scene = transformer.normalizado_para_cena(
        normalized,
        origem=PontoPlano(17, 31),
        escala=1.75,
    )
    scene_round_trip = transformer.cena_para_normalizado(
        scene,
        origem=PontoPlano(17, 31),
        escala=1.75,
    )
    assert float(scene_round_trip.x) == pytest.approx(float(normalized.x))
    assert float(scene_round_trip.y) == pytest.approx(float(normalized.y))


def test_recorded_affine_matrices_are_used_and_invertible() -> None:
    page = PaginaDocumento(
        id=uuid4(),
        numero=1,
        largura_pontos=Decimal(200),
        altura_pontos=Decimal(100),
        rotacao_graus=0,
        media_box=CaixaPagina(Decimal(0), Decimal(0), Decimal(200), Decimal(100)),
        crop_box=CaixaPagina(Decimal(0), Decimal(0), Decimal(200), Decimal(100)),
        matriz_pdf_para_pagina=(
            Decimal(1),
            Decimal(0),
            Decimal(0),
            Decimal(-1),
            Decimal(0),
            Decimal(100),
        ),
        matriz_rotacao_pagina=(
            Decimal(1),
            Decimal(0),
            Decimal(0),
            Decimal(1),
            Decimal(0),
            Decimal(0),
        ),
    )
    transformer = TransformadorCoordenadasPagina(page, dpi=72)

    normalized = transformer.pdf_para_normalizado(PontoPlano(50, 75))

    assert normalized == PontoNormalizado(Decimal("0.25"), Decimal("0.25"))
    assert transformer.normalizado_para_pdf(normalized) == PontoPlano(50, 75)


def test_coordinate_validation_and_affine_failure() -> None:
    page = _page(0)
    with pytest.raises(ValueError, match="DPI"):
        TransformadorCoordenadasPagina(page, dpi=0)
    with pytest.raises(ValueError, match="Rotação"):
        TransformadorCoordenadasPagina(page, dpi=72, rotacao_adicional_graus=45)
    with pytest.raises(ValueError, match="Dimensões"):
        TransformadorCoordenadasPagina(page, dpi=72, largura_pixels=-1)
    transformer = TransformadorCoordenadasPagina(page, dpi=72)
    with pytest.raises(ValueError, match="Escala"):
        transformer.normalizado_para_cena(PontoNormalizado(Decimal(0), Decimal(0)), escala=0)
    with pytest.raises(ValueError, match="página"):
        transformer.pixel_para_normalizado(PontoPlano(1000, 1000))
    with pytest.raises(ValueError, match="seis"):
        TransformacaoAfin.de_coeficientes((Decimal(1),))
    with pytest.raises(ValueError, match="inversível"):
        TransformacaoAfin(1, 0, 1, 0, 0, 0).inversa()


def _page(rotation: int) -> PaginaDocumento:
    width, height = (100, 200) if rotation in {90, 270} else (200, 100)
    return PaginaDocumento(
        id=uuid4(),
        numero=1,
        largura_pontos=Decimal(width),
        altura_pontos=Decimal(height),
        rotacao_graus=rotation,
        media_box=CaixaPagina(Decimal(0), Decimal(0), Decimal(200), Decimal(100)),
        crop_box=CaixaPagina(Decimal(0), Decimal(0), Decimal(200), Decimal(100)),
    )
