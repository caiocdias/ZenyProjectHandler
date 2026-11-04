"""Leitura de texto desenhado como contorno preenchido de glifo, contra a tabela versionada.

Candidatos a glifo consecutivos na ordem de desenho, com a mesma cor e vizinhos, formam um
trecho. O quadro do trecho põe o texto na horizontal para calcular a assinatura de cada glifo:
o ângulo parte da reta de mínimos quadrados dos centros, orientada do primeiro para o último
glifo, e é refinado pela mediana das inclinações entre os fundos dos glifos (Theil-Sen), porque
glifos fora do centro ("=", "-", "(") inclinam a reta dos centros e a assinatura, que mede a
posição em relação à linha de base, deriva ao longo da linha; altura e linha de base saem das
medianas. Num trecho de 2 glifos com fundos diferentes o quadro continua torto. Glifo
desconhecido ou ambíguo anula o texto em que cairia; nunca sai um texto com caractere faltando.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median
from typing import Final

from zeny_project_handler.adapters.analysis.drawing_model.glyph_signature import (
    AssinaturaGlifo,
    achatar_subcaminho,
    assinatura_glifo,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    Resolucao,
    TabelaGlifos,
    resolver_glifo,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa, Caminho, Cor, Ponto

LIMITE_GLIFOS_PAGINA: Final = 20_000
LADO_MAXIMO_GLIFO: Final = 7.0
_LADO_MINIMO_GLIFO: Final = 0.05
_MAXIMO_SUBCAMINHOS: Final = 8
_MAXIMO_ITENS: Final = 256
_FATOR_VIZINHANCA: Final = 1.6
_MINIMO_GLIFOS_TRECHO: Final = 2
_MAXIMO_GLIFOS_TRECHO: Final = 64
_CASAS_MEMORIA: Final = 3
_TIPOS_PREENCHIDOS: Final = frozenset({"preenchimento", "traco_e_preenchimento"})

_ChaveAssinatura = tuple[int, tuple[float, ...], tuple[tuple[float, ...], ...]]


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
    poligonos: tuple[tuple[Ponto, ...], ...]
    caixa: Caixa
    cor: Cor | None


@dataclass(frozen=True, slots=True)
class _Trecho:
    publico: TrechoGlifos
    angulo: float
    caixas_quadro: tuple[Caixa, ...]


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
    pontos = [ponto for item in itens for ponto in item.pontos]
    if not all(math.isfinite(x) and math.isfinite(y) for x, y in pontos):
        return False
    x0, y0, x1, y1 = _caixa_de(pontos)
    return _LADO_MINIMO_GLIFO < max(x1 - x0, y1 - y0) < LADO_MAXIMO_GLIFO


def _candidato(indice: int, caminho: Caminho) -> _Candidato:
    poligonos = tuple(achatar_subcaminho(subcaminho) for subcaminho in caminho.subcaminhos)
    caixa = _caixa_de([ponto for poligono in poligonos for ponto in poligono])
    return _Candidato(indice, poligonos, caixa, caminho.estilo.preenchimento)


def _centro(caixa: Caixa) -> Ponto:
    return ((caixa[0] + caixa[2]) / 2.0, (caixa[1] + caixa[3]) / 2.0)


def _maior_lado(caixa: Caixa) -> float:
    return max(caixa[2] - caixa[0], caixa[3] - caixa[1])


def _vizinhos(anterior: _Candidato, atual: _Candidato) -> bool:
    if atual.indice != anterior.indice + 1 or atual.cor != anterior.cor:
        return False
    alcance = _FATOR_VIZINHANCA * max(_maior_lado(anterior.caixa), _maior_lado(atual.caixa))
    return math.dist(_centro(anterior.caixa), _centro(atual.caixa)) <= alcance


def _agrupar(candidatos: Sequence[_Candidato]) -> list[list[_Candidato]]:
    grupos: list[list[_Candidato]] = []
    atual: list[_Candidato] = []
    for candidato in candidatos:
        if atual and not _vizinhos(atual[-1], candidato):
            grupos.append(atual)
            atual = []
        atual.append(candidato)
    if atual:
        grupos.append(atual)
    return [g for g in grupos if _MINIMO_GLIFOS_TRECHO <= len(g) <= _MAXIMO_GLIFOS_TRECHO]


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


def _para_quadro(ponto: Ponto, angulo: float) -> Ponto:
    c, s = math.cos(angulo), math.sin(angulo)
    return (ponto[0] * c + ponto[1] * s, -ponto[0] * s + ponto[1] * c)


def _para_pagina(ponto: Ponto, angulo: float) -> Ponto:
    c, s = math.cos(angulo), math.sin(angulo)
    return (ponto[0] * c - ponto[1] * s, ponto[0] * s + ponto[1] * c)


def _refinar_pelos_fundos(grupo: Sequence[_Candidato], angulo: float) -> float:
    """Corrige o ângulo provisório pela mediana das inclinações par a par dos fundos dos glifos
    no quadro provisório (Theil-Sen): fundos fora da linha de base ("-", "=", descendentes)
    são minoria e não puxam a mediana, como puxariam a reta dos centros."""
    fundos: list[Ponto] = []
    for candidato in grupo:
        pontos = [_para_quadro(p, angulo) for poligono in candidato.poligonos for p in poligono]
        x0, _, x1, y1 = _caixa_de(pontos)
        fundos.append(((x0 + x1) / 2.0, y1))
    inclinacoes = [
        (b[1] - a[1]) / (b[0] - a[0])
        for i, a in enumerate(fundos)
        for b in fundos[i + 1 :]
        if abs(b[0] - a[0]) > 1e-9
    ]
    if not inclinacoes:
        return angulo
    return angulo + math.atan(float(median(inclinacoes)))


def _trecho(grupo: Sequence[_Candidato]) -> _Trecho:
    angulo = _refinar_pelos_fundos(grupo, _angulo([_centro(c.caixa) for c in grupo]))
    no_quadro = [
        [[_para_quadro(p, angulo) for p in poligono] for poligono in c.poligonos] for c in grupo
    ]
    caixas = tuple(_caixa_de([p for poligono in pol for p in poligono]) for pol in no_quadro)
    altura = float(median(caixa[3] - caixa[1] for caixa in caixas))
    base = float(median(caixa[3] for caixa in caixas))
    glifos = tuple(
        GlifoDoTrecho(
            c.indice, c.caixa, assinatura_glifo(pol, altura_linha=altura, base_linha=base)
        )
        for c, pol in zip(grupo, no_quadro, strict=True)
    )
    rotacao = round(math.degrees(angulo), 6) % 360.0
    return _Trecho(TrechoGlifos(glifos, rotacao, altura, grupo[0].cor), angulo, caixas)


def _indices_candidatos(caminhos: Sequence[Caminho]) -> list[int]:
    return [indice for indice, caminho in enumerate(caminhos) if _eh_candidato(caminho)]


def _trechos(caminhos: Sequence[Caminho], indices: Sequence[int]) -> list[_Trecho]:
    candidatos = [_candidato(indice, caminhos[indice]) for indice in indices]
    return [_trecho(grupo) for grupo in _agrupar(candidatos)]


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


def _resolver(
    tabela: TabelaGlifos,
    assinatura: AssinaturaGlifo | None,
    memoria: dict[_ChaveAssinatura, Resolucao],
) -> Resolucao:
    if assinatura is None:
        return Resolucao("desconhecido", None, math.inf)
    chave = _chave(assinatura)
    resolucao = memoria.get(chave)
    if resolucao is None:
        resolucao = memoria[chave] = resolver_glifo(tabela, assinatura)
    return resolucao


def _lacuna(trecho: _Trecho, anterior: int, atual: int) -> float:
    return trecho.caixas_quadro[atual][0] - trecho.caixas_quadro[anterior][2]


def _grupos_de_texto(
    trecho: _Trecho, resolucoes: Sequence[Resolucao], tabela: TabelaGlifos
) -> list[list[int]]:
    """Índices dos glifos de cada texto: "ignorar" e lacuna acima de `quebra` dividem."""
    limite = tabela.quebra * trecho.publico.altura
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
) -> TextoGlifo:
    publico = trecho.publico
    espaco = tabela.espaco * publico.altura
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


def ler_texto_glifos(caminhos: Sequence[Caminho], tabela: TabelaGlifos) -> LeituraGlifos:
    indices = _indices_candidatos(caminhos)
    if len(indices) > LIMITE_GLIFOS_PAGINA:
        return LeituraGlifos((), 0, 0, limitada=True)
    memoria: dict[_ChaveAssinatura, Resolucao] = {}
    textos: list[TextoGlifo] = []
    desconhecidos = ambiguos = 0
    for trecho in _trechos(caminhos, indices):
        resolucoes = [_resolver(tabela, g.assinatura, memoria) for g in trecho.publico.glifos]
        for grupo in _grupos_de_texto(trecho, resolucoes, tabela):
            situacoes = [resolucoes[i].situacao for i in grupo]
            falhas = (situacoes.count("desconhecido"), situacoes.count("ambiguo"))
            if any(falhas):
                desconhecidos += falhas[0]
                ambiguos += falhas[1]
                continue
            textos.append(_texto(trecho, grupo, resolucoes, tabela))
    return LeituraGlifos(tuple(textos), desconhecidos, ambiguos, limitada=False)
