"""Gramática do triângulo dividido (TRANSFORMADOR) sobre o modelo de desenho.

O preenchimento vem primeiro (laboratório da E06.3.3.2.2, H-2): as sementes do `half_cyan` são
os preenchimentos triangulares da página. Um preenchimento ciano e um branco que dividem uma
aresta (a mediana do pictograma) e cuja união é um triângulo quase equilátero formam o triângulo
meio ciano. O `outline` cai no contorno: triângulo fechado de traço (subcaminho de 3 retas ou
polilinha fechada de 3 vértices) ou preenchimento branco de 3 retas, quase equilátero e sem
preenchimento opaco de outra cor por cima. O contorno dentro de um meio ciano é parte dele: o
mesmo desenho sai num grupo só.

Cada candidato é classificado uma vez (R-E06.3.3.2.2-6): `fill`, envolvente e X são lidos aqui
e pagos por candidato; `casa_triangulos` só filtra. A caixa é o pictograma (R-E06.3.3.2.2-3): a
envolvente, quando há, senão o triângulo; o X e a haste de ligação ficam fora dela, e a haste
não é exigida.

Decisões do laboratório da E06.3.3.2.2, como no método E05 (`pymupdf_transformers`):
- o X vence a envolvente: um desenho com círculo e X ao mesmo tempo (há dois nas folhas da
  rodada) é do grupo do X, porque a marca de retirada decide, como em `_referencias_triangulo`;
  o grupo da envolvente exige que não haja X;
- uma metade cheia de outra cor que não o ciano não é `half_cyan`: o desenho cai em `outline`
  pelo contorno, porque só o ciano decide o `fill` (`_toca_ciano`), e a cor nunca decide a
  situação; as metades entram nos componentes.

Rulings da rodada de correção da Task 3:
- o contorno tracejado e o roxo (o triângulo com S, v016 a v018, fora de escopo) não casam;
- a gravata (dois triângulos que se tocam pelo vértice, num caminho ou em dois) não casa;
- o triângulo cheio de cor, inteiro ou em duas metades (ciano inteiro), não casa;
- a metade ciano sobre o fundo branco do triângulo inteiro é `half_cyan`.

Rulings da rodada de correção 2:
- no wipeout (fundo branco inteiro, metade ciano e metade branca, mesmo repetida), os brancos
  fecham o mesmo triângulo e o desenho é `half_cyan`; só é ambíguo o ciano cujos pares fecham
  triângulos diferentes;
- o triângulo de traço com os três vértices na borda de uma moldura retangular (a PLATAFORMA,
  `triangle_in_frame`) não casa;
- o tracejado e o roxo do contorno recusam o triângulo em todos os grupos, também no meio ciano;
- o mesmo preenchimento emitido duas vezes conta uma vez em `_cheio`.

Ruling da rodada de correção 3: a ponta de seta vazada (linha que termina no meio de um lado e
segue para fora) não casa, se a linha tem `_SETA_LINHA_MINIMA_LADOS` lados ou mais.

Rulings da onda final:
- o preenchimento de muitos subcaminhos gasta 1 por subcaminho e sai pela caixa antes da
  envoltória; `_sem_colineares` é de uma passada só;
- o triângulo com uma palavra dentro (o Δ de revisão com o número, de glifo ou não) não casa;
- o triângulo branco só de preenchimento, sem traço visível, não é contorno; o meio ciano segue
  lido pelas metades, que são preenchimentos, com o contorno no traço.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Generic, Literal, TypeVar

from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import (
    MarcasDaPagina,
    angulo,
    diferenca_angular,
    envolvente,
    marcas_do_contexto,
    tem_x,
    um_traco,
)
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
    OrcamentoConsultas,
    Segmento,
    _caixa_de_pontos,
)

_Triangulo = tuple[Ponto, Ponto, Ponto]
T = TypeVar("T")
Preenchimento = Literal["half_cyan", "outline"]

# Forma: lados parecidos e ângulos internos perto de 60°, como o contorno do E05.
_RAZAO_LADOS: Final = 1.25
_ANGULOS: Final = (math.radians(45), math.radians(75))
# Lado médio máximo (pt), em qualquer perfil: 2 vezes o maior lado dos TRANSFORMADOR lidos nas 16
# folhas da rodada de fichas, 13,2 pt. Acima disso é moldura ou seta de traçado, não pictograma.
_LADO_MAXIMO: Final = 2 * 13.2
# Fechamento de um subcaminho de retas e vértices repetidos.
_FECHAMENTO: Final = 0.05
# Vértices comuns aos dois preenchimentos: relativo ao lado, com mínimo absoluto.
_VERTICE_RELATIVO: Final = 0.04
_VERTICE_MINIMO: Final = 0.15
# O vértice do meio da aresta dividida fica entre estas frações dela.
_MEIO_DA_ARESTA: Final = (0.25, 0.75)
# Dois contornos são o mesmo triângulo com os vértices a até esta fração do lado.
_COBERTURA_RELATIVA: Final = 0.08
# Preenchimentos de cor (ciano ou outra, não branca) com o centro no contorno que cobrem esta
# fração da área dele o tornam um triângulo cheio, e não um pictograma; maiores que
# `_PREENCHIMENTO_MAXIMO` vezes o contorno não são dele.
_COBERTURA_CHEIA: Final = 0.9
_PREENCHIMENTO_MAXIMO: Final = 1.5
# Células dos índices de vértices e de centros: o maior alcance das tolerâncias acima, para que
# dois pontos dentro da tolerância caiam em células vizinhas.
_CELULA_VERTICE: Final = max(_VERTICE_MINIMO, _LADO_MAXIMO * _VERTICE_RELATIVO)
_CELULA_CENTRO: Final = _LADO_MAXIMO * _COBERTURA_RELATIVA
# Duplicatas do mesmo preenchimento: vértices iguais nesta casa decimal (pt).
_CASAS_DUPLICATA: Final = 2
# Ponta de seta vazada: uma linha longa termina no meio de um lado, entre estas frações dele, e
# segue para fora; a haste do transformador sai de um vértice.
_LADO_DA_SETA: Final = (0.15, 0.85)
# A linha da seta tem ao menos estes lados do triângulo (ruling da rodada 3). Na rodada de fichas,
# um transformador anotado tem no meio de um lado a haste de um vizinho, de cerca de 1 lado
# (1,08): com o limiar de 1 lado ele saía, com 2 ele fica.
_SETA_LINHA_MINIMA_LADOS: Final = 2.0
# Traço contínuo: `dashes` vazio ou o padrão vazio do PyMuPDF.
_TRACOS_CONTINUOS: Final = frozenset({"", "[]", "[]0"})
# Haste de ligação: sai de um vértice, para fora, alinhada à mediana dele.
_HASTE_MINIMA: Final = 0.5
_HASTE_ANGULO: Final = math.radians(20)
_HASTE_TOLERANCIA: Final = 0.1


@dataclass(frozen=True, slots=True)
class Perfil:
    """Tolerâncias de um perfil de página; o padrão são os mínimos absolutos do legado."""

    lado_minimo: float = 3.0


_PERFIL_PADRAO: Final = Perfil()
_PERFIL_ESCALA: Final = Perfil(lado_minimo=1.5)
_PERFIS: Final[Mapping[str, Perfil]] = {
    "glifo": _PERFIL_ESCALA,
    "shx": _PERFIL_PADRAO,
    "nativo": _PERFIL_PADRAO,
}


@dataclass(frozen=True, slots=True)
class Triangulo:
    """Triângulo já classificado: `fill`, envolvente e X lidos uma vez, com o contexto de origem."""

    caixa: Caixa
    caminho: int
    componentes: tuple[int, ...]
    fill: Preenchimento
    envolvente: bool
    x: bool
    contexto: ContextoGramatica = field(compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class _Forma:
    """Triângulo quase equilátero lido de um ou mais caminhos."""

    vertices: _Triangulo
    origens: tuple[int, ...]
    lado: float

    @property
    def centro(self) -> Ponto:
        return (
            sum(p[0] for p in self.vertices) / 3,
            sum(p[1] for p in self.vertices) / 3,
        )

    @property
    def caixa(self) -> Caixa:
        caixa = _caixa_de_pontos(self.vertices)
        assert caixa is not None
        return caixa


@dataclass(frozen=True, slots=True)
class _MeioCiano:
    forma: _Forma
    eixo: float


def _ciano(cor: Cor | None) -> bool:
    """O ciano do E05 (`_colored(..., "cyan")`): só decide o `fill`, nunca a situação."""
    if cor is None:
        return False
    r, g, b = cor
    return b > 0.35 and g > 0.3 and r < min(b, g) * 0.75


def _branco(cor: Cor | None) -> bool:
    return cor is not None and min(cor) >= 0.9


def _roxo(cor: Cor | None) -> bool:
    """O roxo do E05 (`_colored(..., "purple")`): o traço do triângulo com S, fora de escopo."""
    if cor is None:
        return False
    r, g, b = cor
    return r > 0.2 and b > 0.2 and g < min(r, b) * 0.8


def _traco_de_pictograma(caminho: Caminho) -> bool:
    """Traço contínuo e não roxo: o tracejado e o roxo (v016 a v018) não são o transformador."""
    return caminho.estilo.tracejado.replace(" ", "") in _TRACOS_CONTINUOS and not _roxo(
        caminho.estilo.cor
    )


def _mediana_depois_do_fecho(subcaminho: Sequence[ItemCaminho]) -> bool:
    """Depois das 3 retas que fecham, no máximo uma reta, que sai do fecho para dentro do
    triângulo (a mediana desenhada no mesmo caminho). Mais retas são outra figura (a gravata)."""
    if len(subcaminho) == 3:
        return True
    if len(subcaminho) != 4:
        return False
    a, b, c = (item.pontos[0] for item in subcaminho[:3])
    inicio, fim = subcaminho[3].pontos[0], subcaminho[3].pontos[-1]
    folga = max(_FECHAMENTO, sum(_lados((a, b, c))) / 3 * _VERTICE_RELATIVO)
    return math.dist(inicio, a) <= _FECHAMENTO and _dentro(fim, (a, b, c), folga)


def _vertices(subcaminho: Sequence[ItemCaminho], implicito: bool) -> _Triangulo | None:
    """Os 3 vértices de um subcaminho de retas que fecha um triângulo.

    Um preenchimento fecha implícito. Um traço fecha nas 3 primeiras retas; uma reta a mais
    depois do fecho, para dentro (a mediana desenhada no mesmo caminho), não desfaz o triângulo.
    """
    if len(subcaminho) < 2 or any(item.tipo != "l" for item in subcaminho):
        return None
    pontos = [item.pontos[0] for item in subcaminho] + [subcaminho[-1].pontos[-1]]
    if len(subcaminho) >= 3 and math.dist(subcaminho[2].pontos[-1], pontos[0]) <= _FECHAMENTO:
        if not _mediana_depois_do_fecho(subcaminho):
            return None
        pontos = pontos[:3]
    elif math.dist(pontos[-1], pontos[0]) <= _FECHAMENTO:
        pontos = pontos[:-1]
    elif not implicito:
        return None
    distintos: list[Ponto] = []
    for ponto in pontos:
        if not distintos or math.dist(ponto, distintos[-1]) > _FECHAMENTO:
            distintos.append(ponto)
    if len(distintos) > 1 and math.dist(distintos[0], distintos[-1]) <= _FECHAMENTO:
        distintos.pop()
    if len(distintos) != 3:
        return None
    return distintos[0], distintos[1], distintos[2]


def _lados(vertices: _Triangulo) -> tuple[float, float, float]:
    a, b, c = vertices
    return math.dist(a, b), math.dist(b, c), math.dist(c, a)


def _quase_equilatero(vertices: _Triangulo, perfil: Perfil) -> float | None:
    """O lado médio do triângulo, se os lados e os ângulos são de pictograma; senão None."""
    lados = _lados(vertices)
    menor, maior = min(lados), max(lados)
    medio = sum(lados) / 3
    if menor <= 0 or maior / menor > _RAZAO_LADOS:
        return None
    if not perfil.lado_minimo <= medio <= _LADO_MAXIMO:
        return None
    for i, vertice in enumerate(vertices):
        p, q = vertices[i - 1], vertices[(i + 1) % 3]
        u = (p[0] - vertice[0], p[1] - vertice[1])
        v = (q[0] - vertice[0], q[1] - vertice[1])
        cosseno = (u[0] * v[0] + u[1] * v[1]) / (math.hypot(*u) * math.hypot(*v))
        if not _ANGULOS[0] <= math.acos(max(-1.0, min(1.0, cosseno))) <= _ANGULOS[1]:
            return None
    return medio


def _de_tamanho(vertices: _Triangulo, perfil: Perfil) -> bool:
    """Preenchimento do tamanho de um pictograma ou de metade dele; a forma vem depois."""
    lados = _lados(vertices)
    return min(lados) >= perfil.lado_minimo / 2 and max(lados) <= _LADO_MAXIMO * 1.2


def _preenche(caminho: Caminho) -> bool:
    return caminho.tipo in ("preenchimento", "traco_e_preenchimento")


def _traca(caminho: Caminho) -> bool:
    return caminho.tipo in ("traco", "traco_e_preenchimento")


@dataclass(frozen=True, slots=True)
class _Lidos:
    """Triângulos da página por papel: preenchimentos ciano, brancos, opacos de outra cor,
    contornos (traço ou polilinha fechada) e contornos recusados (tracejados ou roxos)."""

    cianos: list[tuple[_Triangulo, int]]
    brancos: list[tuple[_Triangulo, int]]
    opacos: list[tuple[_Triangulo, int]]
    contornos: list[tuple[_Triangulo, int | tuple[int, ...]]]
    recusados: list[_Triangulo]


def _area(vertices: Sequence[Ponto]) -> float:
    return (
        abs(
            sum(
                vertices[i - 1][0] * vertices[i][1] - vertices[i][0] * vertices[i - 1][1]
                for i in range(len(vertices))
            )
        )
        / 2
    )


def _envoltoria(pontos: Sequence[Ponto]) -> list[Ponto]:
    """Envoltória convexa (cadeia monótona), sem pontos repetidos."""
    unicos = sorted(set(pontos))
    if len(unicos) < 3:
        return unicos

    def giro(o: Ponto, a: Ponto, b: Ponto) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    baixo: list[Ponto] = []
    for p in unicos:
        while len(baixo) >= 2 and giro(baixo[-2], baixo[-1], p) <= 0:
            baixo.pop()
        baixo.append(p)
    cima: list[Ponto] = []
    for p in reversed(unicos):
        while len(cima) >= 2 and giro(cima[-2], cima[-1], p) <= 0:
            cima.pop()
        cima.append(p)
    return baixo[:-1] + cima[:-1]


def _altura(p: Ponto, a: Ponto, b: Ponto) -> float:
    """A distância de `p` à reta de `a` a `b`; 0 se os dois coincidem."""
    base = math.dist(a, b)
    if base <= 0:
        return 0.0
    return abs((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / base


def _sem_colineares(contorno: list[Ponto], tolerancia: float) -> list[Ponto]:
    """Tira os vértices que ficam sobre a reta dos vizinhos (fatias de hachura) ou repetidos.

    Uma passada só, linear: cada vértice é medido contra o último mantido e o próximo; no fim, o
    primeiro é medido de novo contra o último mantido, que pode não ser o original.
    """
    if len(contorno) <= 3:
        return contorno
    mantidos: list[Ponto] = []
    for i, p in enumerate(contorno):
        anterior = mantidos[-1] if mantidos else contorno[-1]
        if _altura(p, anterior, contorno[(i + 1) % len(contorno)]) > tolerancia:
            mantidos.append(p)
    if len(mantidos) > 3 and _altura(mantidos[0], mantidos[-1], mantidos[1]) <= tolerancia:
        mantidos.pop(0)
    return mantidos


def _triangulo_preenchido(caminho: Caminho, orcamento: OrcamentoConsultas) -> _Triangulo | None:
    """O triângulo de um preenchimento: um subcaminho de retas ou vários triângulos de hachura
    que, juntos, cobrem a envoltória (a área soma a dela) e ela é um triângulo.

    Com vários subcaminhos, o preenchimento cuja caixa passa do tamanho de pictograma sai antes
    da envoltória, depois de uma leitura linear; o que chega à envoltória gasta 1 por
    subcaminho, e `_sem_colineares` é linear.
    """
    partes = [_vertices(s, implicito=True) for s in caminho.subcaminhos]
    if not partes or any(parte is None for parte in partes):
        return None
    triangulos = [parte for parte in partes if parte is not None]
    if len(triangulos) == 1:
        return triangulos[0]
    caixa = _caixa_de_pontos(p for t in triangulos for p in t)
    if caixa is None or max(caixa[2] - caixa[0], caixa[3] - caixa[1]) > _LADO_MAXIMO * 1.2:
        return None
    orcamento.gastar(len(triangulos))
    envoltoria = _envoltoria([p for t in triangulos for p in t])
    if len(envoltoria) < 3:
        return None
    lado = max(math.dist(envoltoria[i - 1], envoltoria[i]) for i in range(len(envoltoria)))
    contorno = _sem_colineares(envoltoria, max(_FECHAMENTO, lado * 0.01))
    if len(contorno) != 3:
        return None
    area = _area(contorno)
    if area <= 0 or abs(sum(_area(t) for t in triangulos) - area) > 0.05 * area:
        return None
    return contorno[0], contorno[1], contorno[2]


def _triangulos_da_pagina(
    modelo: PaginaModelo, excluidos: frozenset[int], perfil: Perfil, orcamento: OrcamentoConsultas
) -> _Lidos:
    lidos = _Lidos([], [], [], [], [])
    for posicao, caminho in enumerate(modelo.caminhos):
        if posicao in excluidos:
            continue
        if _preenche(caminho):
            vertices = _triangulo_preenchido(caminho, orcamento)
            if vertices is not None and _de_tamanho(vertices, perfil):
                cor = caminho.estilo.preenchimento
                destino = (
                    lidos.cianos if _ciano(cor) else lidos.brancos if _branco(cor) else lidos.opacos
                )
                destino.append((vertices, posicao))
        # O traço de um preenchimento de hachura contorna as fatias, não o pictograma.
        if _traca(caminho) and (caminho.tipo == "traco" or len(caminho.subcaminhos) == 1):
            destino_traco = lidos.contornos if _traco_de_pictograma(caminho) else None
            for subcaminho in caminho.subcaminhos:
                vertices = _vertices(subcaminho, implicito=False)
                if vertices is None or _quase_equilatero(vertices, perfil) is None:
                    continue
                if destino_traco is None:
                    lidos.recusados.append(vertices)
                else:
                    destino_traco.append((vertices, posicao))
    for primitiva in modelo.primitivas:
        if not isinstance(primitiva, Polilinha) or not primitiva.fechada or not primitiva.origens:
            continue
        if any(origem in excluidos for origem in primitiva.origens):
            continue
        pontos = list(primitiva.pontos)
        if len(pontos) == 4 and math.dist(pontos[0], pontos[-1]) <= _FECHAMENTO:
            pontos = pontos[:3]
        if len(pontos) == 3:
            vertices = (pontos[0], pontos[1], pontos[2])
            if _quase_equilatero(vertices, perfil) is None:
                continue
            if all(_traco_de_pictograma(modelo.caminhos[o]) for o in primitiva.origens):
                lidos.contornos.append((vertices, tuple(primitiva.origens)))
            else:
                lidos.recusados.append(vertices)
    return lidos


def _comuns(a: _Triangulo, b: _Triangulo, tolerancia: float) -> list[tuple[int, int]]:
    return [
        (i, j) for i, p in enumerate(a) for j, q in enumerate(b) if math.dist(p, q) <= tolerancia
    ]


def _no_segmento(ponto: Ponto, a: Ponto, b: Ponto, tolerancia: float) -> float | None:
    """A fração de `ponto` ao longo de `a`-`b`, se ele está sobre o segmento; senão None."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    comprimento = math.hypot(dx, dy)
    if comprimento <= 0:
        return None
    t = ((ponto[0] - a[0]) * dx + (ponto[1] - a[1]) * dy) / (comprimento * comprimento)
    distancia = abs((ponto[0] - a[0]) * dy - (ponto[1] - a[1]) * dx) / comprimento
    return t if distancia <= tolerancia else None


