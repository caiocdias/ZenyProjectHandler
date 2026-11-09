"""Gramática do disco com marca (`disc_mark`) sobre a página do modelo de desenho.

A semente é o disco vermelho de `_disco_de_curva` (R-E06.3.5-3): todos os discos reais de
equipamento de interrupção são de curva, e o caminho de faixas de `discos_candidatos` sairia
quadrático com o teto de 72 pt. A caixa é o disco (R-E06.3.5-4); o conteúdo, pintado depois dele
e dentro da elipse, só confirma a variante e entra em `componentes`:

* `fuse_curve`: duas polilinhas pretas abertas, de 10 ou mais segmentos, e dois pontos pretos
  preenchidos;
* `double_box`: um retângulo preto de 4 retas (girado ou não), uma reta preta paralela ao lado
  longo dele, do lado de fora, e os dois pontos.

Cada peça conta por posição, não por caminho: o Ghostscript escreve o conteúdo em preenchimento e
traço. O vermelho é por `cor_canonica`, e o disco sem esse conteúdo (poste,
aterramento, ponto) não casa. `_coberto_depois` e `_palavra_sobre_o_disco` valem como no
`terminal_disc`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, TypeVar

from zeny_project_handler.adapters.analysis.drawing_model.grammar_disc import (
    Disco,
    _centro,
    _coberto_depois,
    _disco_de_curva,
    _palavra_sobre_o_disco,
)
from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import cor_canonica
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caixa,
    Caminho,
    ItemCaminho,
    PaginaModelo,
    Ponto,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    ContextoGramatica,
    OrcamentoConsultas,
)

# O teto do schema: `max_span` da variante filtra depois (R-E06.3.5-3).
_VAO_MAXIMO_CANDIDATO: Final = 72.0
_VERMELHO: Final = "#FF0000"
_PRETO: Final = "#000000"
_ITENS_DO_DISCO: Final = (4, 5)

_TOLERANCIA_ELIPSE: Final = 1.05
_MESMA_POSICAO: Final = 0.1
_MESMO_DISCO: Final = 0.15
# Célula única, que cabe a maior tolerância: com uma célula por vão, discos de vãos próximos
# cairiam em células distantes longe da origem.
_CELULA_DO_DISCO: Final = _MESMO_DISCO * _VAO_MAXIMO_CANDIDATO
_MINIMO_SEGMENTOS_CURVA: Final = 10
_MINIMO_LADOS_PONTO: Final = 6
_VAO_MAXIMO_PONTO: Final = 0.2
_FRACAO_FECHADO: Final = 0.25
_PONTOS_DO_DISCO: Final = 2
_CURVAS_DO_FUSIVEL: Final = 2
_LADOS_DO_RETANGULO: Final = 4
_FOLGA_ENCADEADO: Final = 0.05
_PERPENDICULAR_MAXIMO: Final = 0.08
_PARALELA_MINIMO: Final = math.cos(math.radians(8))
_RAZAO_COMPRIMENTO_RETA: Final = (0.75, 1.3)
_AFASTAMENTO_DA_RETA: Final = (0.5, 1.25)


@dataclass(frozen=True, slots=True)
class CandidatoDiscMark:
    """Disco lido uma vez por página; as variantes só filtram esta classificação."""

    contexto: ContextoGramatica
    caixa: Caixa
    caminho_ancora: int
    componentes: tuple[int, ...]
    content: str


@dataclass(frozen=True, slots=True)
class _Peca:
    """Um desenho preto dentro do disco: o caminho dele e o centro da caixa."""

    caminho: int
    posicao: Ponto


@dataclass(frozen=True, slots=True)
class _Retangulo:
    caminho: int
    centro: Ponto
    longo: tuple[float, float]
    comprimento_longo: float
    comprimento_curto: float

    @property
    def posicao(self) -> tuple[float, ...]:
        """Centro e lados: retângulos concêntricos de tamanhos diferentes são dois desenhos."""
        return (*self.centro, self.comprimento_longo, self.comprimento_curto)


@dataclass(frozen=True, slots=True)
class _Reta:
    caminho: int
    a: Ponto
    b: Ponto

    @property
    def posicao(self) -> tuple[float, ...]:
        """Meio e comprimento: o mesmo traço escrito de novo cai no mesmo lugar."""
        return ((self.a[0] + self.b[0]) / 2, (self.a[1] + self.b[1]) / 2, math.dist(self.a, self.b))


_Posicionada = TypeVar("_Posicionada", _Peca, _Retangulo, _Reta)


@dataclass(slots=True)
class _Conteudo:
    curvas: list[_Peca]
    pontos: list[_Peca]
    retangulos: list[_Retangulo]
    retas: list[_Reta]


def _unitario(de: Ponto, para: Ponto) -> tuple[float, float] | None:
    dx, dy = para[0] - de[0], para[1] - de[1]
    norma = math.hypot(dx, dy)
    return None if norma <= 0 else (dx / norma, dy / norma)


def _disco_vermelho(contexto: ContextoGramatica, posicao: int, caminho: Caminho) -> Disco | None:
    if cor_canonica(caminho.estilo.preenchimento, None) != _VERMELHO:
        return None
    # Cada subcaminho é contado: o caminho hostil de muitos subcaminhos não sai de graça.
    contexto.orcamento.gastar(len(caminho.subcaminhos))
    itens = sum(len(subcaminho) for subcaminho in caminho.subcaminhos)
    if itens not in _ITENS_DO_DISCO:
        return None
    return _disco_de_curva(
        caminho, posicao, contexto.caixas_caminhos.get(posicao), vao_maximo=_VAO_MAXIMO_CANDIDATO
    )


def _discos_vermelhos(contexto: ContextoGramatica) -> list[Disco]:
    caminhos = contexto.pagina.modelo.caminhos
    contexto.orcamento.gastar(len(caminhos))
    discos = (_disco_vermelho(contexto, i, caminho) for i, caminho in enumerate(caminhos))
    return [disco for disco in discos if disco is not None]


def _dentro_da_elipse(disco: Disco, pontos: Iterable[Ponto]) -> bool:
    cx, cy = _centro(disco.caixa)
    semi_x = (disco.caixa[2] - disco.caixa[0]) / 2
    semi_y = (disco.caixa[3] - disco.caixa[1]) / 2
    return all(
        math.hypot((x - cx) / semi_x, (y - cy) / semi_y) <= _TOLERANCIA_ELIPSE for x, y in pontos
    )


def _preto(caminho: Caminho) -> bool:
    return cor_canonica(caminho.estilo.cor, caminho.estilo.preenchimento) == _PRETO


def _preenchido_de_preto(caminho: Caminho) -> bool:
    return cor_canonica(caminho.estilo.preenchimento, None) == _PRETO


def _caixa_dos_itens(itens: Sequence[ItemCaminho]) -> Caixa:
    xs = [p[0] for item in itens for p in item.pontos]
    ys = [p[1] for item in itens for p in item.pontos]
    return (min(xs), min(ys), max(xs), max(ys))


def _encadeados(itens: Sequence[ItemCaminho], folga: float) -> bool:
    return all(
        math.dist(a.pontos[-1], b.pontos[0]) <= folga
        for a, b in zip(itens, (*itens[1:], itens[0]), strict=True)
    )


def _retangulo(posicao: int, itens: Sequence[ItemCaminho], caixa: Caixa) -> _Retangulo | None:
    """Quatro retas encadeadas e fechadas, com os lados consecutivos perpendiculares."""
    folga = _FOLGA_ENCADEADO * max(caixa[2] - caixa[0], caixa[3] - caixa[1])
    if len(itens) != _LADOS_DO_RETANGULO or not _encadeados(itens, folga):
        return None
    direcoes = [d for item in itens if (d := _unitario(item.pontos[0], item.pontos[-1]))]
    if len(direcoes) != _LADOS_DO_RETANGULO or any(
        abs(a[0] * b[0] + a[1] * b[1]) > _PERPENDICULAR_MAXIMO
        for a, b in zip(direcoes, (*direcoes[1:], direcoes[0]), strict=True)
    ):
        return None
    comprimentos = [math.dist(item.pontos[0], item.pontos[-1]) for item in itens]
    longo = 0 if comprimentos[0] >= comprimentos[1] else 1
    return _Retangulo(
        posicao,
        _centro(caixa),
        direcoes[longo],
        comprimentos[longo],
        comprimentos[1 - longo],
    )


def _uma_por_posicao(
    pecas: Sequence[_Posicionada], tolerancia: float, orcamento: OrcamentoConsultas
) -> list[_Posicionada]:
    """As peças distintas por posição: preenchimento e traço do mesmo desenho contam uma vez."""
    unicas: list[_Posicionada] = []
    for peca in pecas:
        orcamento.gastar(1 + len(unicas))
        if all(math.dist(peca.posicao, outra.posicao) > tolerancia for outra in unicas):
            unicas.append(peca)
    return unicas


def _reta_da_caixa_dupla(retangulo: _Retangulo, reta: _Reta) -> bool:
    a, b = reta.a, reta.b
    direcao = _unitario(a, b)
    if (
        direcao is None
        or abs(direcao[0] * retangulo.longo[0] + direcao[1] * retangulo.longo[1]) < _PARALELA_MINIMO
    ):
        return False
    razao = math.dist(a, b) / retangulo.comprimento_longo
    if not _RAZAO_COMPRIMENTO_RETA[0] <= razao <= _RAZAO_COMPRIMENTO_RETA[1]:
        return False
    normal = (-retangulo.longo[1], retangulo.longo[0])
    meio = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    afastamento = abs(
        (meio[0] - retangulo.centro[0]) * normal[0] + (meio[1] - retangulo.centro[1]) * normal[1]
    )
    relativo = afastamento / retangulo.comprimento_curto
    return _AFASTAMENTO_DA_RETA[0] < relativo <= _AFASTAMENTO_DA_RETA[1]


def _classificar_peca(
    modelo: PaginaModelo, posicao: int, disco: Disco, conteudo: _Conteudo
) -> None:
    caminho = modelo.caminhos[posicao]
    if len(caminho.subcaminhos) != 1:
        return
    itens = caminho.subcaminhos[0]
    if any(item.tipo != "l" for item in itens):
        return
    if not _dentro_da_elipse(disco, (p for item in itens for p in item.pontos)):
        return
    caixa = _caixa_dos_itens(itens)
    vao_disco = max(disco.caixa[2] - disco.caixa[0], disco.caixa[3] - disco.caixa[1])
    fechado = math.dist(itens[0].pontos[0], itens[-1].pontos[-1]) <= _FRACAO_FECHADO * max(
        caixa[2] - caixa[0], caixa[3] - caixa[1]
    )
    if (
        fechado
        and len(itens) >= _MINIMO_LADOS_PONTO
        and _preenchido_de_preto(caminho)
        and max(caixa[2] - caixa[0], caixa[3] - caixa[1]) <= _VAO_MAXIMO_PONTO * vao_disco
    ):
        conteudo.pontos.append(_Peca(posicao, _centro(caixa)))
    elif not fechado and len(itens) >= _MINIMO_SEGMENTOS_CURVA:
        conteudo.curvas.append(_Peca(posicao, _centro(caixa)))
    elif fechado and len(itens) == _LADOS_DO_RETANGULO:
        retangulo = _retangulo(posicao, itens, caixa)
        if retangulo is not None:
            conteudo.retangulos.append(retangulo)
    elif len(itens) == 1:
        conteudo.retas.append(_Reta(posicao, itens[0].pontos[0], itens[0].pontos[-1]))


def _conteudo_do_disco(contexto: ContextoGramatica, disco: Disco) -> _Conteudo:
    pagina = contexto.pagina
    modelo = pagina.modelo
    conteudo = _Conteudo([], [], [], [])
    ultimo_membro = max(disco.membros)
    for posicao in contexto.grade_caminhos.consultar(disco.caixa):
        caminho = modelo.caminhos[posicao]
        if (
            posicao <= ultimo_membro
            or posicao in pagina.glifos_lidos
            or posicao in pagina.translucidos
            or not _preto(caminho)
        ):
            continue
        contexto.orcamento.gastar(sum(len(subcaminho) for subcaminho in caminho.subcaminhos))
        _classificar_peca(modelo, posicao, disco, conteudo)
    return conteudo


def _marca_do_disco(
    conteudo: _Conteudo, vao: float, orcamento: OrcamentoConsultas
) -> tuple[str, tuple[int, ...]] | None:
    """O tipo do conteúdo e os caminhos dele, ou None sem o desenho completo."""
    tolerancia = _MESMA_POSICAO * vao
    if len(_uma_por_posicao(conteudo.pontos, tolerancia, orcamento)) != _PONTOS_DO_DISCO:
        return None
    caminhos_pontos = tuple(ponto.caminho for ponto in conteudo.pontos)
    curvas = _uma_por_posicao(conteudo.curvas, tolerancia, orcamento)
    if len(curvas) == _CURVAS_DO_FUSIVEL:
        return "fuse_curve", (*caminhos_pontos, *(curva.caminho for curva in conteudo.curvas))
    if curvas:
        return None
    retangulos = _uma_por_posicao(conteudo.retangulos, tolerancia, orcamento)
    if len(retangulos) != 1:
        return None
    orcamento.gastar(len(conteudo.retas))
    retas = [reta for reta in conteudo.retas if _reta_da_caixa_dupla(retangulos[0], reta)]
    if len(_uma_por_posicao(retas, tolerancia, orcamento)) != 1:
        return None
    caminhos_retangulos = (retangulo.caminho for retangulo in conteudo.retangulos)
    return "double_box", (*caminhos_pontos, *caminhos_retangulos, *(r.caminho for r in retas))


def _classificar(contexto: ContextoGramatica, disco: Disco) -> CandidatoDiscMark | None:
    vao = max(disco.caixa[2] - disco.caixa[0], disco.caixa[3] - disco.caixa[1])
    marca = _marca_do_disco(_conteudo_do_disco(contexto, disco), vao, contexto.orcamento)
    if marca is None:
        return None
    if _palavra_sobre_o_disco(contexto, disco.caixa) or _coberto_depois(contexto, disco):
        return None
    content, caminhos = marca
    return CandidatoDiscMark(
        contexto, disco.caixa, disco.caminho, tuple(sorted(set(caminhos))), content
    )


def _deduplicar(
    candidatos: Sequence[CandidatoDiscMark], orcamento: OrcamentoConsultas
) -> tuple[CandidatoDiscMark, ...]:
    """Um por disco visual: redesenhos com o centro próximo ficam com o mais antigo."""
    escolhidos: list[CandidatoDiscMark] = []
    por_celula: dict[tuple[int, int], list[int]] = {}
    for candidato in candidatos:
        caixa = candidato.caixa
        tolerancia = _MESMO_DISCO * max(caixa[2] - caixa[0], caixa[3] - caixa[1])
        centro = _centro(caixa)
        cx = math.floor(centro[0] / _CELULA_DO_DISCO)
        cy = math.floor(centro[1] / _CELULA_DO_DISCO)
        vizinhos = [
            i
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for i in por_celula.get((cx + dx, cy + dy), ())
        ]
        orcamento.gastar(1 + len(vizinhos))
        if any(math.dist(_centro(escolhidos[i].caixa), centro) <= tolerancia for i in vizinhos):
            continue
        por_celula.setdefault((cx, cy), []).append(len(escolhidos))
        escolhidos.append(candidato)
    return tuple(escolhidos)


def disc_mark_candidatos(contexto: ContextoGramatica) -> tuple[CandidatoDiscMark, ...]:
    """Os discos vermelhos com conteúdo confirmado, classificados uma vez por página."""
    achados: list[CandidatoDiscMark] = []
    for disco in _discos_vermelhos(contexto):
        contexto.orcamento.gastar()
        candidato = _classificar(contexto, disco)
        if candidato is not None:
            achados.append(candidato)
    return _deduplicar(achados, contexto.orcamento)


def casa_disc_mark(
    contexto: ContextoGramatica,
    gramatica: Mapping[str, Any],
    *,
    candidatos: tuple[CandidatoDiscMark, ...],
) -> list[tuple[Caixa, int, tuple[int, ...]]]:
    """(caixa do disco, caminho do disco, caminhos do conteúdo) dos candidatos desta variante.

    Só filtra a classificação pronta: não gasta do orçamento.
    """
    if any(candidato.contexto is not contexto for candidato in candidatos):
        raise ValueError("Candidato de disco com marca de outro contexto de gramáticas.")
    achados: list[tuple[Caixa, int, tuple[int, ...]]] = []
    for candidato in candidatos:
        caixa = candidato.caixa
        vao = max(caixa[2] - caixa[0], caixa[3] - caixa[1])
        if (
            candidato.content == gramatica["content"]
            and gramatica["min_span"] <= vao <= gramatica["max_span"]
        ):
            achados.append((caixa, candidato.caminho_ancora, candidato.componentes))
    return achados
