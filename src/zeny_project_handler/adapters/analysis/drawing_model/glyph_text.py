"""Leitura de texto desenhado como contorno preenchido de glifo, contra a tabela versionada.

Candidatos a glifo consecutivos na ordem de desenho, com a mesma cor e vizinhos, formam um
trecho; a vizinhança de um glifo pequeno (".", ",", "-") é medida pelo maior lado da faixa ao
lado, para que pontuação em sequência não saia do valor em silêncio. Um caminho preenchido da
mesma cor, vizinho na ordem de desenho e encostado na ponta de um trecho, mas reprovado no
filtro de candidato (grande demais, subcaminhos ou itens demais, coordenada não finita), pode
ser um glifo do próprio valor: o trecho não é lido e o caminho conta como desconhecido.
A página passa a `limitada` acima de `LIMITE_GLIFOS_PAGINA` candidatos, de
`LIMITE_PONTOS_PAGINA` pontos achatados somados dos candidatos ou de `LIMITE_RESOLUCOES_PAGINA`
resoluções distintas contra a tabela.

O quadro do trecho põe o texto na horizontal para calcular a assinatura de cada glifo. O
ângulo parte da reta de mínimos quadrados dos centros, orientada do primeiro para o último
glifo, e é refinado até convergir pela mediana das inclinações entre os fundos (Theil-Sen) só
dos glifos de corpo inteiro (altura perto da dos glifos altos; sem "-", "=", ".", ","), porque
glifos fora do centro inclinam a reta dos centros e a assinatura, que mede a posição em
relação à linha de base, deriva ao longo da linha. Altura e linha de base são as medianas dos
mesmos glifos.

Em trecho curto a geometria é mal determinada (a cauda do "Q" entorta a reta dos fundos e o
"Q" passaria por "O"). Por isso cada glifo é resolvido também em quadros independentes: o
refinado pelos topos e, com até `_CORPO_CURTO` glifos de corpo inteiro, a reta dos centros
deles. Um glifo só vale se todos os quadros o leem igual; senão é ambíguo. Com menos de 2
glifos de corpo inteiro ("-1", "Q-") o quadro não é determinado e o trecho inteiro é ambíguo.
Trechos em que a maioria é pontuação alta ("(1)", "(((") têm altura errada e ficam
desconhecidos. Glifo desconhecido ou ambíguo anula o texto em que cairia: a leitura falha
fechada, nunca sai texto com caractere trocado ou faltando.

Espaço e quebra são medidos numa escala que não depende de quais glifos o texto tem: a altura
bruta da linha sobe com glifos redondos ("3", "0" passam um pouco da altura do "1") e a mesma
lacuna mudaria de tamanho em unidades de h. A escala das lacunas é a mediana, sobre os glifos
altos reconhecidos, da altura do glifo dividida pela altura típica do seu caractere na tabela
(mediana das entradas do caractere).

O h do trecho é a altura de maiúscula ou, num trecho só de minúsculas, a altura-x, e a tabela
tem entradas colhidas nas duas escalas ("e" a ~0,75 h e a ~1,0 h). Um "z" lido com h = altura-x
tem o desenho e a altura relativa do "Z" colhido com h = altura de maiúscula. Por isso os glifos
altos reconhecidos do trecho têm de indicar a mesma escala (altura acima ou até `RAZAO_ESCALA_X`
x a menor altura do caractere na tabela); se indicam as duas, todos ficam ambíguos. Só um
caractere colhido nas duas escalas ancora a escala; num trecho sem âncora (ver
`_com_escala_coerente`), letra sem par de caixa na tabela ou forma que, com a escala igualada,
aponta outro caractere faz o trecho falhar fechado.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from statistics import median, median_low
from typing import Final

from zeny_project_handler.adapters.analysis.drawing_model.glyph_signature import (
    PASSOS_BEZIER,
    AssinaturaGlifo,
    achatar_subcaminho,
    assinatura_glifo,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    Resolucao,
    TabelaGlifos,
    forma_sem_escala_confirma,
    resolver_glifo,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa, Caminho, Cor, Ponto

LIMITE_GLIFOS_PAGINA: Final = 20_000
# Orçamento de pontos achatados (1 por segmento, PASSOS_BEZIER por Bézier) somados dos
# candidatos da página: o custo da leitura cresce com os pontos, não só com os candidatos.
LIMITE_PONTOS_PAGINA: Final = 2_000_000
# Teto de resoluções distintas (varreduras da tabela que a memória não poupou: resolução de
# glifo e confirmação de forma sem escala), conferido entre trechos. Formas que não se repetem
# escapam da memória, e cada varredura custa ~5 ms na tabela real; nas 16 folhas reais a mais
# pesada faz 2 277, e o teto põe o pior caso perto de 2x o dessa folha.
LIMITE_RESOLUCOES_PAGINA: Final = 4_000
LADO_MAXIMO_GLIFO: Final = 7.0
_LADO_MINIMO_GLIFO: Final = 0.05
_MAXIMO_SUBCAMINHOS: Final = 8
_MAXIMO_ITENS: Final = 256
_FATOR_VIZINHANCA: Final = 1.6
_MINIMO_GLIFOS_TRECHO: Final = 2
_MAXIMO_GLIFOS_TRECHO: Final = 64
_CASAS_MEMORIA: Final = 3
_FRACAO_GLIFO_ALTO: Final = 0.5
_DESVIO_CORPO: Final = 0.15
_PONTOS_POR_TIPO: Final = {"l": 2, "c": 4}
# Abaixo disso (radianos, ~0,006°) os quadros pelos fundos e pelos topos são o mesmo.
_DIFERENCA_QUADROS: Final = 1e-4
_ITERACOES_REFINO: Final = 4
_CORPO_CURTO: Final = 4
# Quadros (fundos, topos, centros do corpo) mais afastados que isso: quadro não confirmado.
_ESPALHAMENTO_QUADROS: Final = math.radians(1.0)
_TIPOS_PREENCHIDOS: Final = frozenset({"preenchimento", "traco_e_preenchimento"})
# Altura do glifo / menor altura do caractere na tabela que separa a escala do trecho: até ela,
# h é a altura de maiúscula; acima, a altura-x (Arial: 0,716/0,519 ≈ 1,38). Nas 16 folhas
# reais a razão fica em ≤ 1,168 e ≥ 1,214, sem nada entre as duas.
RAZAO_ESCALA_X: Final = 1.19

_ChaveAssinatura = tuple[int, tuple[float, ...], tuple[tuple[float, ...], ...]]
# ("caminho", posição) do vizinho reprovado, ou ("ordem", ordem) do desenho descartado
_Veneno = tuple[str, int]


@dataclass(frozen=True, slots=True)
class GlifoDoTrecho:
    indice_caminho: int
    caixa: Caixa
    assinatura: AssinaturaGlifo | None


@dataclass(frozen=True, slots=True)
class TrechoGlifos:
    glifos: tuple[GlifoDoTrecho, ...]
    rotacao: float
    altura: float
    cor: Cor | None
    # quadro não confirmado: menos de 2 glifos de corpo inteiro, ou os quadros pelos fundos,
    # pelos topos e pelos centros do corpo divergem mais que `_ESPALHAMENTO_QUADROS`
    quadro_incerto: bool


@dataclass(frozen=True, slots=True)
class TextoGlifo:
    texto: str
    bbox: Caixa
    cantos: tuple[Ponto, Ponto, Ponto, Ponto]
    rotacao: float
    altura: float
    quantidade_glifos: int
    cor: Cor | None
    glifos: tuple[tuple[str, Caixa], ...]


@dataclass(frozen=True, slots=True)
class LeituraGlifos:
    textos: tuple[TextoGlifo, ...]
    desconhecidos: int
    ambiguos: int
    limitada: bool


@dataclass(frozen=True, slots=True)
class _Candidato:
    indice: int
    ordem: int
    poligonos: tuple[tuple[Ponto, ...], ...]
    caixa: Caixa
    cor: Cor | None


@dataclass(frozen=True, slots=True)
class _Trecho:
    publico: TrechoGlifos
    angulo: float
    caixas_quadro: tuple[Caixa, ...]
    # assinaturas nos outros quadros (topos; centros do corpo inteiro) que diferem do principal
    alternativas: tuple[tuple[AssinaturaGlifo | None, ...], ...]
    # menos de 2 glifos de corpo inteiro: o quadro não é determinado e nada é lido
    sem_quadro: bool
    # caminhos preenchidos vizinhos, da mesma cor e encostados numa ponta, reprovados no filtro
    # de candidato, ou desenhos descartados na extração (salto em `Caminho.ordem` numa ponta):
    # podem ser glifos do próprio valor, então o trecho não é lido
    venenos: tuple[_Veneno, ...] = ()


# --- candidatos e trechos -------------------------------------------------------------------


def _caixa_de(pontos: Sequence[Ponto]) -> Caixa:
    xs = [p[0] for p in pontos]
    ys = [p[1] for p in pontos]
    return (min(xs), min(ys), max(xs), max(ys))


def _eh_candidato(caminho: Caminho) -> bool:
    """Teste barato (caixa dos pontos de controle), usado também para o teto da página."""
    if caminho.tipo not in _TIPOS_PREENCHIDOS:
        return False
    if not 1 <= len(caminho.subcaminhos) <= _MAXIMO_SUBCAMINHOS:
        return False
    itens = [item for subcaminho in caminho.subcaminhos for item in subcaminho]
    if not itens or len(itens) > _MAXIMO_ITENS:
        return False
    if any(len(item.pontos) != _PONTOS_POR_TIPO.get(item.tipo) for item in itens):
        return False
    pontos = [ponto for item in itens for ponto in item.pontos]
    if not all(math.isfinite(x) and math.isfinite(y) for x, y in pontos):
        return False
    x0, y0, x1, y1 = _caixa_de(pontos)
    return _LADO_MINIMO_GLIFO < max(x1 - x0, y1 - y0) < LADO_MAXIMO_GLIFO


def _pontos_achatados(caminho: Caminho) -> int:
    return sum(
        1 if item.tipo == "l" else PASSOS_BEZIER
        for subcaminho in caminho.subcaminhos
        for item in subcaminho
    )


def _candidatos_limitados(caminhos: Sequence[Caminho]) -> list[int] | None:
    """Índices dos candidatos, ou None assim que a página passa do teto de candidatos ou do
    orçamento de pontos (a contagem para ali: página hostil não custa a varredura inteira)."""
    indices: list[int] = []
    pontos = 0
    for indice, caminho in enumerate(caminhos):
        if not _eh_candidato(caminho):
            continue
        indices.append(indice)
        pontos += _pontos_achatados(caminho)
        if len(indices) > LIMITE_GLIFOS_PAGINA or pontos > LIMITE_PONTOS_PAGINA:
            return None
    return indices


def _candidato(indice: int, caminho: Caminho) -> _Candidato:
    poligonos = tuple(achatar_subcaminho(subcaminho) for subcaminho in caminho.subcaminhos)
    caixa = _caixa_de([ponto for poligono in poligonos for ponto in poligono])
    return _Candidato(indice, caminho.ordem, poligonos, caixa, caminho.estilo.preenchimento)


def _centro(caixa: Caixa) -> Ponto:
    return ((caixa[0] + caixa[2]) / 2.0, (caixa[1] + caixa[3]) / 2.0)


def _maior_lado(caixa: Caixa) -> float:
    return max(caixa[2] - caixa[0], caixa[3] - caixa[1])


def _vizinhos(anterior: _Candidato, atual: _Candidato, lado: float) -> bool:
    """Consecutivos na ordem de desenho, mesma cor e centros a até 1,6 x `lado`. Um salto em
    `Caminho.ordem` é um desenho descartado na extração: os dois lados não são vizinhos."""
    if atual.indice != anterior.indice + 1 or atual.ordem != anterior.ordem + 1:
        return False
    if atual.cor != anterior.cor:
        return False
    alcance = _FATOR_VIZINHANCA * max(lado, _maior_lado(anterior.caixa), _maior_lado(atual.caixa))
    return math.dist(_centro(anterior.caixa), _centro(atual.caixa)) <= alcance


@dataclass(slots=True)
class _Faixa:
    """Faixa [inicio, fim) de candidatos consecutivos e o maior lado entre eles."""

    inicio: int
    fim: int
    lado: float


def _faixas(candidatos: Sequence[_Candidato]) -> list[_Faixa]:
    faixas: list[_Faixa] = []
    for indice, candidato in enumerate(candidatos):
        lado = _maior_lado(candidato.caixa)
        if faixas and _vizinhos(candidatos[indice - 1], candidato, 0.0):
            faixas[-1].fim = indice + 1
            faixas[-1].lado = max(faixas[-1].lado, lado)
        else:
            faixas.append(_Faixa(indice, indice + 1, lado))
    return faixas


def _encostam(candidatos: Sequence[_Candidato], esquerda: _Faixa, direita: _Faixa) -> bool:
    lado = max(esquerda.lado, direita.lado)
    return _vizinhos(candidatos[esquerda.fim - 1], candidatos[direita.inicio], lado)


def _fundir(
    candidatos: Sequence[_Candidato], faixas: list[_Faixa], *, para_tras: bool
) -> list[_Faixa]:
    """Funde faixas vizinhas medindo o alcance pelo maior lado das duas faixas, numa varredura."""
    ordem = reversed(faixas) if para_tras else iter(faixas)
    fundidas: list[_Faixa] = []
    for faixa in ordem:
        if fundidas:
            ultima = fundidas[-1]
            esquerda, direita = (faixa, ultima) if para_tras else (ultima, faixa)
            if _encostam(candidatos, esquerda, direita):
                fundidas[-1] = _Faixa(esquerda.inicio, direita.fim, max(faixa.lado, ultima.lado))
                continue
        fundidas.append(faixa)
    return fundidas[::-1] if para_tras else fundidas


def _agrupar(candidatos: Sequence[_Candidato]) -> list[list[_Candidato]]:
    """Trechos de candidatos vizinhos. Glifo pequeno (".", ",", "-") ao lado de outro pequeno
    fica longe demais pela regra par a par; as varreduras de fusão medem o alcance pelo maior
    lado da faixa vizinha, para que a pontuação na ponta de um valor não saia em silêncio."""
    faixas = _faixas(candidatos)
    faixas = _fundir(candidatos, _fundir(candidatos, faixas, para_tras=True), para_tras=False)
    return [
        list(candidatos[f.inicio : f.fim])
        for f in faixas
        if _MINIMO_GLIFOS_TRECHO <= f.fim - f.inicio <= _MAXIMO_GLIFOS_TRECHO
    ]


def _angulo(centros: Sequence[Ponto]) -> float:
    """Reta de mínimos quadrados (total) pelos centros, orientada do primeiro ao último."""
    mx = sum(x for x, _ in centros) / len(centros)
    my = sum(y for _, y in centros) / len(centros)
    sxx = sum((x - mx) ** 2 for x, _ in centros)
    syy = sum((y - my) ** 2 for _, y in centros)
    sxy = sum((x - mx) * (y - my) for x, y in centros)
    angulo = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
    dx = centros[-1][0] - centros[0][0]
    dy = centros[-1][1] - centros[0][1]
    if dx * math.cos(angulo) + dy * math.sin(angulo) < 0:
        angulo += math.pi
    return angulo


def _no_quadro(candidato: _Candidato, cosseno: float, seno: float) -> list[list[Ponto]]:
    """Polígonos do glifo girados para o quadro (cosseno e seno calculados uma vez por quadro)."""
    return [
        [(x * cosseno + y * seno, -x * seno + y * cosseno) for x, y in poligono]
        for poligono in candidato.poligonos
    ]


def _para_pagina(ponto: Ponto, angulo: float) -> Ponto:
    c, s = math.cos(angulo), math.sin(angulo)
    return (ponto[0] * c - ponto[1] * s, ponto[0] * s + ponto[1] * c)


def _caixas_no_quadro(grupo: Sequence[_Candidato], angulo: float) -> list[Caixa]:
    cosseno, seno = math.cos(angulo), math.sin(angulo)
    return [
        _caixa_de([p for poligono in _no_quadro(c, cosseno, seno) for p in poligono]) for c in grupo
    ]


def _corpo_inteiro(caixas: Sequence[Caixa]) -> list[int]:
    """Glifos "de corpo inteiro": altura perto da mediana (baixa) das alturas dos glifos altos.

    Pontuação baixa ("-", "=", ".", ",") fica de fora, e também os parênteses quando a maioria
    é de letras e algarismos. A mediana baixa é uma das alturas, então o conjunto nunca é vazio.
    """
    alturas = [caixa[3] - caixa[1] for caixa in caixas]
    maior = max(alturas)
    referencia = median_low([a for a in alturas if a >= _FRACAO_GLIFO_ALTO * maior])
    return [i for i, a in enumerate(alturas) if abs(a - referencia) <= _DESVIO_CORPO * referencia]


def _refinar(pontos: Sequence[Ponto], angulo: float) -> float:
    """Corrige o ângulo provisório pela mediana das inclinações par a par dos pontos
    (Theil-Sen), no quadro provisório; com menos de 2 pontos fica o ângulo provisório."""
    inclinacoes = [
        (b[1] - a[1]) / (b[0] - a[0])
        for i, a in enumerate(pontos)
        for b in pontos[i + 1 :]
        if abs(b[0] - a[0]) > 1e-9
    ]
    if not inclinacoes:
        return angulo
    return angulo + math.atan(float(median(inclinacoes)))


def _quadro(
    grupo: Sequence[_Candidato], angulo: float, corpo: Sequence[int]
) -> tuple[tuple[Caixa, ...], float, tuple[AssinaturaGlifo | None, ...]]:
    """Caixas no quadro, altura e assinaturas dos glifos no quadro de `angulo`."""
    cosseno, seno = math.cos(angulo), math.sin(angulo)
    no_quadro = [_no_quadro(c, cosseno, seno) for c in grupo]
    caixas = tuple(_caixa_de([p for poligono in pol for p in poligono]) for pol in no_quadro)
    altura = float(median(caixas[i][3] - caixas[i][1] for i in corpo))
    base = float(median(caixas[i][3] for i in corpo))
    assinaturas = tuple(
        assinatura_glifo(pol, altura_linha=altura, base_linha=base) for pol in no_quadro
    )
    return caixas, altura, assinaturas


def _diferenca_angular(a: float, b: float) -> float:
    return (a - b + math.pi) % (2.0 * math.pi) - math.pi


def _fundo(caixa: Caixa) -> Ponto:
    return ((caixa[0] + caixa[2]) / 2.0, caixa[3])


def _topo(caixa: Caixa) -> Ponto:
    return ((caixa[0] + caixa[2]) / 2.0, caixa[1])


def _refinado(
    grupo: Sequence[_Candidato],
    corpo: Sequence[int],
    angulo: float,
    ponto: Callable[[Caixa], Ponto],
) -> float:
    """Refina até convergir: as caixas medidas num quadro torto não têm o fundo (ou o topo) no
    ponto certo do glifo, então um passo só, partindo de longe, não chega à reta verdadeira."""
    glifos = [grupo[i] for i in corpo]
    for _ in range(_ITERACOES_REFINO):
        anterior = angulo
        angulo = _refinar([ponto(c) for c in _caixas_no_quadro(glifos, angulo)], angulo)
        if abs(angulo - anterior) <= _DIFERENCA_QUADROS / 10:
            break
    return angulo


def _trecho(grupo: Sequence[_Candidato]) -> _Trecho:
    provisorio = _angulo([_centro(c.caixa) for c in grupo])
    corpo = _corpo_inteiro(_caixas_no_quadro(grupo, provisorio))
    angulo = _refinado(grupo, corpo, provisorio, _fundo)
    corpo = _corpo_inteiro(_caixas_no_quadro(grupo, angulo))
    angulo = _refinado(grupo, corpo, angulo, _fundo)
    # estimativas independentes: os topos partem da reta dos centros, não do quadro dos fundos,
    # para não caírem no mesmo ponto fixo errado; com poucos glifos de corpo inteiro a
    # geometria é mal determinada e a reta dos centros deles entra como terceiro quadro
    outros = [_refinado(grupo, corpo, provisorio, _topo)]
    if 2 <= len(corpo) <= _CORPO_CURTO:
        outros.append(_angulo([_centro(grupo[i].caixa) for i in corpo]))
    caixas, altura, assinaturas = _quadro(grupo, angulo, corpo)
    afastamentos = [abs(_diferenca_angular(outro, angulo)) for outro in outros]
    alternativas = tuple(
        _quadro(grupo, outro, corpo)[2]
        for outro, afastamento in zip(outros, afastamentos, strict=True)
        if afastamento > _DIFERENCA_QUADROS
    )
    glifos = tuple(
        GlifoDoTrecho(c.indice, c.caixa, assinatura)
        for c, assinatura in zip(grupo, assinaturas, strict=True)
    )
    rotacao = round(math.degrees(angulo), 6) % 360.0
    incerto = len(corpo) < 2 or max(afastamentos) > _ESPALHAMENTO_QUADROS
    publico = TrechoGlifos(glifos, rotacao, altura, grupo[0].cor, incerto)
    return _Trecho(publico, angulo, caixas, alternativas, len(corpo) < 2)


def _indices_candidatos(caminhos: Sequence[Caminho]) -> list[int]:
    return [indice for indice, caminho in enumerate(caminhos) if _eh_candidato(caminho)]


def _envenena(caminho: Caminho, vizinho: _Candidato, lado: float) -> bool:
    """Caminho preenchido da mesma cor, reprovado no filtro de candidato e encostado na ponta
    do trecho: pode ser um glifo do próprio valor (grande demais, subcaminhos ou itens demais,
    coordenada não finita). Sem coordenada finita não dá para medir, e conta como encostado."""
    if caminho.tipo not in _TIPOS_PREENCHIDOS or caminho.estilo.preenchimento != vizinho.cor:
        return False
    pontos = [p for subcaminho in caminho.subcaminhos for item in subcaminho for p in item.pontos]
    if not pontos:
        return False
    if not all(math.isfinite(x) and math.isfinite(y) for x, y in pontos):
        return True
    alcance = _FATOR_VIZINHANCA * lado
    return math.dist(_centro(_caixa_de(pontos)), _centro(vizinho.caixa)) <= alcance


def _descartado(
    caminhos: Sequence[Caminho], indice: int, vizinho: _Candidato, total_desenhos: int | None
) -> _Veneno | None:
    """Desenho descartado por `caminhos_da_pagina` entre a ponta do trecho e o caminho vizinho
    (salto em `Caminho.ordem`), antes do primeiro caminho da página (ordem acima de 0) ou,
    sabendo quantos desenhos a página tem, depois do último."""
    passo = 1 if indice > vizinho.indice else -1
    if 0 <= indice < len(caminhos):
        if caminhos[indice].ordem == vizinho.ordem + passo:
            return None
        return ("ordem", vizinho.ordem + passo)
    if indice < 0 < vizinho.ordem:
        return ("ordem", vizinho.ordem - 1)
    sem_seguinte = indice >= len(caminhos)
    if sem_seguinte and total_desenhos is not None and vizinho.ordem + 1 < total_desenhos:
        return ("ordem", vizinho.ordem + 1)
    return None


def _venenos(
    caminhos: Sequence[Caminho],
    grupo: Sequence[_Candidato],
    candidatos: set[int],
    total_desenhos: int | None,
) -> tuple[_Veneno, ...]:
    lado = max(_maior_lado(c.caixa) for c in grupo)
    pontas = ((grupo[0].indice - 1, grupo[0]), (grupo[-1].indice + 1, grupo[-1]))
    venenos: list[_Veneno] = []
    for indice, vizinho in pontas:
        descartado = _descartado(caminhos, indice, vizinho, total_desenhos)
        if descartado is not None:
            venenos.append(descartado)
        elif (
            0 <= indice < len(caminhos)
            and indice not in candidatos
            and _envenena(caminhos[indice], vizinho, lado)
        ):
            venenos.append(("caminho", indice))
    return tuple(venenos)


def _trechos(
    caminhos: Sequence[Caminho], indices: Sequence[int], total_desenhos: int | None = None
) -> Iterator[_Trecho]:
    """Trechos um a um: a leitura que para no teto de resoluções não mede os seguintes."""
    candidatos = [_candidato(indice, caminhos[indice]) for indice in indices]
    conjunto = set(indices)
    for grupo in _agrupar(candidatos):
        yield replace(_trecho(grupo), venenos=_venenos(caminhos, grupo, conjunto, total_desenhos))


def extrair_trechos(caminhos: Sequence[Caminho]) -> tuple[TrechoGlifos, ...]:
    """Trechos de glifos (2 a 64), com os glifos na ordem de leitura."""
    return tuple(t.publico for t in _trechos(caminhos, _indices_candidatos(caminhos)))


# --- leitura --------------------------------------------------------------------------------


def _chave(assinatura: AssinaturaGlifo) -> _ChaveAssinatura:
    return (
        assinatura.subcaminhos,
        tuple(round(v, _CASAS_MEMORIA) for v in assinatura.caixa),
        tuple(
            tuple(round(v, _CASAS_MEMORIA) for ponto in contorno for v in ponto)
            for contorno in assinatura.contornos
        ),
    )


@dataclass(slots=True)
class _Memoria:
    """Varreduras da tabela já feitas na página, pela assinatura arredondada."""

    resolucoes: dict[_ChaveAssinatura, Resolucao] = field(default_factory=dict)
    formas: dict[tuple[_ChaveAssinatura, str], bool] = field(default_factory=dict)

    def distintas(self) -> int:
        return len(self.resolucoes) + len(self.formas)


def _resolver(
    tabela: TabelaGlifos, assinatura: AssinaturaGlifo | None, memoria: _Memoria
) -> Resolucao:
    if assinatura is None:
        return Resolucao("desconhecido", None, math.inf)
    chave = _chave(assinatura)
    resolucao = memoria.resolucoes.get(chave)
    if resolucao is None:
        resolucao = memoria.resolucoes[chave] = resolver_glifo(tabela, assinatura)
    return resolucao


def _forma_confirma(
    tabela: TabelaGlifos, assinatura: AssinaturaGlifo, caractere: str, memoria: _Memoria
) -> bool:
    chave = (_chave(assinatura), caractere)
    confirma = memoria.formas.get(chave)
    if confirma is None:
        confirma = memoria.formas[chave] = forma_sem_escala_confirma(tabela, assinatura, caractere)
    return confirma


def _lacuna(trecho: _Trecho, anterior: int, atual: int) -> float:
    return trecho.caixas_quadro[atual][0] - trecho.caixas_quadro[anterior][2]


def alturas_tipicas(tabela: TabelaGlifos) -> dict[str, float]:
    """Altura típica (em h) de cada caractere: mediana da altura das entradas dele."""
    alturas: dict[str, list[float]] = {}
    for entrada in tabela.glifos:
        if entrada.caractere is not None:
            alturas.setdefault(entrada.caractere, []).append(entrada.assinatura.caixa[1])
    return {caractere: float(median(valores)) for caractere, valores in alturas.items()}


@dataclass(frozen=True, slots=True)
class EscalasDaTabela:
    """O que a tabela diz sobre a escala do h de um trecho (altura de maiúscula ou altura-x)."""

    # menor altura de cada caractere alto
    minimas: dict[str, float]
    # caracteres altos colhidos nas duas escalas (alguma entrada acima de `RAZAO_ESCALA_X` x a
    # menor): só neles a menor altura é, com certeza, a de maiúscula
    referencias: frozenset[str]
    # letras cujo par de caixa (maiúscula/minúscula) não está na tabela: na outra escala elas
    # podem ser o par ("Z" lido onde está "z"), e a tabela não tem como dizer que não são
    sem_par: frozenset[str]


def escalas_da_tabela(tabela: TabelaGlifos) -> EscalasDaTabela:
    alturas: dict[str, list[float]] = {}
    for entrada in tabela.glifos:
        if entrada.caractere is not None:
            alturas.setdefault(entrada.caractere, []).append(entrada.assinatura.caixa[1])
    minimas = {c: min(v) for c, v in alturas.items() if min(v) >= _FRACAO_GLIFO_ALTO}
    referencias = frozenset(c for c in minimas if max(alturas[c]) > RAZAO_ESCALA_X * minimas[c])
    sem_par = frozenset(
        c for c in minimas if len(par := c.swapcase()) == 1 and par != c and par not in alturas
    )
    return EscalasDaTabela(minimas, referencias, sem_par)


def _com_escala_coerente(
    trecho: _Trecho,
    resolucoes: list[Resolucao],
    tabela: TabelaGlifos,
    escalas: EscalasDaTabela,
    memoria: _Memoria,
) -> list[Resolucao]:
    """Os glifos altos reconhecidos têm de dizer a mesma escala do h do trecho, e ela tem de estar
    ancorada; senão todos ficam ambíguos. Um glifo acima de `RAZAO_ESCALA_X` x a menor altura do
    seu caractere na tabela foi lido com h = altura-x; até ela, com h = altura de maiúscula.

    Trecho sem âncora (um caractere alto só, repetido; ou, numa tabela com as duas escalas,
    nenhum caractere de referência) tira a escala e a linha de base de si mesmo, e nada nele
    contradiz uma leitura na escala errada. Ele falha fechado se tem letra sem par de caixa na
    tabela ("zz" → "ZZ", "lzz" → "lZZ") ou, com um caractere só, se a forma com a escala
    igualada aponta outro caractere ("jj" → "ii")."""
    minimas = escalas.minimas
    altos = [
        (
            indice,
            resolucao.caractere,
            assinatura,
            assinatura.caixa[1] > RAZAO_ESCALA_X * minimas[resolucao.caractere],
        )
        for indice, (glifo, resolucao) in enumerate(
            zip(trecho.publico.glifos, resolucoes, strict=True)
        )
        if resolucao.situacao == "reconhecido"
        and resolucao.caractere in minimas
        and (assinatura := glifo.assinatura) is not None
    ]
    if not altos:
        return resolucoes
    caracteres = {caractere for _, caractere, _, _ in altos}
    duas_escalas = bool(escalas.referencias)
    um_so = len(caracteres) == 1
    sem_ancora = um_so or (duas_escalas and caracteres.isdisjoint(escalas.referencias))
    coerente = len({escala for *_, escala in altos}) == 1
    if sem_ancora and duas_escalas and not caracteres.isdisjoint(escalas.sem_par):
        coerente = False
    if um_so and coerente:
        coerente = all(
            _forma_confirma(tabela, assinatura, caractere, memoria)
            for _, caractere, assinatura, _ in altos
        )
    if coerente:
        return resolucoes
    return [
        Resolucao("ambiguo", None, r.distancia) if r.situacao == "reconhecido" else r
        for r in resolucoes
    ]


def _escala_das_lacunas(
    trecho: _Trecho, resolucoes: Sequence[Resolucao], tipicas: dict[str, float]
) -> float:
    """Altura da linha estimada glifo a glifo pela altura típica do caractere na tabela; sem
    glifo alto reconhecido, a altura bruta do trecho."""
    estimativas = [
        (caixa[3] - caixa[1]) / tipicas[resolucao.caractere]
        for caixa, resolucao in zip(trecho.caixas_quadro, resolucoes, strict=True)
        if resolucao.situacao == "reconhecido"
        and resolucao.caractere is not None
        and tipicas.get(resolucao.caractere, 0.0) >= _FRACAO_GLIFO_ALTO
    ]
    return float(median(estimativas)) if estimativas else trecho.publico.altura


def _grupos_de_texto(
    trecho: _Trecho, resolucoes: Sequence[Resolucao], tabela: TabelaGlifos, escala: float
) -> list[list[int]]:
    """Índices dos glifos de cada texto: "ignorar" e lacuna acima de `quebra` dividem."""
    limite = tabela.quebra * escala
    grupos: list[list[int]] = []
    atual: list[int] = []
    for indice, resolucao in enumerate(resolucoes):
        if resolucao.situacao == "ignorar":
            if atual:
                grupos.append(atual)
            atual = []
            continue
        if atual and _lacuna(trecho, atual[-1], indice) > limite:
            grupos.append(atual)
            atual = []
        atual.append(indice)
    if atual:
        grupos.append(atual)
    return grupos


def _cantos(trecho: _Trecho, grupo: Sequence[int]) -> tuple[Ponto, Ponto, Ponto, Ponto]:
    caixas = [trecho.caixas_quadro[i] for i in grupo]
    x0, y0 = min(c[0] for c in caixas), min(c[1] for c in caixas)
    x1, y1 = max(c[2] for c in caixas), max(c[3] for c in caixas)
    angulo = trecho.angulo
    return (
        _para_pagina((x0, y1), angulo),
        _para_pagina((x1, y1), angulo),
        _para_pagina((x1, y0), angulo),
        _para_pagina((x0, y0), angulo),
    )


def _texto(
    trecho: _Trecho,
    grupo: Sequence[int],
    resolucoes: Sequence[Resolucao],
    tabela: TabelaGlifos,
    escala: float,
) -> TextoGlifo:
    publico = trecho.publico
    espaco = tabela.espaco * escala
    partes: list[str] = []
    for posicao, indice in enumerate(grupo):
        if posicao and _lacuna(trecho, grupo[posicao - 1], indice) > espaco:
            partes.append(" ")
        partes.append(resolucoes[indice].caractere or "")
    caixas = [publico.glifos[i].caixa for i in grupo]
    return TextoGlifo(
        texto="".join(partes),
        bbox=(
            min(c[0] for c in caixas),
            min(c[1] for c in caixas),
            max(c[2] for c in caixas),
            max(c[3] for c in caixas),
        ),
        cantos=_cantos(trecho, grupo),
        rotacao=publico.rotacao,
        altura=publico.altura,
        quantidade_glifos=len(grupo),
        cor=publico.cor,
        glifos=tuple((resolucoes[i].caractere or "", publico.glifos[i].caixa) for i in grupo),
    )


def _concordar(principal: Resolucao, alternativa: Resolucao) -> Resolucao:
    """Um glifo só vale se os dois quadros o resolvem igual; senão é ambíguo."""
    if (principal.situacao, principal.caractere) == (alternativa.situacao, alternativa.caractere):
        return principal
    if principal.situacao == alternativa.situacao == "desconhecido":
        return principal
    return Resolucao("ambiguo", None, principal.distancia)


def _resolucoes(trecho: _Trecho, tabela: TabelaGlifos, memoria: _Memoria) -> list[Resolucao]:
    if trecho.sem_quadro:
        return [Resolucao("ambiguo", None, math.inf) for _ in trecho.publico.glifos]
    resolucoes = [_resolver(tabela, g.assinatura, memoria) for g in trecho.publico.glifos]
    for assinaturas in trecho.alternativas:
        resolucoes = [
            _concordar(resolucao, _resolver(tabela, alternativa, memoria))
            for resolucao, alternativa in zip(resolucoes, assinaturas, strict=True)
        ]
    return resolucoes


def ler_texto_glifos(
    caminhos: Sequence[Caminho], tabela: TabelaGlifos, total_desenhos: int | None = None
) -> LeituraGlifos:
    """Lê os trechos no quadro refinado pelos fundos e, quando difere, também no refinado pelos
    topos dos glifos de corpo inteiro: em trecho curto um glifo de fundo fora da linha de base
    (a cauda do "Q") entorta um dos quadros, e um glifo que os dois quadros leem diferente é
    ambíguo (falha fechada) em vez de virar outro caractere ("Q" lido como "O").

    `total_desenhos` é quantos desenhos de traço/preenchimento a página tinha antes de
    `caminhos_da_pagina` descartar os malformados; com ele, um descarte depois do último
    caminho também envenena o trecho da ponta (sem ele, esse caso não é detectável).

    Passando de `LIMITE_RESOLUCOES_PAGINA` resoluções distintas (conferido ao fim de cada
    trecho), a leitura para e a página fica `limitada`, sem texto."""
    indices = _candidatos_limitados(caminhos)
    if indices is None:
        return LeituraGlifos((), 0, 0, limitada=True)
    memoria = _Memoria()
    tipicas = alturas_tipicas(tabela)
    escalas = escalas_da_tabela(tabela)
    textos: list[TextoGlifo] = []
    desconhecidos = ambiguos = 0
    venenos: set[_Veneno] = set()
    for trecho in _trechos(caminhos, indices, total_desenhos):
        if trecho.venenos:
            venenos.update(trecho.venenos)
            continue
        resolucoes = _com_escala_coerente(
            trecho, _resolucoes(trecho, tabela, memoria), tabela, escalas, memoria
        )
        if memoria.distintas() > LIMITE_RESOLUCOES_PAGINA:
            return LeituraGlifos((), 0, 0, limitada=True)
        escala = _escala_das_lacunas(trecho, resolucoes, tipicas)
        for grupo in _grupos_de_texto(trecho, resolucoes, tabela, escala):
            situacoes = [resolucoes[i].situacao for i in grupo]
            falhas = (situacoes.count("desconhecido"), situacoes.count("ambiguo"))
            if any(falhas):
                desconhecidos += falhas[0]
                ambiguos += falhas[1]
                continue
            textos.append(_texto(trecho, grupo, resolucoes, tabela, escala))
    return LeituraGlifos(tuple(textos), desconhecidos + len(venenos), ambiguos, limitada=False)
