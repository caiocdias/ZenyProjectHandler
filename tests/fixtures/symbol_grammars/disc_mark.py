"""Fixtures autorais da gramática `disc_mark`, montadas direto no modelo de desenho.

Nenhuma coordenada vem de folha real: o desenho é relativo ao vão do disco, em torno de `CENTRO`.
`fuse_curve` é uma diagonal, duas polilinhas abertas e dois pontos; `double_box` é a mesma diagonal,
um retângulo girado, uma reta paralela ao lado longo dele e os dois pontos.
"""

from __future__ import annotations

import math
from itertools import pairwise
from typing import Any, Final

from tests.fixtures.symbol_grammars.paginas import circulo_bezier, linha, poligono

from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caminho,
    Cor,
    Estilo,
    ItemCaminho,
    Ponto,
)

PRETO: Final[Cor] = (0.0, 0.0, 0.0)
VERMELHO: Final[Cor] = (1.0, 0.0, 0.0)
VERDE: Final[Cor] = (0.0, 0.5, 0.0)
BRANCO: Final[Cor] = (1.0, 1.0, 1.0)
CENTRO: Final[Ponto] = (150.0, 150.0)
VAOS: Final = (5.0, 7.2, 10.0, 14.4)
VAO: Final = 14.4

FUSIVEL: Final[dict[str, Any]] = {
    "kind": "disc_mark",
    "fill": "red",
    "content": "fuse_curve",
    "min_span": 4.0,
    "max_span": 72.0,
}
CAIXA_DUPLA: Final[dict[str, Any]] = {**FUSIVEL, "content": "double_box"}

# O retângulo da caixa dupla: metades dos lados, relativas ao vão; `_AFASTAMENTO` é a distância
# da reta ao centro dele.
_MEIA_LONGA: Final = 0.2
_MEIA_CURTA: Final = 0.14
_AFASTAMENTO: Final = 0.24
_RAIO_DO_PONTO: Final = 0.045
_LADOS_DO_PONTO: Final = 8
_ONDULACAO: Final = 0.03
SEGMENTOS_DA_CURVA: Final = 12


def relativo(vao: float, x: float, y: float, centro: Ponto = CENTRO) -> Ponto:
    return (centro[0] + x * vao, centro[1] + y * vao)


def disco(vao: float = VAO, cor: Cor = VERMELHO, ordem: int = 0, centro: Ponto = CENTRO) -> Caminho:
    return circulo_bezier(centro, vao / 2, ordem, cor=cor, preenchimento=cor)


def disco_em_dois_caminhos(vao: float = VAO, ordem: int = 0) -> list[Caminho]:
    """O disco do Ghostscript: o preenchimento e, depois, o traço de fecho sem preenchimento."""
    return [
        circulo_bezier(CENTRO, vao / 2, ordem, cor=None, preenchimento=VERMELHO),
        circulo_bezier(CENTRO, vao / 2, ordem + 1, cor=VERMELHO),
    ]


def elipse_vermelha(vao: float = VAO, razao: float = 2.0) -> Caminho:
    """Um disco esticado na horizontal por `razao`: 4 curvas, mas sem aspecto de disco."""
    base = disco(vao)
    itens = tuple(
        ItemCaminho(
            item.tipo,
            tuple((CENTRO[0] + (x - CENTRO[0]) * razao, y) for x, y in item.pontos),
        )
        for item in base.subcaminhos[0]
    )
    return Caminho((itens,), base.estilo, base.tipo, base.ordem)


def polilinha(
    vao: float,
    inicio: tuple[float, float],
    fim: tuple[float, float],
    ordem: int,
    *,
    segmentos: int = SEGMENTOS_DA_CURVA,
    cor: Cor = PRETO,
    centro: Ponto = CENTRO,
) -> Caminho:
    pontos = [
        relativo(
            vao,
            inicio[0] + (fim[0] - inicio[0]) * i / segmentos,
            inicio[1] + (fim[1] - inicio[1]) * i / segmentos + _ONDULACAO * math.sin(i),
            centro,
        )
        for i in range(segmentos + 1)
    ]
    itens = tuple(ItemCaminho("l", (a, b)) for a, b in pairwise(pontos))
    return Caminho((itens,), Estilo("", cor, None, 0.14, ""), "traco", ordem)