def _meio_ciano(
    ciano: _Triangulo, branco: _Triangulo, perfil: Perfil
) -> tuple[_Triangulo, float] | None:
    """O triângulo união e o ângulo da aresta dividida, se os dois dividem uma mediana.

    O branco é a outra metade (os dois dividem a mediana) ou o fundo do triângulo inteiro, com a
    metade ciano por cima: o meio da aresta, vértice livre do ciano, fica num lado do branco.
    """
    lado = sum(_lados(ciano)) / 3
    tolerancia = max(_VERTICE_MINIMO, lado * _VERTICE_RELATIVO)
    comuns = _comuns(ciano, branco, tolerancia)
    if len(comuns) != 2:
        return None
    usados_c = {i for i, _ in comuns}
    usados_b = {j for _, j in comuns}
    b = next(p for i, p in enumerate(ciano) if i not in usados_c)
    c = next(p for j, p in enumerate(branco) if j not in usados_b)
    pares = (
        (ciano[comuns[0][0]], ciano[comuns[1][0]]),
        (ciano[comuns[1][0]], ciano[comuns[0][0]]),
    )
    for apice, meio in pares:
        # Metade ao lado da outra: o meio da aresta é comum e fica entre os vértices livres.
        t = _no_segmento(meio, b, c, tolerancia)
        if t is not None and _MEIO_DA_ARESTA[0] <= t <= _MEIO_DA_ARESTA[1]:
            return _uniao((apice, b, c), apice, meio, perfil)
    for apice, lateral in pares:
        # Fundo inteiro: o vértice livre do ciano é o meio do lado `lateral`-`c` do branco.
        t = _no_segmento(b, lateral, c, tolerancia)
        if t is not None and _MEIO_DA_ARESTA[0] <= t <= _MEIO_DA_ARESTA[1]:
            return _uniao((apice, lateral, c), apice, b, perfil)
    return None


