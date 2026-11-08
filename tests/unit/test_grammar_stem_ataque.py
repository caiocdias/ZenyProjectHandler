"""Ataque à gramática `stem_bars`: exclusividade, X, envolvente, componentes, pureza e orçamento."""

from __future__ import annotations

import ast
import math
from pathlib import Path
from typing import Any, Final

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.paginas import linha, pagina_gramatica
from tests.fixtures.symbol_grammars.stem_bars import (
    ALTERNADAS,
    CASOS_HASTE,
    CENTRO,
    DECRESCENTES,
    HASTE,
    LACUNA,
    PRETO,
    VERMELHO,
    desenhar_haste,
    desenhar_positivo,
    pagina_desenhada,
)

from zeny_project_handler.adapters.analysis.drawing_model import grammar_stem
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    PaginaGramatica,
    TetoGramaticasExcedido,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import (
    CasamentoGramatica,
    casar_variantes,
)

_V: Final = [variante for variante, _ in CASOS_HASTE]
_PARES: Final = [
    ({"family_id": "autoral"}, {"id": v, "recognition": {"status": "enabled", "grammar": g}})
    for v, g in CASOS_HASTE
]
_MEIO_X: Final = (CENTRO[0], CENTRO[1] - HASTE / 2 - LACUNA)


def _casa(pagina: PaginaGramatica) -> tuple[CasamentoGramatica, ...]:
    return casar_variantes(pagina, _PARES)


def _ids(pagina: PaginaGramatica) -> list[str]:
    return [str(c.variante["id"]) for c in _casa(pagina)]


def _x(pagina: pymupdf.Page, cor_a: Any, cor_b: Any, t: float = 7.2, desloc: float = 0.0) -> None:
    mx, my = _MEIO_X
    pagina.draw_line((mx - t, my - t), (mx + t, my + t), color=cor_a, width=0.5)
    pagina.draw_line((mx - t + desloc, my + t), (mx + t + desloc, my - t), color=cor_b, width=0.5)


def _com_haste_e(
    extra: Any, comprimentos: tuple[float, ...] = DECRESCENTES, **opcoes: Any
) -> PaginaGramatica:
    def desenhar(p: pymupdf.Page) -> None:
        desenhar_haste(p, comprimentos, **opcoes)
        extra(p)

    return pagina_desenhada(desenhar)


# --- quatro barras, três barras e sub-hastes -------------------------------------------------


def test_quatro_alternadas_com_a_ultima_barra_faltando_nao_casam() -> None:
    assert _ids(pagina_desenhada(lambda p: desenhar_haste(p, ALTERNADAS[:3]))) == []


def test_quatro_alternadas_com_x_nao_viram_aterramento_com_x() -> None:
    """Sub-haste: as 3 primeiras barras de um para-raios não podem ser lidas como aterramento."""
    pagina = pagina_desenhada(lambda p: desenhar_haste(p, ALTERNADAS, x=True))

    assert _ids(pagina) == ["cemig-eo-r3-s21-v008"]


def test_cinco_barras_nao_casam_como_para_raios() -> None:
    """Cinco barras decrescentes: o recorte do começo não pode fabricar quatro alternadas."""
    pagina = pagina_desenhada(lambda p: desenhar_haste(p, (9.0, 7.5, 6.0, 4.5, 3.0)))

    assert not any(v.startswith("cemig-eo-r3-s21") for v in _ids(pagina))


# --- o X: braço solto, cor e posição ----------------------------------------------------------


def test_x_de_mesma_cor_diferente_da_haste_e_marca_de_retirada() -> None:
    """A cor não decide nada: X preto, como a haste, ainda é a variante com X."""
    pagina = _com_haste_e(lambda p: _x(p, PRETO, PRETO))

    assert _ids(pagina) == ["cemig-eo-r3-s19-v004"]


def test_x_com_bracos_de_cores_diferentes_nao_e_marca_de_retirada() -> None:
    pagina = _com_haste_e(lambda p: _x(p, PRETO, VERMELHO))

    assert _ids(pagina) == ["cemig-eo-r3-s19-v001"]


def test_bracos_que_nao_se_cruzam_nao_sao_marca_de_retirada() -> None:
    pagina = _com_haste_e(lambda p: _x(p, VERMELHO, VERMELHO, desloc=12.0))

    assert _ids(pagina) == ["cemig-eo-r3-s19-v001"]


