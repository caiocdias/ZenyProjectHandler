# mypy: disable-error-code="no-untyped-call"
"""Ataques à gramática `split_triangle` (E06.3.3.2.2, Task 3), pelo testador.

Páginas puras e pacotes em `tmp_path`, com os desenhos de `tests/fixtures/symbol_grammars/
triangulo.py` e desenhos autorais deste arquivo, relativos ao lado `LADO`; nada vem de folha
real. Cobre os falsos positivos que a fixture do desenvolvedor não tenta (traço tracejado,
contorno roxo com S, gravata, triângulo ciano em duas metades), rotações a 45° e 180° e `/Rotate`
180 e 270 com a caixa conferida, `max_span` contra a caixa do pictograma, componentes como
invariante, contexto misturado, gasto linear e o trabalho fora do orçamento, a R-5 conferida pelos
componentes do E05 e o agrupamento de formas comuns (Task 2) sobre esta gramática.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.paginas import estilo, pagina_gramatica, poligono, texto
from tests.fixtures.symbol_grammars.rect_diagonal import CASOS_RECT_DIAGONAL, pagina_desenhada
from tests.fixtures.symbol_grammars.triangulo import (
    BRANCO,
    CASOS_TRIANGULO,
    CENTRO,
    CIANO,
    GRUPO_DA_VARIANTE,
    GRUPOS,
    LADO,
    PRETO,
    ROXO,
    VERDE,
    VERMELHO,
    Grupo,
    bracos_x,
    caminhos_trafo,
    desenhar_grupo,
    desenhar_trafo,
    desenhar_trafo_e05,
    pagina_com_texto,
    ponta_da_haste,
    raio_envolvente,
    variantes_do_grupo,
    vertices,
)
from tests.unit.test_guarda_fonte_estendida_testador import (
    _violacoes_de_bytes_e_inteiros,
    _violacoes_de_comentarios,
)
from tests.unit.test_symbol_packages_sem_memorizacao import _violacoes_de_fonte

from zeny_project_handler.adapters.analysis.declarative_symbols import carregar_pacotes
from zeny_project_handler.adapters.analysis.drawing_model import (
    grammar_triangulo,
    symbol_matcher,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    TabelaGlifos,
    carregar_tabela_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.grammar_triangulo import (
    casa_triangulos,
    triangulos_candidatos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caixa,
    Caminho,
    Cor,
    ItemCaminho,
    Ponto,
    TextoModelo,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    PaginaGramatica,
    TetoGramaticasExcedido,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import (
    CasamentoGramatica,
    casar_variantes,
    gasto_por_fase,
)
from zeny_project_handler.adapters.analysis.model_symbols import observar_pacotes_modelo
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_para_gramaticas
from zeny_project_handler.adapters.analysis.pymupdf_transformers import observar_transformadores
from zeny_project_handler.application.symbol_reconciliation import (
    CalibrationPolicy,
    reconcile_symbols,
)
from zeny_project_handler.domain.symbols import ObservacaoSimbolo

Pacote = dict[str, Any]

_EPSILON: Final = 1e-3  # PyMuPDF devolve coordenadas em float32
_TOLERANCIA_CAIXA: Final = 0.05
_BASE_CONTORNO: Final[Grupo] = ("outline", "none", False)
_BASE_MEIO_CIANO: Final[Grupo] = ("half_cyan", "none", False)
_SHA: Final = "d" * 64
_FAMILIA: Final = "family-autoral-trafo"
_ARQUIVO: Final = Path(__file__).resolve()


def _id_grupo(grupo: Grupo) -> str:
    return f"{grupo[0]}-{grupo[1]}-{'x' if grupo[2] else 'sem_x'}"


def _pares(
    casos: Sequence[tuple[str, Mapping[str, Any]]] = CASOS_TRIANGULO,
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    return [
        (
            {"family_id": "autoral"},
            {"id": variante, "recognition": {"status": "enabled", "grammar": gramatica}},
        )
        for variante, gramatica in casos
    ]


def _casamentos(pagina: PaginaGramatica) -> tuple[CasamentoGramatica, ...]:
    return casar_variantes(pagina, _pares())


def _variantes(pagina: PaginaGramatica) -> set[str]:
    return {str(c.variante["id"]) for c in _casamentos(pagina)}


def _desenhada(desenhar: Callable[[pymupdf.Page], object]) -> set[str]:
    return _variantes(pagina_desenhada(desenhar))


def _um_desenho(pagina: PaginaGramatica) -> CasamentoGramatica:
    """O casamento do único desenho da página: todas as variantes casam a mesma caixa."""
    casamentos = _casamentos(pagina)
    assert len({(c.caixa, c.caminho, c.componentes) for c in casamentos}) == 1
    return casamentos[0]


def _contem(caixa: Caixa, ponto: Ponto) -> bool:
    return (
        caixa[0] - _EPSILON <= ponto[0] <= caixa[2] + _EPSILON
        and caixa[1] - _EPSILON <= ponto[1] <= caixa[3] + _EPSILON
    )


def _caixa_dos(pontos: Sequence[Ponto]) -> Caixa:
    return (
        min(p[0] for p in pontos),
        min(p[1] for p in pontos),
        max(p[0] for p in pontos),
        max(p[1] for p in pontos),
    )


def _caixa_do_pictograma(grupo: Grupo, centro: Ponto, graus: float) -> Caixa:
    """A caixa esperada: o círculo envolvente (72 retas, raio exato nos eixos) ou o triângulo."""
    if grupo[1] == "ellipse":
        raio = raio_envolvente()
        return (centro[0] - raio, centro[1] - raio, centro[0] + raio, centro[1] + raio)
    return _caixa_dos(vertices(centro, graus))


def _poligono(
    pagina: pymupdf.Page,
    pontos: Sequence[Ponto],
    cor: Cor | None,
    fill: Cor | None,
    *,
    dashes: str | None = None,
) -> None:
    pagina.draw_polyline(
        [*pontos, pontos[0]], color=cor, fill=fill, width=0.14, closePath=True, dashes=dashes
    )


def _meio(p: Ponto, q: Ponto) -> Ponto:
    return (p[0] + q[0]) / 2, (p[1] + q[1]) / 2


def _indice_do_traco(pagina: PaginaGramatica, p0: Ponto, p1: Ponto) -> int:
    """A posição do caminho de um traço só de `p0` a `p1`, em qualquer sentido."""
    achados = [
        posicao
        for posicao, caminho in enumerate(pagina.modelo.caminhos)
        if len(caminho.subcaminhos) == 1
        and len(caminho.subcaminhos[0]) == 1
        and caminho.subcaminhos[0][0].tipo == "l"
        and {
            (round(x, 2), round(y, 2))
            for x, y in (caminho.subcaminhos[0][0].pontos[0], caminho.subcaminhos[0][0].pontos[-1])
        }
        == {(round(p0[0], 2), round(p0[1], 2)), (round(p1[0], 2), round(p1[1], 2))}
    ]
    assert len(achados) == 1
    return achados[0]


# Falsos positivos ------------------------------------------------------------------------------


def _verde_solido_na_linha_ao_lado_do_poste(pagina: pymupdf.Page) -> None:
    """Triângulo verde de um preenchimento só, sobre uma linha de rede e ao lado de um poste."""
    pagina.draw_line((CENTRO[0] - 8 * LADO, CENTRO[1]), (CENTRO[0] + 8 * LADO, CENTRO[1]))
    _poligono(pagina, vertices(), VERDE, VERDE)
    pagina.draw_circle((CENTRO[0] + 2 * LADO, CENTRO[1]), LADO / 3, color=PRETO, width=0.14)


def _verde_com_haste_para_a_linha(pagina: pymupdf.Page) -> None:
    """O verde sólido ligado por haste a uma linha: a haste não salva um preenchimento opaco."""
    a, _, _ = vertices()
    fora = ponta_da_haste()
    _poligono(pagina, vertices(), VERDE, VERDE)
    pagina.draw_line(a, fora, color=PRETO, width=0.14)
    pagina.draw_line((fora[0] - 5 * LADO, fora[1]), (fora[0] + 5 * LADO, fora[1]), color=PRETO)


def _ponta_de_seta_equilatera(pagina: pymupdf.Page) -> None:
    """Ponta de seta quase equilátera, cheia e de traço, presa no fim de uma linha longa: a seta
    da fixture do desenvolvedor tem lados 1,42 vez diferentes e cai pela forma, não pelo cheio."""
    a, b, c = vertices(lado=LADO / 2)
    m = _meio(b, c)
    pagina.draw_line((m[0], m[1] + 10 * LADO), m, color=PRETO, width=0.3)
    _poligono(pagina, [a, b, c], PRETO, PRETO)


def _ponta_de_seta_sem_traco(pagina: pymupdf.Page) -> None:
    a, b, c = vertices(lado=LADO / 2)
    pagina.draw_line((a[0], a[1] + 10 * LADO), a, color=PRETO, width=0.3)
    _poligono(pagina, [a, b, c], None, PRETO)


def _ciano_inteiro_com_contorno_separado(pagina: pymupdf.Page) -> None:
    _poligono(pagina, vertices(), None, CIANO)
    _poligono(pagina, vertices(), PRETO, None)


def _so_metade_ciano(pagina: pymupdf.Page) -> None:
    """A metade ciano sozinha, como uma amostra de cor de legenda: não é equilátera."""
    a, b, c = vertices()
    _poligono(pagina, [_meio(b, c), a, b], None, CIANO)


def _so_metade_verde(pagina: pymupdf.Page) -> None:
    a, b, c = vertices()
    _poligono(pagina, [_meio(b, c), a, c], PRETO, VERDE)


def _regulador_com_seta_cheia(pagina: pymupdf.Page) -> None:
    """Círculo atravessado por seta de ponta cheia, o regulador fora de escopo."""
    pagina.draw_circle(CENTRO, LADO * 0.75, color=PRETO, width=0.14)
    inicio = (CENTRO[0] - LADO * 1.25, CENTRO[1] + LADO * 1.25)
    fim = (CENTRO[0] + LADO, CENTRO[1] - LADO)
    pagina.draw_line(inicio, fim, color=PRETO, width=0.14)
    d = (math.sqrt(0.5), -math.sqrt(0.5))
    n = (-d[1], d[0])
    ponta = (fim[0] + d[0] * LADO * 0.4, fim[1] + d[1] * LADO * 0.4)
    largura = LADO / 4
    b = (fim[0] + n[0] * largura, fim[1] + n[1] * largura)
    c = (fim[0] - n[0] * largura, fim[1] - n[1] * largura)
    _poligono(pagina, [ponta, b, c], PRETO, PRETO)


def _muito_maior_que_o_maximo(pagina: pymupdf.Page) -> None:
    desenhar_trafo(pagina, "outline", lado=LADO * 10)


def _moldura_meio_ciano_gigante(pagina: pymupdf.Page) -> None:
    """O meio ciano com lado de 5 vezes o normal, ainda dentro do `max_span` de 72."""
    desenhar_trafo(pagina, "half_cyan", lado=LADO * 5)


_NEGATIVOS_QUE_PASSAM: Final[dict[str, Callable[[pymupdf.Page], object]]] = {
    "verde_solido_na_linha_ao_lado_do_poste": _verde_solido_na_linha_ao_lado_do_poste,
    "verde_solido_com_haste_para_a_linha": _verde_com_haste_para_a_linha,
    "ponta_de_seta_equilatera_cheia": _ponta_de_seta_equilatera,
    "ponta_de_seta_cheia_sem_traco": _ponta_de_seta_sem_traco,
    "ciano_inteiro_com_contorno_separado": _ciano_inteiro_com_contorno_separado,
    "so_metade_ciano": _so_metade_ciano,
    "so_metade_verde": _so_metade_verde,
    "regulador_com_seta_cheia": _regulador_com_seta_cheia,
    "muito_maior_que_o_maximo": _muito_maior_que_o_maximo,
    "meio_ciano_de_lado_cinco_vezes": _moldura_meio_ciano_gigante,
}


@pytest.mark.parametrize("nome", sorted(_NEGATIVOS_QUE_PASSAM))
def test_negativo_adicional_nao_casa(nome: str) -> None:
    assert _desenhada(_NEGATIVOS_QUE_PASSAM[nome]) == set()


def test_o_controle_dos_negativos_casa() -> None:
    """Controle: o contorno preto do mesmo tamanho, no mesmo lugar, casa o contorno base. Os
    negativos acima não são vazios por falta de leitura do desenho."""
    assert _desenhada(lambda p: _poligono(p, vertices(), PRETO, None)) == variantes_do_grupo(
        _BASE_CONTORNO
    )
    assert _desenhada(lambda p: _poligono(p, vertices(lado=LADO / 2), PRETO, None)) == (
        variantes_do_grupo(_BASE_CONTORNO)
    )


def test_triangulo_de_traco_tracejado_nao_casa() -> None:
    """Um triângulo tracejado não é o pictograma do transformador (traço contínuo)."""
    pagina = pagina_desenhada(lambda p: _poligono(p, vertices(), PRETO, None, dashes="[1 1] 0"))
    assert any(c.estilo.tracejado for c in pagina.modelo.caminhos)

    assert _variantes(pagina) == set()


def test_contorno_roxo_com_s_nao_casa() -> None:
    """v016 a v018 (roxo com S) estão fora de escopo. O E05 reconhece o roxo pelo traço do contorno
    (`_forma_triangular`); a fixture do desenvolvedor só tenta o roxo cheio, que cai pelo opaco."""

    def desenhar(p: pymupdf.Page) -> None:
        _poligono(p, vertices(), ROXO, None)
        p.insert_text((CENTRO[0] - 2, CENTRO[1] + 2), "S", fontsize=5, color=ROXO)

    assert _desenhada(desenhar) == set()


def _gravata_num_caminho(pagina: pymupdf.Page) -> None:
    a, b, c = vertices()
    d = (2 * a[0] - b[0], 2 * a[1] - b[1])
    e = (2 * a[0] - c[0], 2 * a[1] - c[1])
    pagina.draw_polyline([a, b, c, a, d, e, a], color=PRETO, width=0.14)


def _gravata_em_dois_caminhos(pagina: pymupdf.Page) -> None:
    a, b, c = vertices()
    d = (2 * a[0] - b[0], 2 * a[1] - b[1])
    e = (2 * a[0] - c[0], 2 * a[1] - c[1])
    _poligono(pagina, [a, b, c], PRETO, None)
    _poligono(pagina, [a, d, e], PRETO, None)


@pytest.mark.parametrize(
    "desenhar",
    [
        pytest.param(_gravata_num_caminho, id="num_caminho"),
        pytest.param(_gravata_em_dois_caminhos, id="dois_caminhos"),
    ],
)
def test_gravata_de_dois_triangulos_que_se_tocam_nao_casa(
    desenhar: Callable[[pymupdf.Page], object],
) -> None:
    """Dois triângulos pelo ápice (gravata): nenhum dos dois é o pictograma isolado."""
    assert _desenhada(desenhar) == set()


def test_triangulo_ciano_inteiro_em_duas_metades_nao_casa() -> None:
    """O ciano inteiro é negativo (plano); desenhado em duas metades ciano, é o mesmo desenho."""

    def desenhar(p: pymupdf.Page) -> None:
        a, b, c = vertices()
        m = _meio(b, c)
        _poligono(p, [a, b, c], PRETO, None)
        _poligono(p, [m, a, b], None, CIANO)
        _poligono(p, [m, a, c], None, CIANO)

    assert _desenhada(desenhar) == set()


# Grupos ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_cada_desenho_casa_so_o_seu_grupo_e_cada_grupo_tem_um_desenho(grupo: Grupo) -> None:
    """Os 6 desenhos numa página: cada caixa casa exatamente as variantes de um grupo, e cada
    grupo casa exatamente uma caixa."""

    def desenhar(p: pymupdf.Page) -> None:
        for i, seu in enumerate(GRUPOS):
            desenhar_grupo(p, seu, centro=(40.0 + 45.0 * i, 150.0))

    casamentos = _casamentos(pagina_desenhada(desenhar))
    por_caixa: dict[Caixa, set[str]] = {}
    for c in casamentos:
        por_caixa.setdefault(c.caixa, set()).add(str(c.variante["id"]))

    assert len(por_caixa) == len(GRUPOS)
    assert sum(1 for ids in por_caixa.values() if ids == variantes_do_grupo(grupo)) == 1


@pytest.mark.parametrize(
    "cor", [VERMELHO, VERDE, ROXO, PRETO], ids=["vermelho", "verde", "roxo", "preto"]
)
@pytest.mark.parametrize("enclosure", ["none", "ellipse"])
@pytest.mark.parametrize("x", [False, True], ids=["sem_x", "x"])
def test_metade_cheia_de_cor_nao_ciano_e_outline_no_grupo_do_marcador(
    cor: Cor, enclosure: str, x: bool
) -> None:
    """Ruling: metade de outra cor é `outline`; o marcador (X vence a envolvente) segue valendo."""

    def desenhar(p: pymupdf.Page) -> None:
        desenhar_trafo(p, "half_cyan", cor_da_metade=cor, envolvente=enclosure == "ellipse", x=x)

    esperado: Grupo = ("outline", "none", True) if x else ("outline", enclosure, False)
    assert _desenhada(desenhar) == variantes_do_grupo(esperado)


def test_metades_trocadas_ainda_sao_meio_ciano() -> None:
    """O ciano do outro lado da mediana: o lado não decide."""

    def desenhar(p: pymupdf.Page) -> None:
        a, b, c = vertices()
        m = _meio(b, c)
        _poligono(p, [a, b, c], PRETO, None)
        _poligono(p, [m, a, b], None, BRANCO)
        _poligono(p, [m, a, c], None, CIANO)

    assert _desenhada(desenhar) == variantes_do_grupo(_BASE_MEIO_CIANO)


def test_metade_ciano_sobre_fundo_branco_inteiro_e_meio_ciano() -> None:
    """Fundo branco do triângulo inteiro e a metade ciano por cima: o ciano decide o `fill`
    (R-E06.3.3.2.2-1, como `_toca_ciano`), e o desenho é o meio ciano à vista."""

    def desenhar(p: pymupdf.Page) -> None:
        a, b, c = vertices()
        _poligono(p, [a, b, c], PRETO, BRANCO)
        _poligono(p, [_meio(b, c), a, b], None, CIANO)

    assert _desenhada(desenhar) == variantes_do_grupo(_BASE_MEIO_CIANO)


@pytest.mark.parametrize("fill", ["half_cyan", "outline"])
def test_x_do_vizinho_nao_marca_o_triangulo_ao_lado(fill: str) -> None:
    """Dois pictogramas a 1,8 lado: o X de um não leva o outro para o grupo do X."""

    def desenhar(p: pymupdf.Page) -> None:
        desenhar_trafo(p, fill, centro=CENTRO, x=True)
        desenhar_trafo(p, fill, centro=(CENTRO[0] + 1.8 * LADO, CENTRO[1]))

    por_caixa: dict[float, set[str]] = {}
    for c in _casamentos(pagina_desenhada(desenhar)):
        por_caixa.setdefault(round(c.caixa[0]), set()).add(str(c.variante["id"]))

    assert sorted(por_caixa.values(), key=sorted) == sorted(
        [variantes_do_grupo((fill, "none", True)), variantes_do_grupo((fill, "none", False))],
        key=sorted,
    )


# Rotações --------------------------------------------------------------------------------------


@pytest.mark.parametrize("graus", [0.0, 45.0, 90.0, 180.0], ids=["0", "45", "90", "180"])
@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_rotacao_mantem_o_grupo_e_a_caixa(grupo: Grupo, graus: float) -> None:
    casamento = _um_desenho(pagina_desenhada(lambda p: desenhar_grupo(p, grupo, graus)))

    assert _desenhada(lambda p: desenhar_grupo(p, grupo, graus)) == variantes_do_grupo(grupo)
    assert casamento.caixa == pytest.approx(
        _caixa_do_pictograma(grupo, CENTRO, graus), abs=_TOLERANCIA_CAIXA
    )
    assert not _contem(casamento.caixa, ponta_da_haste(CENTRO, graus))
    if grupo[2]:
        assert not any(
            _contem(casamento.caixa, p) for braco in bracos_x(graus=graus) for p in braco
        )


@pytest.mark.parametrize("rotacao", [90, 180, 270])
@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_pagina_com_rotate_mantem_o_grupo_e_a_caixa_exibida(grupo: Grupo, rotacao: int) -> None:
    """Fora do centro da página, para a rotação mover o desenho: a caixa é a da página exibida."""
    centro: Ponto = (100.0, 80.0)
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        desenhar_grupo(pagina, grupo, centro=centro)
        pagina.set_rotation(rotacao)
        matriz = pagina.rotation_matrix
        exibida = pagina_para_gramaticas(pagina, 0)

    def exibir(ponto: Ponto) -> Ponto:
        x, y = ponto
        return (matriz.a * x + matriz.c * y + matriz.e, matriz.b * x + matriz.d * y + matriz.f)

    assert _variantes(exibida) == variantes_do_grupo(grupo)
    caixa = _um_desenho(exibida).caixa
    if grupo[1] == "ellipse":
        cx, cy = exibir(centro)
        raio = raio_envolvente()
        esperada = (cx - raio, cy - raio, cx + raio, cy + raio)
    else:
        esperada = _caixa_dos([exibir(v) for v in vertices(centro)])
    assert caixa == pytest.approx(esperada, abs=_TOLERANCIA_CAIXA)
    assert not _contem(caixa, exibir(ponta_da_haste(centro)))
    if grupo[2]:
        assert not any(_contem(caixa, exibir(p)) for braco in bracos_x(centro) for p in braco)


# Escala ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lado", "origem"),
    [
        pytest.param(LADO / 10, "glifo", id="lado_1_2_em_glifo"),
        pytest.param(LADO / 6, "nativo", id="lado_2_em_nativo"),
        pytest.param(LADO / 6, "shx", id="lado_2_em_shx"),
    ],
)
@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_triangulo_do_tamanho_de_glifo_nao_casa(grupo: Grupo, lado: float, origem: str) -> None:
    caminhos = caminhos_trafo(grupo, CENTRO, lado)

    assert _variantes(pagina_com_texto(caminhos, origem)) == set()  # type: ignore[arg-type]


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_max_span_mede_a_caixa_do_pictograma(grupo: Grupo) -> None:
    """Entre o lado do triângulo e o diâmetro da envolvente: só o grupo da envolvente cai. O X,
    que vai além do triângulo, não conta: a caixa do grupo do X é o triângulo."""
    pagina = pagina_desenhada(lambda p: desenhar_grupo(p, grupo))
    gramatica = dict(CASOS_TRIANGULO)[min(variantes_do_grupo(grupo))]
    entre = (LADO + 2 * raio_envolvente()) / 2
    assert LADO < entre < 2 * raio_envolvente()
    assert LADO < entre < 2 * LADO * 0.7  # o X tem meia diagonal de 0,7 lado
    gramatica_estreita = {**gramatica, "max_span": entre}

    achados = casa_triangulos(contexto_gramaticas(pagina), gramatica_estreita)

    assert len(achados) == (0 if grupo[1] == "ellipse" else 1)


# Componentes -----------------------------------------------------------------------------------


_OPCOES_DE_DESENHO: Final[dict[str, dict[str, Any]]] = {
    "padrao": {},
    "sem_haste": {"haste": False},
    "linha_de_rede": {"linha_de_rede": True},
    "lados_soltos": {"contorno": "lados"},
    "mediana_no_contorno": {"contorno": "mediana"},
    "metades_sem_traco": {"metades": "sem_traco"},
    "hachura": {"metades": "hachura"},
    "circulo_bezier": {"forma_envolvente": "circulo"},
    "girado_45": {"graus": 45.0},
}


@pytest.mark.parametrize("opcao", sorted(_OPCOES_DE_DESENHO))
@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_componentes_sao_o_desenho_inteiro_sem_a_ancora_e_sem_repetir(
    grupo: Grupo, opcao: str
) -> None:
    """Âncora mais componentes são todos os caminhos do pictograma: contorno, metades, haste
    (quando há), envolvente e X; a linha de rede fica de fora, e nada se repete."""
    opcoes = dict(_OPCOES_DE_DESENHO[opcao])
    graus = float(opcoes.pop("graus", 0.0))
    pagina = pagina_desenhada(lambda p: desenhar_grupo(p, grupo, graus, **opcoes))
    casamento = _um_desenho(pagina)
    todos = set(range(len(pagina.modelo.caminhos)))
    if opcoes.get("linha_de_rede"):
        fora = ponta_da_haste(CENTRO, graus)
        rede = _indice_do_traco(
            pagina,
            (fora[0] - 60.0, fora[1]),
            (fora[0] + 60.0, fora[1]),
        )
        todos.discard(rede)
        assert rede not in casamento.componentes
    if opcoes.get("haste", True) or opcoes.get("linha_de_rede"):
        haste = _indice_do_traco(pagina, vertices(CENTRO, graus)[0], ponta_da_haste(CENTRO, graus))
        assert haste in casamento.componentes

    assert casamento.caminho not in casamento.componentes
    assert list(casamento.componentes) == sorted(set(casamento.componentes))
    assert {casamento.caminho, *casamento.componentes} == todos


@pytest.mark.parametrize("x", [False, True], ids=["sem_x", "x"])
def test_metades_de_cor_nao_ciano_entram_nos_componentes(x: bool) -> None:
    """No `outline` de metade cheia de outra cor (ruling), as duas metades são preenchimentos do
    pictograma (R-E06.3.3.2.2-3): ficam nos componentes, e não sobram no resíduo."""
    pagina = pagina_desenhada(lambda p: desenhar_trafo(p, "half_cyan", cor_da_metade=VERMELHO, x=x))
    casamento = _um_desenho(pagina)

    assert {casamento.caminho, *casamento.componentes} == set(range(len(pagina.modelo.caminhos)))


# Contexto --------------------------------------------------------------------------------------


def test_candidatos_misturados_de_dois_contextos_recusa() -> None:
    pagina = pagina_desenhada(lambda p: desenhar_trafo(p, "outline"))
    contexto = contexto_gramaticas(pagina)
    meus = triangulos_candidatos(contexto)
    alheios = triangulos_candidatos(contexto_gramaticas(pagina))
    assert meus
    assert alheios

    with pytest.raises(ValueError, match="outro contexto"):
        casa_triangulos(contexto, CASOS_TRIANGULO[0][1], candidatos=(*meus, *alheios))


def test_candidatos_vazios_sao_respeitados_e_nao_recalculados() -> None:
    pagina = pagina_desenhada(lambda p: desenhar_trafo(p, "outline"))
    contexto = contexto_gramaticas(pagina)
    gramatica = dict(CASOS_TRIANGULO)["cemig-eo-r3-s18-v007"]
    antes = contexto.orcamento.gasto

    assert casa_triangulos(contexto, gramatica, candidatos=()) == []
    assert contexto.orcamento.gasto == antes
    assert len(casa_triangulos(contexto, gramatica)) == 1


# Gasto -----------------------------------------------------------------------------------------


def test_triangulos_candidatos_roda_uma_vez_por_pagina(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[int] = []
    original = vars(symbol_matcher)["triangulos_candidatos"]

    def contar(*args: Any, **kwargs: Any) -> Any:
        chamadas.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(symbol_matcher, "triangulos_candidatos", contar)
    pagina = pagina_desenhada(lambda p: desenhar_trafo(p, "half_cyan", x=True))

    assert len(casar_variantes(pagina, _pares())) == len(
        variantes_do_grupo(("half_cyan", "none", True))
    )
    assert len(chamadas) == 1


def test_sem_variante_de_triangulo_nao_classifica(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[int] = []
    original = vars(symbol_matcher)["triangulos_candidatos"]

    def contar(*args: Any, **kwargs: Any) -> Any:
        chamadas.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(symbol_matcher, "triangulos_candidatos", contar)
    pagina = pagina_desenhada(lambda p: desenhar_trafo(p, "outline"))

    casar_variantes(pagina, _pares(CASOS_RECT_DIAGONAL[:1]))

    assert chamadas == []


def _grade_de_contornos(n: int) -> PaginaGramatica:
    """`n` contornos base, 10 por fileira, a 80 pt um do outro: a densidade não muda com `n`."""
    passo = 80.0
    fileiras = math.ceil(n / 10)

    def desenhar(p: pymupdf.Page) -> None:
        for i in range(n):
            desenhar_trafo(p, "outline", centro=(30.0 + (i % 10) * passo, 30.0 + (i // 10) * passo))

    return pagina_desenhada(desenhar, largura=60.0 + 10 * passo, altura=60.0 + fileiras * passo)


def test_gasto_cresce_linear_com_os_triangulos() -> None:
    dez = gasto_por_fase(_grade_de_contornos(10), _pares())
    cem = gasto_por_fase(_grade_de_contornos(100), _pares())

    assert dez.gramaticas > 0
    assert cem.gramaticas <= 10 * dez.gramaticas * 1.1
    assert cem.indices <= 10 * dez.indices * 1.1


def test_trabalho_fora_do_orcamento_cresce_linear_com_os_triangulos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_contornos` compara cada contorno com todas as formas já aceitas (`_mesmo_triangulo`, na
    busca do `igual`), sem gastar do orçamento. Contornos longe uns dos outros não deveriam ser
    comparados: o trabalho tem de crescer como o gasto, linear, ou o teto (Task 5) não o vê."""
    chamadas: list[int] = []
    original = grammar_triangulo._mesmo_triangulo

    def contar(*args: Any) -> bool:
        chamadas.append(1)
        return original(*args)

    monkeypatch.setattr(grammar_triangulo, "_mesmo_triangulo", contar)
    gasto_por_fase(_grade_de_contornos(10), _pares())
    dez = len(chamadas)
    chamadas.clear()
    gasto_por_fase(_grade_de_contornos(100), _pares())
    cem = len(chamadas)

    assert dez > 0
    assert cem <= 10 * dez * 1.5, f"10 triângulos: {dez} comparações; 100: {cem}"