def _uniao(
    uniao: _Triangulo, apice: Ponto, meio: Ponto, perfil: Perfil
) -> tuple[_Triangulo, float] | None:
    if _quase_equilatero(uniao, perfil) is None:
        return None
    return uniao, angulo(Segmento(apice, meio, -1))


def _dentro(ponto: Ponto, vertices: _Triangulo, folga: float) -> bool:
    """O ponto no triângulo, com folga nas arestas."""
    sinais = []
    for i in range(3):
        a, b = vertices[i], vertices[(i + 1) % 3]
        comprimento = math.dist(a, b)
        if comprimento <= 0:
            return False
        sinais.append(
            ((b[0] - a[0]) * (ponto[1] - a[1]) - (b[1] - a[1]) * (ponto[0] - a[0])) / comprimento
        )
    return all(s >= -folga for s in sinais) or all(s <= folga for s in sinais)


def _mesmo_triangulo(a: _Triangulo, b: _Triangulo, tolerancia: float) -> bool:
    return all(any(math.dist(p, q) <= tolerancia for q in b) for p in a)


def _limites(modelo: PaginaModelo) -> Caixa:
    return (
        -_MARGEM_PAGINA,
        -_MARGEM_PAGINA,
        modelo.largura + _MARGEM_PAGINA,
        modelo.altura + _MARGEM_PAGINA,
    )


