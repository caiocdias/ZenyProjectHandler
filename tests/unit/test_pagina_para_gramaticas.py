# mypy: disable-error-code="no-untyped-call"
"""Página para as gramáticas a partir da página aberta: índice cru e caminhos translúcidos."""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from tests.fixtures.glyphs.fonte_livre import LinhaTexto, pdf_texto_contorno, tabela_do_alfabeto
from tests.unit.test_pymupdf_drawing_model_pagina import _pdf_com_clip

from zeny_project_handler.adapters.analysis import pymupdf_drawing_model
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import TabelaGlifos
from zeny_project_handler.adapters.analysis.drawing_model.glyph_text import (
    LeituraGlifos,
    ler_texto_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import PaginaGramatica
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import (
    _DesenhosFiltrados,
    extrair_modelo_desenho,
    pagina_modelo_com_indices,
    pagina_para_gramaticas,
)


def _pdf_retangulos(caminho: Path, opacidades: list[float]) -> Path:
    """Uma página com um retângulo preenchido por opacidade, depois de um `clip`."""
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=200, height=200)
        pagina.draw_rect(pymupdf.Rect(0, 0, 150, 150), color=None, fill=None)
        for indice, opacidade in enumerate(opacidades):
            deslocamento = 10 + 30 * indice
            pagina.draw_rect(
                pymupdf.Rect(deslocamento, 10, deslocamento + 20, 40),
                fill=(0, 0, 1),
                fill_opacity=opacidade,
            )
        documento.save(caminho)
    return caminho


def _desenho_retangulo(x: float, opacidade: Any) -> dict[str, Any]:
    return {
        "type": "f",
        "items": [("re", pymupdf.Rect(x, 10, x + 20, 40), 1)],
        "fill": (0.0, 0.0, 1.0),
        "color": None,
        "fill_opacity": opacidade,
        "stroke_opacity": 1.0,
        "width": 0.0,
        "closePath": True,
        "even_odd": False,
        "rect": pymupdf.Rect(x, 10, x + 20, 40),
        "layer": "",
    }


def _com_desenhos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, desenhos: list[dict[str, Any]]
) -> Path:
    pdf = tmp_path / "vazio.pdf"
    with pymupdf.open() as documento:
        documento.new_page(width=200, height=200)
        documento.save(pdf)
    monkeypatch.setattr(pymupdf.Page, "get_drawings", lambda _pagina, extended=False: desenhos)
    return pdf


def test_indices_crus_alinhados_com_clip_e_grupo(tmp_path: Path) -> None:
    pdf = _pdf_com_clip(tmp_path / "clip.pdf")

    with pymupdf.open(pdf) as documento:
        pagina = documento[0]
        esperado = pagina_modelo_com_indices(pagina, 0)
        obtida = pagina_para_gramaticas(pagina, 0)

    assert isinstance(obtida, PaginaGramatica)
    assert (obtida.modelo, obtida.indices_crus) == esperado
    assert obtida.indices_crus and obtida.indices_crus[0] > 0


def test_translucido_marcado_pela_posicao_no_caminho(tmp_path: Path) -> None:
    pdf = _pdf_retangulos(tmp_path / "t.pdf", [1.0, 0.5, 1.0])

    with pymupdf.open(pdf) as documento:
        pagina = pagina_para_gramaticas(documento[0], 0)

    posicoes = [
        posicao
        for posicao, caminho in enumerate(pagina.modelo.caminhos)
        if caminho.estilo.preenchimento is not None
    ]
    assert len(posicoes) == 3
    assert pagina.translucidos == {posicoes[1]}