# E05 (R-E06.3.3.2.2-5) -------------------------------------------------------------------------


def _observacao_e05(desenhar: Callable[[pymupdf.Page], object]) -> list[ObservacaoSimbolo]:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        desenhar(pagina)
        resultado = observar_transformadores(
            pagina, documento_id="autoral", documento_sha256="0" * 64, pagina_numero=1
        )
    return [o for o in resultado.observacoes if o.alternativas[0].classe == "TRANSFORMADOR"]


def _papeis_e05(observacao: ObservacaoSimbolo) -> list[str]:
    componentes = json.loads(str(dict(observacao.atributos)["componentes"]))
    return [str(c["tipo"]) for c in componentes]


def _caixa_e05(observacao: ObservacaoSimbolo) -> Caixa:
    return _caixa_dos([(float(x), float(y)) for x, y in observacao.geometria.pontos_originais])


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_trafo_e05_e_lido_pelo_e05_pelos_marcadores_certos(grupo: Grupo) -> None:
    """A R-5 conferida por dentro, e não só pelas referências: o E05 lê o contorno, o ciano
    (`preenchimento_ciano`), a envolvente e o X do desenho. O suporte observado é a haste
    externa no `outline` e o eixo interno (a aresta da mediana das metades) no `half_cyan`."""
    (observacao,) = _observacao_e05(lambda p: desenhar_trafo_e05(p, grupo))
    papeis = _papeis_e05(observacao)
    atributos = dict(observacao.atributos)

    assert papeis[0] == "contorno_triangular"
    assert papeis[1] == ("eixo_interno" if grupo[0] == "half_cyan" else "haste_externa")
    assert ("preenchimento_ciano" in papeis) == (grupo[0] == "half_cyan")
    assert ("envoltoria" in papeis) == (grupo[1] == "ellipse")
    assert ("x_vermelho" in papeis) == grupo[2]
    assert atributos["variante_grafica"] == (
        "triangulo_meio_ciano" if grupo[0] == "half_cyan" else "triangulo"
    )