def test_x_da_rede_cruzando_perto_nao_e_marca_de_retirada() -> None:
    """Duas linhas longas da rede que se cruzam sobre o símbolo: braços longos demais."""
    pagina = _com_haste_e(lambda p: _x(p, VERMELHO, VERMELHO, t=60.0))

    assert _ids(pagina) == ["cemig-eo-r3-s19-v001"]


def test_bracos_de_x_de_tamanhos_muito_diferentes_nao_formam_x() -> None:
    def desigual(p: pymupdf.Page) -> None:
        mx, my = _MEIO_X
        p.draw_line((mx - 7.0, my - 7.0), (mx + 7.0, my + 7.0), color=VERMELHO, width=0.5)
        p.draw_line((mx - 3.0, my + 3.0), (mx + 3.0, my - 3.0), color=VERMELHO, width=0.5)

    assert _ids(_com_haste_e(desigual)) == ["cemig-eo-r3-s19-v001"]


def test_bracos_quase_paralelos_a_haste_nao_formam_x() -> None:
    def quase_verticais(p: pymupdf.Page) -> None:
        mx, my = _MEIO_X
        p.draw_line((mx - 1.5, my - 7.0), (mx + 1.5, my + 7.0), color=VERMELHO, width=0.5)
        p.draw_line((mx + 1.5, my - 7.0), (mx - 1.5, my + 7.0), color=VERMELHO, width=0.5)

    assert _ids(_com_haste_e(quase_verticais)) == ["cemig-eo-r3-s19-v001"]


# --- envolvente: Bézier e polilinha elíptica --------------------------------------------------


def _circulo_poligonal(n: int, recuo: float = 0.0) -> tuple[float, ...]:
    """Raios relativos: vértices pares na elipse, ímpares recuados em `recuo`."""
    return tuple(1.0 if k % 2 == 0 else 1.0 - recuo for k in range(n))


@pytest.mark.parametrize(
    ("vertices", "esperada"), [(7, "cemig-eo-r3-s19-v001"), (8, "cemig-eo-r3-s19-v002")]
)
def test_limiar_de_vertices_da_envolvente_poligonal(vertices: int, esperada: str) -> None:
    contorno = (1.0,) * vertices
    pagina = pagina_desenhada(
        lambda p: desenhar_haste(p, DECRESCENTES, envolvente=True, contorno=contorno)
    )

    assert _ids(pagina) == [esperada]


@pytest.mark.parametrize(
    ("recuo", "esperada"),
    [
        (0.15, "cemig-eo-r3-s19-v002"),
        (0.19, "cemig-eo-r3-s19-v002"),
        (0.21, "cemig-eo-r3-s19-v001"),
    ],
)
def test_limiar_de_desvio_da_envolvente_poligonal(recuo: float, esperada: str) -> None:
    contorno = _circulo_poligonal(32, recuo)
    pagina = pagina_desenhada(
        lambda p: desenhar_haste(p, DECRESCENTES, envolvente=True, contorno=contorno)
    )

    assert _ids(pagina) == [esperada]


def test_polilinha_aberta_com_muitos_vertices_nao_e_envolvente() -> None:
    def aberta(p: pymupdf.Page) -> None:
        desenhar_haste(p, DECRESCENTES)
        cx, cy = CENTRO[0], CENTRO[1] - HASTE / 2 - LACUNA
        pontos = [
            (cx + 10 * math.cos(2 * math.pi * k / 32), cy + 10 * math.sin(2 * math.pi * k / 32))
            for k in range(31)
        ]
        p.draw_polyline(pontos, color=PRETO, width=0.5, closePath=False)

    assert _ids(pagina_desenhada(aberta)) == ["cemig-eo-r3-s19-v001"]


@pytest.mark.parametrize(
    ("raio", "esperada"),
    [(11.0, "cemig-eo-r3-s19-v002"), (14.0, "cemig-eo-r3-s19-v001")],
    ids=["envolvente-cabe", "envolvente-grande-demais"],
)
def test_diametro_maximo_da_envolvente_bezier(raio: float, esperada: str) -> None:
    """Acima de ~3 vezes a maior barra o oval é outro desenho (um poste, uma moldura)."""

    def oval(p: pymupdf.Page) -> None:
        cx, cy = CENTRO[0], CENTRO[1] - HASTE / 2 - LACUNA
        p.draw_oval(pymupdf.Rect(cx - raio, cy - raio, cx + raio, cy + raio), color=PRETO)  # type: ignore[no-untyped-call]

    assert _ids(_com_haste_e(oval)) == [esperada]


