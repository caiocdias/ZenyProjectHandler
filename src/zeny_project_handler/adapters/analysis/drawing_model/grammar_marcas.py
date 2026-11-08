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
from typing import Final, Literal

from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caixa,
    Caminho,
    Cor,
    ItemCaminho,
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
# perto da elipse ajustada a eles, girada como os eixos principais dos vértices.
_ENVOLVENTE: Final = (0.95, 3.06)
_VERTICES_MINIMOS_ELIPSE: Final = 8
_DESVIO_RAIO_ELIPSE: Final = 0.2
# Abaixo desta anisotropia dos momentos, (l1 - l2) / (l1 + l2), a direção principal é ruído (um
# círculo de retas): a elipse fica alinhada aos eixos, como antes da R-E06.3.3.2.1-1.
_ANISOTROPIA_MINIMA: Final = 0.02
# O momento cruzado de uma elipse alinhada aos eixos é ruído de ponto flutuante: abaixo desta
# fração da soma dos momentos, a inclinação é exatamente 0.
_RUIDO_INCLINACAO: Final = 1e-9
# Envolvente desenhada como subcaminho de retas (R-E06.3.3.2.1-1): nas folhas medidas o oval
# fecha por reta explícita, a distância 0 entre o primeiro e o último ponto, e o arco aberto
# mais próximo fica a 0,24 pt; 0,05 pt dá folga ao arredondamento sem fechar arco nenhum.
_TOLERANCIA_FECHAMENTO: Final = 0.05
# A mesma elipse lida da polilinha: os vértices da polilinha são os nós de
# `reconstruir_polilinhas`, que funde pontos a até 0,5 pt.
_TOLERANCIA_MESMA_ELIPSE: Final = 0.5

# X de retirada: braços de comprimento relativo à escala, cruzando perto dos meios.
_MARGEM_X: Final = 0.5
_BRACO_X: Final = (0.8, 3.0)
_ANGULO_BRACO_X: Final = (math.radians(25), math.radians(65))
_MEIO_DO_BRACO: Final = (0.3, 0.7)
_RAZAO_BRACOS: Final = 1.3
_ABERTURA_X: Final = math.radians(45)
# O cruzamento fica perto do símbolo (R-E06.3.3.2.1-2): a até esta vez a escala do centro do
# pictograma. Nas 16 folhas, os X próprios cruzam a até 0,38 vez a escala do centro, e os X de
# vizinho que marcavam o símbolo, a 1,82 vez ou mais.
_CRUZAMENTO_X: Final = 1.0
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
    """Envolvente candidata: elipse do índice de molduras, polilinha fechada elíptica ou
    subcaminho fechado elíptico de um caminho de traço (`subcaminho` é o índice dele).

    `caixa` é a caixa alinhada aos eixos; a elipse é a de `centro`, `semieixos` e `inclinacao`
    (radianos, do primeiro semieixo sobre o eixo x), que vale para o "dentro" e o tamanho.
    """

    caixa: Caixa
    caminhos: tuple[int, ...]
    origem: Literal["moldura", "polilinha", "subcaminho"]
    centro: Ponto
    semieixos: tuple[float, float]
    inclinacao: float
    subcaminho: int | None = None


@dataclass(frozen=True, slots=True)
class _Elipse:
    caixa: Caixa
    centro: Ponto
    semieixos: tuple[float, float]
    inclinacao: float


class MarcasDaPagina:
    """As marcas de uma página, lidas uma vez por contexto e só quando alguém as pede."""

    __slots__ = ("_contexto", "_contornos", "_origem")

    def __init__(self, contexto: ContextoGramatica) -> None:
        self._contexto = contexto
        self._origem: str | None = None
        self._contornos: GradeEspacial[Contorno] | None = None

    @property
    def contexto(self) -> ContextoGramatica:
        """O contexto de página destas marcas; as gramáticas recusam marcas de outro."""
        return self._contexto

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


def marcas_do_contexto(
    contexto: ContextoGramatica, marcas: MarcasDaPagina | None
) -> MarcasDaPagina:
    """As `marcas` dadas, se são do `contexto` (R-E06.3.3.2.1-3); sem elas, marcas novas dele.

    Marcas de outro contexto pagariam o orçamento e leriam os contornos de outra página.
    """
    if marcas is None:
        return MarcasDaPagina(contexto)
    if marcas.contexto is not contexto:
        raise ValueError("As marcas da página são de outro contexto de gramáticas.")
    return marcas