def _origens(origem: int | tuple[int, ...]) -> tuple[int, ...]:
    return (origem,) if isinstance(origem, int) else origem


def _meios_cianos(contexto: ContextoGramatica, lidos: _Lidos, perfil: Perfil) -> list[_MeioCiano]:
    """Pares ciano e branco que formam o triângulo meio ciano; cada ciano examinado gasta 1."""
    if not lidos.cianos or not lidos.brancos:
        return []
    limites = _limites(contexto.pagina.modelo)
    grade = GradeEspacial(
        ((_caixa_de_pontos(v) or (0.0, 0.0, 0.0, 0.0), (v, p)) for v, p in lidos.brancos),
        limites,
        contexto.orcamento,
    )
    achados: list[_MeioCiano] = []
    for vertices, posicao in lidos.cianos:
        contexto.orcamento.gastar()
        caixa = _caixa_de_pontos(vertices)
        if caixa is None:
            continue
        pares = []
        for branco, outro in grade.consultar(caixa):
            lido = _meio_ciano(vertices, branco, perfil)
            if lido is not None:
                pares.append((lido, outro))
        if not pares:
            continue
        (uniao, eixo), _ = pares[0]
        lado = sum(_lados(uniao)) / 3
        # Um ciano com brancos que fecham triângulos diferentes é ambíguo: recusa. Brancos que
        # fecham o mesmo (o fundo inteiro, a metade e as cópias dela, no wipeout) são um só.
        if not all(_mesmo_triangulo(u, uniao, lado * _COBERTURA_RELATIVA) for (u, _), _ in pares):
            continue
        origens = tuple(sorted({posicao, *(outro for _, outro in pares)}))
        achados.append(_MeioCiano(_Forma(uniao, origens, lado), eixo))
    return achados


