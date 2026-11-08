"""Marcas compartilhadas pelas gramáticas do modelo: sinal da página, cor, envolvente e X.

Saíram de `grammar_stem.py` com os mesmos limiares e a mesma semântica (R-E06.3.3.1-2), para
outra gramática reaproveitá-los. Os contornos da página são pagos uma vez por contexto e só
quando alguém os pede, por `MarcasDaPagina`; a função que os monta fica privada.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caixa,
    Cor,
    PaginaModelo,
    Polilinha,
    Ponto,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    _MARGEM_PAGINA,
    ContextoGramatica,
    GradeEspacial,
    Segmento,
    _caixa_de_pontos,
)

_ORIGENS: Final = ("glifo", "shx", "nativo")

# Envolvente: diâmetro relativo à escala; polilinha fechada com vértices bastantes e todos
# perto da elipse da caixa.
_ENVOLVENTE: Final = (0.95, 3.06)
_VERTICES_MINIMOS_ELIPSE: Final = 8
_DESVIO_RAIO_ELIPSE: Final = 0.2

# X de retirada: braços de comprimento relativo à escala, cruzando perto dos meios.
_MARGEM_X: Final = 0.5
_BRACO_X: Final = (0.8, 3.0)
_ANGULO_BRACO_X: Final = (math.radians(25), math.radians(65))
_MEIO_DO_BRACO: Final = (0.3, 0.7)
_RAZAO_BRACOS: Final = 1.3
_ABERTURA_X: Final = math.radians(45)
_TOLERANCIA_COR: Final = 0.02


def origem_predominante(modelo: PaginaModelo) -> str:
    """Origem de texto mais frequente da página; sem texto, "nativo". Empate: a maior no nome."""
    contagem: Counter[str] = Counter(texto.origem for texto in modelo.textos)
    if not contagem:
        return "nativo"
    return max(_ORIGENS, key=lambda origem: (contagem[origem], origem))


def cor_canonica(cor: Cor | None, preenchimento: Cor | None) -> str | None:
    """As cores do legado (`_canonical_symbol_color`): preto, vermelho e verde; o resto sai."""
    for bruto in (cor, preenchimento):
        if bruto is None:
            continue
        r, g, b = (round(canal * 255) for canal in bruto)
        if max(r, g, b) <= 40:
            return "#000000"
        if r >= 96 and r >= g * 2 and r >= b * 2:
            return "#FF0000"
        if g >= 64 and g >= r * 2 and g >= b * 2:
            return "#008000"
    return None


def diferenca_angular(a: float, b: float) -> float:
    """Diferença entre dois ângulos de reta, em [0, pi/2]."""
    d = abs(a - b) % math.pi
    return min(d, math.pi - d)


def um_traco(modelo: PaginaModelo, caminho: int) -> bool:
    """Caminho de um subcaminho com um item só: a haste, as barras e os braços do X são traços
    soltos, e o lado de um contorno (moldura, caixa do poste) não conta como nenhum deles."""
    subcaminhos = modelo.caminhos[caminho].subcaminhos
    return len(subcaminhos) == 1 and len(subcaminhos[0]) == 1


@dataclass(frozen=True, slots=True)
class Contorno:
    """Envolvente candidata: elipse do índice de molduras ou polilinha fechada elíptica."""

    caixa: Caixa
    caminhos: tuple[int, ...]


class MarcasDaPagina:
    """As marcas de uma página, lidas uma vez por contexto e só quando alguém as pede."""

    __slots__ = ("_contexto", "_contornos", "_origem")

    def __init__(self, contexto: ContextoGramatica) -> None:
        self._contexto = contexto
        self._origem: str | None = None
        self._contornos: GradeEspacial[Contorno] | None = None

    @property
    def origem(self) -> str:
        """A origem predominante dos textos da página; não gasta do orçamento."""
        if self._origem is None:
            self._origem = origem_predominante(self._contexto.pagina.modelo)
        return self._origem

    @property
    def contornos(self) -> GradeEspacial[Contorno]:
        """O índice das envolventes da página, pago no primeiro pedido."""
        if self._contornos is None:
            self._contornos = _contornos(self._contexto)
        return self._contornos


def _dentro_da_elipse(caixa: Caixa, ponto: Ponto, tolerancia: float) -> bool:
    a = (caixa[2] - caixa[0]) / 2 + tolerancia
    b = (caixa[3] - caixa[1]) / 2 + tolerancia
    if a <= 0 or b <= 0:
        return False
    cx, cy = (caixa[0] + caixa[2]) / 2, (caixa[1] + caixa[3]) / 2
    return ((ponto[0] - cx) / a) ** 2 + ((ponto[1] - cy) / b) ** 2 <= 1.0


def _elipse_poligonal(polilinha: Polilinha) -> Caixa | None:
    """Caixa da polilinha fechada cujos vértices estão todos perto da elipse inscrita nela."""
    if (
        not polilinha.fechada
        or not polilinha.origens
        or len(polilinha.pontos) < _VERTICES_MINIMOS_ELIPSE
    ):
        return None
    caixa = _caixa_de_pontos(polilinha.pontos)
    if caixa is None:
        return None
    a, b = (caixa[2] - caixa[0]) / 2, (caixa[3] - caixa[1]) / 2
    if a <= 0 or b <= 0:
        return None
    cx, cy = (caixa[0] + caixa[2]) / 2, (caixa[1] + caixa[3]) / 2
    elipticos = all(
        abs(math.hypot((x - cx) / a, (y - cy) / b) - 1.0) <= _DESVIO_RAIO_ELIPSE
        for x, y in polilinha.pontos
    )
    return caixa if elipticos else None


def _contornos(contexto: ContextoGramatica) -> GradeEspacial[Contorno]:
    """Índice das envolventes da página: as elipses das molduras (Béziers e círculos) e as
    polilinhas fechadas elípticas; cada polilinha fechada examinada gasta 1."""
    modelo = contexto.pagina.modelo
    contornos = [
        Contorno(moldura.caixa, (moldura.caminho,))
        for moldura in contexto.molduras
        if moldura.forma == "elipse"
    ]
    fechadas = [p for p in modelo.primitivas if isinstance(p, Polilinha) and p.fechada]
    contexto.orcamento.gastar(len(fechadas))
    for polilinha in fechadas:
        caixa = _elipse_poligonal(polilinha)
        if caixa is not None:
            contornos.append(Contorno(caixa, tuple(sorted(set(polilinha.origens)))))
    limites = (
        -_MARGEM_PAGINA,
        -_MARGEM_PAGINA,
        modelo.largura + _MARGEM_PAGINA,
        modelo.altura + _MARGEM_PAGINA,
    )
    return GradeEspacial(((c.caixa, c) for c in contornos), limites, contexto.orcamento)


def envolvente(
    contornos: GradeEspacial[Contorno],
    exigidos: Sequence[Ponto],
    escala: float,
    ancora: Ponto,
    proprios: frozenset[int],
) -> Contorno | None:
    """A menor elipse que contém todos os `exigidos`, como `_enclosing_outline` do legado.

    O diâmetro fica entre `_ENVOLVENTE` vezes a `escala`, a busca é numa janela em torno da
    `ancora`, e um contorno com caminho em `proprios` não conta.
    """
    minimo, maximo = _ENVOLVENTE
    tolerancia = max(0.01, escala * 0.02)
    alcance = escala * maximo
    janela = (
        ancora[0] - alcance,
        ancora[1] - alcance,
        ancora[0] + alcance,
        ancora[1] + alcance,
    )
    opcoes: list[tuple[float, tuple[int, ...], Contorno]] = []
    for contorno in contornos.consultar(janela):
        caixa = contorno.caixa
        diametro = max(caixa[2] - caixa[0], caixa[3] - caixa[1])
        if (
            proprios.isdisjoint(contorno.caminhos)
            and minimo * escala <= diametro <= maximo * escala
            and all(_dentro_da_elipse(caixa, p, tolerancia) for p in exigidos)
        ):
            opcoes.append((diametro, contorno.caminhos, contorno))
    if not opcoes:
        return None
    return min(opcoes, key=lambda opcao: (opcao[0], opcao[1]))[2]


def angulo(segmento: Segmento) -> float:
    """Ângulo de reta do segmento, em [0, pi)."""
    return math.atan2(segmento.b[1] - segmento.a[1], segmento.b[0] - segmento.a[0]) % math.pi


def _intersecao(a: Segmento, b: Segmento) -> tuple[float, float] | None:
    """Parâmetros (ta, tb) em (0, 1) do cruzamento próprio dos dois segmentos."""
    dax, day = a.b[0] - a.a[0], a.b[1] - a.a[1]
    dbx, dby = b.b[0] - b.a[0], b.b[1] - b.a[1]
    det = dax * dby - day * dbx
    if abs(det) < 1e-12:
        return None
    ex, ey = b.a[0] - a.a[0], b.a[1] - a.a[1]
    ta = (ex * dby - ey * dbx) / det
    tb = (ex * day - ey * dax) / det
    return (ta, tb) if 0.0 < ta < 1.0 and 0.0 < tb < 1.0 else None


def _mesma_cor(a: Cor | None, b: Cor | None) -> bool:
    """Mesma cor canônica do legado; fora delas, canais a no máximo `_TOLERANCIA_COR`."""
    canonica_a, canonica_b = cor_canonica(a, None), cor_canonica(b, None)
    if canonica_a is not None or canonica_b is not None:
        return canonica_a == canonica_b
    if a is None or b is None:
        return a is b
    return all(abs(x - y) <= _TOLERANCIA_COR for x, y in zip(a, b, strict=True))


def _formam_x(primeiro: Segmento, segundo: Segmento, contexto: ContextoGramatica) -> bool:
    cruz = _intersecao(primeiro, segundo)
    if cruz is None:
        return False
    c1, c2 = math.dist(primeiro.a, primeiro.b), math.dist(segundo.a, segundo.b)
    caminhos = contexto.pagina.modelo.caminhos
    return (
        all(_MEIO_DO_BRACO[0] <= t <= _MEIO_DO_BRACO[1] for t in cruz)
        and max(c1, c2) <= min(c1, c2) * _RAZAO_BRACOS
        and diferenca_angular(angulo(primeiro), angulo(segundo)) >= _ABERTURA_X
        and _mesma_cor(caminhos[primeiro.caminho].estilo.cor, caminhos[segundo.caminho].estilo.cor)
    )


def tem_x(
    contexto: ContextoGramatica,
    pictograma: Caixa,
    escala: float,
    eixo: float,
    proprios: frozenset[Segmento],
) -> tuple[Segmento, Segmento] | None:
    """Dois braços soltos de mesma cor e comprimento parecido que se cruzam perto dos meios.

    Os braços ficam em torno do `pictograma`, com comprimento relativo à `escala` e inclinados
    em relação ao `eixo` (ângulo de reta, em radianos); os segmentos `proprios` não contam.
    """
    margem = escala * _MARGEM_X
    janela = (
        pictograma[0] - margem,
        pictograma[1] - margem,
        pictograma[2] + margem,
        pictograma[3] + margem,
    )
    bracos = [
        s
        for s in contexto.grade_segmentos.consultar(janela)
        if s not in proprios
        and um_traco(contexto.pagina.modelo, s.caminho)
        and escala * _BRACO_X[0] <= math.dist(s.a, s.b) <= escala * _BRACO_X[1]
        and _ANGULO_BRACO_X[0] <= diferenca_angular(angulo(s), eixo) <= _ANGULO_BRACO_X[1]
    ]
    # Cada par examinado é uma consulta: muitas diagonais longas na janela pagam o produto.
    contexto.orcamento.gastar(len(bracos) * (len(bracos) - 1) // 2)
    for i, primeiro in enumerate(bracos):
        for segundo in bracos[i + 1 :]:
            if _formam_x(primeiro, segundo, contexto):
                return primeiro, segundo
    return None
