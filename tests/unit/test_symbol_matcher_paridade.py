# mypy: disable-error-code="no-untyped-call"
"""Casamento de variantes sobre o modelo: paridade com `observar_pacotes` no corpus sintético."""

from __future__ import annotations

import ast
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final, Literal

import pymupdf
import pytest
from tests.fixtures.declarative_symbols.corpus import ENABLED_CASES, build_enabled_corpus
from tests.fixtures.symbol_grammars.paginas import (
    circulo_bezier,
    linha,
    pagina_gramatica,
    poligono,
    retangulo_traco,
    texto,
)

from zeny_project_handler.adapters.analysis.declarative_symbols import (
    carregar_pacotes,
    observar_pacotes,
    variantes_do_motor,
)
from zeny_project_handler.adapters.analysis.drawing_model import (
    grammar_disc,
    grammar_frames,
    symbol_grammars,
    symbol_matcher,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    carregar_tabela_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.grammar_disc import (
    discos_candidatos,
    pontas_terminais,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa, Ponto
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    FonteGramaticaFalhou,
    PaginaGramatica,
    TetoGramaticasExcedido,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import (
    CasamentoGramatica,
    casar_variantes,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_para_gramaticas

Pacotes = tuple[dict[str, Any], ...]
Variantes = tuple[tuple[Mapping[str, Any], Mapping[str, Any]], ...]
Desenho = Callable[[pymupdf.Page], None]

_TOLERANCIA_NORMALIZADA: Final = 1e-3
_SHA: Final = "a" * 64
_TIPO_DA_VARIANTE: Final = {caso.variant_id: caso.kind for caso in ENABLED_CASES}

_CAMARA_CT: Final = "cemig-eo-r3-s06-v001"
_ROTULO_EC_ELIPSE: Final = "cemig-eo-r3-s28-v003"
_TRIANGULO_VAZIO: Final = "cemig-eo-r3-s07-v001"
_TRIANGULO_CHEIO: Final = "cemig-eo-r3-s07-v002"
_BARRA: Final = "cemig-eo-r3-s05-v004"
_DIAGONAIS: Final = "cemig-eo-r3-s11-v001"
_DISCO: Final = "cemig-eo-r3-s28-v001"

_MOLDURA_CAMARA: Final[Caixa] = (101.0, 115.0, 169.0, 149.0)
_MOLDURA_QUADRADA: Final[Caixa] = (110.0, 110.0, 158.0, 158.0)
_INTERNA_DA_BARRA: Final[Caixa] = (118.0, 118.0, 150.0, 150.0)
_CAIXA_ROTULO_CAMARA: Final[Caixa] = (107.0, 130.0, 125.0, 142.0)
_CENTRO_DISCO: Final[Ponto] = (150.0, 150.0)
_RAIO_DISCO: Final = 1.4
_ROXO: Final = (0.31, 0.10, 0.30)
_PRETO: Final = (0, 0, 0)
_CINZA: Final = (0.5, 0.5, 0.5)


@pytest.fixture(scope="module")
def pacotes() -> Pacotes:
    return carregar_pacotes()


@pytest.fixture(scope="module")
def variantes(pacotes: Pacotes) -> Variantes:
    return variantes_do_motor(pacotes)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[dict[str, Any]]]:
    caminho = tmp_path_factory.mktemp("corpus") / "c.pdf"
    return caminho, build_enabled_corpus(caminho)["cases"]


def _motor(pagina: pymupdf.Page, pacotes: Pacotes) -> Any:
    return observar_pacotes(
        pagina,
        documento_id="paridade",
        documento_sha256=_SHA,
        pagina_numero=pagina.number + 1,
        pacotes=pacotes,
    )


def _ids(casamentos: Sequence[CasamentoGramatica]) -> set[str]:
    return {casamento.variante["id"] for casamento in casamentos}


def _ids_do_motor(pagina: pymupdf.Page, pacotes: Pacotes) -> set[str]:
    return {str(observacao.template) for observacao in _motor(pagina, pacotes).observacoes}


def _ids_do_nucleo(pagina: pymupdf.Page, variantes: Variantes) -> set[str]:
    return _ids(casar_variantes(pagina_para_gramaticas(pagina, 0), variantes))


def _rotulo(row: Mapping[str, Any]) -> str:
    return f"page={row['page']} variant_id={row['variant_id']} stratum={row['stratum']}"


def _envelope(observacao: Any) -> Caixa:
    pontos = observacao.geometria.pontos_normalizados
    xs = [float(ponto.x) for ponto in pontos]
    ys = [float(ponto.y) for ponto in pontos]
    return (min(xs), min(ys), max(xs), max(ys))


def _divergencias_de_caixa_e_indice(pagina: pymupdf.Page, pacotes: Pacotes) -> list[str]:
    """Pares casamento e observação por variante, nas duas ordens: caixa e índice cru."""
    gramatica = pagina_para_gramaticas(pagina, pagina.number or 0)
    modelo = gramatica.modelo
    casamentos = casar_variantes(gramatica, variantes_do_motor(pacotes))
    observacoes = _motor(pagina, pacotes).observacoes
    if [c.variante["id"] for c in casamentos] != [str(o.template) for o in observacoes]:
        return [
            "variantes: "
            f"{[c.variante['id'] for c in casamentos]} != {[o.template for o in observacoes]}"
        ]
    divergencias: list[str] = []
    for casamento, observacao in zip(casamentos, observacoes, strict=True):
        x0, y0, x1, y1 = casamento.caixa
        normalizada = (
            x0 / modelo.largura,
            y0 / modelo.altura,
            x1 / modelo.largura,
            y1 / modelo.altura,
        )
        if any(
            abs(nossa - dele) > _TOLERANCIA_NORMALIZADA
            for nossa, dele in zip(normalizada, _envelope(observacao), strict=True)
        ):
            divergencias.append(
                f"caixa de {casamento.variante['id']}: {normalizada} != {_envelope(observacao)}"
            )
        indice_cru = gramatica.indices_crus[casamento.caminho]
        if indice_cru != int(observacao.primitivas[0].indice):
            divergencias.append(
                f"índice de {casamento.variante['id']}: "
                f"{indice_cru} != {observacao.primitivas[0].indice}"
            )
    return divergencias


def _positivas(row: Mapping[str, Any]) -> bool:
    return str(row["stratum"]).startswith("positive")


def _invariante_em_qualquer_rotacao(row: Mapping[str, Any]) -> bool:
    if not _positivas(row):
        return False
    tipo = _TIPO_DA_VARIANTE[row["variant_id"]]
    if tipo == "terminal_disc":
        return row["stratum"] in {"positive", "positive_split"}
    return tipo in {"label_in_frame", "framed_diagonals", "diamond_three_dots"}


def _invariante_em_180(row: Mapping[str, Any]) -> bool:
    if _invariante_em_qualquer_rotacao(row):
        return True
    tipo = _TIPO_DA_VARIANTE[row["variant_id"]]
    return (row["stratum"] == "positive" and tipo == "nested_rectangles_bar") or (
        row["stratum"] == "positive_stripes"
    )


# --- paridade no corpus ---------------------------------------------------------------------


def test_paridade_de_variantes_por_pagina_no_corpus(
    corpus: tuple[Path, list[dict[str, Any]]], pacotes: Pacotes, variantes: Variantes
) -> None:
    caminho, linhas = corpus
    divergencias: list[str] = []
    with pymupdf.open(caminho) as documento:
        for row in linhas:
            indice = row["page"] - 1
            pagina = documento[indice]
            nucleo = _ids(casar_variantes(pagina_para_gramaticas(pagina, indice), variantes))
            motor = _ids_do_motor(pagina, pacotes)
            esperado = set(row["expected_variant_ids"])
            if not nucleo == esperado == motor:
                divergencias.append(
                    f"{_rotulo(row)}: núcleo={sorted(nucleo)} motor={sorted(motor)} "
                    f"esperado={sorted(esperado)}"
                )
    assert divergencias == []
    assert any(row["expected_variant_ids"] for row in linhas)


def test_paridade_com_a_tabela_de_glifos(
    corpus: tuple[Path, list[dict[str, Any]]], variantes: Variantes
) -> None:
    """A E06.2.2 sempre passa a tabela: a leitura dela não muda o corpus."""
    caminho, linhas = corpus
    tabela = carregar_tabela_glifos()
    divergencias: list[str] = []
    with pymupdf.open(caminho) as documento:
        for row in linhas:
            indice = row["page"] - 1
            obtidos = _ids(
                casar_variantes(
                    pagina_para_gramaticas(documento[indice], indice, tabela), variantes
                )
            )
            if obtidos != set(row["expected_variant_ids"]):
                divergencias.append(f"{_rotulo(row)}: {sorted(obtidos)}")
    assert divergencias == []


def test_caixa_e_indice_cru_batem_com_o_motor_atual(
    corpus: tuple[Path, list[dict[str, Any]]], pacotes: Pacotes
) -> None:
    caminho, linhas = corpus
    positivas = [row for row in linhas if _positivas(row)]
    assert {_TIPO_DA_VARIANTE[row["variant_id"]] for row in positivas} == set(
        _TIPO_DA_VARIANTE.values()
    )
    divergencias: list[str] = []
    with pymupdf.open(caminho) as documento:
        for row in positivas:
            achados = _divergencias_de_caixa_e_indice(documento[row["page"] - 1], pacotes)
            divergencias.extend(f"{_rotulo(row)}: {achado}" for achado in achados)
    assert divergencias == []


@pytest.mark.parametrize("rotacao", [90, 180, 270])
def test_rotacao_nas_gramaticas_invariantes(
    corpus: tuple[Path, list[dict[str, Any]]], pacotes: Pacotes, rotacao: int
) -> None:
    caminho, linhas = corpus
    filtro = _invariante_em_180 if rotacao == 180 else _invariante_em_qualquer_rotacao
    selecionadas = [row for row in linhas if filtro(row)]
    assert selecionadas
    divergencias: list[str] = []
    with pymupdf.open(caminho) as documento:
        for row in selecionadas:
            pagina = documento[row["page"] - 1]
            pagina.set_rotation(rotacao)
            achados = _divergencias_de_caixa_e_indice(pagina, pacotes)
            divergencias.extend(f"{_rotulo(row)}: {achado}" for achado in achados)
            if not _ids_do_motor(pagina, pacotes):
                divergencias.append(f"{_rotulo(row)}: o motor não casou a página girada")
    assert divergencias == []


def _sensivel_a_orientacao(row: Mapping[str, Any], rotacao: int) -> bool:
    """R-7: triângulo em qualquer rotação; barra e faixas só deitadas (90 e 270)."""
    tipo = _TIPO_DA_VARIANTE[row["variant_id"]]
    if tipo == "triangle_in_frame":
        return True
    if rotacao == 180:
        return False
    return tipo == "nested_rectangles_bar" or row["stratum"] == "positive_stripes"


@pytest.mark.parametrize("rotacao", [90, 180, 270])
def test_rotacao_so_diverge_onde_r7_preve_em_todo_o_corpus(
    corpus: tuple[Path, list[dict[str, Any]]],
    pacotes: Pacotes,
    variantes: Variantes,
    rotacao: int,
) -> None:
    """Negativos também: fora de R-7 os dois concordam, e em R-7 o núcleo só perde o que o motor
    casa em coordenadas cruas, sem achar nada a mais."""
    caminho, linhas = corpus
    divergencias: list[str] = []
    with pymupdf.open(caminho) as documento:
        for row in linhas:
            indice = row["page"] - 1
            pagina = documento[indice]
            pagina.set_rotation(rotacao)
            nucleo = _ids(casar_variantes(pagina_para_gramaticas(pagina, indice), variantes))
            motor = _ids_do_motor(pagina, pacotes)
            esperado = set() if _sensivel_a_orientacao(row, rotacao) and motor else motor
            if nucleo != esperado:
                divergencias.append(
                    f"{_rotulo(row)}: núcleo={sorted(nucleo)} motor={sorted(motor)}"
                )
    assert divergencias == []


def _linha_do_corpus(
    linhas: Sequence[Mapping[str, Any]], variante: str, estrato: str = "positive"
) -> Mapping[str, Any]:
    return next(
        row for row in linhas if row["variant_id"] == variante and row["stratum"] == estrato
    )


@pytest.mark.parametrize(
    ("variante", "estrato", "rotacao"),
    [
        pytest.param(_TRIANGULO_VAZIO, "positive", 180, id="triangulo-vazio-180"),
        pytest.param(_TRIANGULO_CHEIO, "positive", 180, id="triangulo-cheio-180"),
        pytest.param(_BARRA, "positive", 90, id="barra-90"),
        pytest.param(_DISCO, "positive_stripes", 90, id="faixas-90"),
    ],
)
def test_divergencia_esperada_conteudo_cru_em_pe_so_o_motor_casa(
    corpus: tuple[Path, list[dict[str, Any]]],
    pacotes: Pacotes,
    variantes: Variantes,
    variante: str,
    estrato: str,
    rotacao: int,
) -> None:
    """R-7: o que está em pé só em coordenadas cruas fica deitado para quem vê a página."""
    caminho, linhas = corpus
    row = _linha_do_corpus(linhas, variante, estrato)
    with pymupdf.open(caminho) as documento:
        indice = row["page"] - 1
        pagina = documento[indice]
        pagina.set_rotation(rotacao)
        nucleo = _ids(casar_variantes(pagina_para_gramaticas(pagina, indice), variantes))
        motor = _ids_do_motor(pagina, pacotes)
    assert variante not in nucleo
    assert variante in motor


def _cru_do_visual(pagina: pymupdf.Page, rotacao: int) -> pymupdf.Matrix:
    """Matriz que leva da página visual, com `/Rotate`, às coordenadas de desenho."""
    pagina.set_rotation(rotacao)
    matriz = pymupdf.Matrix(pagina.derotation_matrix)
    pagina.set_rotation(0)
    return matriz


def _ponto_cru(matriz: pymupdf.Matrix, ponto: Ponto) -> pymupdf.Point:
    cru: pymupdf.Point = pymupdf.Point(ponto) * matriz
    return cru


def _retangulo_cru(matriz: pymupdf.Matrix, caixa: Caixa) -> pymupdf.Rect:
    a = _ponto_cru(matriz, (caixa[0], caixa[1]))
    b = _ponto_cru(matriz, (caixa[2], caixa[3]))
    return pymupdf.Rect(min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y))


def _triangulo_visual(pagina: pymupdf.Page, matriz: pymupdf.Matrix, *, cheio: bool) -> None:
    pagina.draw_rect(_retangulo_cru(matriz, _MOLDURA_QUADRADA), color=_PRETO, width=1)
    forma = pagina.new_shape()
    forma.draw_polyline(
        [_ponto_cru(matriz, p) for p in ((134, 112), (156, 156), (112, 156), (134, 112))]
    )
    cor = (0.7, 0, 0)
    forma.finish(color=cor, fill=cor if cheio else None, width=1)
    forma.commit()


def _barra_visual(pagina: pymupdf.Page, matriz: pymupdf.Matrix) -> None:
    pagina.draw_rect(_retangulo_cru(matriz, _MOLDURA_QUADRADA), color=_PRETO, width=1)
    pagina.draw_rect(_retangulo_cru(matriz, _INTERNA_DA_BARRA), color=_PRETO, width=1)
    pagina.draw_line(
        _ponto_cru(matriz, (119, 134)), _ponto_cru(matriz, (149, 134)), color=_PRETO, width=1
    )


def _faixas_visuais(pagina: pymupdf.Page, matriz: pymupdf.Matrix) -> None:
    pagina.draw_line(
        _ponto_cru(matriz, (60, 150)), _ponto_cru(matriz, _CENTRO_DISCO), color=_CINZA, width=0.7
    )
    cx, cy = _CENTRO_DISCO
    altura = 2 * _RAIO_DISCO / 12
    for indice in range(12):
        topo = cy - _RAIO_DISCO + indice * altura
        desvio = topo + altura / 2 - cy
        meia = math.sqrt(_RAIO_DISCO * _RAIO_DISCO - desvio * desvio)
        faixa = _retangulo_cru(matriz, (cx - meia, topo, cx + meia, topo + altura))
        pagina.draw_rect(faixa, color=None, fill=_ROXO)


_DESENHOS_VISUAIS: Final[dict[str, Callable[[pymupdf.Page, pymupdf.Matrix], None]]] = {
    _TRIANGULO_VAZIO: lambda pagina, matriz: _triangulo_visual(pagina, matriz, cheio=False),
    _TRIANGULO_CHEIO: lambda pagina, matriz: _triangulo_visual(pagina, matriz, cheio=True),
    _BARRA: _barra_visual,
    _DISCO: _faixas_visuais,
}


@pytest.mark.parametrize(
    "variante",
    [
        pytest.param(_TRIANGULO_VAZIO, id="triangulo-vazio"),
        pytest.param(_TRIANGULO_CHEIO, id="triangulo-cheio"),
        pytest.param(_BARRA, id="barra"),
        pytest.param(_DISCO, id="faixas"),
    ],
)
def test_divergencia_esperada_em_pe_com_rotate_90_so_o_nucleo_casa(
    pacotes: Pacotes, variantes: Variantes, variante: str
) -> None:
    """R-7, o outro sentido: em pé para quem vê a página, deitado em coordenadas cruas."""
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        _DESENHOS_VISUAIS[variante](pagina, _cru_do_visual(pagina, 90))
        pagina.set_rotation(90)
        assert variante in _ids_do_nucleo(pagina, variantes)
        assert variante not in _ids_do_motor(pagina, pacotes)


def test_divergencia_esperada_em_pe_sem_rotate_ambos_casam(
    pacotes: Pacotes, variantes: Variantes
) -> None:
    """Controle: os mesmos desenhos, sem `/Rotate`, casam nos dois."""
    for variante, desenho in _DESENHOS_VISUAIS.items():
        with pymupdf.open() as documento:
            pagina = documento.new_page(width=300, height=300)
            desenho(pagina, pymupdf.Matrix(1, 1))
            assert variante in _ids_do_nucleo(pagina, variantes), variante
            assert variante in _ids_do_motor(pagina, pacotes), variante


@pytest.mark.parametrize("rotacao", [0, 90], ids=["sem-rotate", "rotate-90"])
def test_cropbox_nao_desloca_a_caixa(
    corpus: tuple[Path, list[dict[str, Any]]], pacotes: Pacotes, rotacao: int
) -> None:
    caminho, linhas = corpus
    filtro = _positivas if rotacao == 0 else _invariante_em_qualquer_rotacao
    selecionadas = [row for row in linhas if filtro(row)]
    divergencias: list[str] = []
    with pymupdf.open(caminho) as documento:
        for row in selecionadas:
            pagina = documento[row["page"] - 1]
            pagina.set_cropbox(pymupdf.Rect(50, 60, 250, 280))
            pagina.set_rotation(rotacao)
            achados = _divergencias_de_caixa_e_indice(pagina, pacotes)
            divergencias.extend(f"{_rotulo(row)}: {achado}" for achado in achados)
            if not _ids_do_motor(pagina, pacotes):
                divergencias.append(f"{_rotulo(row)}: o motor não casou a página recortada")
    assert divergencias == []


# --- ganhos previstos (R-5) -----------------------------------------------------------------


def _rotulo_ct(pagina: pymupdf.Page) -> None:
    pagina.insert_text((107, 140), "CT", fontsize=11)


def _quatro_tracos(pagina: pymupdf.Page, *, canto_aberto: float = 0.0) -> None:
    x0, y0, x1, y1 = _MOLDURA_CAMARA
    pagina.draw_line((x0, y0), (x1, y0), color=_PRETO, width=1)
    pagina.draw_line((x1, y0), (x1, y1), color=_PRETO, width=1)
    pagina.draw_line((x1, y1), (x0, y1), color=_PRETO, width=1)
    pagina.draw_line((x0, y1), (x0, y0 + canto_aberto), color=_PRETO, width=1)


def _nova_pagina(desenho: Desenho) -> tuple[pymupdf.Document, pymupdf.Page]:
    documento = pymupdf.open()
    pagina = documento.new_page(width=300, height=300)
    desenho(pagina)
    return documento, pagina


def _ids_dos_dois(
    desenho: Desenho, pacotes: Pacotes, variantes: Variantes
) -> tuple[set[str], set[str]]:
    documento, pagina = _nova_pagina(desenho)
    with documento:
        return _ids_do_nucleo(pagina, variantes), _ids_do_motor(pagina, pacotes)


def test_ganho_moldura_de_quatro_tracos(pacotes: Pacotes, variantes: Variantes) -> None:
    def desenho(pagina: pymupdf.Page) -> None:
        _quatro_tracos(pagina)
        _rotulo_ct(pagina)

    assert _ids_dos_dois(desenho, pacotes, variantes) == ({_CAMARA_CT}, set())


def test_quase_acerto_de_quatro_tracos_com_folga(pacotes: Pacotes, variantes: Variantes) -> None:
    def desenho(pagina: pymupdf.Page) -> None:
        _quatro_tracos(pagina, canto_aberto=2.0)
        _rotulo_ct(pagina)

    assert _ids_dos_dois(desenho, pacotes, variantes) == (set(), set())


def _confere_rotulo_de_origem(variantes: Variantes, origem: Literal["glifo", "shx"]) -> None:
    moldura = retangulo_traco(_MOLDURA_CAMARA)
    com_texto = pagina_gramatica((moldura,), (texto("CT", _CAIXA_ROTULO_CAMARA, origem=origem),))
    assert _ids(casar_variantes(com_texto, variantes)) == {_CAMARA_CT}
    assert casar_variantes(pagina_gramatica((moldura,)), variantes) == ()


def test_ganho_rotulo_em_glifo(variantes: Variantes) -> None:
    _confere_rotulo_de_origem(variantes, "glifo")


def test_ganho_rotulo_em_shx(variantes: Variantes) -> None:
    _confere_rotulo_de_origem(variantes, "shx")


def test_ganho_retangulo_de_quatro_linhas_em_um_caminho(variantes: Variantes) -> None:
    x0, y0, x1, y1 = _MOLDURA_CAMARA
    pagina = pagina_gramatica(
        (poligono(((x0, y0), (x1, y0), (x1, y1), (x0, y1))),),
        (texto("CT", _CAIXA_ROTULO_CAMARA),),
    )
    assert _ids(casar_variantes(pagina, variantes)) == {_CAMARA_CT}


def test_quase_acerto_de_quatro_linhas_com_canto_torto(variantes: Variantes) -> None:
    x0, y0, x1, y1 = _MOLDURA_CAMARA
    pagina = pagina_gramatica(
        (poligono(((x0, y0), (x1, y0), (x1 + 2.0, y1), (x0, y1))),),
        (texto("CT", _CAIXA_ROTULO_CAMARA),),
    )
    assert casar_variantes(pagina, variantes) == ()


def test_ganho_qu_alinhado(pacotes: Pacotes, variantes: Variantes) -> None:
    def desenho(pagina: pymupdf.Page) -> None:
        pagina.draw_quad(pymupdf.Rect(_MOLDURA_CAMARA).quad, color=_PRETO, width=1)
        _rotulo_ct(pagina)

    documento, pagina = _nova_pagina(desenho)
    with documento:
        assert [item[0] for item in pagina.get_drawings(extended=True)[0]["items"]] == ["qu"]
    assert _ids_dos_dois(desenho, pacotes, variantes) == ({_CAMARA_CT}, set())


def test_quase_acerto_de_qu_inclinado(pacotes: Pacotes, variantes: Variantes) -> None:
    def desenho(pagina: pymupdf.Page) -> None:
        x0, y0, x1, y1 = _MOLDURA_CAMARA
        quad = pymupdf.Quad((x0, y0), (x1, y0 + 2.0), (x0, y1), (x1, y1 + 2.0))
        pagina.draw_quad(quad, color=_PRETO, width=1)
        _rotulo_ct(pagina)

    assert _ids_dos_dois(desenho, pacotes, variantes) == (set(), set())


def _arcos(pagina: pymupdf.Page, *, dois: bool) -> None:
    cx, cy, raio = 134.0, 134.0, 24.0
    alca = 4.0 / 3.0 * raio
    forma = pagina.new_shape()
    forma.draw_bezier(
        (cx + raio, cy), (cx + raio, cy + alca), (cx - raio, cy + alca), (cx - raio, cy)
    )
    if dois:
        forma.draw_bezier(
            (cx - raio, cy), (cx - raio, cy - alca), (cx + raio, cy - alca), (cx + raio, cy)
        )
    forma.finish(color=_PRETO, width=1, closePath=False)
    forma.commit()
    pagina.insert_text((126, 139), "EC", fontsize=11)


def test_ganho_circulo_de_dois_arcos(pacotes: Pacotes, variantes: Variantes) -> None:
    assert _ids_dos_dois(lambda p: _arcos(p, dois=True), pacotes, variantes) == (
        {_ROTULO_EC_ELIPSE},
        set(),
    )


def test_quase_acerto_de_um_arco_so(pacotes: Pacotes, variantes: Variantes) -> None:
    assert _ids_dos_dois(lambda p: _arcos(p, dois=False), pacotes, variantes) == (set(), set())


# --- `qu` e `re` girados: viram `l` no modelo; o motor conta só `l` literal -------------------


def _inclinado(pagina: pymupdf.Page, ul: Ponto, ur: Ponto, ll: Ponto, lr: Ponto) -> None:
    """Um `qu` no `get_drawings`: 5 pontos, voltando ao primeiro."""
    forma = pagina.new_shape()
    forma.draw_polyline([ul, ur, lr, ll, ul])
    forma.finish(color=_PRETO, width=1, closePath=False)
    forma.commit()


def _re_girado(pagina: pymupdf.Page, caixa: Caixa, graus: float) -> None:
    """Operador `re` sob matriz girada: o `get_drawings` já o entrega como 4 `l` literais."""
    x0, y0, x1, y1 = caixa
    forma = pagina.new_shape()
    forma.draw_rect(pymupdf.Rect(caixa))
    forma.finish(
        color=_PRETO,
        width=1,
        morph=(pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2), pymupdf.Matrix(graus)),
    )
    forma.commit()