@pytest.mark.parametrize("grupo", [g for g in GRUPOS if g[0] == "outline"], ids=_id_grupo)
def test_sem_a_haste_o_e05_nao_le_o_contorno(grupo: Grupo) -> None:
    """A haste do `desenhar_trafo_e05` é o que faz o E05 ler o contorno (não é por acaso): o
    mesmo desenho sem ela não é observado, e a gramática nova, que não exige haste, ainda casa."""
    _, enclosure, removal = grupo

    def desenhar(p: pymupdf.Page) -> None:
        _poligono(p, vertices(), PRETO, None)
        if enclosure == "ellipse":
            p.draw_circle(CENTRO, raio_envolvente(), color=PRETO, width=0.14)
        if removal:
            for p0, p1 in bracos_x():
                p.draw_line(p0, p1, color=VERMELHO, width=0.5)

    assert _observacao_e05(desenhar) == []
    assert _desenhada(desenhar) == variantes_do_grupo(grupo)


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_caixa_da_gramatica_dentro_da_do_e05(grupo: Grupo) -> None:
    """A diferença de caixa da R-5: o E05 soma os extremos do X, a gramática não. Sem X, as
    caixas são iguais; com X, a da gramática fica dentro da do E05."""
    (observacao,) = _observacao_e05(lambda p: desenhar_trafo_e05(p, grupo))
    do_e05 = _caixa_e05(observacao)
    da_gramatica = _um_desenho(pagina_desenhada(lambda p: desenhar_trafo_e05(p, grupo))).caixa

    if grupo[2]:
        assert do_e05[0] < da_gramatica[0] - 1 and do_e05[2] > da_gramatica[2] + 1
        assert do_e05[1] < da_gramatica[1] and do_e05[3] > da_gramatica[3]
    else:
        assert da_gramatica == pytest.approx(do_e05, abs=_EPSILON)