def _no_referencial(contorno: Contorno, ponto: Ponto) -> Ponto:
    """O `ponto` relativo ao centro, nos eixos da elipse do `contorno`."""
    dx, dy = ponto[0] - contorno.centro[0], ponto[1] - contorno.centro[1]
    c, s = math.cos(contorno.inclinacao), math.sin(contorno.inclinacao)
    return dx * c + dy * s, -dx * s + dy * c


def _dentro_da_elipse(contorno: Contorno, ponto: Ponto, tolerancia: float) -> bool:
    a = contorno.semieixos[0] + tolerancia
    b = contorno.semieixos[1] + tolerancia
    if a <= 0 or b <= 0:
        return False
    u, v = _no_referencial(contorno, ponto)
    return (u / a) ** 2 + (v / b) ** 2 <= 1.0


def cruzamentos_da_borda(contorno: Contorno, ponto: Ponto, direcao: Ponto) -> list[Ponto]:
    """Onde a reta por `ponto` na `direcao` (unitária) cruza a elipse do `contorno`."""
    a, b = contorno.semieixos
    if a <= 0 or b <= 0:
        return []
    u, v = _no_referencial(contorno, ponto)
    c, s = math.cos(contorno.inclinacao), math.sin(contorno.inclinacao)
    du, dv = direcao[0] * c + direcao[1] * s, -direcao[0] * s + direcao[1] * c
    dx, dy, ux, uy = u / a, v / b, du / a, dv / b
    # |d + t u|² = 1 nas coordenadas da elipse unitária.
    qa, qb, qc = ux * ux + uy * uy, 2 * (dx * ux + dy * uy), dx * dx + dy * dy - 1
    discriminante = qb * qb - 4 * qa * qc
    if qa <= 0 or discriminante < 0:
        return []
    raiz = math.sqrt(discriminante)
    return [
        (ponto[0] + t * direcao[0], ponto[1] + t * direcao[1])
        for t in ((-qb + raiz) / (2 * qa), (-qb - raiz) / (2 * qa))
    ]


def _momentos_do_contorno(vertices: Sequence[Ponto]) -> tuple[float, float, float]:
    """Momentos centrais de segunda ordem (xx, yy, xy) do contorno fechado pelos vértices, por
    unidade de comprimento: os lados pesam pelo comprimento, e vértices desigualmente espaçados
    (o círculo de 32 retas das folhas) não inventam uma direção."""
    # Relativos ao primeiro vértice: coordenadas de página grandes não engolem a variância.
    ox, oy = vertices[0]
    relativos = [(x - ox, y - oy) for x, y in vertices]
    soma = sx = sy = sxx = syy = sxy = 0.0
    for i, (px, py) in enumerate(relativos):
        qx, qy = relativos[(i + 1) % len(relativos)]
        lado = math.hypot(qx - px, qy - py)
        soma += lado
        sx += lado * (px + qx) / 2
        sy += lado * (py + qy) / 2
        sxx += lado * (px * px + px * qx + qx * qx) / 3
        syy += lado * (py * py + py * qy + qy * qy) / 3
        sxy += lado * (2 * px * py + px * qy + qx * py + 2 * qx * qy) / 6
    if soma <= 0:
        return 0.0, 0.0, 0.0
    mx, my = sx / soma, sy / soma
    return sxx / soma - mx * mx, syy / soma - my * my, sxy / soma - mx * my


def _inclinacao_principal(vertices: Sequence[Ponto]) -> float:
    """Ângulo do eixo principal dos momentos de segunda ordem do contorno, em (-pi/4, pi/4]:
    girar de pi/2 só troca os semieixos. Momentos quase isótropos dão 0, a elipse alinhada."""
    sxx, syy, sxy = _momentos_do_contorno(vertices)
    if math.hypot(sxx - syy, 2 * sxy) <= _ANISOTROPIA_MINIMA * (sxx + syy) or abs(
        2 * sxy
    ) <= _RUIDO_INCLINACAO * (sxx + syy):
        return 0.0
    inclinacao = 0.5 * math.atan2(2 * sxy, sxx - syy)
    if inclinacao > math.pi / 4:
        inclinacao -= math.pi / 2
    elif inclinacao <= -math.pi / 4:
        inclinacao += math.pi / 2
    return inclinacao