def test_envolvente_que_nao_contem_as_barras_nao_conta() -> None:
    def deslocada(p: pymupdf.Page) -> None:
        cx, cy = CENTRO[0] + 40.0, CENTRO[1]
        p.draw_oval(pymupdf.Rect(cx - 11, cy - 11, cx + 11, cy + 11), color=PRETO)  # type: ignore[no-untyped-call]

    assert _ids(_com_haste_e(deslocada)) == ["cemig-eo-r3-s19-v001"]


# --- componentes e determinismo ---------------------------------------------------------------


@pytest.mark.parametrize("graus", [0.0, 45.0, 90.0], ids=["0", "45", "90"])
@pytest.mark.parametrize("variante", _V)
def test_componentes_ordenados_sem_repetir_o_caminho_da_ancora(variante: str, graus: float) -> None:
    pagina = pagina_desenhada(lambda p: desenhar_positivo(p, variante, graus=graus))

    [casamento] = _casa(pagina)
    assert list(casamento.componentes) == sorted(set(casamento.componentes))
    assert casamento.caminho not in casamento.componentes
    assert all(0 <= c < len(pagina.modelo.caminhos) for c in casamento.componentes)


def test_envolvente_poligonal_entra_nos_componentes() -> None:
    contorno = (1.0,) * 32
    pagina = pagina_desenhada(
        lambda p: desenhar_haste(p, DECRESCENTES, envolvente=True, contorno=contorno)
    )

    [casamento] = _casa(pagina)
    assert casamento.variante["id"] == "cemig-eo-r3-s19-v002"
    assert casamento.componentes == (1, 2, 3, 4)


def test_ordem_dos_casamentos_nao_depende_da_ordem_de_desenho() -> None:
    desenhos = (
        lambda p: desenhar_haste(p, DECRESCENTES, centro=(60.0, 60.0)),
        lambda p: desenhar_haste(p, DECRESCENTES, centro=(200.0, 200.0), envolvente=True),
        lambda p: desenhar_haste(p, ALTERNADAS, centro=(60.0, 240.0)),
        lambda p: desenhar_haste(p, ALTERNADAS, centro=(240.0, 60.0), x=True),
    )

    def resumo(ordem: tuple[int, ...]) -> list[tuple[str, tuple[float, ...]]]:
        def desenhar(p: pymupdf.Page) -> None:
            for i in ordem:
                desenhos[i](p)

        return [
            (str(c.variante["id"]), tuple(round(v, 2) for v in c.caixa))
            for c in _casa(pagina_desenhada(desenhar))
        ]

    direto, inverso = resumo((0, 1, 2, 3)), resumo((3, 2, 1, 0))
    assert len(direto) == 4
    assert direto == inverso


# --- kind, pureza e orçamento -----------------------------------------------------------------


def test_kind_desconhecido_recusa_mesmo_com_variantes_validas_na_mesma_chamada() -> None:
    pagina = pagina_desenhada(lambda p: desenhar_haste(p, DECRESCENTES))
    ruim: tuple[dict[str, Any], dict[str, Any]] = (
        {},
        {"id": "x", "recognition": {"status": "enabled", "grammar": {"kind": "haste"}}},
    )

    with pytest.raises(ValueError, match="haste"):
        casar_variantes(pagina, [*_PARES, ruim])


def test_grammar_stem_nao_importa_pymupdf() -> None:
    arvore = ast.parse(Path(grammar_stem.__file__).read_text(encoding="utf-8"))
    importados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados.update(alias.name.split(".")[0] for alias in no.names)
        elif isinstance(no, ast.ImportFrom):
            importados.add((no.module or "").split(".")[0])
    assert not importados & {"pymupdf", "fitz"}


def test_pagina_hostil_de_segmentos_curtos_paralelos_estoura_o_teto_do_orcamento() -> None:
    """3000 traços de haste lado a lado: o teto de 200.000 vem do orçamento, nunca de um laço."""

    def traco(i: int) -> Any:
        x, y = 5.0 + (i % 100) * 2.9, 5.0 + (i // 100) * 0.7
        return linha((x, y), (x, y + 8.0))

    pagina = pagina_gramatica([traco(i) for i in range(3000)])

    with pytest.raises(TetoGramaticasExcedido):
        casar_variantes(pagina, _PARES, limite=200_000)
