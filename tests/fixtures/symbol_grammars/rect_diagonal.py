"""Retângulos atravessados por diagonal sintéticos (PARA_RAIOS_BT), desenhados com PyMuPDF.

Desenho autoral: corpo retangular de `CORPO` pt (lado maior sobre o eixo), diagonal que o cruza
pelos lados longos e passa além dele; ganchos, haste de ligação, envolvente e X opcionais.
`desenhar_bt_classico` desenha o estilo do analisador legado (haste alinhada ao corpo, diagonal
mais íngreme que a de canto a canto). Nada vem de folha real.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

import pymupdf

from zeny_project_handler.adapters.analysis.drawing_model.model import Cor, Ponto
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import PaginaGramatica
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_para_gramaticas

PRETO: Final[Cor] = (0.0, 0.0, 0.0)
VERMELHO: Final[Cor] = (1.0, 0.0, 0.0)
CENTRO: Final[Ponto] = (150.0, 150.0)
CORPO: Final = (8.0, 3.0)
HASTE: Final = 10.0
# Estilo clássico: haste de `HASTE` pt alinhada ao corpo, que começa onde ela termina.
CORPO_CLASSICO: Final = (9.0, 3.0)
DIAGONAL_CLASSICA: Final = (8.0, math.radians(60))


def _gramatica(envolvente: bool, x: bool) -> dict[str, Any]:
    return {
        "kind": "rect_diagonal",
        "enclosure": "ellipse" if envolvente else "none",
        "removal_mark": x,
        "max_span": 72,
    }


CASOS_RECT_DIAGONAL: Final[tuple[tuple[str, dict[str, Any]], ...]] = (
    ("cemig-eo-r3-s21-v001", _gramatica(envolvente=False, x=False)),
    ("cemig-eo-r3-s21-v002", _gramatica(envolvente=True, x=False)),
    ("cemig-eo-r3-s21-v003", _gramatica(envolvente=True, x=True)),
    ("cemig-eo-r3-s21-v004", _gramatica(envolvente=False, x=True)),
)
"""Id de cada variante de f02-21 (PARA_RAIOS_BT) e a gramática dela."""


@dataclass(frozen=True, slots=True)
class DesenhoRetangulo:
    """O que foi desenhado, no espaço da página antes de qualquer `/Rotate`."""

    cantos: tuple[Ponto, ...]
    diagonal: tuple[Ponto, Ponto]
    ganchos: tuple[Ponto, ...]
    haste: tuple[Ponto, Ponto] | None
    bracos_x: tuple[tuple[Ponto, Ponto], ...]


def _gira(ponto: Ponto, centro: Ponto, graus: float) -> Ponto:
    r = math.radians(graus)
    dx, dy = ponto[0] - centro[0], ponto[1] - centro[1]
    return (
        centro[0] + dx * math.cos(r) - dy * math.sin(r),
        centro[1] + dx * math.sin(r) + dy * math.cos(r),
    )


def _oval_poligonal(pagina: pymupdf.Page, centro: Ponto, raio: float, cor: Cor) -> None:
    vertices = [
        (
            centro[0] + raio * math.cos(2 * math.pi * k / 32),
            centro[1] + raio * math.sin(2 * math.pi * k / 32),
        )
        for k in range(32)
    ]
    pagina.draw_polyline([*vertices, vertices[0]], color=cor, width=0.5)


def _envolvente(pagina: pymupdf.Page, centro: Ponto, raio: float, graus: float, cor: Cor) -> None:
    if graus == 0:
        caixa = pymupdf.Rect(  # type: ignore[no-untyped-call]
            centro[0] - raio, centro[1] - raio, centro[0] + raio, centro[1] + raio
        )
        pagina.draw_oval(caixa, color=cor, width=0.5)
    else:
        _oval_poligonal(pagina, centro, raio, cor)


def _x(
    pagina: pymupdf.Page, centro: Ponto, meio: float, graus: float
) -> tuple[tuple[Ponto, Ponto], ...]:
    cx, cy = centro
    bracos = []
    for sinal in (1, -1):
        p0 = _gira((cx - meio, cy - sinal * meio), centro, graus)
        p1 = _gira((cx + meio, cy + sinal * meio), centro, graus)
        pagina.draw_line(p0, p1, color=VERMELHO, width=0.5)
        bracos.append((p0, p1))
    return tuple(bracos)


def desenhar_retangulo(
    pagina: pymupdf.Page,
    centro: Ponto = CENTRO,
    graus: float = 0.0,
    *,
    corpo: tuple[float, float] = CORPO,
    diagonal: tuple[Ponto, Ponto] | None = None,
    ganchos: bool = False,
    cauda: float = 0.0,
    haste: bool = False,
    haste_longa: float = 0.0,
    traco_de_lado: bool = False,
    envolvente: bool = False,
    x: bool = False,
    segunda_diagonal: bool = False,
    cor: Cor = PRETO,
) -> DesenhoRetangulo:
    """Corpo `corpo` (lado maior na vertical) centrado em `centro`, tudo girado `graus`.

    Ordem dos caminhos: retângulo, diagonal (com ganchos ou `cauda` no mesmo caminho), segunda
    diagonal, haste de ligação, traço de lado, envolvente e os dois braços do X.
    """
    cx, cy = centro
    meio_h, meio_l = corpo[0] / 2, corpo[1] / 2

    def g(p: Ponto) -> Ponto:
        return _gira(p, centro, graus)

    cantos = [(cx - meio_l, cy - meio_h), (cx + meio_l, cy - meio_h)]
    cantos += [(cx + meio_l, cy + meio_h), (cx - meio_l, cy + meio_h)]
    gc = [g(p) for p in cantos]
    pagina.draw_polyline([*gc, gc[0]], color=cor, width=0.5)
    a, b = diagonal or ((cx - meio_l * 2, cy + meio_h * 0.5), (cx + meio_l * 2, cy - meio_h * 0.5))
    ga, gb = g(a), g(b)
    pontas_ganchos: tuple[Ponto, ...] = ()
    if ganchos:
        # Cada gancho sai da ponta da diagonal na horizontal, para dentro do desenho.
        pontas_ganchos = (g((a[0] + 1.2, a[1])), g((b[0] - 1.2, b[1])))
        pagina.draw_polyline([pontas_ganchos[0], ga, gb, pontas_ganchos[1]], color=cor, width=0.5)
    elif cauda:
        # Um traço longo demais para ser gancho, no mesmo caminho da diagonal.
        pontas_ganchos = (g((b[0] + cauda, b[1])),)
        pagina.draw_polyline([ga, gb, pontas_ganchos[0]], color=cor, width=0.5)
    else:
        pagina.draw_line(ga, gb, color=cor, width=0.5)
    if segunda_diagonal:
        pagina.draw_line(g((a[0], b[1])), g((b[0], a[1])), color=cor, width=0.5)
    ligacao = None
    if haste:
        topo = (cx, cy - meio_h)
        ligacao = (g(topo), g((cx, topo[1] - (haste_longa or HASTE))))
        pagina.draw_line(ligacao[0], ligacao[1], color=cor, width=0.5)
    if traco_de_lado:
        # Encosta no meio da ponta de baixo, mas perpendicular ao corpo: não é haste.
        base = (cx, cy + meio_h)
        pagina.draw_line(g(base), g((cx + HASTE, base[1])), color=cor, width=0.5)
    if envolvente:
        _envolvente(pagina, g(centro), 7.0, graus, cor)
    bracos = _x(pagina, centro, 5.0, graus) if x else ()
    return DesenhoRetangulo(tuple(gc), (ga, gb), pontas_ganchos, ligacao, bracos)


def _parametros(variante: str) -> tuple[bool, bool]:
    gramatica = dict(CASOS_RECT_DIAGONAL)[variante]
    return gramatica["enclosure"] == "ellipse", bool(gramatica["removal_mark"])


def desenhar_positivo(
    pagina: pymupdf.Page,
    variante: str,
    centro: Ponto = CENTRO,
    graus: float = 0.0,
    **opcoes: Any,
) -> DesenhoRetangulo:
    """O positivo da variante `variante` de `CASOS_RECT_DIAGONAL`."""
    envolvente, x = _parametros(variante)
    return desenhar_retangulo(pagina, centro, graus, envolvente=envolvente, x=x, **opcoes)


def desenhar_bt_classico(
    pagina: pymupdf.Page, situacao: str, centro: Ponto = CENTRO
) -> DesenhoRetangulo:
    """PARA_RAIOS_BT no estilo do legado, na situação `situacao` (variante de f02-21).

    Haste horizontal de `HASTE` pt que termina no meio da ponta esquerda do corpo
    `CORPO_CLASSICO`, de proporção 3; diagonal de `DIAGONAL_CLASSICA` (0,8 vezes a haste, 60 graus
    do eixo) centrada no corpo, que cruza os lados longos e passa além deles. É o que
    `_bt_arrester_matches` pede: mesma cor e camada, haste de 6 pt ou mais, corpo e diagonal
    a 0,35-1,4 vezes a haste da ponta, diagonal a 0,4-1,2 rad da haste.
    """
    envolvente, x = _parametros(situacao)
    cx, cy = centro
    meio_maior, meio_menor = CORPO_CLASSICO[0] / 2, CORPO_CLASSICO[1] / 2
    ponta = (cx - meio_maior, cy)
    haste = (ponta[0] - HASTE, cy), ponta
    pagina.draw_line(haste[0], haste[1], color=PRETO, width=0.5)
    caixa = pymupdf.Rect(  # type: ignore[no-untyped-call]
        cx - meio_maior, cy - meio_menor, cx + meio_maior, cy + meio_menor
    )
    pagina.draw_rect(caixa, color=PRETO, width=0.5)
    comprimento, inclinacao = DIAGONAL_CLASSICA
    du = math.cos(inclinacao) * comprimento / 2
    dv = math.sin(inclinacao) * comprimento / 2
    diagonal = (cx - du, cy + dv), (cx + du, cy - dv)
    pagina.draw_line(diagonal[0], diagonal[1], color=PRETO, width=0.5)
    if envolvente:
        _envolvente(pagina, centro, 6.0, 0.0, PRETO)
    bracos = _x(pagina, centro, 5.0, 0.0) if x else ()
    cantos = tuple(
        (caixa.x0 + dx, caixa.y0 + dy) for dx in (0.0, caixa.width) for dy in (0.0, caixa.height)
    )
    return DesenhoRetangulo(cantos, diagonal, (), (haste[1], haste[0]), bracos)


def _torre(pagina: pymupdf.Page) -> None:
    """Moldura quadrada com as duas diagonais canto a canto."""
    pagina.draw_rect(pymupdf.Rect(140, 140, 150, 150), color=PRETO, width=0.5)  # type: ignore[no-untyped-call]
    pagina.draw_line((140, 140), (150, 150), color=PRETO, width=0.5)
    pagina.draw_line((150, 140), (140, 150), color=PRETO, width=0.5)


def _torre_alongada(pagina: pymupdf.Page) -> None:
    """Moldura de proporção de corpo com as duas diagonais canto a canto: não passam além."""
    pagina.draw_rect(pymupdf.Rect(140, 146, 149, 149), color=PRETO, width=0.5)  # type: ignore[no-untyped-call]
    pagina.draw_line((140, 146), (149, 149), color=PRETO, width=0.5)
    pagina.draw_line((149, 146), (140, 149), color=PRETO, width=0.5)


def desenhar_moldura_de_rotulo(pagina: pymupdf.Page, *, com_texto: bool = True) -> None:
    """Moldura de proporção de corpo com um risco que a atravessa e, por padrão, um texto."""
    pagina.draw_rect(pymupdf.Rect(140, 140, 148, 143), color=PRETO, width=0.5)  # type: ignore[no-untyped-call]
    if com_texto:
        pagina.insert_text((141, 142), "AB", fontsize=2)
    pagina.draw_line((139, 144), (149, 139), color=PRETO, width=0.5)


def _diagonal_nao_passa_alem(pagina: pymupdf.Page) -> None:
    pagina.draw_rect(pymupdf.Rect(148.5, 146, 151.5, 154), color=PRETO, width=0.5)  # type: ignore[no-untyped-call]
    pagina.draw_line((148.5, 154), (151.5, 146), color=PRETO, width=0.5)


def _diagonal_sem_retangulo(pagina: pymupdf.Page) -> None:
    pagina.draw_line((146, 154), (154, 146), color=PRETO, width=0.5)


def _losango(pagina: pymupdf.Page) -> None:
    pagina.draw_polyline(
        [(150, 144), (153, 150), (150, 156), (147, 150), (150, 144)], color=PRETO, width=0.5
    )
    pagina.draw_line((146, 154), (154, 146), color=PRETO, width=0.5)


def diagonal_inclinada(corpo: tuple[float, float], radianos: float) -> tuple[Ponto, Ponto]:
    """Diagonal centrada no corpo vertical, a `radianos` do eixo, com as pontas a 0,8 vezes o lado
    menor fora de cada lado longo."""
    cx, cy = CENTRO
    lateral = corpo[1] / 2 * 1.6
    ao_longo = lateral / math.tan(radianos)
    return (cx - lateral, cy + ao_longo), (cx + lateral, cy - ao_longo)


def diagonal_deslocada(fracao: float) -> tuple[Ponto, Ponto]:
    """A diagonal padrão do `CORPO` deslocada ao longo do eixo de `fracao` vezes o lado maior."""
    cx, cy = CENTRO
    meio_h, meio_l = CORPO[0] / 2, CORPO[1] / 2
    desvio = fracao * CORPO[0]
    return (cx - meio_l * 2, cy + meio_h * 0.5 + desvio), (
        cx + meio_l * 2,
        cy - meio_h * 0.5 + desvio,
    )


NEGATIVOS: Final[dict[str, Callable[[pymupdf.Page], object]]] = {
    "torre_duas_diagonais": _torre,
    "torre_alongada_duas_diagonais": _torre_alongada,
    "moldura_de_rotulo_com_risco": desenhar_moldura_de_rotulo,
    "diagonal_que_nao_passa_alem": _diagonal_nao_passa_alem,
    "diagonal_sem_retangulo": _diagonal_sem_retangulo,
    "losango": _losango,
    "quadrado_com_diagonal_alem": lambda p: desenhar_retangulo(p, corpo=(5.0, 5.0)),
    "proporcao_baixa_demais": lambda p: desenhar_retangulo(p, corpo=(8.0, 4.44)),
    "proporcao_alta_demais": lambda p: desenhar_retangulo(p, corpo=(10.0, 2.0)),
    "proporcao_muito_alta": lambda p: desenhar_retangulo(p, corpo=(10.0, 1.2)),
    "duas_diagonais_no_retangulo": lambda p: desenhar_retangulo(p, segunda_diagonal=True),
    "diagonal_quase_perpendicular": lambda p: desenhar_retangulo(
        p, diagonal=diagonal_inclinada(CORPO, 1.3)
    ),
    "diagonal_quase_paralela": lambda p: desenhar_retangulo(
        p, corpo=(8.8, 2.0), diagonal=diagonal_inclinada((8.8, 2.0), 0.35)
    ),
    "diagonal_longe_do_centro": lambda p: desenhar_retangulo(p, diagonal=diagonal_deslocada(0.3)),
}
"""Desenhos que nenhuma variante de `CASOS_RECT_DIAGONAL` pode casar."""


VIZINHOS_POSITIVOS: Final[dict[str, Callable[[pymupdf.Page], object]]] = {
    "moldura_sem_texto": lambda p: desenhar_moldura_de_rotulo(p, com_texto=False),
    "proporcao_2_2": lambda p: desenhar_retangulo(p, corpo=(8.0, 3.6)),
    "proporcao_4_2": lambda p: desenhar_retangulo(p, corpo=(8.4, 2.0)),
    "diagonal_a_1_1_rad": lambda p: desenhar_retangulo(p, diagonal=diagonal_inclinada(CORPO, 1.1)),
    "diagonal_a_0_45_rad": lambda p: desenhar_retangulo(
        p, corpo=(8.8, 2.0), diagonal=diagonal_inclinada((8.8, 2.0), 0.45)
    ),
    "diagonal_pouco_deslocada": lambda p: desenhar_retangulo(p, diagonal=diagonal_deslocada(0.2)),
}
"""O vizinho de cada limiar que ainda casa a v001: o negativo correspondente falha só nele."""


def pagina_desenhada(
    desenhar: Callable[[pymupdf.Page], object],
    *,
    rotacao: int = 0,
    largura: float = 300.0,
    altura: float = 300.0,
) -> PaginaGramatica:
    """Desenha numa página nova, aplica `/Rotate` e lê a página para as gramáticas."""
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=largura, height=altura)
        desenhar(pagina)
        pagina.set_rotation(rotacao)
        return pagina_para_gramaticas(pagina, 0)
