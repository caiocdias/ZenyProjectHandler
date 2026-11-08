"""Ataque à envolvente lida do subcaminho fechado (R-E06.3.3.2.1-1), pelo testador.

Desenho autoral, relativo à escala: elipses de muitos lados num subcaminho de retas, traços
encostados que partem a polilinha reconstruída e páginas com muitos subcaminhos fechados curtos.
O gasto esperado de `MarcasDaPagina.contornos` é sempre recomposto pelas suas três parcelas:
1 por polilinha fechada examinada, 1 por subcaminho que passa no filtro estrutural e 1 por
contorno inserido no índice. Nada vem de folha real.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Final, Literal

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.paginas import (
    circulo_bezier,
    estilo,
    linha,
    pagina_gramatica,
)
from tests.fixtures.symbol_grammars.stem_bars import (
    ALTERNADAS,
    CASOS_HASTE,
    DECRESCENTES,
    HASTE,
    LACUNA,
    PRETO,
    desenhar_haste,
    pagina_desenhada,
)

from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import (
    _TOLERANCIA_FECHAMENTO,
    _VERTICES_MINIMOS_ELIPSE,
    Contorno,
    MarcasDaPagina,
    envolvente,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caminho,
    Cor,
    ItemCaminho,
    Polilinha,
    Ponto,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    ContextoGramatica,
    PaginaGramatica,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import casar_variantes

# Escala do símbolo: a maior barra da haste; os tamanhos abaixo são frações dela.
_ESCALA: Final = max(ALTERNADAS)
_CENTRO: Final[Ponto] = (12.5 * _ESCALA, 12.5 * _ESCALA)
_SEMI_A: Final = 1.25 * _ESCALA
_SEMI_B: Final = 0.875 * _ESCALA
_LADOS: Final = 40
_PAGINA: Final = 300.0
_TODA_A_PAGINA: Final = (0.0, 0.0, _PAGINA, _PAGINA)
_VERDE: Final[Cor] = (0.0, 0.5, 0.0)
# A menor distância entre o primeiro e o último ponto de um arco aberto medida nas folhas.
_FOLGA_ARCO_ABERTO_MEDIDA: Final = 0.24


def _vertices(
    centro: Ponto = _CENTRO, a: float = _SEMI_A, b: float = _SEMI_B, lados: int = _LADOS
) -> list[Ponto]:
    return [
        (
            centro[0] + a * math.cos(2 * math.pi * k / lados),
            centro[1] + b * math.sin(2 * math.pi * k / lados),
        )
        for k in range(lados)
    ]


def _subcaminho(vertices: Sequence[Ponto], folga: float = 0.0) -> tuple[ItemCaminho, ...]:
    """Retas na ordem dos vértices; a última volta ao primeiro deslocada de `folga` em y."""
    fim = (vertices[0][0], vertices[0][1] + folga)
    destinos = [*vertices[1:], fim]
    return tuple(ItemCaminho("l", (p, q)) for p, q in zip(vertices, destinos, strict=True))


def _caminho(*subcaminhos: tuple[ItemCaminho, ...], preenchimento: Cor | None = None) -> Caminho:
    tipo = "traco" if preenchimento is None else "traco_e_preenchimento"
    return Caminho(tuple(subcaminhos), estilo(PRETO, preenchimento), tipo, 0)


def _encostado(vertice: Ponto, centro: Ponto) -> Caminho:
    """Traço radial para fora, no mesmo estilo: com dois deles a polilinha da elipse se parte."""
    dx, dy = vertice[0] - centro[0], vertice[1] - centro[1]
    norma = math.hypot(dx, dy)
    comprimento = 0.375 * _ESCALA
    return linha(
        vertice, (vertice[0] + dx / norma * comprimento, vertice[1] + dy / norma * comprimento)
    )


def _dois_encostados(vertices: Sequence[Ponto], centro: Ponto) -> list[Caminho]:
    return [
        _encostado(vertices[len(vertices) // 8 + k * len(vertices) // 2], centro) for k in (0, 1)
    ]


def _ler(pagina: PaginaGramatica) -> tuple[ContextoGramatica, list[Contorno], int]:
    contexto = contexto_gramaticas(pagina)
    antes = contexto.orcamento.gasto
    grade = MarcasDaPagina(contexto).contornos
    # O gasto é lido antes da consulta, que também paga.
    gasto = contexto.orcamento.gasto - antes
    return contexto, list(grade.consultar(_TODA_A_PAGINA)), gasto


def _ler_caminhos(
    caminhos: Sequence[Caminho], *, sem_primitivas: bool = False
) -> tuple[ContextoGramatica, list[Contorno], int]:
    """Com `sem_primitivas`, nenhuma polilinha é reconstruída: só a rota do subcaminho fala."""
    return _ler(pagina_gramatica(caminhos, primitivas=() if sem_primitivas else None))


def _fechadas(contexto: ContextoGramatica) -> int:
    return sum(
        1 for p in contexto.pagina.modelo.primitivas if isinstance(p, Polilinha) and p.fechada
    )


def _do_subcaminho(contornos: Sequence[Contorno]) -> list[Contorno]:
    return [c for c in contornos if c.origem == "subcaminho"]


def _pagou_filtro(contexto: ContextoGramatica, contornos: Sequence[Contorno], gasto: int) -> int:
    """O que sobra do gasto depois das polilinhas fechadas e das inserções no índice."""
    return gasto - _fechadas(contexto) - len(contornos)


# --- borda da tolerância de fechamento --------------------------------------------------------


@pytest.mark.parametrize(
    ("fator", "passa"),
    [(0.0, True), (0.98, True), (1.02, False), (2.0, False)],
    ids=["fecha-exato", "dentro-da-borda", "fora-da-borda", "o-dobro"],
)
def test_fechamento_na_borda_da_tolerancia_decide_o_filtro(fator: float, passa: bool) -> None:
    caminhos = [_caminho(_subcaminho(_vertices(), folga=_TOLERANCIA_FECHAMENTO * fator))]

    contexto, contornos, gasto = _ler_caminhos(caminhos)
    _, isolados, gasto_isolado = _ler_caminhos(caminhos, sem_primitivas=True)

    assert len(_do_subcaminho(contornos)) == int(passa)
    assert _pagou_filtro(contexto, contornos, gasto) == int(passa)
    assert [c.origem for c in isolados] == (["subcaminho"] if passa else [])
    assert gasto_isolado == 2 * int(passa)


def test_arco_aberto_com_a_menor_folga_medida_nao_vira_contorno_de_subcaminho_nem_paga() -> None:
    caminhos = [_caminho(_subcaminho(_vertices(), folga=_FOLGA_ARCO_ABERTO_MEDIDA))]

    contexto, contornos, gasto = _ler_caminhos(caminhos)
    _, isolados, gasto_isolado = _ler_caminhos(caminhos, sem_primitivas=True)

    assert _do_subcaminho(contornos) == []
    assert _pagou_filtro(contexto, contornos, gasto) == 0
    assert isolados == []
    assert gasto_isolado == 0


# --- mínimo de retas ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lados", "contornos_esperados"),
    [(_VERTICES_MINIMOS_ELIPSE - 1, 0), (_VERTICES_MINIMOS_ELIPSE, 1)],
    ids=["sete-retas", "oito-retas"],
)
def test_elipse_fechada_abaixo_do_minimo_de_retas_nao_vira_contorno_nem_paga(
    lados: int, contornos_esperados: int
) -> None:
    raio = _SEMI_A
    caminhos = [_caminho(_subcaminho(_vertices(a=raio, b=raio, lados=lados)))]

    contexto, contornos, gasto = _ler_caminhos(caminhos)
    _, isolados, gasto_isolado = _ler_caminhos(caminhos, sem_primitivas=True)

    assert len(contornos) == contornos_esperados
    assert _pagou_filtro(contexto, contornos, gasto) == contornos_esperados
    assert len(isolados) == contornos_esperados
    assert gasto_isolado == 2 * contornos_esperados


def test_sete_retas_e_uma_bezier_nao_passam_no_filtro() -> None:
    """O filtro conta retas, não itens: sete retas e uma curva fechando não pagam."""
    vertices = _vertices(lados=_VERTICES_MINIMOS_ELIPSE)
    retas = _subcaminho(vertices)[:-1]
    ultimo, primeiro = vertices[-1], vertices[0]
    curva = ItemCaminho("c", (ultimo, ultimo, primeiro, primeiro))

    _, contornos, gasto = _ler_caminhos([_caminho((*retas, curva))], sem_primitivas=True)

    assert contornos == []
    assert gasto == 0


# --- preenchimento -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cor", "tipo"),
    [(None, "preenchimento"), (PRETO, "traco_e_preenchimento")],
    ids=["preenchimento", "traco-e-preenchimento"],
)
def test_elipse_em_caminho_preenchido_nao_vira_contorno_nem_paga(
    cor: Cor | None, tipo: Literal["preenchimento", "traco_e_preenchimento"]
) -> None:
    """A elipse preenchida é o segundo subcaminho; um oval de traço longe dela é o controle."""
    quadrado = _subcaminho([(1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0)])
    preenchida = Caminho((quadrado, _subcaminho(_vertices())), estilo(cor, _VERDE), tipo, 0)
    controle_centro = (_CENTRO[0] + 10 * _ESCALA, _CENTRO[1])
    controle = _caminho(_subcaminho(_vertices(controle_centro)))

    contexto, contornos, gasto = _ler_caminhos([preenchida, controle])
    _, isolados, gasto_isolado = _ler_caminhos([preenchida], sem_primitivas=True)

    [contorno] = contornos
    assert (contorno.caminhos, contorno.origem) == ((1,), "subcaminho")
    assert _pagou_filtro(contexto, contornos, gasto) == 1
    assert isolados == []
    assert gasto_isolado == 0


# --- deduplicação e o campo `caminhos` ---------------------------------------------------------


def test_mesma_elipse_de_moldura_polilinha_e_subcaminho_vira_um_contorno() -> None:
    """Um caminho com o círculo duas vezes: quatro Béziers (moldura) e 40 retas (polilinha e
    subcaminho); as três leituras são da mesma elipse e entram uma vez só."""
    raio = _SEMI_A
    bezier = circulo_bezier(_CENTRO, raio).subcaminhos[0]
    retas = _subcaminho(_vertices(a=raio, b=raio))
    contexto = contexto_gramaticas(pagina_gramatica([_caminho(bezier, retas)]))
    molduras = [m for m in contexto.molduras if m.forma == "elipse"]
    antes = contexto.orcamento.gasto

    grade = MarcasDaPagina(contexto).contornos
    gasto = contexto.orcamento.gasto - antes
    contornos = list(grade.consultar(_TODA_A_PAGINA))

    assert [m.caminho for m in molduras] == [0]
    assert _fechadas(contexto) == 1
    [contorno] = contornos
    assert (contorno.origem, contorno.subcaminho, contorno.caminhos) == ("subcaminho", 1, (0,))
    # Uma polilinha fechada, um subcaminho no filtro (o de Béziers não tem retas), uma inserção.
    assert gasto == 1 + 1 + 1


def test_mesma_elipse_em_caminhos_diferentes_nao_e_deduplicada() -> None:
    """A deduplicação é por caminho: o mesmo oval redesenhado em outro caminho é outro desenho."""
    raio = _SEMI_A
    caminhos = [circulo_bezier(_CENTRO, raio), _caminho(_subcaminho(_vertices(a=raio, b=raio)))]

    _, contornos, _ = _ler_caminhos(caminhos)

    assert sorted((c.origem, c.caminhos) for c in contornos) == [
        ("moldura", (0,)),
        ("subcaminho", (1,)),
    ]


_Casos = Sequence[tuple[str, Mapping[str, Any]]]


def _pares(casos: _Casos) -> list[tuple[Any, Any]]:
    return [
        ({"family_id": "autoral"}, {"id": v, "recognition": {"status": "enabled", "grammar": g}})
        for v, g in casos
    ]


def _casamentos(pagina: PaginaGramatica) -> list[tuple[str, int, tuple[int, ...]]]:
    return [
        (str(c.variante["id"]), c.caminho, c.componentes)
        for c in casar_variantes(pagina, _pares(CASOS_HASTE))
    ]


def _haste(centro: Ponto, barras: Sequence[float]) -> tuple[list[Caminho], Ponto, float]:
    """Haste e barras como em `stem_bars.desenhar_haste`; devolve o centro e o raio do oval."""
    cx, cy = centro
    ponta = cy - HASTE / 2
    caminhos = [linha((cx, cy + HASTE / 2), (cx, ponta))]
    for i, comprimento in enumerate(barras):
        y, meio = ponta - i * LACUNA, comprimento / 2
        caminhos.append(linha((cx - meio, y), (cx + meio, y)))
    raio = max(barras) * 0.8 + len(barras) * LACUNA / 2
    return caminhos, (cx, ponta - (len(barras) - 1) * LACUNA / 2), raio


@pytest.mark.parametrize(
    ("barras", "esperada"),
    [(DECRESCENTES, "cemig-eo-r3-s19-v002"), (ALTERNADAS, "cemig-eo-r3-s21-v006")],
    ids=["tres-barras", "quatro-barras"],
)
def test_envolvente_de_subcaminho_entrega_os_mesmos_componentes_que_a_moldura(
    barras: Sequence[float], esperada: str
) -> None:
    """O consumidor lê `Contorno.caminhos`: o oval de retas partido e o de Béziers, na mesma
    posição, produzem o mesmo casamento, com o caminho do oval entre os componentes."""
    haste, centro_oval, raio = _haste(_CENTRO, barras)
    vertices = _vertices(centro_oval, raio, raio)
    encostados = _dois_encostados(vertices, centro_oval)
    posicao_oval = len(haste)

    de_retas = _casamentos(pagina_gramatica([*haste, _caminho(_subcaminho(vertices)), *encostados]))
    de_bezier = _casamentos(
        pagina_gramatica([*haste, circulo_bezier(centro_oval, raio), *encostados])
    )

    assert de_retas == de_bezier
    [(variante, _, componentes)] = de_retas
    assert variante == esperada
    assert posicao_oval in componentes


# --- `proprios` --------------------------------------------------------------------------------


def _com_traco_proprio(oval: Caminho) -> list[Caminho]:
    """O oval e um traço da haste no mesmo caminho (dois subcaminhos)."""
    traco = _subcaminho([_CENTRO, (_CENTRO[0], _CENTRO[1] - 0.5 * _ESCALA)])[:1]
    return [Caminho((traco, *oval.subcaminhos), oval.estilo, oval.tipo, 0)]


def _oval_de_tracos_soltos() -> list[Caminho]:
    vertices = _vertices()
    return [linha(p, vertices[(i + 1) % len(vertices)]) for i, p in enumerate(vertices)]


@pytest.mark.parametrize(
    ("caminhos", "origem", "conta"),
    [
        (_com_traco_proprio(_caminho(_subcaminho(_vertices()))), "subcaminho", True),
        (_com_traco_proprio(circulo_bezier(_CENTRO, _SEMI_A)), "moldura", False),
        (_oval_de_tracos_soltos(), "polilinha", False),
    ],
    ids=["subcaminho", "moldura", "polilinha"],
)
def test_so_o_contorno_de_subcaminho_escapa_de_proprios(
    caminhos: list[Caminho], origem: str, conta: bool
) -> None:
    _, contornos, _ = _ler_caminhos(caminhos)
    contexto = contexto_gramaticas(pagina_gramatica(caminhos))
    grade = MarcasDaPagina(contexto).contornos

    achada = envolvente(grade, [_CENTRO], _ESCALA, _CENTRO, frozenset({0}))
    sem_proprios = envolvente(grade, [_CENTRO], _ESCALA, _CENTRO, frozenset())

    assert [c.origem for c in contornos] == [origem]
    assert sem_proprios is not None
    assert (achada is not None) is conta
    if conta:
        assert achada == sem_proprios


# --- duas elipses num caminho -----------------------------------------------------------------


def test_duas_elipses_no_mesmo_caminho_viram_dois_contornos() -> None:
    outro_centro = (_CENTRO[0] + 6 * _ESCALA, _CENTRO[1] + 6 * _ESCALA)
    caminhos = [
        _caminho(_subcaminho(_vertices()), _subcaminho(_vertices(outro_centro, _SEMI_B, _SEMI_A)))
    ]

    contexto, contornos, gasto = _ler_caminhos(caminhos)

    assert sorted((c.origem, c.caminhos, c.subcaminho) for c in contornos) == [
        ("subcaminho", (0,), 0),
        ("subcaminho", (0,), 1),
    ]
    assert _pagou_filtro(contexto, contornos, gasto) == 2


# --- muitos subcaminhos fechados curtos -------------------------------------------------------


def _hachura(celulas: int, pontos: int) -> list[tuple[ItemCaminho, ...]]:
    """Células fechadas de 4 retas, traços de hachura de 1 reta e `pontos` círculos de 12 retas,
    todos pequenos e separados, num caminho só."""
    passo = _ESCALA / 2
    lado = passo / 4
    subcaminhos: list[tuple[ItemCaminho, ...]] = []
    for k in range(celulas):
        x, y = passo * (1 + k % 30), passo * (1 + k // 30)
        subcaminhos.append(
            _subcaminho([(x, y), (x + lado, y), (x + lado, y + lado), (x, y + lado)])
        )
        subcaminhos.append(_subcaminho([(x, y + 2 * lado), (x + lado, y + 2 * lado)])[:1])
    for k in range(pontos):
        centro = (passo * (1 + k % 30), _PAGINA - passo * (1 + k // 30))
        subcaminhos.append(_subcaminho(_vertices(centro, lado, lado, 12)))
    return subcaminhos


@pytest.mark.parametrize(
    ("celulas", "pontos"),
    [(300, 0), (300, 40), (600, 40), (300, 80)],
    ids=["so-hachura", "hachura-e-40-pontos", "o-dobro-de-hachura", "o-dobro-de-pontos"],
)
def test_hachura_de_subcaminhos_fechados_paga_so_os_que_passam_no_filtro(
    celulas: int, pontos: int
) -> None:
    caminhos = [_caminho(*_hachura(celulas, pontos))]

    contexto, contornos, gasto = _ler_caminhos(caminhos)
    _, isolados, gasto_isolado = _ler_caminhos(caminhos, sem_primitivas=True)

    assert _pagou_filtro(contexto, contornos, gasto) == pontos
    assert len(_do_subcaminho(contornos)) == pontos
    assert gasto_isolado == pontos + len(isolados)
    assert len(isolados) == pontos


# --- a haste de `stem_bars.py` dentro e fora do oval ------------------------------------------


@pytest.mark.parametrize(
    ("barras", "deslocamento", "fator_raio", "esperada"),
    [
        (DECRESCENTES, 0.0, 1.0, "cemig-eo-r3-s19-v002"),
        (ALTERNADAS, 0.0, 1.0, "cemig-eo-r3-s21-v006"),
        (DECRESCENTES, 4.0, 1.0, "cemig-eo-r3-s19-v001"),
        (ALTERNADAS, 4.0, 1.0, "cemig-eo-r3-s21-v005"),
        (DECRESCENTES, 0.0, 2.5, "cemig-eo-r3-s19-v001"),
        (ALTERNADAS, 0.0, 0.45, "cemig-eo-r3-s21-v005"),
    ],
    ids=[
        "tres-dentro",
        "quatro-dentro",
        "tres-oval-ao-lado",
        "quatro-oval-ao-lado",
        "tres-oval-grande-demais",
        "quatro-oval-que-nao-contem-as-barras",
    ],
)
def test_haste_dentro_do_oval_de_subcaminho_casa_a_envolvente_e_fora_dele_a_base(
    barras: Sequence[float], deslocamento: float, fator_raio: float, esperada: str
) -> None:
    haste, centro_oval, raio = _haste(_CENTRO, barras)
    centro = (centro_oval[0] + deslocamento * _ESCALA, centro_oval[1])
    vertices = _vertices(centro, raio * fator_raio, raio * fator_raio)
    oval = [_caminho(_subcaminho(vertices)), *_dois_encostados(vertices, centro)]

    contexto, contornos, _ = _ler_caminhos([*haste, *oval])

    assert [c.origem for c in contornos] == ["subcaminho"]
    assert [v for v, _, _ in _casamentos(pagina_gramatica([*haste, *oval]))] == [esperada]
    assert _fechadas(contexto) == 0


def _haste_com_oval_partido(pagina: pymupdf.Page, barras: Sequence[float]) -> None:
    """`stem_bars.desenhar_haste` com o oval de 40 retas e dois traços encostados nele."""
    desenho = desenhar_haste(pagina, barras, envolvente=True, contorno=(1.0,) * _LADOS)
    assert desenho.envolvente is not None
    x0, y0, x1, y1 = desenho.envolvente
    centro, raio = ((x0 + x1) / 2, (y0 + y1) / 2), (x1 - x0) / 2
    for traco in _dois_encostados(_vertices(centro, raio, raio), centro):
        a, b = traco.subcaminhos[0][0].pontos
        pagina.draw_line(a, b, color=PRETO, width=0.5)


@pytest.mark.parametrize(
    ("barras", "esperada"),
    [(DECRESCENTES, "cemig-eo-r3-s19-v002"), (ALTERNADAS, "cemig-eo-r3-s21-v006")],
    ids=["tres-barras", "quatro-barras"],
)
def test_oval_partido_lido_pelo_pymupdf_casa_a_variante_com_envolvente(
    barras: Sequence[float], esperada: str
) -> None:
    pagina = pagina_desenhada(lambda p: _haste_com_oval_partido(p, barras))

    contexto, contornos, _ = _ler(pagina)

    assert _fechadas(contexto) == 0
    assert [c.origem for c in contornos] == ["subcaminho"]
    assert [v for v, _, _ in _casamentos(pagina)] == [esperada]