def _centro_de(vertices: _Triangulo) -> Ponto:
    return sum(p[0] for p in vertices) / 3, sum(p[1] for p in vertices) / 3


class _IndicePontos(Generic[T]):
    """Pontos por célula, com inserção a qualquer momento: os vizinhos de um ponto estão nas 9
    células em volta. Cada vizinho devolvido gasta 1 do orçamento, como uma consulta à grade."""

    __slots__ = ("_celula", "_celulas", "_orcamento")

    def __init__(self, celula: float, orcamento: OrcamentoConsultas) -> None:
        self._celula = celula
        self._orcamento = orcamento
        self._celulas: dict[tuple[int, int], list[T]] = {}

    def _chave(self, ponto: Ponto) -> tuple[int, int]:
        return math.floor(ponto[0] / self._celula), math.floor(ponto[1] / self._celula)

    def inserir(self, ponto: Ponto, valor: T) -> None:
        self._celulas.setdefault(self._chave(ponto), []).append(valor)

    def vizinhos(self, ponto: Ponto) -> list[T]:
        cx, cy = self._chave(ponto)
        achados = [
            valor
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for valor in self._celulas.get((cx + dx, cy + dy), ())
        ]
        self._orcamento.gastar(len(achados))
        return achados


def _que_se_tocam(
    contexto: ContextoGramatica, contornos: Sequence[tuple[_Triangulo, object]], perfil: Perfil
) -> set[int]:
    """Os contornos que encostam um vértice num outro triângulo de fora (a gravata): nenhum dos
    dois é o pictograma isolado. O mesmo triângulo lido duas vezes não conta."""
    indice: _IndicePontos[tuple[int, Ponto]] = _IndicePontos(_CELULA_VERTICE, contexto.orcamento)
    lados: dict[int, float] = {}
    for i, (vertices, _) in enumerate(contornos):
        lado = _quase_equilatero(vertices, perfil)
        if lado is not None:
            lados[i] = lado
            for vertice in vertices:
                indice.inserir(vertice, (i, vertice))
    tocados: set[int] = set()
    for i, lado in lados.items():
        vertices = contornos[i][0]
        tolerancia = max(_VERTICE_MINIMO, lado * _VERTICE_RELATIVO)
        for vertice in vertices:
            for j, outro in indice.vizinhos(vertice):
                if j == i or math.dist(vertice, outro) > tolerancia:
                    continue
                alheio = contornos[j][0]
                if not _mesmo_triangulo(vertices, alheio, lado * _COBERTURA_RELATIVA) and not (
                    _dentro(_centro_de(alheio), vertices, tolerancia)
                ):
                    tocados.update((i, j))
    return tocados


