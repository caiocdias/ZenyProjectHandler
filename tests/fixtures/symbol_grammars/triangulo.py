"""Fixtures autorais da gramática `split_triangle` (TRANSFORMADOR).

Nenhuma coordenada vem de folha real: o pictograma é um triângulo equilátero de lado `LADO`
centrado em `CENTRO`, girado, com a metade ciano e a branca divididas pela mediana do vértice da
haste, ou só o contorno; envolvente (círculo de retas, círculo de Béziers ou elipse de retas) e X
vermelho opcionais. `desenhar_trafo_e05` desenha o mesmo pictograma no estilo que o método E05
(`pymupdf_transformers.observar_transformadores`) observa. As páginas de glifo são montadas
direto no modelo de desenho (`paginas.py`), sem PyMuPDF.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, Final, Literal

import pymupdf
from tests.fixtures.symbol_grammars.paginas import circulo_bezier, linha, pagina_gramatica, poligono
from tests.fixtures.symbol_grammars.paginas import texto as texto_modelo

from zeny_project_handler.adapters.analysis.drawing_model.model import Caminho, Cor, Ponto
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import PaginaGramatica

PRETO: Final[Cor] = (0.0, 0.0, 0.0)
BRANCO: Final[Cor] = (1.0, 1.0, 1.0)
CIANO: Final[Cor] = (0.0, 1.0, 0.75)
VERDE: Final[Cor] = (0.0, 0.5, 0.0)
VERMELHO: Final[Cor] = (1.0, 0.0, 0.0)
VERMELHO_ESCURO: Final[Cor] = (0.5, 0.0, 0.0)
ROXO: Final[Cor] = (0.5, 0.0, 0.5)
CENTRO: Final[Ponto] = (150.0, 150.0)
LADO: Final = 12.0
# Raio da envolvente relativo ao raio do círculo circunscrito ao triângulo.
FOLGA_ENVOLVENTE: Final = 1.12
# Meia diagonal do X relativa ao lado.
MEIO_X: Final = 0.7
# Haste de ligação: ponta de fora a esta fração do lado, a partir do centro.
ALCANCE_HASTE: Final = 1.6

Grupo = tuple[str, str, bool]
FormaEnvolvente = Literal["retas", "circulo", "elipse"]
FormaContorno = Literal["polilinha", "lados", "mediana"]
FormaMetades = Literal["com_traco", "sem_traco", "hachura", "hachura_com_falha"]

_GRUPOS: Final[dict[Grupo, tuple[int, ...]]] = {
    ("half_cyan", "none", False): (1, 4),
    ("half_cyan", "none", True): (2, 5),
    ("half_cyan", "ellipse", False): (3, 6),
    ("outline", "none", False): (7, 10, 13),
    ("outline", "none", True): (8, 11, 14),
    ("outline", "ellipse", False): (9, 12, 15),
}


def _gramatica(fill: str, enclosure: str, removal_mark: bool) -> dict[str, Any]:
    return {
        "kind": "split_triangle",
        "fill": fill,
        "enclosure": enclosure,
        "removal_mark": removal_mark,
        "max_span": 72,
    }


def _id(numero: int) -> str:
    return f"cemig-eo-r3-s18-v{numero:03d}"


CASOS_TRIANGULO: Final[tuple[tuple[str, dict[str, Any]], ...]] = tuple(
    sorted(
        (_id(numero), _gramatica(*grupo))
        for grupo, numeros in _GRUPOS.items()
        for numero in numeros
    )
)
"""Id de cada variante v001 a v015 de f02-18 e a gramática dela, pela tabela de R-E06.3.3.2.2-1."""

GRUPO_DA_VARIANTE: Final[dict[str, Grupo]] = {
    _id(numero): grupo for grupo, numeros in _GRUPOS.items() for numero in numeros
}
GRUPOS: Final[tuple[Grupo, ...]] = tuple(sorted(_GRUPOS))


def variantes_do_grupo(grupo: Grupo) -> set[str]:
    return {variante for variante, seu in GRUPO_DA_VARIANTE.items() if seu == grupo}


def _gira(ponto: Ponto, centro: Ponto, graus: float) -> Ponto:
    r = math.radians(graus)
    dx, dy = ponto[0] - centro[0], ponto[1] - centro[1]
    return (
        centro[0] + dx * math.cos(r) - dy * math.sin(r),
        centro[1] + dx * math.sin(r) + dy * math.cos(r),
    )


def vertices(centro: Ponto = CENTRO, graus: float = 0.0, lado: float = LADO) -> list[Ponto]:
    """Ápice (o vértice da haste) primeiro; depois os dois da base."""
    raio = lado / math.sqrt(3)
    return [_gira((centro[0], centro[1] - raio), centro, graus + 120 * k) for k in range(3)]


def raio_envolvente(lado: float = LADO) -> float:
    return lado / math.sqrt(3) * FOLGA_ENVOLVENTE


def ponta_da_haste(centro: Ponto = CENTRO, graus: float = 0.0, lado: float = LADO) -> Ponto:
    return _gira((centro[0], centro[1] - lado * ALCANCE_HASTE), centro, graus)


def bracos_x(
    centro: Ponto = CENTRO, graus: float = 0.0, lado: float = LADO
) -> list[tuple[Ponto, Ponto]]:
    meio = lado * MEIO_X
    return [
        (
            _gira((centro[0] - meio, centro[1] - sinal * meio), centro, graus),
            _gira((centro[0] + meio, centro[1] + sinal * meio), centro, graus),
        )
        for sinal in (1, -1)
    ]


def _meio(p: Ponto, q: Ponto) -> Ponto:
    return (p[0] + q[0]) / 2, (p[1] + q[1]) / 2


def _triangulo(
    pagina: pymupdf.Page, pontos: list[Ponto], cor: Cor | None, fill: Cor | None
) -> None:
    pagina.draw_polyline([*pontos, pontos[0]], color=cor, fill=fill, width=0.14, closePath=True)


def _contorno_de_retas(
    pagina: pymupdf.Page, centro: Ponto, semieixos: tuple[float, float], graus: float, cor: Cor
) -> None:
    pontos = [
        _gira(
            (
                centro[0] + semieixos[0] * math.cos(2 * math.pi * k / 72),
                centro[1] + semieixos[1] * math.sin(2 * math.pi * k / 72),
            ),
            centro,
            graus,
        )
        for k in range(72)
    ]
    pagina.draw_polyline([*pontos, pontos[0]], color=cor, width=0.14)


def _envolvente(
    pagina: pymupdf.Page, centro: Ponto, raio: float, graus: float, forma: FormaEnvolvente
) -> None:
    if forma == "circulo":
        pagina.draw_circle(centro, raio, color=VERDE, width=0.14)
    elif forma == "elipse":
        _contorno_de_retas(pagina, centro, (raio * 1.15, raio), graus + 20, VERDE)
    else:
        _contorno_de_retas(pagina, centro, (raio, raio), graus, VERDE)


def _hachura(pagina: pymupdf.Page, metade: list[Ponto], fill: Cor, *, falha: bool) -> None:
    """A metade `metade` (meio da aresta, ápice, vértice da base) num preenchimento só, fatiada
    em dois triângulos pelo meio do lado ápice-base, como o AutoCAD faz. Com `falha`, a segunda
    fatia encolhe à metade e as duas deixam de cobrir a metade inteira."""
    m, a, b = metade
    q = _meio(a, b)
    segunda = [q, b, _meio(m, b)] if falha else [q, b, m]
    forma = pagina.new_shape()  # type: ignore[no-untyped-call]
    for fatia in ([m, a, q], segunda):
        forma.draw_polyline([*fatia, fatia[0]])
    forma.finish(color=None, fill=fill, closePath=True)
    forma.commit()


def _contorno(pagina: pymupdf.Page, pontos: list[Ponto], estilo: FormaContorno) -> None:
    a, b, c = pontos
    if estilo == "lados":
        for inicio, fim in ((a, b), (b, c), (c, a)):
            pagina.draw_line(inicio, fim, color=PRETO, width=0.14)
    elif estilo == "mediana":
        # A mediana do ápice no mesmo caminho, uma reta depois do fecho.
        pagina.draw_polyline([a, b, c, a, _meio(b, c)], color=PRETO, width=0.14)
    else:
        _triangulo(pagina, [a, b, c], PRETO, None)


def desenhar_trafo(
    pagina: pymupdf.Page,
    fill: str,
    *,
    centro: Ponto = CENTRO,
    graus: float = 0.0,
    lado: float = LADO,
    envolvente: bool = False,
    forma_envolvente: FormaEnvolvente = "retas",
    x: bool = False,
    haste: bool = True,
    linha_de_rede: bool = False,
    contorno: FormaContorno = "polilinha",
    metades: FormaMetades = "com_traco",
    cor_da_metade: Cor = CIANO,
) -> None:
    """O pictograma, nesta ordem de caminhos: contorno (três, com `contorno="lados"`), metades
    (no `half_cyan`: a da cor `cor_da_metade` e a branca), haste, linha de rede, envolvente e os
    dois braços do X."""
    a, b, c = vertices(centro, graus, lado)
    _contorno(pagina, [a, b, c], contorno)
    if fill == "half_cyan":
        m = _meio(b, c)
        if metades in ("hachura", "hachura_com_falha"):
            falha = metades == "hachura_com_falha"
            _hachura(pagina, [m, a, b], cor_da_metade, falha=falha)
            _hachura(pagina, [m, a, c], BRANCO, falha=False)
        else:
            traco = PRETO if metades == "com_traco" else None
            _triangulo(pagina, [m, a, b], traco, cor_da_metade)
            _triangulo(pagina, [m, a, c], traco, BRANCO)
    fora = ponta_da_haste(centro, graus, lado)
    if haste or linha_de_rede:
        pagina.draw_line(a, fora, color=PRETO, width=0.14)
    if linha_de_rede:
        # A rede passa pela ponta da haste, perpendicular a ela, longe do pictograma.
        p0 = _gira((fora[0] - 60.0, fora[1]), fora, graus)
        p1 = _gira((fora[0] + 60.0, fora[1]), fora, graus)
        pagina.draw_line(p0, p1, color=PRETO, width=0.14)
    if envolvente:
        _envolvente(pagina, centro, raio_envolvente(lado), graus, forma_envolvente)
    if x:
        for p0, p1 in bracos_x(centro, graus, lado):
            pagina.draw_line(p0, p1, color=VERMELHO, width=0.5)


def desenhar_grupo(pagina: pymupdf.Page, grupo: Grupo, graus: float = 0.0, **opcoes: Any) -> None:
    fill, enclosure, removal = grupo
    desenhar_trafo(
        pagina, fill, graus=graus, envolvente=enclosure == "ellipse", x=removal, **opcoes
    )


def desenhar_trafo_e05(page: pymupdf.Page, grupo: Grupo, centro: Ponto = CENTRO) -> None:
    """O positivo do grupo no estilo que o E05 observa: triângulo de traço, haste externa na
    mediana do ápice e, no `half_cyan`, as metades só de preenchimento (ciano e branca)."""
    fill, enclosure, removal = grupo
    a, b, c = vertices(centro, 0.0, LADO)
    m = _meio(b, c)
    if fill == "half_cyan":
        _triangulo(page, [m, a, b], None, CIANO)
        _triangulo(page, [m, a, c], None, BRANCO)
    _triangulo(page, [a, b, c], PRETO, None)
    page.draw_line(a, ponta_da_haste(centro, 0.0, LADO), color=PRETO, width=0.14)
    if enclosure == "ellipse":
        _contorno_de_retas(page, centro, (raio_envolvente(), raio_envolvente()), 0.0, PRETO)
    if removal:
        for p0, p1 in bracos_x(centro):
            page.draw_line(p0, p1, color=VERMELHO, width=0.5)


def caminhos_trafo(grupo: Grupo, centro: Ponto, lado: float) -> list[Caminho]:
    """O pictograma do grupo direto no modelo: contorno, metades, haste, envolvente e X."""
    fill, enclosure, removal = grupo
    a, b, c = vertices(centro, 0.0, lado)
    caminhos = [poligono([a, b, c])]
    if fill == "half_cyan":
        m = _meio(b, c)
        caminhos += [
            poligono([m, a, b], preenchimento=CIANO),
            poligono([m, a, c], preenchimento=BRANCO),
        ]
    caminhos.append(linha(a, ponta_da_haste(centro, 0.0, lado)))
    if enclosure == "ellipse":
        caminhos.append(circulo_bezier(centro, raio_envolvente(lado), cor=VERDE))
    if removal:
        caminhos += [linha(p0, p1, cor=VERMELHO) for p0, p1 in bracos_x(centro, 0.0, lado)]
    return caminhos


def pagina_com_texto(
    caminhos: list[Caminho],
    origem: Literal["nativo", "shx", "glifo"] | None,
    glifos_lidos: frozenset[int] = frozenset(),
) -> PaginaGramatica:
    """Página do modelo com uma palavra da `origem` longe do desenho (nenhuma, com None)."""
    textos = () if origem is None else (texto_modelo("LIVRE", (5.0, 5.0, 30.0, 12.0), origem),)
    pagina = pagina_gramatica(caminhos, textos)
    return PaginaGramatica(pagina.modelo, pagina.indices_crus, pagina.translucidos, glifos_lidos)


def pagina_delta_de_glifo(*, lido: bool) -> PaginaGramatica:
    """Um Δ de glifo: o contorno fechado de um triângulo equilátero numa página de texto em
    glifo. Com `lido`, ele virou texto (`glifos_lidos`); sem, é um contorno solto qualquer."""
    caminhos = [poligono(vertices(CENTRO, 0.0, 6.0))]
    return pagina_com_texto(caminhos, "glifo", frozenset({0}) if lido else frozenset())


def _verde_solido(pagina: pymupdf.Page) -> None:
    _triangulo(pagina, vertices(), VERDE, VERDE)


def _ponta_de_seta(pagina: pymupdf.Page) -> None:
    pagina.draw_line((100, 150), (150, 150), color=PRETO, width=0.3)
    _triangulo(pagina, [(150, 150), (142, 147), (142, 153)], PRETO, PRETO)


def _ciano_inteiro(pagina: pymupdf.Page) -> None:
    _triangulo(pagina, vertices(), PRETO, CIANO)


def _roxo_com_s(pagina: pymupdf.Page) -> None:
    _triangulo(pagina, vertices(), ROXO, ROXO)
    pagina.insert_text((147, 153), "S", fontsize=6, color=BRANCO)


def _aberto(pagina: pymupdf.Page) -> None:
    a, b, c = vertices()
    pagina.draw_polyline([b, a, c], color=PRETO, width=0.14)


def _grande(pagina: pymupdf.Page) -> None:
    desenhar_trafo(pagina, "half_cyan", lado=30.0)


def _circulo_sem_triangulo(pagina: pymupdf.Page) -> None:
    _contorno_de_retas(pagina, CENTRO, (8.0, 8.0), 0.0, VERDE)


NEGATIVOS: Final[dict[str, Callable[[pymupdf.Page], object]]] = {
    "verde_solido": _verde_solido,
    "ponta_de_seta": _ponta_de_seta,
    "ciano_inteiro": _ciano_inteiro,
    "roxo_com_s": _roxo_com_s,
    "triangulo_aberto": _aberto,
    "acima_do_maximo": _grande,
    "circulo_sem_triangulo": _circulo_sem_triangulo,
}
"""Desenhos que nenhuma variante de `CASOS_TRIANGULO` pode casar; o Δ de glifo, que é uma página
do modelo e não um desenho PyMuPDF, está em `pagina_delta_de_glifo`."""
