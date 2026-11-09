"""Gramática do disco terminal sobre a página do modelo de desenho.

Porte puro do `terminal_disc` de `declarative_symbols`, com os mesmos limiares. A linha terminal
vem das pontas das polilinhas abertas (R-E06.2.1-6), e a altura das faixas é a do espaço visual
(R-E06.2.1-7).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from itertools import chain
from typing import Any, Final

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
    _TOLERANCIA_ALINHAMENTO,
    ContextoGramatica,
    GradeEspacial,
    OrcamentoConsultas,
    Segmento,
    _caixa_de_pontos,
    _encadeados,
    _lados_alternam_eixos,
    _moldura_do_subcaminho,
    _segmentos_do_subcaminho,
    contem,
    ponto_em,
    sobrepoe,
)

_ROXO_MINIMO: Final = 0.2
_ROXO_FRACAO_VERDE: Final = 0.8
_ROXO_MAXIMO: Final = 0.6

_VAO_MAXIMO_DISCO: Final = 8.0
_ASPECTO_MINIMO: Final = 0.8
_ASPECTO_MAXIMO: Final = 1.25
_CURVAS_DO_DISCO: Final = 4
_LINHAS_DE_FECHO_MAXIMAS: Final = 1
_FRACAO_LINHA_DE_FECHO: Final = 0.25
_TOLERANCIA_ELIPSE: Final = 0.12

_LADOS_DO_RETANGULO: Final = 4
_ITENS_MINIMOS_POLIGONO: Final = 3
_ALTURA_MAXIMA_FAIXA: Final = 0.6
_FAIXAS_MINIMAS: Final = 5
_FOLGA_VERTICAL_FAIXAS: Final = 0.15
_FRACAO_CONTINUACAO: Final = 0.5
_FRACAO_DESVIO_CENTRO: Final = 0.15
_FRACAO_DESVIO_CORDA: Final = 0.25
_CASAS_DE_ARREDONDAMENTO: Final = 3

_PERTO_MINIMO: Final = 0.6
_FRACAO_PERTO: Final = 0.35
_FRACAO_LONGE: Final = 2.0
_COR_QUASE_BRANCA: Final = 0.9
_FOLGA_COBERTURA: Final = 0.01

_Faixa = tuple[Caixa, int]


@dataclass(frozen=True, slots=True)
class Disco:
    """`caminho` e `membros` são posições em `modelo.caminhos`; `caminho = min(membros)`."""

    caixa: Caixa
    caminho: int
    membros: frozenset[int]
    preenchimento: Cor


def _eh_roxo(cor: Cor) -> bool:
    """Roxo escuro: vermelho e azul dominam o verde; lilás claro e violeta ficam de fora."""
    vermelho, verde, azul = cor
    return (
        vermelho > _ROXO_MINIMO
        and azul > _ROXO_MINIMO
        and verde < _ROXO_FRACAO_VERDE * min(vermelho, azul)
        and max(cor) <= _ROXO_MAXIMO
    )


_PREENCHIMENTOS: Final[Mapping[str, Callable[[Cor], bool]]] = {"purple": _eh_roxo}


def _centro(caixa: Caixa) -> Ponto:
    return ((caixa[0] + caixa[2]) / 2, (caixa[1] + caixa[3]) / 2)


def _largura(caixa: Caixa) -> float:
    return caixa[2] - caixa[0]


def _altura(caixa: Caixa) -> float:
    return caixa[3] - caixa[1]


def _aspecto_redondo(caixa: Caixa, vao_maximo: float) -> bool:
    largura, altura = _largura(caixa), _altura(caixa)
    # Pela metade: a de um lado subnormal arredonda a 0, e quem vem depois divide por ela.
    if largura / 2 <= 0 or altura / 2 <= 0:
        return False
    return (
        _ASPECTO_MINIMO <= largura / altura <= _ASPECTO_MAXIMO
        and max(largura, altura) <= vao_maximo
    )


# --- disco de curva -----------------------------------------------------------------------


def _pontas_na_elipse(curvas: Sequence[ItemCaminho], caixa: Caixa) -> bool:
    centro_x, centro_y = _centro(caixa)
    semi_x, semi_y = _largura(caixa) / 2, _altura(caixa) / 2
    return all(
        abs(math.hypot((x - centro_x) / semi_x, (y - centro_y) / semi_y) - 1) <= _TOLERANCIA_ELIPSE
        for curva in curvas
        for x, y in (curva.pontos[0], curva.pontos[-1])
    )


def _disco_de_curva(
    caminho: Caminho, posicao: int, caixa: Caixa | None, vao_maximo: float
) -> Disco | None:
    """Um caminho preenchido de 4 curvas, fechado no máximo por uma linha curta."""
    preenchimento = caminho.estilo.preenchimento
    if preenchimento is None or caixa is None:
        return None
    itens = [item for subcaminho in caminho.subcaminhos for item in subcaminho]
    curvas = [item for item in itens if item.tipo == "c"]
    linhas = [item for item in itens if item.tipo == "l"]
    if len(curvas) != _CURVAS_DO_DISCO or len(linhas) > _LINHAS_DE_FECHO_MAXIMAS:
        return None
    if not _aspecto_redondo(caixa, vao_maximo) or not _pontas_na_elipse(curvas, caixa):
        return None
    limite = min(_largura(caixa), _altura(caixa)) * _FRACAO_LINHA_DE_FECHO
    if any(math.dist(linha.pontos[0], linha.pontos[1]) > limite for linha in linhas):
        return None
    return Disco(caixa, posicao, frozenset({posicao}), preenchimento)


# --- disco em faixas ----------------------------------------------------------------------


def _caixa_do_retangulo(subcaminho: Sequence[ItemCaminho]) -> Caixa | None:
    """A caixa do subcaminho que for um retângulo de 4 `l` alinhado aos eixos."""
    if len(subcaminho) != _LADOS_DO_RETANGULO:
        return None
    lados = [(item.pontos[0], item.pontos[1]) for item in subcaminho]
    if not _encadeados(lados, _TOLERANCIA_ALINHAMENTO) or not _lados_alternam_eixos(lados):
        return None
    return _caixa_de_pontos(ponto for lado in lados for ponto in lado)


def _caixas_de_faixa(caminho: Caminho, caixa: Caixa | None, vao_maximo: float) -> list[Caixa]:
    """Faixas finas de um caminho só de `l`: uma por retângulo (o `re` e o `qu` do motor), ou
    uma pela caixa de um polígono ou faixa teselada em triângulos."""
    itens = [item for subcaminho in caminho.subcaminhos for item in subcaminho]
    if any(item.tipo != "l" for item in itens):
        return []
    retangulos = [_caixa_do_retangulo(subcaminho) for subcaminho in caminho.subcaminhos]
    caixas: list[Caixa | None]
    if all(retangulos):
        caixas = retangulos
    else:
        caixas = [caixa] if len(itens) >= _ITENS_MINIMOS_POLIGONO else []
    return [
        faixa
        for faixa in caixas
        if faixa is not None
        and 0 < _altura(faixa) <= _ALTURA_MAXIMA_FAIXA
        and 0 < _largura(faixa) <= vao_maximo
    ]


def _perfil_de_disco(pilha: Sequence[_Faixa], uniao: Caixa) -> bool:
    """Cada faixa está centrada e tem mais ou menos a largura da corda do disco na sua altura."""
    centro_x, centro_y = _centro(uniao)
    largura = _largura(uniao)
    for faixa, _ in pilha:
        faixa_x, faixa_y = _centro(faixa)
        if abs(faixa_x - centro_x) > largura * _FRACAO_DESVIO_CENTRO:
            return False
        desvio = (faixa_y - centro_y) / (_altura(uniao) / 2)
        corda = largura * math.sqrt(max(0.0, 1 - desvio * desvio))
        if abs(_largura(faixa) - corda) > largura * _FRACAO_DESVIO_CORDA:
            return False
    return True


def _disco_da_pilha(pilha: Sequence[_Faixa], preenchimento: Cor, vao_maximo: float) -> Disco | None:
    if len(pilha) < _FAIXAS_MINIMAS:
        return None
    uniao: Caixa = (
        min(faixa[0] for faixa, _ in pilha),
        min(faixa[1] for faixa, _ in pilha),
        max(faixa[2] for faixa, _ in pilha),
        max(faixa[3] for faixa, _ in pilha),
    )
    if not _aspecto_redondo(uniao, vao_maximo) or not _perfil_de_disco(pilha, uniao):
        return None
    membros = frozenset(posicao for _, posicao in pilha)
    return Disco(uniao, min(membros), membros, preenchimento)


def _continua(pilha: Sequence[_Faixa], caixa: Caixa) -> bool:
    ultima = pilha[-1][0]
    desvio = abs(_centro(caixa)[0] - _centro(ultima)[0])
    return (
        abs(caixa[1] - ultima[3]) <= _FOLGA_VERTICAL_FAIXAS
        and desvio <= max(_largura(ultima), _largura(caixa)) * _FRACAO_CONTINUACAO
    )


def _pilhas_de_faixas(
    faixas: Iterable[_Faixa], orcamento: OrcamentoConsultas
) -> Iterator[list[_Faixa]]:
    """Empilha faixas de uma cor, sem buraco na vertical; cada pilha aberta visitada gasta 1."""
    abertas: list[list[_Faixa]] = []
    for caixa, posicao in sorted(faixas, key=lambda faixa: (faixa[0][1], faixa[0][0])):
        seguem: list[list[_Faixa]] = []
        alvo: list[_Faixa] | None = None
        for pilha in abertas:
            orcamento.gastar()
            if pilha[-1][0][3] < caixa[1] - _FOLGA_VERTICAL_FAIXAS:
                yield pilha
                continue
            seguem.append(pilha)
            if alvo is None and _continua(pilha, caixa):
                alvo = pilha
        abertas = seguem
        if alvo is None:
            abertas.append([(caixa, posicao)])
        else:
            alvo.append((caixa, posicao))
    yield from abertas


def _discos_de_faixas(contexto: ContextoGramatica, vao_maximo: float) -> list[Disco]:
    faixas_por_cor: dict[Cor, list[_Faixa]] = {}
    for posicao, caminho in enumerate(contexto.pagina.modelo.caminhos):
        cor = caminho.estilo.preenchimento
        if cor is None:
            continue
        chave: Cor = (
            round(cor[0], _CASAS_DE_ARREDONDAMENTO),
            round(cor[1], _CASAS_DE_ARREDONDAMENTO),
            round(cor[2], _CASAS_DE_ARREDONDAMENTO),
        )
        faixas = _caixas_de_faixa(caminho, contexto.caixas_caminhos.get(posicao), vao_maximo)
        faixas_por_cor.setdefault(chave, []).extend((faixa, posicao) for faixa in faixas)
    discos: list[Disco] = []
    for cor, faixas_da_cor in faixas_por_cor.items():
        for pilha in _pilhas_de_faixas(faixas_da_cor, contexto.orcamento):
            disco = _disco_da_pilha(pilha, cor, vao_maximo)
            if disco is not None:
                discos.append(disco)
    return discos


def _caixa_arredondada(caixa: Caixa) -> Caixa:
    return (
        round(caixa[0], _CASAS_DE_ARREDONDAMENTO),
        round(caixa[1], _CASAS_DE_ARREDONDAMENTO),
        round(caixa[2], _CASAS_DE_ARREDONDAMENTO),
        round(caixa[3], _CASAS_DE_ARREDONDAMENTO),
    )


def discos_candidatos(
    contexto: ContextoGramatica, *, vao_maximo: float = _VAO_MAXIMO_DISCO
) -> tuple[Disco, ...]:
    """Discos de curva e discos em faixas, um por caixa arredondada, de vão até `vao_maximo`."""
    caixas = contexto.caixas_caminhos
    de_curva = (
        _disco_de_curva(caminho, posicao, caixas.get(posicao), vao_maximo)
        for posicao, caminho in enumerate(contexto.pagina.modelo.caminhos)
    )
    achados: dict[Caixa, Disco] = {}
    for disco in chain(filter(None, de_curva), _discos_de_faixas(contexto, vao_maximo)):
        achados.setdefault(_caixa_arredondada(disco.caixa), disco)
    return tuple(achados.values())


# --- linha terminal -----------------------------------------------------------------------


def _cor_visivel(cor: Cor | None) -> bool:
    return cor is not None and min(cor) < _COR_QUASE_BRANCA


def _pontas_de_polilinhas(modelo: PaginaModelo) -> Iterator[Segmento]:
    """R-E06.2.1-6: de uma linha de traço puro, só as pontas da polilinha aberta terminam."""
    for primitiva in modelo.primitivas:
        if (
            isinstance(primitiva, Polilinha)
            and not primitiva.fechada
            and len(primitiva.pontos) >= 2
            and primitiva.origens
            and _cor_visivel(primitiva.estilo.cor)
            and _caixa_de_pontos((primitiva.pontos[0], primitiva.pontos[-1])) is not None
        ):
            yield Segmento(primitiva.pontos[0], primitiva.pontos[-1], primitiva.origens[0])


def _segmentos_com_traco_e_preenchimento(modelo: PaginaModelo) -> Iterator[Segmento]:
    """Os mesmos segmentos do contexto: subcaminho que vira moldura fechada não dá segmento."""
    pagina: Caixa = (0.0, 0.0, modelo.largura, modelo.altura)
    for posicao, caminho in enumerate(modelo.caminhos):
        if caminho.tipo != "traco_e_preenchimento" or not _cor_visivel(caminho.estilo.cor):
            continue
        for subcaminho in caminho.subcaminhos:
            if _moldura_do_subcaminho(subcaminho, posicao, pagina) is None:
                yield from _segmentos_do_subcaminho(subcaminho, posicao)


def _entradas_por_ponta(linhas: Iterable[Segmento]) -> Iterator[tuple[Caixa, Segmento]]:
    for linha in linhas:
        yield ((*linha.a, *linha.a), linha)
        yield ((*linha.b, *linha.b), Segmento(linha.b, linha.a, linha.caminho))


def pontas_terminais(contexto: ContextoGramatica) -> GradeEspacial[Segmento]:
    """Cada linha candidata, uma entrada por ponta: `a` é a ponta indexada e `b`, a outra.

    Cada ponta indexada gasta 1 do orçamento; construa uma vez por página.
    """
    modelo = contexto.pagina.modelo
    linhas = (*_pontas_de_polilinhas(modelo), *_segmentos_com_traco_e_preenchimento(modelo))
    limites: Caixa = (
        -_MARGEM_PAGINA,
        -_MARGEM_PAGINA,
        modelo.largura + _MARGEM_PAGINA,
        modelo.altura + _MARGEM_PAGINA,
    )
    return GradeEspacial(_entradas_por_ponta(linhas), limites, contexto.orcamento)


def _tem_linha_terminal(disco: Disco, vao: float, pontas: GradeEspacial[Segmento]) -> bool:
    """Uma linha vinda de longe termina no centro do disco, em vez de passar por ele."""
    centro = _centro(disco.caixa)
    perto, longe = max(_PERTO_MINIMO, _FRACAO_PERTO * vao), _FRACAO_LONGE * vao
    janela: Caixa = (centro[0] - perto, centro[1] - perto, centro[0] + perto, centro[1] + perto)
    return any(
        segmento.caminho not in disco.membros
        and math.dist(segmento.a, centro) <= perto
        and math.dist(segmento.b, centro) > longe
        for segmento in pontas.consultar(janela)
    )


# --- guardas ------------------------------------------------------------------------------


def _coberto_depois(contexto: ContextoGramatica, disco: Disco) -> bool:
    """Um preenchimento opaco posterior que contém o disco o esconde na página renderizada."""
    x0, y0, x1, y1 = disco.caixa
    interna: Caixa = (
        x0 + _FOLGA_COBERTURA,
        y0 + _FOLGA_COBERTURA,
        x1 - _FOLGA_COBERTURA,
        y1 - _FOLGA_COBERTURA,
    )
    ultimo_membro = max(disco.membros)
    pagina = contexto.pagina
    return any(
        posicao > ultimo_membro
        and pagina.modelo.caminhos[posicao].estilo.preenchimento is not None
        and posicao not in pagina.translucidos
        and contem(contexto.caixas_caminhos[posicao], interna)
        for posicao in contexto.grade_caminhos.consultar(disco.caixa)
    )


def _palavra_sobre_o_disco(contexto: ContextoGramatica, caixa: Caixa) -> bool:
    """`ponto_em` é fechado: diferente do motor, o centro exato na borda também recusa."""
    return any(
        ponto_em(caixa, _centro(palavra.caixa))
        or (palavra.inteira and sobrepoe(caixa, palavra.caixa))
        for palavra in contexto.grade_palavras.consultar(caixa)
    )


def casa_disco(
    contexto: ContextoGramatica,
    gramatica: Mapping[str, Any],
    disco: Disco,
    pontas: GradeEspacial[Segmento],
) -> bool:
    vao = max(_largura(disco.caixa), _altura(disco.caixa))
    if not gramatica["min_span"] <= vao <= gramatica["max_span"]:
        return False
    if not _PREENCHIMENTOS[gramatica["fill"]](disco.preenchimento):
        return False
    if _palavra_sobre_o_disco(contexto, disco.caixa):
        return False
    return _tem_linha_terminal(disco, vao, pontas) and not _coberto_depois(contexto, disco)
