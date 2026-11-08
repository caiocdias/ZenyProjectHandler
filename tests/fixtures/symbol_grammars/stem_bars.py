"""Hastes com barras sintéticas (ATERRAMENTO e PARA_RAIOS_MT), desenhadas com PyMuPDF.

Desenho autoral: haste de `HASTE` pt com as barras a partir de uma ponta, perpendiculares a ela e
espaçadas de `LACUNA` pt; envolvente circular e X vermelho opcionais. Nada vem de folha real.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final

import pymupdf

from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa, Cor, Ponto
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import PaginaGramatica
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_para_gramaticas

PRETO: Final[Cor] = (0.0, 0.0, 0.0)
VERMELHO: Final[Cor] = (1.0, 0.0, 0.0)
HASTE: Final = 10.0
LACUNA: Final = 2.5
DECRESCENTES: Final = (8.0, 5.5, 3.0)
ALTERNADAS: Final = (8.0, 5.0, 8.0, 5.0)
CENTRO: Final[Ponto] = (150.0, 150.0)
# Raios relativos dos vértices de uma envolvente desenhada como polilinha fechada.
CIRCULO_POLIGONAL: Final = (1.0,) * 32
HEXAGONO: Final = (1.0,) * 6
ESTRELA: Final = (1.0, 0.6) * 8


def _gramatica(barras: int, envolvente: bool, x: bool) -> dict[str, Any]:
    return {
        "kind": "stem_bars",
        "bars": barras,
        "taper": "decreasing" if barras == 3 else "alternating",
        "enclosure": "ellipse" if envolvente else "none",
        "removal_mark": x,
        "max_span": 72,
    }


CASOS_HASTE: Final[tuple[tuple[str, dict[str, Any]], ...]] = (
    ("cemig-eo-r3-s19-v001", _gramatica(3, envolvente=False, x=False)),
    ("cemig-eo-r3-s19-v002", _gramatica(3, envolvente=True, x=False)),
    ("cemig-eo-r3-s19-v003", _gramatica(3, envolvente=True, x=True)),
    ("cemig-eo-r3-s19-v004", _gramatica(3, envolvente=False, x=True)),
    ("cemig-eo-r3-s21-v005", _gramatica(4, envolvente=False, x=False)),
    ("cemig-eo-r3-s21-v006", _gramatica(4, envolvente=True, x=False)),
    ("cemig-eo-r3-s21-v007", _gramatica(4, envolvente=True, x=True)),
    ("cemig-eo-r3-s21-v008", _gramatica(4, envolvente=False, x=True)),
)
"""Id de cada variante de f02-19 (ATERRAMENTO) e f02-21 (PARA_RAIOS_MT) e a gramática dela."""


@dataclass(frozen=True, slots=True)
class DesenhoHaste:
    """O que foi desenhado, no espaço da página antes de qualquer `/Rotate`."""

    ponta: Ponto
    base: Ponto
    barras: tuple[tuple[Ponto, Ponto], ...]
    envolvente: Caixa | None
    bracos_x: tuple[tuple[Ponto, Ponto], ...]


def _gira(ponto: Ponto, centro: Ponto, graus: float) -> Ponto:
    r = math.radians(graus)
    dx, dy = ponto[0] - centro[0], ponto[1] - centro[1]
    return (
        centro[0] + dx * math.cos(r) - dy * math.sin(r),
        centro[1] + dx * math.sin(r) + dy * math.cos(r),
    )


def _linha(pagina: pymupdf.Page, a: Ponto, b: Ponto, cor: Cor) -> tuple[Ponto, Ponto]:
    pagina.draw_line(a, b, color=cor, width=0.5)
    return a, b


def desenhar_haste(
    pagina: pymupdf.Page,
    comprimentos: Sequence[float],
    centro: Ponto = CENTRO,
    graus: float = 0.0,
    *,
    lacuna: float = LACUNA,
    haste: float = HASTE,
    envolvente: bool = False,
    x: bool = False,
    cor: Cor = PRETO,
    cor_barras: Cor | None = None,
    desvio_barras: float = 0.0,
    linha_longa: float = 0.0,
    x_em_contorno: bool = False,
    contorno: Sequence[float] = (),
) -> DesenhoHaste:
    """Haste de `centro` para cima, barras a partir da ponta de cima, tudo girado `graus`.

    `linha_longa` > 0 desenha, no mesmo estilo, uma linha da rede colinear que continua a haste a
    partir da base (outro caminho, encostado). `desvio_barras` gira cada barra em torno do meio.
    `x_em_contorno` desenha o X com um braço solto e o outro como lado de um quadrilátero fechado
    (um caminho de quatro traços): o cruzamento de um traço com o contorno de outro desenho.
    Com `contorno`, a envolvente é uma polilinha fechada com um vértice por raio relativo, como
    o círculo achatado em segmentos que alguns PDFs trazem, e não quatro Béziers.
    """
    cx, cy = centro
    ponta, base = (cx, cy - haste / 2), (cx, cy + haste / 2)

    def g(p: Ponto) -> Ponto:
        return _gira(p, centro, graus)

    _linha(pagina, g(base), g(ponta), cor)
    if linha_longa > 0:
        _linha(pagina, g((cx, base[1] + linha_longa)), g(base), cor)
    inclinacao = math.tan(math.radians(desvio_barras))
    barras = []
    for i, comprimento in enumerate(comprimentos):
        y, meio = ponta[1] - i * lacuna, comprimento / 2
        a, b = (cx - meio, y + inclinacao * meio), (cx + meio, y - inclinacao * meio)
        barras.append(_linha(pagina, g(a), g(b), cor if cor_barras is None else cor_barras))
    meio_barras = (cx, ponta[1] - (len(comprimentos) - 1) * lacuna / 2)
    caixa_envolvente = None
    if envolvente:
        raio = max(comprimentos) * 0.8 + len(comprimentos) * lacuna / 2
        centro_env = g(meio_barras)
        if contorno:
            vertices = [
                (
                    centro_env[0] + raio * r * math.cos(2 * math.pi * k / len(contorno)),
                    centro_env[1] + raio * r * math.sin(2 * math.pi * k / len(contorno)),
                )
                for k, r in enumerate(contorno)
            ]
            pagina.draw_polyline([*vertices, vertices[0]], color=cor, width=0.5)
            caixa_envolvente = (
                min(v[0] for v in vertices),
                min(v[1] for v in vertices),
                max(v[0] for v in vertices),
                max(v[1] for v in vertices),
            )
        else:
            caixa_envolvente = (
                centro_env[0] - raio,
                centro_env[1] - raio,
                centro_env[0] + raio,
                centro_env[1] + raio,
            )
            pagina.draw_oval(pymupdf.Rect(caixa_envolvente), color=cor, width=0.5)  # type: ignore[no-untyped-call]
    bracos: list[tuple[Ponto, Ponto]] = []
    if x:
        t = max(comprimentos) * 0.9
        for sinal in (1, -1):
            a = (meio_barras[0] - t, meio_barras[1] - sinal * t)
            b = (meio_barras[0] + t, meio_barras[1] + sinal * t)
            if x_em_contorno and sinal == -1:
                cantos = [g(p) for p in (a, b, (b[0] + 2 * t, b[1]), (a[0] + 2 * t, a[1]))]
                pagina.draw_polyline([*cantos, cantos[0]], color=VERMELHO, width=0.5)
                bracos.append((g(a), g(b)))
            else:
                bracos.append(_linha(pagina, g(a), g(b), VERMELHO))
    return DesenhoHaste(g(ponta), g(base), tuple(barras), caixa_envolvente, tuple(bracos))


def _parametros(variante: str) -> tuple[Sequence[float], bool, bool]:
    gramatica = dict(CASOS_HASTE)[variante]
    comprimentos = DECRESCENTES if gramatica["bars"] == 3 else ALTERNADAS
    return comprimentos, gramatica["enclosure"] == "ellipse", bool(gramatica["removal_mark"])


def desenhar_positivo(
    pagina: pymupdf.Page,
    variante: str,
    centro: Ponto = CENTRO,
    graus: float = 0.0,
    *,
    linha_longa: float = 0.0,
) -> DesenhoHaste:
    """O positivo da variante `variante` de `CASOS_HASTE`."""
    comprimentos, envolvente, x = _parametros(variante)
    return desenhar_haste(
        pagina, comprimentos, centro, graus, envolvente=envolvente, x=x, linha_longa=linha_longa
    )


def _hachura(pagina: pymupdf.Page) -> None:
    for i in range(6):
        _linha(pagina, (140.0 + i * 2.0, 140.0), (140.0 + i * 2.0, 150.0), PRETO)


def _glifo_e(pagina: pymupdf.Page) -> None:
    """Letra E desenhada como traços soltos: a "haste" com três braços iguais na lateral."""
    _linha(pagina, (140.0, 140.0), (140.0, 150.0), PRETO)
    for y in (140.0, 145.0, 150.0):
        _linha(pagina, (140.0, y), (146.0, y), PRETO)


def _glifo_identico(pagina: pymupdf.Page) -> None:
    """`≡` desenhado como três traços paralelos iguais, sem haste."""
    for y in (144.0, 147.0, 150.0):
        _linha(pagina, (140.0, y), (148.0, y), PRETO)


NEGATIVOS: Final[dict[str, Callable[[pymupdf.Page], object]]] = {
    "tres_barras_iguais": lambda p: desenhar_haste(p, (8.0, 8.0, 8.0)),
    "duas_barras": lambda p: desenhar_haste(p, (8.0, 5.0)),
    "barras_nao_perpendiculares": lambda p: desenhar_haste(p, DECRESCENTES, desvio_barras=35.0),
    "espacamento_fora_da_faixa": lambda p: desenhar_haste(p, DECRESCENTES, lacuna=9.0),
    "hachura_de_seis_tracos": _hachura,
    "glifo_e": _glifo_e,
    "glifo_identico": _glifo_identico,
    "barras_de_outra_cor": lambda p: desenhar_haste(p, DECRESCENTES, cor_barras=VERMELHO),
}
"""Desenhos que nenhuma variante de `CASOS_HASTE` pode casar."""


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
