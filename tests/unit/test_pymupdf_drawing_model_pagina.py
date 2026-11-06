# mypy: disable-error-code="no-untyped-call"
"""Página do modelo de desenho com o índice cru de `get_drawings` de cada caminho."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pymupdf
import pytest

from zeny_project_handler.adapters.analysis.drawing_model.model import Caminho, Ponto
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import (
    extrair_modelo_desenho,
    pagina_modelo_com_indices,
)

_TOLERANCIA = 1e-3


def _pdf_formas(caminho: Path) -> Path:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=200, height=200)
        forma = pagina.new_shape()
        forma.draw_line((10, 10), (100, 10))
        forma.finish(color=(1, 0, 0), width=1)
        forma.draw_rect(pymupdf.Rect(20, 20, 80, 60))
        forma.finish(color=(0, 0, 1), fill=(0, 1, 0))
        forma.draw_circle((60, 120), 20)
        forma.finish(color=(0, 0, 0))
        forma.commit()
        pagina.insert_text((30, 180), "POSTE")
        documento.save(caminho)
    return caminho


def _pdf_com_clip(caminho: Path, rotacao: int = 0) -> Path:
    """Página que mostra um recorte de outra: o Form XObject traz `clip` antes dos traços."""
    with pymupdf.open() as origem, pymupdf.open() as destino:
        base = origem.new_page(width=200, height=200)
        forma = base.new_shape()
        forma.draw_line((10, 10), (100, 10))
        forma.finish(color=(1, 0, 0), width=1)
        forma.draw_rect(pymupdf.Rect(20, 20, 80, 60))
        forma.finish(color=(0, 0, 1), fill=(0, 1, 0))
        forma.draw_circle((60, 120), 20)
        forma.finish(color=(0, 0, 0))
        forma.commit()
        pagina = destino.new_page(width=300, height=300)
        pagina.show_pdf_page(
            pymupdf.Rect(0, 0, 150, 150), origem, 0, clip=pymupdf.Rect(0, 0, 90, 90)
        )
        pagina.draw_line((200, 200), (250, 250))
        pagina.set_rotation(rotacao)
        destino.save(caminho)
    return caminho


def _pontos_crus(desenho: dict[str, Any], matriz: pymupdf.Matrix) -> list[Ponto]:
    pontos: list[pymupdf.Point] = []
    for item in desenho["items"]:
        if item[0] == "re":
            retangulo = pymupdf.Rect(item[1])
            pontos += [retangulo.tl, retangulo.tr, retangulo.br, retangulo.bl]
        elif item[0] == "qu":
            quadrilatero = pymupdf.Quad(item[1])
            pontos += [quadrilatero.ul, quadrilatero.ur, quadrilatero.lr, quadrilatero.ll]
        else:
            pontos += [pymupdf.Point(p) for p in item[1:]]
    return [
        (p.x * matriz.a + p.y * matriz.c + matriz.e, p.x * matriz.b + p.y * matriz.d + matriz.f)
        for p in pontos
    ]


def _pontos_do_caminho(caminho: Caminho) -> list[Ponto]:
    return [p for subcaminho in caminho.subcaminhos for item in subcaminho for p in item.pontos]


def _cobre(a: list[Ponto], b: list[Ponto]) -> bool:
    return all(
        any(abs(x - u) < _TOLERANCIA and abs(y - v) < _TOLERANCIA for u, v in b) for x, y in a
    )


def _caixa(pontos: list[Ponto]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in pontos]
    ys = [p[1] for p in pontos]
    return (min(xs), min(ys), max(xs), max(ys))


def test_pagina_modelo_igual_a_extracao_do_documento(tmp_path: Path) -> None:
    pdf = _pdf_formas(tmp_path / "formas.pdf")

    with pymupdf.open(pdf) as documento:
        modelo, indices = pagina_modelo_com_indices(documento[0], 0)

    assert modelo == extrair_modelo_desenho(pdf).paginas[0]
    assert modelo.caminhos
    assert modelo.textos
    assert len(indices) == len(modelo.caminhos)


@pytest.mark.parametrize("rotacao", [0, 90])
def test_indices_crus_apontam_para_o_desenho_de_origem(tmp_path: Path, rotacao: int) -> None:
    pdf = _pdf_com_clip(tmp_path / "clip.pdf", rotacao)

    with pymupdf.open(pdf) as documento:
        pagina = documento[0]
        crus = pagina.get_drawings(extended=True)
        modelo, indices = pagina_modelo_com_indices(pagina, 0)
        matriz = pagina.rotation_matrix

    tipos = [desenho["type"] for desenho in crus]
    assert {"clip", "group"} & set(tipos)
    assert modelo.caminhos
    assert len(indices) == len(modelo.caminhos)
    assert len(set(indices)) == len(indices)
    for caminho, indice in zip(modelo.caminhos, indices, strict=True):
        desenho = crus[indice]
        assert desenho["type"] in {"s", "f", "fs"}
        esperados = _pontos_crus(desenho, matriz)
        obtidos = _pontos_do_caminho(caminho)
        assert _cobre(esperados, obtidos)
        assert _cobre(obtidos, esperados)
        caixa_cruzada = _caixa(_pontos_crus({"items": [("re", desenho["rect"])]}, matriz))
        assert _caixa(obtidos) == pytest.approx(caixa_cruzada, abs=_TOLERANCIA)


def test_indices_nao_coincidem_com_a_ordem_do_caminho_quando_ha_clip(tmp_path: Path) -> None:
    pdf = _pdf_com_clip(tmp_path / "clip.pdf")

    with pymupdf.open(pdf) as documento:
        _, indices = pagina_modelo_com_indices(documento[0], 0)

    assert indices != tuple(range(len(indices)))


def test_pagina_sem_desenhos(tmp_path: Path) -> None:
    pdf = tmp_path / "vazio.pdf"
    with pymupdf.open() as documento:
        documento.new_page(width=100, height=100)
        documento.save(pdf)

    with pymupdf.open(pdf) as documento:
        modelo, indices = pagina_modelo_com_indices(documento[0], 0)

    assert indices == ()
    assert modelo == extrair_modelo_desenho(pdf).paginas[0]
    assert modelo.caminhos == ()


def test_get_drawings_chamado_uma_vez(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = _pdf_com_clip(tmp_path / "clip.pdf")
    chamadas: list[bool] = []
    original = pymupdf.Page.get_drawings

    def contado(self: pymupdf.Page, *args: Any, **kwargs: Any) -> Any:
        chamadas.append(True)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pymupdf.Page, "get_drawings", contado)

    with pymupdf.open(pdf) as documento:
        pagina_modelo_com_indices(documento[0], 0)

    assert len(chamadas) == 1