def test_trafo_e05_sem_ciano_cai_no_outline_nos_dois_metodos() -> None:
    """Contraprova do ciano: a metade ciano do desenho do E05 trocada por verde leva o E05 às
    referências do contorno e a gramática ao `outline`."""

    def desenhar(p: pymupdf.Page) -> None:
        a, b, c = vertices()
        m = _meio(b, c)
        _poligono(p, [m, a, b], None, VERDE)
        _poligono(p, [m, a, c], None, BRANCO)
        _poligono(p, [a, b, c], PRETO, None)
        p.draw_line(a, ponta_da_haste(), color=PRETO, width=0.14)

    (observacao,) = _observacao_e05(desenhar)
    referencias = set(json.loads(str(dict(observacao.atributos)["referencias_possiveis"])))

    assert referencias == {v for v, g in GRUPO_DA_VARIANTE.items() if g[0] == "outline"}
    assert _desenhada(desenhar) == variantes_do_grupo(_BASE_CONTORNO)


# Formas comuns (Task 2) com esta gramática -----------------------------------------------------


@pytest.fixture(scope="module")
def tabela() -> TabelaGlifos:
    return carregar_tabela_glifos()


def _id_autoral(variante: str) -> str:
    return variante.replace("cemig-eo-r3-s18", "autoral-trafo")