def _elipse_de_vertices(vertices: Sequence[Ponto]) -> _Elipse | None:
    """Elipse dos vértices, se são bastantes e estão todos perto dela.

    A inclinação vem dos momentos de segunda ordem; o centro e os semieixos, dos extremos dos
    vértices nos eixos girados. Sem inclinação, é a elipse inscrita na caixa, como antes.
    """
    if len(vertices) < _VERTICES_MINIMOS_ELIPSE:
        return None
    caixa = _caixa_de_pontos(vertices)
    if caixa is None:
        return None
    inclinacao = _inclinacao_principal(vertices)
    c, s = math.cos(inclinacao), math.sin(inclinacao)
    us = [x * c + y * s for x, y in vertices]
    vs = [-x * s + y * c for x, y in vertices]
    a, b = (max(us) - min(us)) / 2, (max(vs) - min(vs)) / 2
    if a <= 0 or b <= 0:
        return None
    cu, cv = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
    elipticos = all(
        abs(math.hypot((u - cu) / a, (v - cv) / b) - 1.0) <= _DESVIO_RAIO_ELIPSE
        for u, v in zip(us, vs, strict=True)
    )
    if not elipticos:
        return None
    return _Elipse(caixa, (cu * c - cv * s, cu * s + cv * c), (a, b), inclinacao)


def _elipse_poligonal(polilinha: Polilinha) -> _Elipse | None:
    """Elipse da polilinha fechada cujos vértices estão todos perto dela."""
    if not polilinha.fechada or not polilinha.origens:
        return None
    return _elipse_de_vertices(polilinha.pontos)


def _fecha_com_retas(subcaminho: Sequence[ItemCaminho]) -> bool:
    """Filtro estrutural barato: retas bastantes e o fim de volta ao começo."""
    retas = sum(1 for item in subcaminho if item.tipo == "l")
    return (
        retas >= _VERTICES_MINIMOS_ELIPSE
        and math.dist(subcaminho[0].pontos[0], subcaminho[-1].pontos[-1]) <= _TOLERANCIA_FECHAMENTO
    )


def _contornos_de_subcaminhos(
    caminhos: Sequence[Caminho], contexto: ContextoGramatica
) -> list[Contorno]:
    """Subcaminhos elípticos dos caminhos de traço; cada um que passa no filtro gasta 1."""
    achados: list[Contorno] = []
    for posicao, caminho in enumerate(caminhos):
        if caminho.tipo != "traco":
            continue
        for indice, subcaminho in enumerate(caminho.subcaminhos):
            if not _fecha_com_retas(subcaminho):
                continue
            contexto.orcamento.gastar()
            elipse = _elipse_de_vertices([item.pontos[0] for item in subcaminho])
            if elipse is not None:
                achados.append(_contorno(elipse, (posicao,), "subcaminho", indice))
    return achados


def _contorno(
    elipse: _Elipse,
    caminhos: tuple[int, ...],
    origem: Literal["moldura", "polilinha", "subcaminho"],
    subcaminho: int | None = None,
) -> Contorno:
    return Contorno(
        elipse.caixa,
        caminhos,
        origem,
        elipse.centro,
        elipse.semieixos,
        elipse.inclinacao,
        subcaminho,
    )


def _elipse_da_caixa(caixa: Caixa) -> _Elipse:
    """A elipse inscrita na caixa, alinhada aos eixos: a das molduras."""
    centro = ((caixa[0] + caixa[2]) / 2, (caixa[1] + caixa[3]) / 2)
    return _Elipse(caixa, centro, ((caixa[2] - caixa[0]) / 2, (caixa[3] - caixa[1]) / 2), 0.0)


def _mesma_elipse(contorno: Contorno, do_subcaminho: Contorno) -> bool:
    return all(
        abs(p - q) <= _TOLERANCIA_MESMA_ELIPSE
        for p, q in zip(contorno.caixa, do_subcaminho.caixa, strict=True)
    )