def _diagonais_qu(pagina: pymupdf.Page) -> None:
    x0, y0, x1, y1 = _MOLDURA_QUADRADA
    pagina.draw_rect(pymupdf.Rect(_MOLDURA_QUADRADA), color=_PRETO, width=1)
    _inclinado(pagina, (x0 + 1, y0), (x1, y1 - 1), (x0, y0 + 1), (x1 - 1, y1))
    _inclinado(pagina, (x1, y0 + 1), (x0 + 1, y1), (x1 - 1, y0), (x0, y1 - 1))


def _diagonais_re(pagina: pymupdf.Page) -> None:
    pagina.draw_rect(pymupdf.Rect(_MOLDURA_QUADRADA), color=_PRETO, width=1)
    meio = 48.0 * math.sqrt(2.0) / 2.0
    faixa: Caixa = (134.0 - meio, 133.3, 134.0 + meio, 134.7)
    _re_girado(pagina, faixa, 45.0)
    _re_girado(pagina, faixa, -45.0)


def _guarda_qu(pagina: pymupdf.Page) -> None:
    pagina.draw_rect(pymupdf.Rect(_MOLDURA_CAMARA), color=_PRETO, width=1)
    _rotulo_ct(pagina)
    _inclinado(pagina, (105, 117), (165, 145), (105, 119), (165, 147))


