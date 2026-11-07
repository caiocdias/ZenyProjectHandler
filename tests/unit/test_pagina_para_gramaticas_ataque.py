# mypy: disable-error-code="no-untyped-call"
"""Ataque a `pagina_para_gramaticas`: alinhamento de índice cru e translucidos sob clip, grupo,
descarte e rotação."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from tests.unit.test_pagina_para_gramaticas import _com_desenhos, _desenho_retangulo
from tests.unit.test_pymupdf_drawing_model_pagina import _pdf_com_clip

from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import (
    extrair_modelo_desenho,
    pagina_modelo_com_indices,
    pagina_para_gramaticas,
)


def _pdf_clip_e_translucidos(caminho: Path, rotacao: int = 0) -> Path:
    """Recorte (clip) de outra página, depois um retângulo translúcido e um opaco."""
    _pdf_com_clip(caminho, rotacao=0)
    with pymupdf.open(caminho) as documento:
        pagina = documento[0]
        pagina.draw_rect(pymupdf.Rect(160, 160, 200, 200), fill=(1, 0, 0), fill_opacity=0.4)
        pagina.draw_rect(pymupdf.Rect(210, 160, 250, 200), fill=(0, 1, 0), fill_opacity=1.0)
        pagina.draw_rect(pymupdf.Rect(160, 210, 200, 250), fill=(0, 0, 1), fill_opacity=0.2)
        pagina.set_rotation(rotacao)
        documento.save(caminho.with_name("r" + caminho.name))
    return caminho.with_name("r" + caminho.name)


@pytest.mark.parametrize("rotacao", [0, 90, 180, 270], ids=lambda r: f"rot{r}")
def test_translucidos_e_indices_alinhados_sob_clip_e_rotacao(tmp_path: Path, rotacao: int) -> None:
    pdf = _pdf_clip_e_translucidos(tmp_path / "c.pdf", rotacao)

    with pymupdf.open(pdf) as documento:
        pagina = documento[0]
        obtida = pagina_para_gramaticas(pagina, 0)
        cru = pagina.get_drawings(extended=True)
        esperado = pagina_modelo_com_indices(pagina, 0)

    assert (obtida.modelo, obtida.indices_crus) == esperado
    translucidos_reais = {
        posicao
        for posicao, indice in enumerate(obtida.indices_crus)
        if (cru[indice].get("fill_opacity") or 1.0) < 0.99
    }
    assert len(translucidos_reais) == 2
    assert obtida.translucidos == translucidos_reais
    for posicao, indice in enumerate(obtida.indices_crus):
        assert cru[indice]["type"] in {"s", "f", "fs"}, posicao


def test_clip_no_cru_desloca_indice_e_translucidos_seguem_o_desenho_certo(tmp_path: Path) -> None:
    pdf = _pdf_clip_e_translucidos(tmp_path / "c.pdf")

    with pymupdf.open(pdf) as documento:
        pagina = pagina_para_gramaticas(documento[0], 0)
        tipos = [d["type"] for d in documento[0].get_drawings(extended=True)]

    assert "clip" in tipos
    # o índice cru conta as entradas clip/group; a posição em caminhos não
    assert max(pagina.indices_crus) >= len(pagina.modelo.caminhos)
    assert all(p < len(pagina.modelo.caminhos) for p in pagina.translucidos)


@pytest.mark.parametrize("rotacao", [0, 90, 180, 270], ids=lambda r: f"rot{r}")
def test_modelo_igual_ao_de_extrair_modelo_desenho_sob_clip_e_rotacao(
    tmp_path: Path, rotacao: int
) -> None:
    pdf = _pdf_clip_e_translucidos(tmp_path / "c.pdf", rotacao)

    with pymupdf.open(pdf) as documento:
        pagina = pagina_para_gramaticas(documento[0], 0)

    assert pagina.modelo == extrair_modelo_desenho(pdf).paginas[0]


def test_varios_descartados_intercalados_mantem_alinhamento(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def ruim() -> dict[str, Any]:
        d = _desenho_retangulo(0, 0.1)
        d["items"] = [("l", pymupdf.Point(math.inf, 0.0), pymupdf.Point(1.0, 1.0))]
        return d

    clip = {"type": "clip", "items": [], "rect": pymupdf.Rect(0, 0, 1, 1), "level": 0}
    desenhos = [
        ruim(),
        clip,
        _desenho_retangulo(10, 1.0),
        ruim(),
        {"type": "group", "items": [], "rect": pymupdf.Rect(0, 0, 1, 1)},
        _desenho_retangulo(40, 0.5),
        ruim(),
        _desenho_retangulo(70, 0.3),
        _desenho_retangulo(100, 1.0),
    ]
    pdf = _com_desenhos(tmp_path, monkeypatch, desenhos)

    with pymupdf.open(pdf) as documento:
        pagina = pagina_para_gramaticas(documento[0], 0)

    assert pagina.indices_crus == (2, 5, 7, 8)
    assert pagina.translucidos == {1, 2}


@pytest.mark.parametrize(
    "opacidade",
    [math.inf, -math.inf, [0.5], {"a": 1}, b"0.1"],
    ids=["inf", "menos_inf", "lista", "dict", "bytes"],
)
def test_opacidade_nao_numerica_ou_infinita_nao_marca_nem_levanta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, opacidade: Any
) -> None:
    pdf = _com_desenhos(tmp_path, monkeypatch, [_desenho_retangulo(10, opacidade)])

    with pymupdf.open(pdf) as documento:
        pagina = pagina_para_gramaticas(documento[0], 0)

    assert len(pagina.modelo.caminhos) == 1
    assert pagina.translucidos == frozenset()


def test_opacidade_inteira_zero_vale_como_translucida(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _com_desenhos(tmp_path, monkeypatch, [_desenho_retangulo(10, 0)])

    with pymupdf.open(pdf) as documento:
        pagina = pagina_para_gramaticas(documento[0], 0)

    assert pagina.translucidos == {0}


def test_pagina_sem_desenhos_traz_tudo_vazio_e_consistente(tmp_path: Path) -> None:
    pdf = tmp_path / "vazia.pdf"
    with pymupdf.open() as documento:
        documento.new_page(width=100, height=100)
        documento.save(pdf)

    with pymupdf.open(pdf) as documento:
        pagina = pagina_para_gramaticas(documento[0], 3)

    assert pagina.modelo.caminhos == ()
    assert pagina.indices_crus == ()
    assert pagina.translucidos == frozenset()
    assert pagina.modelo.diagnosticos == ()
    assert pagina.modelo.indice == 3


def test_pagina_so_com_clip_nao_gera_caminhos_nem_indices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clip = {"type": "clip", "items": [], "rect": pymupdf.Rect(0, 0, 1, 1), "level": 0}
    pdf = _com_desenhos(tmp_path, monkeypatch, [clip, clip])

    with pymupdf.open(pdf) as documento:
        pagina = pagina_para_gramaticas(documento[0], 0)

    assert (pagina.indices_crus, pagina.translucidos) == ((), frozenset())
    assert pagina.modelo.diagnosticos == ()


def test_so_desenhos_descartados_nao_levanta_e_fica_vazio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _desenho_retangulo(0, 0.1)
    d["items"] = [("l", pymupdf.Point(math.nan, 0.0), pymupdf.Point(1.0, 1.0))]
    pdf = _com_desenhos(tmp_path, monkeypatch, [d])

    with pymupdf.open(pdf) as documento:
        pagina = pagina_para_gramaticas(documento[0], 0)

    assert (pagina.modelo.caminhos, pagina.indices_crus, pagina.translucidos) == (
        (),
        (),
        frozenset(),
    )


def test_nao_fecha_nem_consome_a_pagina_do_chamador(tmp_path: Path) -> None:
    pdf = _pdf_clip_e_translucidos(tmp_path / "c.pdf")

    with pymupdf.open(pdf) as documento:
        primeira = pagina_para_gramaticas(documento[0], 0)
        segunda = pagina_para_gramaticas(documento[0], 0)
        assert not documento.is_closed

    assert primeira == segunda