def _contornos(contexto: ContextoGramatica) -> GradeEspacial[Contorno]:
    """Índice das envolventes da página: as elipses das molduras (Béziers e círculos), as
    polilinhas fechadas elípticas e os subcaminhos fechados elípticos dos caminhos de traço.

    Cada polilinha fechada examinada gasta 1, e cada subcaminho que passa no filtro estrutural
    também. A mesma elipse vinda da moldura ou da polilinha e do subcaminho (mesmo caminho, mesma
    caixa) entra uma vez só, pelo subcaminho.
    """
    modelo = contexto.pagina.modelo
    dos_subcaminhos = _contornos_de_subcaminhos(modelo.caminhos, contexto)
    por_caminho: dict[int, list[Contorno]] = {}
    for do_subcaminho in dos_subcaminhos:
        por_caminho.setdefault(do_subcaminho.caminhos[0], []).append(do_subcaminho)
    contornos = [
        _contorno(_elipse_da_caixa(moldura.caixa), (moldura.caminho,), "moldura")
        for moldura in contexto.molduras
        if moldura.forma == "elipse"
    ]
    fechadas = [p for p in modelo.primitivas if isinstance(p, Polilinha) and p.fechada]
    contexto.orcamento.gastar(len(fechadas))
    for polilinha in fechadas:
        elipse = _elipse_poligonal(polilinha)
        if elipse is not None:
            contornos.append(_contorno(elipse, tuple(sorted(set(polilinha.origens))), "polilinha"))
    contornos = [
        contorno
        for contorno in contornos
        if not any(
            _mesma_elipse(contorno, do_subcaminho)
            for caminho in contorno.caminhos
            for do_subcaminho in por_caminho.get(caminho, ())
        )
    ]
    contornos.extend(dos_subcaminhos)
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

    O diâmetro (o dobro do maior semieixo) fica entre `_ENVOLVENTE` vezes a `escala`, o "dentro"
    é o da elipse girada, a busca é numa janela em torno da
    `ancora`, e um contorno com caminho em `proprios` não conta, salvo o de subcaminho: com
    `_VERTICES_MINIMOS_ELIPSE` retas ou mais, ele nunca é o retângulo nem um traço da haste,
    ainda que divida o caminho com eles.
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
        diametro = 2 * max(contorno.semieixos)
        if (
            (contorno.origem == "subcaminho" or proprios.isdisjoint(contorno.caminhos))
            and minimo * escala <= diametro <= maximo * escala
            and all(_dentro_da_elipse(contorno, p, tolerancia) for p in exigidos)
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


def _formam_x(
    primeiro: Segmento,
    segundo: Segmento,
    contexto: ContextoGramatica,
    centro: Ponto,
    alcance: float,
) -> bool:
    cruz = _intersecao(primeiro, segundo)
    if cruz is None:
        return False
    ponto = (
        primeiro.a[0] + (primeiro.b[0] - primeiro.a[0]) * cruz[0],
        primeiro.a[1] + (primeiro.b[1] - primeiro.a[1]) * cruz[0],
    )
    c1, c2 = math.dist(primeiro.a, primeiro.b), math.dist(segundo.a, segundo.b)
    caminhos = contexto.pagina.modelo.caminhos
    return (
        math.dist(ponto, centro) <= alcance
        and all(_MEIO_DO_BRACO[0] <= t <= _MEIO_DO_BRACO[1] for t in cruz)
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
    em relação ao `eixo` (ângulo de reta, em radianos); os segmentos `proprios` não contam. O
    cruzamento fica a até `_CRUZAMENTO_X` vezes a `escala` do centro do pictograma: o X de um
    símbolo vizinho, que cruza longe dele, não é a marca de retirada deste.
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
    centro = ((pictograma[0] + pictograma[2]) / 2, (pictograma[1] + pictograma[3]) / 2)
    alcance = escala * _CRUZAMENTO_X
    for i, primeiro in enumerate(bracos):
        for segundo in bracos[i + 1 :]:
            if _formam_x(primeiro, segundo, contexto, centro, alcance):
                return primeiro, segundo
    return None