def _guarda_re(pagina: pymupdf.Page) -> None:
    pagina.draw_rect(pymupdf.Rect(_MOLDURA_CAMARA), color=_PRETO, width=1)
    _rotulo_ct(pagina)
    _re_girado(pagina, (101.0, 131.0, 169.0, 133.0), 25.0)


def _retangulos_da_barra(pagina: pymupdf.Page) -> None:
    pagina.draw_rect(pymupdf.Rect(_MOLDURA_QUADRADA), color=_PRETO, width=1)
    pagina.draw_rect(pymupdf.Rect(_INTERNA_DA_BARRA), color=_PRETO, width=1)


def _barra_qu(pagina: pymupdf.Page) -> None:
    _retangulos_da_barra(pagina)
    _inclinado(pagina, (119, 133.6), (149, 133.9), (119, 134.1), (149, 134.4))


def _barra_re(pagina: pymupdf.Page) -> None:
    _retangulos_da_barra(pagina)
    _re_girado(pagina, (119.0, 133.7, 149.0, 134.3), 1.0)


@pytest.mark.parametrize(
    ("desenho", "operador", "variante", "no_nucleo", "no_motor"),
    [
        pytest.param(_diagonais_qu, "qu", _DIAGONAIS, True, False, id="diagonais-qu"),
        pytest.param(_diagonais_re, "l", _DIAGONAIS, True, True, id="diagonais-re"),
        pytest.param(_guarda_qu, "qu", _CAMARA_CT, False, True, id="guarda-qu"),
        pytest.param(_guarda_re, "l", _CAMARA_CT, False, False, id="guarda-re"),
        pytest.param(_barra_qu, "qu", _BARRA, True, False, id="barra-qu"),
        pytest.param(_barra_re, "l", _BARRA, True, True, id="barra-re"),
    ],
)
def test_par_de_qu_e_re_girados(
    pacotes: Pacotes,
    variantes: Variantes,
    desenho: Desenho,
    operador: str,
    variante: str,
    no_nucleo: bool,
    no_motor: bool,
) -> None:
    """O `qu` girado é o único que chega como `qu`: o núcleo vê os lados, e o motor não.

    O `re` sob matriz girada a PyMuPDF já entrega como `l` literal, e os dois concordam. O operador
    da última forma é conferido para o caso não mudar de assunto com outra versão da PyMuPDF.
    """
    documento, pagina = _nova_pagina(desenho)
    with documento:
        ultimo = pagina.get_drawings(extended=True)[-1]
        assert {item[0] for item in ultimo["items"]} == {operador}
    nucleo, motor = _ids_dos_dois(desenho, pacotes, variantes)
    assert (variante in nucleo, variante in motor) == (no_nucleo, no_motor)