def _preenchimentos_dentro(
    grade: GradeEspacial[tuple[_Triangulo, int, bool]], vertices: _Triangulo, caixa: Caixa
) -> list[tuple[_Triangulo, int, bool]]:
    """Os preenchimentos com o centro no triângulo e do tamanho dele, no máximo."""
    area = _area(vertices)
    folga = sum(_lados(vertices)) / 3 * _VERTICE_RELATIVO
    return [
        item
        for item in grade.consultar(caixa)
        if _area(item[0]) <= area * _PREENCHIMENTO_MAXIMO
        and _dentro(_centro_de(item[0]), vertices, folga)
    ]


def _cheio(vertices: _Triangulo, dentro: Sequence[tuple[_Triangulo, int, bool]]) -> bool:
    """Preenchimentos de cor (ciano ou outra, não branca) cobrem o triângulo: é um triângulo
    cheio, como o ciano inteiro em uma ou em duas metades, e não um pictograma de contorno."""
    area = _area(vertices)
    # O mesmo preenchimento emitido duas vezes cobre a área uma vez só.
    unicos = {_chave_do_triangulo(v): v for v, _, de_cor in dentro if de_cor}
    coberta = sum(min(_area(v), area) for v in unicos.values())
    return area > 0 and coberta >= _COBERTURA_CHEIA * area


def _chave_do_triangulo(vertices: _Triangulo) -> tuple[tuple[float, float], ...]:
    return tuple(
        sorted((round(x, _CASAS_DUPLICATA), round(y, _CASAS_DUPLICATA)) for x, y in vertices)
    )


def _contornos(
    contexto: ContextoGramatica,
    lidos: _Lidos,
    meios: Sequence[_MeioCiano],
    perfil: Perfil,
) -> tuple[list[_Forma], dict[int, set[int]]]:
    """Contornos de pictograma, sem os que pertencem a um meio ciano (cujos caminhos vão para
    ele, pelo índice do meio), os cheios de cor e os que encostam noutro triângulo (gravata).

    Os preenchimentos dentro do contorno (a metade de outra cor e a branca) são caminhos dele.
    O mesmo triângulo lido de vários caminhos vira uma forma só, achada pelo índice de centros.
    """
    modelo = contexto.pagina.modelo
    limites = _limites(modelo)
    grade_meios = GradeEspacial(
        ((m.forma.caixa, i) for i, m in enumerate(meios)), limites, contexto.orcamento
    )
    preenchidos = [
        *((v, p, True) for v, p in (*lidos.opacos, *lidos.cianos)),
        *((v, p, False) for v, p in lidos.brancos),
    ]
    grade_preenchidos = GradeEspacial(
        ((_caixa_de_pontos(item[0]) or (0.0, 0.0, 0.0, 0.0), item) for item in preenchidos),
        limites,
        contexto.orcamento,
    )
    candidatos: list[tuple[_Triangulo, int | tuple[int, ...]]] = [
        *lidos.contornos,
        # O branco só de preenchimento não aparece na folha: só o de traço visível é contorno.
        *(
            (v, p)
            for v, p in lidos.brancos
            if _traca(modelo.caminhos[p]) and _traco_de_pictograma(modelo.caminhos[p])
        ),
    ]
    tocados = _que_se_tocam(contexto, candidatos, perfil)
    anexos: dict[int, set[int]] = {}
    formas: list[_Forma] = []
    centros: _IndicePontos[int] = _IndicePontos(_CELULA_CENTRO, contexto.orcamento)
    for k, (vertices, origem) in enumerate(candidatos):
        contexto.orcamento.gastar()
        lado = _quase_equilatero(vertices, perfil)
        caixa = _caixa_de_pontos(vertices)
        if lado is None or caixa is None:
            continue
        centro = _centro_de(vertices)
        dono = next(
            (
                i
                for i in grade_meios.consultar(caixa)
                if _dentro(centro, meios[i].forma.vertices, meios[i].forma.lado * _VERTICE_RELATIVO)
            ),
            None,
        )
        if dono is not None:
            anexos.setdefault(dono, set()).update(_origens(origem))
            continue
        dentro = _preenchimentos_dentro(grade_preenchidos, vertices, caixa)
        if k in tocados or _cheio(vertices, dentro):
            continue
        caminhos = {*_origens(origem), *(p for _, p, _ in dentro)}
        tolerancia = lado * _COBERTURA_RELATIVA
        igual = next(
            (
                i
                for i in centros.vizinhos(centro)
                if _mesmo_triangulo(vertices, formas[i].vertices, tolerancia)
            ),
            None,
        )
        if igual is not None:
            antiga = formas[igual]
            formas[igual] = _Forma(
                antiga.vertices, tuple(sorted({*antiga.origens, *caminhos})), antiga.lado
            )
            continue
        centros.inserir(centro, len(formas))
        formas.append(_Forma(vertices, tuple(sorted(caminhos)), lado))
    return formas, anexos