def ponto_terminal(
    vao: float,
    x: float,
    y: float,
    ordem: int,
    *,
    preenchido: bool = True,
    raio: float = _RAIO_DO_PONTO,
    centro: Ponto = CENTRO,
) -> Caminho:
    cx, cy = relativo(vao, x, y, centro)
    pontos = [
        (
            cx + raio * vao * math.cos(2 * math.pi * i / _LADOS_DO_PONTO),
            cy + raio * vao * math.sin(2 * math.pi * i / _LADOS_DO_PONTO),
        )
        for i in range(_LADOS_DO_PONTO)
    ]
    return poligono(pontos, ordem, PRETO if preenchido else None, cor=PRETO)


def diagonal(vao: float, ordem: int, centro: Ponto = CENTRO) -> Caminho:
    return linha(relativo(vao, -0.12, 0.25, centro), relativo(vao, 0.12, -0.25, centro), ordem)


def curvas_do_fusivel(
    vao: float, ordem: int, *, segmentos: int = SEGMENTOS_DA_CURVA
) -> list[Caminho]:
    return [
        polilinha(vao, (-0.05, 0.3), (0.05, 0.02), ordem, segmentos=segmentos),
        polilinha(vao, (0.05, -0.3), (-0.05, -0.02), ordem + 1, segmentos=segmentos),
    ]


def pontos_dos_terminais(vao: float, ordem: int, centro: Ponto = CENTRO) -> list[Caminho]:
    return [
        ponto_terminal(vao, -0.13, 0.27, ordem, centro=centro),
        ponto_terminal(vao, 0.13, -0.27, ordem + 1, centro=centro),
    ]


def conteudo_fusivel(vao: float = VAO, ordem: int = 1, centro: Ponto = CENTRO) -> list[Caminho]:
    """Diagonal (ordem), 2 polilinhas (+1, +2) e 2 pontos (+3, +4)."""
    return [
        diagonal(vao, ordem, centro),
        polilinha(vao, (-0.05, 0.3), (0.05, 0.02), ordem + 1, centro=centro),
        polilinha(vao, (0.05, -0.3), (-0.05, -0.02), ordem + 2, centro=centro),
        *pontos_dos_terminais(vao, ordem + 3, centro),
    ]


def _eixos(graus: float) -> tuple[tuple[float, float], tuple[float, float]]:
    angulo = math.radians(graus)
    return (math.cos(angulo), math.sin(angulo)), (math.sin(angulo), -math.cos(angulo))


def retangulo_girado(
    vao: float = VAO,
    ordem: int = 1,
    *,
    graus: float = 25.0,
    torcao: float = 0.0,
    escala: float = 1.0,
) -> Caminho:
    """Retângulo de 4 retas; `torcao` empurra um canto, para que os lados deixem de ser retos."""
    u, n = _eixos(graus)
    cantos = [
        relativo(
            vao,
            escala * (su * _MEIA_LONGA * u[0] + sn * _MEIA_CURTA * n[0]),
            escala * (su * _MEIA_LONGA * u[1] + sn * _MEIA_CURTA * n[1]),
        )
        for su, sn in ((-1, 1), (1, 1), (1, -1), (-1, -1))
    ]
    cantos[0] = (cantos[0][0] + torcao * vao, cantos[0][1])
    return poligono(cantos, ordem, None, cor=PRETO)


def reta_paralela(
    vao: float = VAO,
    ordem: int = 2,
    *,
    graus: float = 25.0,
    afastamento: float = _AFASTAMENTO,
    fracao_do_lado: float = 1.0,
    giro: float = 0.0,
) -> Caminho:
    """Reta do lado de fora do retângulo; `giro` a tira do paralelismo com o lado longo."""
    _, n = _eixos(graus)
    direcao, _ = _eixos(graus + giro)
    meio = (-afastamento * n[0], -afastamento * n[1])
    meia = _MEIA_LONGA * fracao_do_lado
    return linha(
        relativo(vao, meio[0] - meia * direcao[0], meio[1] - meia * direcao[1]),
        relativo(vao, meio[0] + meia * direcao[0], meio[1] + meia * direcao[1]),
        ordem,
    )


def conteudo_caixa_dupla(vao: float = VAO, ordem: int = 1, *, graus: float = 25.0) -> list[Caminho]:
    """Diagonal (ordem), retângulo (+1), reta (+2) e 2 pontos (+3, +4)."""
    return [
        diagonal(vao, ordem),
        retangulo_girado(vao, ordem + 1, graus=graus),
        reta_paralela(vao, ordem + 2, graus=graus),
        *pontos_dos_terminais(vao, ordem + 3),
    ]


def repintado(caminho: Caminho, ordem: int) -> Caminho:
    """O mesmo desenho escrito de novo, como o Ghostscript faz em preenchimento e traço."""
    return Caminho(caminho.subcaminhos, caminho.estilo, caminho.tipo, ordem)