def _variante(
    variante_id: str, gramatica: Mapping[str, Any], classe: str = "TRANSFORMADOR"
) -> Pacote:
    return {
        "id": variante_id,
        "class_code": classe,
        "role": "operational",
        "destination": "equipment_review",
        "source_ref": {
            "source_id": "F02",
            "pdf_page": 1,
            "locator": "desenho autoral",
            "review_status": "synthetic_fixture",
        },
        "visual_note": "Triângulo autoral",
        "recognition": {
            "status": "enabled",
            "grammar": dict(gramatica),
            "negative_examples": ["triângulo verde sólido"],
        },
    }


def _carrega(tmp_path: Path, variantes: Sequence[Pacote]) -> tuple[Pacote, ...]:
    pacote = {
        "schema_version": 1,
        "family_id": _FAMILIA,
        "profile_id": "profile-autoral",
        "source_id": "F02",
        "variants": list(variantes),
    }
    (tmp_path / f"{_FAMILIA}.json").write_text(json.dumps(pacote), encoding="utf-8")
    return carregar_pacotes(packages_dir=tmp_path)


def _observar(
    pacotes: tuple[Pacote, ...],
    tabela: TabelaGlifos,
    desenhar: Callable[[pymupdf.Page], object],
) -> tuple[ObservacaoSimbolo, ...]:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        desenhar(pagina)
        resultado = observar_pacotes_modelo(
            pagina,
            documento_id="formas-comuns-trafo",
            documento_sha256=_SHA,
            pagina_numero=1,
            pacotes=pacotes,
            tabela=tabela,
        )
    return resultado.observacoes


