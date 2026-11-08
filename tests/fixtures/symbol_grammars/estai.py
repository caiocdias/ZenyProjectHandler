"""Fixtures autorais da gramática `forked_stem` (ESTAI), montadas direto no modelo de desenho.

Nenhuma coordenada vem de folha real: o estai é uma haste de comprimento `HASTE` que sai de
`BASE` na direção `graus`, com dois dentes de `DENTE` abertos para longe dela, envolvente (círculo
de retas) e X opcionais.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Final

from tests.fixtures.symbol_grammars.paginas import linha, pagina_gramatica, poligono

from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caminho,
    Cor,
    Estilo,
    ItemCaminho,
    Ponto,
    TextoModelo,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import PaginaGramatica

PRETO: Final[Cor] = (0.0, 0.0, 0.0)
CINZA: Final[Cor] = (0.2, 0.2, 0.2)
VERDE: Final[Cor] = (0.0, 0.5, 0.0)
VERMELHO: Final[Cor] = (1.0, 0.0, 0.0)
ROXO: Final[Cor] = (0.5, 0.0, 0.5)
BRANCO: Final[Cor] = (1.0, 1.0, 1.0)
BASE: Final[Ponto] = (150.0, 150.0)
HASTE: Final = 16.0
DENTE: Final = 12.0
ABERTURA: Final = 26.0
ESPESSURA: Final = 0.2

# Gasto de orçamento da chamada de `estai_candidatos` (sem montar o contexto) para a página de
# três estais de `test_gasto_de_tres_estais_fica_no_registrado` (verde com círculo e dois pretos).
GASTO_DE_TRES_ESTAIS: Final = 181

GRAMATICAS_ESTAI: Final[dict[str, dict[str, Any]]] = {
    "existente": {
        "kind": "forked_stem",
        "enclosure": "none",
        "removal_mark": False,
        "max_span": 40,
    },
    "instalar": {
        "kind": "forked_stem",
        "enclosure": "ellipse",
        "removal_mark": False,
        "max_span": 40,
    },
    "retirar": {"kind": "forked_stem", "enclosure": "none", "removal_mark": True, "max_span": 40},
}


def fino(
    a: Ponto,
    b: Ponto,
    cor: Cor | None = PRETO,
    *,
    ordem: int = 0,
    camada: str = "",
    tracejado: str = "",
    espessura: float = ESPESSURA,
) -> Caminho:
    base = linha(a, b, ordem, cor=cor, camada=camada)
    estilo = Estilo(camada, cor, None, espessura, tracejado)
    return Caminho(base.subcaminhos, estilo, "traco", ordem)


def polar(origem: Ponto, graus: float, comprimento: float) -> Ponto:
    r = math.radians(graus)
    return (origem[0] + comprimento * math.cos(r), origem[1] + comprimento * math.sin(r))


def vertice_de(graus: float = 0.0, base: Ponto = BASE, haste: float = HASTE) -> Ponto:
    return polar(base, graus, haste)


def garfo(
    graus: float = 0.0,
    cor: Cor | None = PRETO,
    *,
    base: Ponto = BASE,
    haste: float = HASTE,
    dente: float = DENTE,
    abertura: float = ABERTURA,
    tracejado: str = "",
    ordem: int = 0,
) -> list[Caminho]:
    """Haste de `base` até o vértice, e os dentes abertos para longe dela."""
    vertice = vertice_de(graus, base, haste)
    return [
        fino(base, vertice, cor, tracejado=tracejado, ordem=ordem),
        fino(
            vertice, polar(vertice, graus + abertura, dente), cor, tracejado=tracejado, ordem=ordem
        ),
        fino(
            vertice, polar(vertice, graus - abertura, dente), cor, tracejado=tracejado, ordem=ordem
        ),
    ]


def centro_do_garfo(graus: float = 0.0, base: Ponto = BASE) -> Ponto:
    """Centro do círculo em que o vértice fica sobre a borda e os dentes ficam dentro."""
    return polar(vertice_de(graus, base), graus, DENTE * 0.75)


def circulo(centro: Ponto, raio: float, cor: Cor | None = PRETO, *, ordem: int = 0) -> Caminho:
    """Círculo de 32 retas fechado, como a envolvente das folhas."""
    pontos = [polar(centro, i * 360.0 / 32, raio) for i in range(32)]
    base = poligono(pontos, ordem, cor=cor)
    itens = base.subcaminhos[0]
    fecho = (*itens, ItemCaminho("l", (pontos[-1], pontos[0])))[: len(itens)]
    return Caminho((fecho,), Estilo("", cor, None, ESPESSURA, ""), "traco", ordem)


def estai_com_circulo(
    graus: float = 0.0, cor: Cor = VERDE, *, base: Ponto = BASE, cor_circulo: Cor | None = None
) -> list[Caminho]:
    centro = centro_do_garfo(graus, base)
    return [
        *garfo(graus, cor, base=base),
        circulo(centro, DENTE * 0.8, cor if cor_circulo is None else cor_circulo),
    ]


def x_sobre(
    centro: Ponto, meio: float = 9.0, cor: Cor = VERMELHO, *, ordem: int = 1
) -> list[Caminho]:
    return [
        fino(polar(centro, 45, meio), polar(centro, 225, meio), cor, ordem=ordem, espessura=1.2),
        fino(polar(centro, 135, meio), polar(centro, 315, meio), cor, ordem=ordem, espessura=1.2),
    ]


def pagina_estai(
    formas: Sequence[Caminho], *, textos: Sequence[TextoModelo] = ()
) -> PaginaGramatica:
    """A página sintética com as `formas` desenhadas, sem primitivas (como a leitura do modelo)."""
    return pagina_gramatica(formas, textos=textos, primitivas=())
