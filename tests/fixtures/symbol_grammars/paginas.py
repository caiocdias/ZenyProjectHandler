"""Páginas sintéticas do modelo de desenho para testar as gramáticas, sem PyMuPDF."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, Literal

from zeny_project_handler.adapters.analysis.drawing_model.geometry import (
    reconstruir_polilinhas,
    recuperar_circulos_e_arcos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Arco,
    Caixa,
    Caminho,
    Circulo,
    Cor,
    Estilo,
    ItemCaminho,
    PaginaModelo,
    Polilinha,
    Ponto,
    TextoModelo,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import PaginaGramatica

KAPPA: Final = 0.5522847498307936
# `indices_crus` deslocado: um teste nota quem confunde posição com índice cru.
DESLOCAMENTO_INDICE_CRU: Final = 10
PRETO: Final[Cor] = (0.0, 0.0, 0.0)


def estilo(
    cor: Cor | None = PRETO,
    preenchimento: Cor | None = None,
    camada: str = "",
) -> Estilo:
    return Estilo(camada=camada, cor=cor, preenchimento=preenchimento, espessura=1.0, tracejado="")


def _tipo(
    cor: Cor | None, preenchimento: Cor | None
) -> Literal["traco", "preenchimento", "traco_e_preenchimento"]:
    if preenchimento is None:
        return "traco"
    return "preenchimento" if cor is None else "traco_e_preenchimento"


def linha(
    a: Ponto,
    b: Ponto,
    ordem: int = 0,
    *,
    cor: Cor | None = PRETO,
    camada: str = "",
) -> Caminho:
    return Caminho(((ItemCaminho("l", (a, b)),),), estilo(cor, None, camada), "traco", ordem)


def poligono(
    pontos: Sequence[Ponto],
    ordem: int = 0,
    preenchimento: Cor | None = None,
    *,
    cor: Cor | None = PRETO,
    camada: str = "",
) -> Caminho:
    """Um subcaminho fechado com os lados na ordem dos pontos."""
    itens = tuple(
        ItemCaminho("l", (ponto, pontos[(i + 1) % len(pontos)])) for i, ponto in enumerate(pontos)
    )
    return Caminho((itens,), estilo(cor, preenchimento, camada), _tipo(cor, preenchimento), ordem)


def retangulo_traco(
    caixa: Caixa,
    ordem: int = 0,
    *,
    cor: Cor | None = PRETO,
    camada: str = "",
) -> Caminho:
    x0, y0, x1, y1 = caixa
    return poligono(((x0, y0), (x1, y0), (x1, y1), (x0, y1)), ordem, cor=cor, camada=camada)


def circulo_bezier(
    centro: Ponto,
    raio: float,
    ordem: int = 0,
    *,
    cor: Cor | None = PRETO,
    preenchimento: Cor | None = None,
    camada: str = "",
) -> Caminho:
    """Círculo de 4 Béziers cúbicas no mesmo subcaminho."""
    cx, cy = centro
    k = KAPPA * raio
    itens = (
        ItemCaminho(
            "c", ((cx + raio, cy), (cx + raio, cy + k), (cx + k, cy + raio), (cx, cy + raio))
        ),
        ItemCaminho(
            "c", ((cx, cy + raio), (cx - k, cy + raio), (cx - raio, cy + k), (cx - raio, cy))
        ),
        ItemCaminho(
            "c", ((cx - raio, cy), (cx - raio, cy - k), (cx - k, cy - raio), (cx, cy - raio))
        ),
        ItemCaminho(
            "c", ((cx, cy - raio), (cx + k, cy - raio), (cx + raio, cy - k), (cx + raio, cy))
        ),
    )
    return Caminho((itens,), estilo(cor, preenchimento, camada), _tipo(cor, preenchimento), ordem)


def texto(
    palavra: str,
    caixa: Caixa,
    origem: Literal["nativo", "shx", "glifo"] = "nativo",
    rotacao: float = 0.0,
) -> TextoModelo:
    return TextoModelo(palavra, caixa, origem, rotacao, caixa[3] - caixa[1], "", "")


def pagina_gramatica(
    caminhos: Sequence[Caminho],
    textos: Sequence[TextoModelo] = (),
    primitivas: Sequence[Polilinha | Circulo | Arco] | None = None,
    largura: float = 300.0,
    altura: float = 300.0,
    translucidos: frozenset[int] = frozenset(),
    diagnosticos: Sequence[str] = (),
) -> PaginaGramatica:
    """Com `primitivas=None`, as primitivas são as que o modelo reconstruiria dos caminhos."""
    if primitivas is None:
        primitivas = (*reconstruir_polilinhas(caminhos), *recuperar_circulos_e_arcos(caminhos))
    modelo = PaginaModelo(
        indice=0,
        largura=largura,
        altura=altura,
        caminhos=tuple(caminhos),
        textos=tuple(textos),
        primitivas=tuple(primitivas),
        grupos=(),
        imagens=(),
        diagnosticos=tuple(diagnosticos),
    )
    indices_crus = tuple(range(DESLOCAMENTO_INDICE_CRU, DESLOCAMENTO_INDICE_CRU + len(caminhos)))
    return PaginaGramatica(modelo, indices_crus, translucidos)