def test_opacidade_limite_099_vale_como_opaca(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desenhos = [_desenho_retangulo(10, 0.99), _desenho_retangulo(40, 0.98)]
    pdf = _com_desenhos(tmp_path, monkeypatch, desenhos)

    with pymupdf.open(pdf) as documento:
        pagina = pagina_para_gramaticas(documento[0], 0)

    assert pagina.translucidos == {1}


@pytest.mark.parametrize("invalida", [None, float("nan"), "x"], ids=["none", "nan", "texto"])
def test_opacidade_invalida_vale_como_opaca(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalida: Any
) -> None:
    pdf = _com_desenhos(tmp_path, monkeypatch, [_desenho_retangulo(10, invalida)])

    with pymupdf.open(pdf) as documento:
        pagina = pagina_para_gramaticas(documento[0], 0)

    assert len(pagina.modelo.caminhos) == 1
    assert pagina.translucidos == frozenset()


def test_desenho_descartado_nao_desalinha_translucidos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    malformado = _desenho_retangulo(10, 1.0)
    malformado["items"] = [("l", pymupdf.Point(math.nan, 0.0), pymupdf.Point(1.0, 1.0))]
    desenhos = [malformado, _desenho_retangulo(40, 0.5)]
    pdf = _com_desenhos(tmp_path, monkeypatch, desenhos)

    with pymupdf.open(pdf) as documento:
        pagina = pagina_para_gramaticas(documento[0], 0)

    assert len(pagina.modelo.caminhos) == 1
    assert pagina.translucidos == {0}
    assert pagina.indices_crus == (1,)


def test_modelo_igual_ao_de_extrair_modelo_desenho(tmp_path: Path) -> None:
    pdf = _pdf_retangulos(tmp_path / "m.pdf", [1.0, 0.5])

    with pymupdf.open(pdf) as documento:
        pagina = pagina_para_gramaticas(documento[0], 0)

    assert pagina.modelo == extrair_modelo_desenho(pdf).paginas[0]


@pytest.fixture(scope="module")
def tabela(tmp_path_factory: pytest.TempPathFactory) -> TabelaGlifos:
    return tabela_do_alfabeto(tmp_path_factory.mktemp("alfabeto"))


def _pdf_rotulo_e_moldura(tmp_path: Path) -> Path:
    """`CT` em contorno (caminhos 0 e 1) e, depois, uma moldura de traço (caminho 2)."""
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("CT", (100.0, 100.0), 5.0)])
    with pymupdf.open(contorno) as documento:
        documento[0].draw_rect(pymupdf.Rect(97, 93, 110, 103), color=(0.7, 0.0, 0.0))
        documento.save(tmp_path / "m.pdf")
    return tmp_path / "m.pdf"


def test_glifos_lidos_na_pagina(tmp_path: Path, tabela: TabelaGlifos) -> None:
    pdf = _pdf_rotulo_e_moldura(tmp_path)
    sem_t = replace(tabela, glifos=tuple(g for g in tabela.glifos if g.caractere != "T"))

    with pymupdf.open(pdf) as documento:
        lido = pagina_para_gramaticas(documento[0], 0, tabela)
        nao_lido = pagina_para_gramaticas(documento[0], 0, sem_t)

    assert [t.texto for t in lido.modelo.textos] == ["CT"]
    assert len(lido.modelo.caminhos) == 3
    assert lido.glifos_lidos == {0, 1}
    assert lido.modelo == extrair_modelo_desenho(pdf, tabela).paginas[0]
    # glifo não resolvido anula o texto: nenhum dos contornos conta como lido
    assert nao_lido.modelo.textos == ()
    assert len(nao_lido.modelo.caminhos) == 3
    assert nao_lido.glifos_lidos == frozenset()
    assert nao_lido.modelo == extrair_modelo_desenho(pdf, sem_t).paginas[0]


def test_sem_tabela_nao_ha_glifos_lidos(tmp_path: Path) -> None:
    pdf = _pdf_rotulo_e_moldura(tmp_path)

    with pymupdf.open(pdf) as documento:
        pagina = pagina_para_gramaticas(documento[0], 0)

    assert pagina.glifos_lidos == frozenset()


def test_glifos_lidos_sem_segunda_leitura(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf_rotulo_e_moldura(tmp_path)
    leituras: list[int] = []

    def contando(*argumentos: Any) -> LeituraGlifos:
        leituras.append(1)
        return ler_texto_glifos(*argumentos)

    monkeypatch.setattr(pymupdf_drawing_model, "ler_texto_glifos", contando)

    with pymupdf.open(pdf) as documento:
        pagina = pagina_para_gramaticas(documento[0], 0, tabela)

    assert pagina.glifos_lidos == {0, 1}
    assert len(leituras) == 1


def test_sem_fallback_de_indices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = _pdf_retangulos(tmp_path / "f.pdf", [1.0])
    original = pymupdf_drawing_model._desenhos
    monkeypatch.setattr(pymupdf_drawing_model, "_desenhos", lambda pagina: list(original(pagina)))

    with pymupdf.open(pdf) as documento:
        pagina = pagina_para_gramaticas(documento[0], 0)

    assert "modelo.caminhos_falhou" in pagina.modelo.diagnosticos
    assert pagina.modelo.caminhos == ()
    assert pagina.translucidos == frozenset()


def test_desenhos_filtrados_aceita_pares() -> None:
    assert _DesenhosFiltrados([(3, {"type": "f"})]).indices_crus == (3,)