@pytest.mark.parametrize(
    "grupo",
    [g for g in GRUPOS if len(variantes_do_grupo(g)) > 1],
    ids=_id_grupo,
)
def test_variantes_do_mesmo_grupo_viram_uma_observacao_com_a_lista(
    tmp_path: Path, tabela: TabelaGlifos, grupo: Grupo
) -> None:
    """Pacote sintético com as 2 ou 3 variantes do grupo (mesma gramática): uma observação, o
    menor id como representante e a lista ordenada."""
    ids = sorted(_id_autoral(v) for v in variantes_do_grupo(grupo))
    gramatica = dict(CASOS_TRIANGULO)[min(variantes_do_grupo(grupo))]
    # Fora da ordem de id: o representante não é o primeiro do pacote por acaso.
    pacotes = _carrega(tmp_path, [_variante(i, gramatica) for i in reversed(ids)])

    (observacao,) = _observar(pacotes, tabela, lambda p: desenhar_grupo(p, grupo))
    atributos = dict(observacao.atributos)

    assert observacao.template == ids[0]
    assert atributos["variante_inventario"] == ids[0]
    assert json.loads(str(atributos["referencias_possiveis"])) == ids
    assert atributos["gramatica"] == "split_triangle"
    assert [a.classe for a in observacao.alternativas] == ["TRANSFORMADOR"]