def _haste(contexto: ContextoGramatica, forma: _Forma) -> Segmento | None:
    """Traço solto que sai de um vértice para fora, alinhado à mediana dele; o mais longo."""
    centro = forma.centro
    tolerancia = max(_HASTE_TOLERANCIA, forma.lado * _VERTICE_RELATIVO * 2)
    escolhida: Segmento | None = None
    modelo = contexto.pagina.modelo
    for vertice in forma.vertices:
        radial = angulo(Segmento(centro, vertice, -1))
        janela = (
            vertice[0] - tolerancia,
            vertice[1] - tolerancia,
            vertice[0] + tolerancia,
            vertice[1] + tolerancia,
        )
        for s in contexto.grade_segmentos.consultar(janela):
            if s.caminho in forma.origens or not um_traco(modelo, s.caminho):
                continue
            perto, longe = (
                (s.a, s.b) if math.dist(s.a, vertice) <= math.dist(s.b, vertice) else (s.b, s.a)
            )
            comprimento = math.dist(s.a, s.b)
            if (
                math.dist(perto, vertice) <= tolerancia
                and comprimento >= forma.lado * _HASTE_MINIMA
                and math.dist(longe, centro) > math.dist(vertice, centro)
                and diferenca_angular(angulo(s), radial) <= _HASTE_ANGULO
                and (escolhida is None or comprimento > math.dist(escolhida.a, escolhida.b))
            ):
                escolhida = s
    return escolhida


def _eixos(forma: _Forma, eixo: float | None, haste: Segmento | None) -> list[float]:
    """O eixo do pictograma: a aresta dividida, a haste ou, sem elas, as três medianas."""
    if eixo is not None:
        return [eixo]
    if haste is not None:
        return [angulo(haste)]
    centro = forma.centro
    return [angulo(Segmento(centro, vertice, -1)) for vertice in forma.vertices]


def _classificar(
    contexto: ContextoGramatica,
    marcas: MarcasDaPagina,
    forma: _Forma,
    fill: Preenchimento,
    eixo: float | None,
    extras: Iterable[int] = (),
) -> Triangulo:
    """Lê envolvente, haste e X do candidato, uma vez."""
    origens = tuple(sorted({*forma.origens, *extras}))
    achada = envolvente(
        marcas.contornos, list(forma.vertices), forma.lado, forma.centro, frozenset(origens)
    )
    haste = _haste(contexto, forma)
    caixa = forma.caixa if achada is None else achada.caixa
    caminhos = set(origens)
    if achada is not None:
        caminhos.update(achada.caminhos)
    if haste is not None:
        caminhos.add(haste.caminho)
    proprios = frozenset(
        s for s in contexto.grade_segmentos.consultar(forma.caixa) if s.caminho in origens
    ) | frozenset([] if haste is None else [haste])
    x = None
    for direcao in _eixos(forma, eixo, haste):
        x = tem_x(contexto, caixa, forma.lado, direcao, proprios)
        if x is not None:
            break
    if x is not None:
        caminhos.update(braco.caminho for braco in x)
    ancora = origens[0]
    return Triangulo(
        caixa,
        ancora,
        tuple(sorted(caminhos - {ancora})),
        fill,
        achada is not None,
        x is not None,
        contexto,
    )