# --- `casar_variantes` ----------------------------------------------------------------------


def _variante(
    identificador: str, gramatica: Mapping[str, Any]
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    return {"family_id": f"f-{identificador}"}, {
        "id": identificador,
        "recognition": {"status": "enabled", "grammar": gramatica},
    }


def _gramatica_rotulo(rotulo: str = "CT") -> dict[str, Any]:
    return {"kind": "label_in_frame", "frame": "rectangle", "label": rotulo, "max_span": 96}


_GRAMATICA_DISCO: Final[dict[str, Any]] = {
    "kind": "terminal_disc",
    "fill": "purple",
    "min_span": 1.0,
    "max_span": 4.0,
    "terminal_line": True,
}


def _pagina_com_rotulo() -> PaginaGramatica:
    return pagina_gramatica(
        (retangulo_traco(_MOLDURA_CAMARA),), (texto("CT", _CAIXA_ROTULO_CAMARA),)
    )


def test_pagina_sem_desenhos_nao_casa_nada(variantes: Variantes) -> None:
    assert casar_variantes(pagina_gramatica(()), variantes) == ()


def test_pagina_real_sem_desenhos_nao_casa_nada(pacotes: Pacotes, variantes: Variantes) -> None:
    assert _ids_dos_dois(lambda _pagina: None, pacotes, variantes) == (set(), set())


def _contar_chamadas(monkeypatch: pytest.MonkeyPatch, nome: str, chamadas: list[str]) -> None:
    original = getattr(symbol_matcher, nome)

    def contada(*args: Any, **kwargs: Any) -> Any:
        chamadas.append(nome)
        return original(*args, **kwargs)

    monkeypatch.setattr(symbol_matcher, nome, contada)


@pytest.mark.parametrize(
    "lista",
    [
        pytest.param((), id="vazias"),
        pytest.param((_variante("a", _gramatica_rotulo()),), id="so-moldura"),
    ],
)
def test_variantes_vazias_nao_montam_discos(
    monkeypatch: pytest.MonkeyPatch, lista: Variantes
) -> None:
    chamadas: list[str] = []
    _contar_chamadas(monkeypatch, "discos_candidatos", chamadas)
    _contar_chamadas(monkeypatch, "pontas_terminais", chamadas)

    casar_variantes(_pagina_com_rotulo(), lista)

    assert chamadas == []


def _pagina_com_disco() -> PaginaGramatica:
    return pagina_gramatica(
        (
            linha((60.0, 150.0), _CENTRO_DISCO, cor=_CINZA),
            circulo_bezier(_CENTRO_DISCO, _RAIO_DISCO, cor=None, preenchimento=_ROXO),
        )
    )


def test_discos_montados_uma_vez_por_pagina(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[str] = []
    _contar_chamadas(monkeypatch, "discos_candidatos", chamadas)
    _contar_chamadas(monkeypatch, "pontas_terminais", chamadas)
    lista = (_variante("a", _GRAMATICA_DISCO), _variante("b", _GRAMATICA_DISCO))

    casamentos = casar_variantes(_pagina_com_disco(), lista)

    assert sorted(chamadas) == ["discos_candidatos", "pontas_terminais"]
    assert [(c.variante["id"], c.caminho) for c in casamentos] == [("a", 1), ("b", 1)]


def test_pagina_sem_disco_nao_paga_as_pontas(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[str] = []
    _contar_chamadas(monkeypatch, "pontas_terminais", chamadas)

    assert casar_variantes(_pagina_com_rotulo(), (_variante("a", _GRAMATICA_DISCO),)) == ()
    assert chamadas == []


def test_casamento_traz_pacote_variante_caixa_e_caminho() -> None:
    entrada = _variante("a", _gramatica_rotulo())

    casamentos = casar_variantes(_pagina_com_rotulo(), (entrada,))

    assert casamentos == (
        CasamentoGramatica(
            pacote=entrada[0], variante=entrada[1], caixa=_MOLDURA_CAMARA, caminho=0
        ),
    )


def test_ordem_e_deterministica() -> None:
    def pagina() -> PaginaGramatica:
        return pagina_gramatica(
            (
                retangulo_traco((10.0, 10.0, 50.0, 30.0)),
                retangulo_traco((60.0, 10.0, 100.0, 30.0)),
            ),
            (
                texto("CT", (15.0, 15.0, 30.0, 25.0)),
                texto("CT", (65.0, 15.0, 80.0, 25.0)),
                texto("CT", (15.0, 16.0, 30.0, 26.0)),
            ),
        )

    a, b = _variante("a", _gramatica_rotulo()), _variante("b", _gramatica_rotulo())

    primeira = casar_variantes(pagina(), (a, b))
    segunda = casar_variantes(pagina(), (a, b))
    invertida = casar_variantes(pagina(), (b, a))

    assert primeira == segunda
    assert [(c.variante["id"], c.caminho) for c in primeira] == [
        ("a", 0),
        ("a", 1),
        ("b", 0),
        ("b", 1),
    ]
    assert [(c.variante["id"], c.caminho) for c in invertida] == [
        ("b", 0),
        ("b", 1),
        ("a", 0),
        ("a", 1),
    ]


@pytest.mark.parametrize(
    ("deslocamento", "esperados"),
    [
        pytest.param(0.0, 1, id="mesma-caixa"),
        pytest.param(0.0001, 1, id="mesma-a-3-casas"),
        pytest.param(0.01, 2, id="outra-a-3-casas"),
    ],
)
def test_deduplica_por_variante_e_caixa_arredondada(deslocamento: float, esperados: int) -> None:
    x0, y0, x1, y1 = _MOLDURA_CAMARA
    pagina = pagina_gramatica(
        (
            retangulo_traco(_MOLDURA_CAMARA),
            retangulo_traco((x0, y0, x1 + deslocamento, y1)),
        ),
        (texto("CT", _CAIXA_ROTULO_CAMARA),),
    )
    a, b = _variante("a", _gramatica_rotulo()), _variante("b", _gramatica_rotulo())

    casamentos = casar_variantes(pagina, (a, b))

    assert [c.variante["id"] for c in casamentos].count("a") == esperados
    assert [c.variante["id"] for c in casamentos].count("b") == esperados
    assert casamentos[0].caminho == 0


def test_kind_desconhecido_levanta() -> None:
    with pytest.raises(ValueError, match="desconhecida"):
        casar_variantes(_pagina_com_rotulo(), (_variante("a", {"kind": "outra"}),))


def test_varrer_variantes_cobra_o_orcamento() -> None:
    """Cada par de variante e candidato gasta 1: mesmo o que `_moldura_ok` recusa de graça."""
    caminhos = tuple(
        retangulo_traco((float(i), 10.0, float(i) + 5.0, 20.0)) for i in range(0, 200, 2)
    )
    pagina = pagina_gramatica(caminhos)
    molduras = len(contexto_gramaticas(pagina).molduras)
    construir = contexto_gramaticas(pagina).orcamento.gasto
    outra_forma = {"kind": "label_in_frame", "frame": "ellipse", "label": "X", "max_span": 96}
    lista = tuple(_variante(str(i), outra_forma) for i in range(5))
    exato = construir + 5 * molduras

    assert casar_variantes(pagina, lista, limite=exato) == ()
    with pytest.raises(TetoGramaticasExcedido):
        casar_variantes(pagina, lista, limite=exato - 1)


def test_varrer_variantes_cobra_o_orcamento_dos_discos() -> None:
    """Cada par de variante e disco gasta 1: mesmo o que o vão recusa de graça."""
    pagina = _pagina_com_disco()
    contexto = contexto_gramaticas(pagina)
    discos = discos_candidatos(contexto)
    pontas_terminais(contexto)
    fora_do_vao = {**_GRAMATICA_DISCO, "min_span": 100.0, "max_span": 200.0}
    lista = tuple(_variante(str(i), fora_do_vao) for i in range(5))
    exato = contexto.orcamento.gasto + 5 * len(discos)

    assert len(discos) == 1
    assert casar_variantes(pagina, lista, limite=exato) == ()
    with pytest.raises(TetoGramaticasExcedido):
        casar_variantes(pagina, lista, limite=exato - 1)


def test_teto_propaga(variantes: Variantes) -> None:
    caminhos = tuple(retangulo_traco((10.0, 10.0, 50.0, 30.0)) for _ in range(50))
    with pytest.raises(TetoGramaticasExcedido):
        casar_variantes(pagina_gramatica(caminhos), variantes, limite=10)


def test_fonte_falhou_propaga(variantes: Variantes) -> None:
    pagina = pagina_gramatica((), diagnosticos=("modelo.caminhos_falhou",))
    with pytest.raises(FonteGramaticaFalhou) as erro:
        casar_variantes(pagina, variantes)
    assert erro.value.codigo == "modelo.caminhos_falhou"


# --- pureza ---------------------------------------------------------------------------------

_PROIBIDOS: Final = frozenset({"pymupdf", "fitz", "declarative_symbols", "pymupdf_drawing_model"})


def _importados(fonte: str) -> set[str]:
    """Cada segmento dos módulos importados, e cada nome de `from x import nome`."""
    importados: set[str] = set()
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.Import):
            for nome in no.names:
                importados.update(nome.name.split("."))
        elif isinstance(no, ast.ImportFrom):
            importados.update((no.module or "").split("."))
            importados.update(nome.name for nome in no.names)
    return importados


@pytest.mark.parametrize(
    "fonte",
    [
        "import pymupdf",
        "import fitz as f",
        "from zeny_project_handler.adapters.analysis.declarative_symbols import _enabled",
        "from ..pymupdf_drawing_model import pagina_para_gramaticas",
        "from .. import declarative_symbols",
        "def f():\n    import pymupdf\n",
    ],
)
def test_detector_de_import_proibido(fonte: str) -> None:
    assert _importados(fonte) & _PROIBIDOS


def test_modulos_do_nucleo_nao_importam_pymupdf() -> None:
    modulos = (symbol_grammars, grammar_frames, grammar_disc, symbol_matcher)
    for modulo in modulos:
        assert modulo.__file__ is not None
        fonte = Path(modulo.__file__).read_text(encoding="utf-8")
        assert not _importados(fonte) & _PROIBIDOS, modulo.__name__
