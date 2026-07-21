from decimal import Decimal
from uuid import uuid4

import pytest

from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import TipoGeometria
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.values import (
    CaixaPagina,
    CoordenadaCampo,
    GeometriaDocumento,
    PontoNormalizado,
    decimal_value,
)


def page() -> PaginaDocumento:
    media_box = CaixaPagina(Decimal("0"), Decimal("0"), Decimal("595"), Decimal("842"))
    return PaginaDocumento(
        id=uuid4(),
        numero=1,
        largura_pontos=Decimal("595"),
        altura_pontos=Decimal("842"),
        rotacao_graus=0,
        media_box=media_box,
        crop_box=media_box,
    )


def test_geometry_supports_point_box_polyline_and_polygon() -> None:
    page_id = uuid4()
    first = PontoNormalizado(Decimal("0.1"), Decimal("0.2"))
    second = PontoNormalizado(Decimal("0.8"), Decimal("0.9"))

    assert GeometriaDocumento.ponto(page_id, first).tipo is TipoGeometria.PONTO
    assert GeometriaDocumento.caixa(page_id, first, second).pontos == (first, second)
    assert GeometriaDocumento.polilinha(page_id, (first, second)).tipo is TipoGeometria.POLILINHA
    third = PontoNormalizado(Decimal("0.2"), Decimal("0.8"))
    assert (
        GeometriaDocumento.poligono(page_id, (first, second, third)).tipo is TipoGeometria.POLIGONO
    )


@pytest.mark.parametrize(
    ("x", "y"),
    [("-0.01", "0"), ("1.01", "0"), ("0", "-0.01"), ("0", "1.01")],
)
def test_normalized_point_rejects_coordinates_outside_page(x: str, y: str) -> None:
    with pytest.raises(DomainValidationError, match="entre 0 e 1"):
        PontoNormalizado(Decimal(x), Decimal(y))


def test_geometry_rejects_invalid_shapes() -> None:
    page_id = uuid4()
    point = PontoNormalizado(Decimal("0.5"), Decimal("0.5"))

    with pytest.raises(DomainValidationError, match="área positiva"):
        GeometriaDocumento.caixa(page_id, point, point)
    with pytest.raises(DomainValidationError, match="ao menos dois"):
        GeometriaDocumento.polilinha(page_id, (point,))
    with pytest.raises(DomainValidationError, match="consecutivos repetidos"):
        GeometriaDocumento.polilinha(page_id, (point, point))
    with pytest.raises(DomainValidationError, match="três pontos distintos"):
        GeometriaDocumento.poligono(page_id, (point, point, point))


def test_page_and_document_preserve_pdf_metadata() -> None:
    document_page = page()
    document = DocumentoProjeto(
        id=uuid4(),
        nome_arquivo="projeto.pdf",
        sha256="A" * 64,
        paginas=(document_page,),
        tamanho_bytes=552857,
        versao_pdf=" 1.7 ",
        produtor=" AutoCAD ",
    )

    assert document.sha256 == "a" * 64
    assert document.paginas[0].media_box.largura == Decimal("595")
    assert document.paginas[0].media_box.altura == Decimal("842")
    assert document.versao_pdf == "1.7"
    assert document.produtor == "AutoCAD"


def test_page_rejects_incomplete_coordinate_matrix() -> None:
    box = CaixaPagina(Decimal(0), Decimal(0), Decimal(100), Decimal(100))
    with pytest.raises(DomainValidationError, match="seis coeficientes"):
        PaginaDocumento(
            id=uuid4(),
            numero=1,
            largura_pontos=Decimal(100),
            altura_pontos=Decimal(100),
            rotacao_graus=0,
            media_box=box,
            crop_box=box,
            matriz_pdf_para_pagina=(Decimal(1),),
        )


def test_field_coordinate_preserves_reference_without_guessing_it() -> None:
    coordinate = CoordenadaCampo(
        leste=Decimal("397617"),
        norte=Decimal("7725802"),
        sistema_referencia=" SIRGAS 2000 ",
        zona=" 23K ",
    )

    assert coordinate.leste == Decimal("397617")
    assert coordinate.sistema_referencia == "SIRGAS 2000"
    assert coordinate.zona == "23K"


def test_document_rejects_invalid_file_hash_and_page_sequence() -> None:
    first_page = page()
    second_page = PaginaDocumento(
        id=uuid4(),
        numero=3,
        largura_pontos=first_page.largura_pontos,
        altura_pontos=first_page.altura_pontos,
        rotacao_graus=90,
        media_box=first_page.media_box,
        crop_box=first_page.crop_box,
    )

    with pytest.raises(DomainValidationError, match="nome de um PDF"):
        DocumentoProjeto(
            id=uuid4(), nome_arquivo="C:/projeto.pdf", sha256="a" * 64, paginas=(first_page,)
        )
    with pytest.raises(DomainValidationError, match="64 caracteres"):
        DocumentoProjeto(
            id=uuid4(), nome_arquivo="projeto.pdf", sha256="inválido", paginas=(first_page,)
        )
    with pytest.raises(DomainValidationError, match="sem lacunas"):
        DocumentoProjeto(
            id=uuid4(),
            nome_arquivo="projeto.pdf",
            sha256="a" * 64,
            paginas=(first_page, second_page),
        )
    with pytest.raises(DomainValidationError, match="Tamanho do PDF"):
        DocumentoProjeto(
            id=uuid4(),
            nome_arquivo="projeto.pdf",
            sha256="a" * 64,
            paginas=(first_page,),
            tamanho_bytes=0,
        )


def test_numeric_value_rejects_boolean_and_non_finite_value() -> None:
    with pytest.raises(DomainValidationError, match="numérico"):
        decimal_value(True, field_name="valor")
    with pytest.raises(DomainValidationError, match="finito"):
        decimal_value("NaN", field_name="valor")