class _Recusas:
    """O que tira um triângulo já lido do transformador: o contorno tracejado ou roxo dele, os
    três vértices na borda de uma moldura retangular (a PLATAFORMA, `triangle_in_frame`) e a
    linha de `_SETA_LINHA_MINIMA_LADOS` lados ou mais que termina no meio de um lado (a ponta de
    seta vazada) e a palavra dentro dele (o Δ de revisão). Paga as grades."""

    __slots__ = ("_contexto", "_molduras", "_recusados")

    def __init__(self, contexto: ContextoGramatica, recusados: Sequence[_Triangulo]) -> None:
        limites = _limites(contexto.pagina.modelo)
        self._contexto = contexto
        self._recusados = GradeEspacial(
            ((_caixa_de_pontos(v) or (0.0, 0.0, 0.0, 0.0), v) for v in recusados),
            limites,
            contexto.orcamento,
        )
        self._molduras = GradeEspacial(
            ((m.caixa, m.caixa) for m in contexto.molduras if m.forma == "retangulo"),
            limites,
            contexto.orcamento,
        )

    def aceita(self, forma: _Forma) -> bool:
        tolerancia = max(_VERTICE_MINIMO, forma.lado * _VERTICE_RELATIVO)
        caixa = forma.caixa
        return not (
            any(
                _mesmo_triangulo(forma.vertices, v, forma.lado * _COBERTURA_RELATIVA)
                for v in self._recusados.consultar(caixa)
            )
            or any(
                all(_na_borda(p, moldura, tolerancia) for p in forma.vertices)
                for moldura in self._molduras.consultar(caixa)
            )
            or self._seta(forma, tolerancia)
            or self._tem_texto(forma, tolerancia)
        )

    def _tem_texto(self, forma: _Forma, tolerancia: float) -> bool:
        """Uma palavra do modelo (nativa, SHX ou de glifo) com o centro dentro do triângulo: o Δ
        de revisão com o número, e não o pictograma do transformador."""
        return any(
            _dentro(
                ((p.caixa[0] + p.caixa[2]) / 2, (p.caixa[1] + p.caixa[3]) / 2),
                forma.vertices,
                tolerancia,
            )
            for p in self._contexto.grade_palavras.consultar(forma.caixa)
        )

    def _seta(self, forma: _Forma, tolerancia: float) -> bool:
        vertices = forma.vertices
        arestas = [(vertices[i], vertices[(i + 1) % 3]) for i in range(3)]
        minima = forma.lado * _SETA_LINHA_MINIMA_LADOS
        for s in self._contexto.grade_segmentos.consultar(forma.caixa):
            if s.caminho in forma.origens or math.dist(s.a, s.b) < minima:
                continue
            for perto, longe in ((s.a, s.b), (s.b, s.a)):
                if _dentro(longe, vertices, tolerancia):
                    continue
                for p, q in arestas:
                    t = _no_segmento(perto, p, q, tolerancia)
                    if t is not None and _LADO_DA_SETA[0] <= t <= _LADO_DA_SETA[1]:
                        return True
        return False


def _na_borda(ponto: Ponto, caixa: Caixa, tolerancia: float) -> bool:
    """O ponto sobre um lado da caixa retangular, com a tolerância."""
    x, y = ponto
    x0, y0, x1, y1 = caixa
    if not (x0 - tolerancia <= x <= x1 + tolerancia and y0 - tolerancia <= y <= y1 + tolerancia):
        return False
    return min(abs(x - x0), abs(x - x1), abs(y - y0), abs(y - y1)) <= tolerancia


def triangulos_candidatos(
    contexto: ContextoGramatica, *, marcas: MarcasDaPagina | None = None
) -> tuple[Triangulo, ...]:
    """Todos os triângulos de transformador da página, já classificados (fill, envolvente e X).

    `marcas` são as da página, compartilhadas com outras gramáticas; sem elas, são criadas aqui;
    marcas de outro contexto levantam `ValueError`. Gasta 1 por triângulo examinado, as consultas
    às grades e, se há candidato, os contornos das marcas, pagos uma vez por página.
    """
    marcas = marcas_do_contexto(contexto, marcas)
    pagina = contexto.pagina
    perfil = _PERFIS[marcas.origem]
    excluidos = frozenset(pagina.glifos_lidos) | frozenset(pagina.translucidos)
    lidos = _triangulos_da_pagina(pagina.modelo, excluidos, perfil, contexto.orcamento)
    if not lidos.cianos and not lidos.brancos and not lidos.contornos:
        return ()
    recusas = _Recusas(contexto, lidos.recusados)
    meios = [m for m in _meios_cianos(contexto, lidos, perfil) if recusas.aceita(m.forma)]
    formas, anexos = _contornos(contexto, lidos, meios, perfil)
    formas = [forma for forma in formas if recusas.aceita(forma)]
    resultado = [
        _classificar(contexto, marcas, meio.forma, "half_cyan", meio.eixo, anexos.get(i, ()))
        for i, meio in enumerate(meios)
    ]
    resultado.extend(_classificar(contexto, marcas, forma, "outline", None) for forma in formas)
    return tuple(resultado)


def _do_grupo(candidato: Triangulo, gramatica: Mapping[str, Any]) -> bool:
    """O grupo do candidato: o X decide primeiro; sem X, a envolvente."""
    if candidato.fill != gramatica["fill"]:
        return False
    if bool(gramatica["removal_mark"]):
        return candidato.x and gramatica["enclosure"] == "none"
    quer_elipse = gramatica["enclosure"] == "ellipse"
    return not candidato.x and candidato.envolvente == quer_elipse


def casa_triangulos(
    contexto: ContextoGramatica,
    gramatica: Mapping[str, Any],
    *,
    candidatos: tuple[Triangulo, ...] | None = None,
) -> list[tuple[Caixa, int, tuple[int, ...]]]:
    """(caixa do pictograma, caminho âncora, demais caminhos) de cada candidato da variante.

    `candidatos` são os `triangulos_candidatos` da página, já classificados; sem eles, são
    calculados aqui. Só filtra a classificação pronta: não gasta do orçamento. Candidato de outro
    contexto levanta `ValueError`.
    """
    achados = triangulos_candidatos(contexto) if candidatos is None else candidatos
    if any(candidato.contexto is not contexto for candidato in achados):
        raise ValueError("Os candidatos de triângulo são de outro contexto de gramáticas.")
    limite = float(gramatica["max_span"])
    return [
        (c.caixa, c.caminho, c.componentes)
        for c in achados
        if _do_grupo(c, gramatica)
        and max(c.caixa[2] - c.caixa[0], c.caixa[3] - c.caixa[1]) <= limite
    ]