def test_as_15_variantes_dao_uma_observacao_por_desenho(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    """Os 6 desenhos e as 15 variantes: 6 observações, cada uma com a lista do seu grupo, e a
    reconciliação pede revisão por id ambíguo onde o grupo tem mais de um."""
    pacotes = _carrega(tmp_path, [_variante(_id_autoral(v), g) for v, g in CASOS_TRIANGULO])

    def desenhar(p: pymupdf.Page) -> None:
        for i, grupo in enumerate(GRUPOS):
            desenhar_grupo(p, grupo, centro=(40.0 + 45.0 * i, 150.0))

    observacoes = _observar(pacotes, tabela, desenhar)
    listas = sorted(
        json.loads(str(dict(o.atributos)["referencias_possiveis"]))
        if str(dict(o.atributos)["referencias_possiveis"]).startswith("[")
        else [str(dict(o.atributos)["referencias_possiveis"])]
        for o in observacoes
    )
    esperadas = sorted(sorted(_id_autoral(v) for v in variantes_do_grupo(g)) for g in GRUPOS)

    assert len(observacoes) == len(GRUPOS)
    assert listas == esperadas


def test_mesma_forma_de_classe_diferente_nao_se_agrupa(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    gramatica = dict(CASOS_TRIANGULO)["cemig-eo-r3-s18-v007"]
    pacotes = _carrega(
        tmp_path,
        [
            _variante("autoral-trafo-v007", gramatica),
            _variante("autoral-trafo-v010", gramatica),
            _variante("autoral-trafo-v013", gramatica, classe="REGULADOR_TENSAO"),
        ],
    )

    observacoes = _observar(pacotes, tabela, lambda p: desenhar_grupo(p, _BASE_CONTORNO))

    assert sorted(str(dict(o.atributos)["referencias_possiveis"]) for o in observacoes) == [
        json.dumps(["autoral-trafo-v007", "autoral-trafo-v010"]),
        "autoral-trafo-v013",
    ]


def test_reconciliacao_da_lista_do_triangulo_pede_revisao(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    ids = sorted(_id_autoral(v) for v in variantes_do_grupo(_BASE_CONTORNO))
    gramatica = dict(CASOS_TRIANGULO)["cemig-eo-r3-s18-v007"]
    pacotes = _carrega(tmp_path, [_variante(i, gramatica) for i in ids])

    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        desenhar_grupo(pagina, _BASE_CONTORNO)
        resultado = observar_pacotes_modelo(
            pagina,
            documento_id="formas-comuns-trafo",
            documento_sha256=_SHA,
            pagina_numero=1,
            pacotes=pacotes,
            tabela=tabela,
        )

    (ocorrencia,) = reconcile_symbols((resultado,), CalibrationPolicy()).occurrences

    assert len(ocorrencia.observations) == 1
    assert ocorrencia.reference_ids == tuple(ids)
    assert "ambiguous_reference_id" in ocorrencia.reasons
    assert ocorrencia.decision == "review"


# Guarda de fonte -------------------------------------------------------------------------------


def test_este_arquivo_passa_na_guarda_de_fonte() -> None:
    """A guarda de `_GRAMATICAS_NOVAS` (fonte, comentários, bytes e inteiros) neste arquivo."""
    fonte = _ARQUIVO.read_text(encoding="utf-8")

    assert _violacoes_de_fonte(fonte, _ARQUIVO.name) == []
    assert _violacoes_de_comentarios(fonte, _ARQUIVO.name) == []
    assert _violacoes_de_bytes_e_inteiros(fonte, _ARQUIVO.name) == []


# Lacunas da revisão da Task 3 (rulings do orquestrador) -----------------------------------------


def _wipeout(pagina: pymupdf.Page, *, branca_duplicada: bool = False) -> None:
    """Fundo branco inteiro de traço preto, com as duas metades sem traço por cima: a ciano e a
    branca (duas vezes, com `branca_duplicada`)."""
    a, b, c = vertices()
    m = _meio(b, c)
    _poligono(pagina, [a, b, c], PRETO, BRANCO)
    _poligono(pagina, [m, a, b], None, CIANO)
    for _ in range(2 if branca_duplicada else 1):
        _poligono(pagina, [m, a, c], None, BRANCO)


@pytest.mark.parametrize("branca_duplicada", [False, True], ids=["branca_uma_vez", "branca_duas"])
def test_wipeout_com_as_duas_metades_e_meio_ciano(branca_duplicada: bool) -> None:
    """Revisão I-1: o fundo branco inteiro e a metade branca formam, os dois, o mesmo triângulo
    com a metade ciano; o desenho é um meio ciano só, e não um ciano ambíguo recusado."""
    assert _desenhada(lambda p: _wipeout(p, branca_duplicada=branca_duplicada)) == (
        variantes_do_grupo(_BASE_MEIO_CIANO)
    )


def _triangulo_inscrito(lado: float) -> list[Ponto]:
    """Base no lado de baixo de um quadrado de lado `lado` e ápice no meio do lado de cima."""
    x0, y0 = CENTRO[0] - lado / 2, CENTRO[1] - lado / 2
    return [(CENTRO[0], y0), (x0, y0 + lado), (x0 + lado, y0 + lado)]


def test_triangulo_vazado_inscrito_num_quadrado_nao_casa() -> None:
    """Revisão I-2: a PLATAFORMA (`triangle_in_frame`, `fill: empty`) não é transformador."""

    def desenhar(p: pymupdf.Page) -> None:
        x0, y0 = CENTRO[0] - LADO / 2, CENTRO[1] - LADO / 2
        _poligono(
            p, [(x0, y0), (x0 + LADO, y0), (x0 + LADO, y0 + LADO), (x0, y0 + LADO)], PRETO, None
        )
        _poligono(p, _triangulo_inscrito(LADO), PRETO, None)

    assert _desenhada(desenhar) == set()


def test_controle_triangulo_inscrito_sem_o_quadrado_casa_o_contorno() -> None:
    """Controle do anterior: o mesmo triângulo, sem o quadrado, passa na forma e casa."""
    assert _desenhada(lambda p: _poligono(p, _triangulo_inscrito(LADO), PRETO, None)) == (
        variantes_do_grupo(_BASE_CONTORNO)
    )


def _seta_vazada_pela_base(pagina: pymupdf.Page) -> None:
    """Ponta de seta de traço, sem preenchimento, com a base apoiada no fim de uma linha longa."""
    a, b, c = vertices(lado=LADO / 2)
    m = _meio(b, c)
    pagina.draw_line((m[0], m[1] + 10 * LADO), m, color=PRETO, width=0.14)
    _poligono(pagina, [a, b, c], PRETO, None)


def _seta_vazada_pelo_lado(pagina: pymupdf.Page) -> None:
    """A mesma ponta vazada, com um lado apoiado no fim de uma linha longa perpendicular a ele."""
    a, b, _ = vertices(lado=LADO / 2)
    m = _meio(a, b)
    centro = _caixa_dos(vertices(lado=LADO / 2))
    cx, cy = (centro[0] + centro[2]) / 2, (centro[1] + centro[3]) / 2
    dx, dy = m[0] - cx, m[1] - cy
    norma = math.hypot(dx, dy)
    longe = (m[0] + dx / norma * 10 * LADO, m[1] + dy / norma * 10 * LADO)
    pagina.draw_line(longe, m, color=PRETO, width=0.14)
    _poligono(pagina, vertices(lado=LADO / 2), PRETO, None)


@pytest.mark.parametrize(
    "desenhar",
    [
        pytest.param(_seta_vazada_pela_base, id="pela_base"),
        pytest.param(_seta_vazada_pelo_lado, id="pelo_lado"),
    ],
)
def test_ponta_de_seta_vazada_no_fim_de_linha_nao_casa(
    desenhar: Callable[[pymupdf.Page], object],
) -> None:
    """Revisão I-2: a seta vazada encosta a base ou um lado na linha, e não um vértice."""
    assert _desenhada(desenhar) == set()


def test_controle_trafo_com_haste_do_vertice_para_a_linha_casa_o_contorno() -> None:
    """Controle da seta: a haste sai de um vértice para a linha (estilo `desenhar_trafo_e05`)."""

    def desenhar(p: pymupdf.Page) -> None:
        desenhar_trafo_e05(p, _BASE_CONTORNO)
        fora = ponta_da_haste()
        p.draw_line((fora[0] - 10 * LADO, fora[1]), (fora[0] + 10 * LADO, fora[1]), color=PRETO)

    assert _desenhada(desenhar) == variantes_do_grupo(_BASE_CONTORNO)


def _pictograma_de_contorno(
    pagina: pymupdf.Page, grupo: Grupo, cor: Cor, dashes: str | None
) -> None:
    """O pictograma do grupo com o contorno de `cor` e `dashes`; no `half_cyan`, as metades só de
    preenchimento (ciano e branca), sem traço, para o contorno ser o único traço do triângulo."""
    fill, enclosure, removal = grupo
    a, b, c = vertices()
    if fill == "half_cyan":
        m = _meio(b, c)
        _poligono(pagina, [m, a, b], None, CIANO)
        _poligono(pagina, [m, a, c], None, BRANCO)
    _poligono(pagina, [a, b, c], cor, None, dashes=dashes)
    pagina.draw_line(a, ponta_da_haste(), color=PRETO, width=0.14)
    if enclosure == "ellipse":
        pagina.draw_circle(CENTRO, raio_envolvente(), color=VERDE, width=0.14)
    if removal:
        for p0, p1 in bracos_x():
            pagina.draw_line(p0, p1, color=VERMELHO, width=0.5)


@pytest.mark.parametrize(
    ("cor", "dashes"),
    [pytest.param(PRETO, "[1 1] 0", id="tracejado"), pytest.param(ROXO, None, id="roxo")],
)
@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_contorno_tracejado_ou_roxo_nao_casa_em_nenhum_grupo(
    grupo: Grupo, cor: Cor, dashes: str | None
) -> None:
    """Revisão Minor 1: o tracejado e o roxo recusados também com as metades ciano e branca,
    que hoje formam o meio ciano sem passar pelo contorno."""
    assert _desenhada(lambda p: _pictograma_de_contorno(p, grupo, cor, dashes)) == set()


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_controle_contorno_preto_continuo_casa_o_grupo(grupo: Grupo) -> None:
    """Controle do anterior: o mesmo desenho de contorno preto contínuo casa o seu grupo."""
    assert _desenhada(lambda p: _pictograma_de_contorno(p, grupo, PRETO, None)) == (
        variantes_do_grupo(grupo)
    )


def test_metade_de_outra_cor_emitida_duas_vezes_continua_outline() -> None:
    """Revisão Minor 2: o mesmo preenchimento vermelho duas vezes não soma área em `_cheio`; o
    desenho segue a ruling da metade de outra cor, `outline`."""

    def desenhar(p: pymupdf.Page) -> None:
        a, b, c = vertices()
        m = _meio(b, c)
        _poligono(p, [a, b, c], PRETO, None)
        _poligono(p, [m, a, b], None, VERMELHO)
        _poligono(p, [m, a, b], None, VERMELHO)
        _poligono(p, [m, a, c], None, BRANCO)
        p.draw_line(a, ponta_da_haste(), color=PRETO, width=0.14)

    assert _desenhada(desenhar) == variantes_do_grupo(_BASE_CONTORNO)


# Onda final da revisão (rulings do orquestrador), páginas puras e relativas à escala -------------

_FOLGA_POR_FATIA: Final = 4
_FATIAS_LARGAS: Final = 1_000
# Corda (pt) de cada fatia com 4 vezes `_FATIAS_LARGAS`: abaixo de 5 pt a tolerância de colinear
# fica no mínimo absoluto (`_FECHAMENTO`), e a corda cresce com o número de fatias.
_CORDA_MAXIMA: Final = 4.9
_RAZAO_LINEAR: Final = 6


class _ContaDistancias:
    """`math` do módulo da gramática com `dist` contado: o trabalho de fato, não o relógio."""

    def __init__(self) -> None:
        self.chamadas = 0

    def __getattr__(self, nome: str) -> Any:
        return getattr(math, nome)

    def dist(self, p: Sequence[float], q: Sequence[float]) -> float:
        self.chamadas += 1
        return math.dist(p, q)


def _roda_de_fatias_largas(n: int) -> PaginaGramatica:
    """Um preenchimento ciano de `n` fatias triangulares largas em leque fechado (roda).

    Cada fatia vai do centro a dois pontos vizinhos de um círculo; a corda (mais larga que o
    fechamento) cresce com `n`, e o raio com o quadrado de `n`: coordenadas grandes. A envoltória
    tem os `n` pontos do círculo, todos quase colineares com os vizinhos, e `_sem_colineares`
    os tira um a um recomeçando do início.
    """
    corda = _CORDA_MAXIMA * n / (4 * _FATIAS_LARGAS)
    raio = corda * n / (2 * math.pi)
    centro = (raio + 10.0, raio + 10.0)
    pontos = [
        (
            centro[0] + raio * math.cos(2 * math.pi * k / n),
            centro[1] + raio * math.sin(2 * math.pi * k / n),
        )
        for k in range(n)
    ]
    subcaminhos = tuple(
        (
            ItemCaminho("l", (centro, pontos[k])),
            ItemCaminho("l", (pontos[k], pontos[(k + 1) % n])),
            ItemCaminho("l", (pontos[(k + 1) % n], centro)),
        )
        for k in range(n)
    )
    caminho = Caminho(subcaminhos, estilo(None, CIANO), "preenchimento", 0)
    lado = 2 * raio + 20.0
    return pagina_gramatica([caminho], largura=lado, altura=lado)


def _hachura_larga(monkeypatch: pytest.MonkeyPatch, n: int) -> tuple[int, int] | None:
    """(distâncias calculadas, gasto da gramática) da roda de `n` fatias, com o limite nos
    índices mais `_FOLGA_POR_FATIA` por fatia; None se o teto parou a leitura."""
    pagina = _roda_de_fatias_largas(n)
    indices = contexto_gramaticas(pagina).orcamento.gasto
    contexto = contexto_gramaticas(pagina, limite=indices + _FOLGA_POR_FATIA * n)
    contador = _ContaDistancias()
    with monkeypatch.context() as remendo:
        remendo.setattr(grammar_triangulo, "math", contador)
        try:
            triangulos_candidatos(contexto)
        except TetoGramaticasExcedido:
            return None
    return contador.chamadas, contexto.orcamento.gasto - indices


def test_hachura_de_fatias_largas_estoura_o_teto_ou_cresce_linear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Revisão I-1: a envoltória e `_sem_colineares` de um preenchimento de milhares de fatias
    largas trabalham sem gastar do orçamento. Com 4 vezes as fatias, ou o teto (índices mais uma
    folga pequena por fatia) para a leitura, ou o trabalho e o gasto crescem no máximo
    `_RAZAO_LINEAR` vezes."""
    pequeno = _hachura_larga(monkeypatch, _FATIAS_LARGAS)
    grande = _hachura_larga(monkeypatch, 4 * _FATIAS_LARGAS)

    if grande is None:
        return
    assert pequeno is not None, "o teto parou a roda pequena e deixou passar a grande"
    (trabalho_pequeno, gasto_pequeno), (trabalho_grande, gasto_grande) = pequeno, grande
    assert trabalho_pequeno > 0
    assert trabalho_grande <= _RAZAO_LINEAR * trabalho_pequeno, (
        f"{_FATIAS_LARGAS} fatias: {trabalho_pequeno} distâncias e gasto {gasto_pequeno}; "
        f"{4 * _FATIAS_LARGAS}: {trabalho_grande} distâncias e gasto {gasto_grande}"
    )
    assert gasto_grande <= _RAZAO_LINEAR * max(gasto_pequeno, 1)


def _palavra_longe(origem: str) -> TextoModelo:
    """Uma palavra longe do desenho: dá à página o perfil da `origem` nos dois lados do teste."""
    return texto("LIVRE", (5.0, 5.0, 30.0, 12.0), origem)  # type: ignore[arg-type]


def _digito_no_centro() -> TextoModelo:
    """Um dígito de glifo no centro do triângulo de lado `LADO` (o Δ de revisão)."""
    meio = LADO / 8
    caixa = (CENTRO[0] - meio, CENTRO[1] - meio, CENTRO[0] + meio, CENTRO[1] + 2 * meio)
    return texto("1", caixa, "glifo")


def test_triangulo_de_traco_com_digito_de_glifo_dentro_nao_casa() -> None:
    """Revisão I-2: o triângulo equilátero de traço com um número dentro é o Δ de revisão."""
    pagina = pagina_gramatica(
        [poligono(vertices())], textos=(_palavra_longe("glifo"), _digito_no_centro())
    )
    assert _variantes(pagina) == set()


def test_controle_triangulo_de_traco_sem_o_digito_casa_o_contorno() -> None:
    """Controle do anterior: o mesmo triângulo na mesma página de glifo, sem o dígito."""
    pagina = pagina_gramatica([poligono(vertices())], textos=(_palavra_longe("glifo"),))
    assert _variantes(pagina) == variantes_do_grupo(_BASE_CONTORNO)


def test_triangulo_branco_so_de_preenchimento_nao_casa() -> None:
    """Revisão I-2: o triângulo branco sem traço visível não aparece na folha."""
    pagina = pagina_gramatica([poligono(vertices(), preenchimento=BRANCO, cor=None)])
    assert _variantes(pagina) == set()


def test_controle_triangulo_branco_com_traco_preto_casa_o_contorno() -> None:
    """Controle do anterior: o mesmo branco com traço preto é o contorno."""
    pagina = pagina_gramatica([poligono(vertices(), preenchimento=BRANCO, cor=PRETO)])
    assert _variantes(pagina) == variantes_do_grupo(_BASE_CONTORNO)
