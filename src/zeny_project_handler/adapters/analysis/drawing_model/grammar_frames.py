"""As 5 gramáticas de moldura sobre o núcleo, com os limiares do motor `declarative_symbols`.

Toda varredura sai de uma consulta à grade, que cobra o orçamento da página. O modelo já está no
espaço visual, e é nele que se julga a orientação do triângulo e da barra (R-E06.2.1-7).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Mapping
from typing import Any, Final

from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa, Cor, ItemCaminho
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    ContextoGramatica,
    Moldura,
    Palavra,
    contem,
    intersecta,
    ponto_em,
    sobrepoe,
)

_FORMAS: Final = {"rectangle": "retangulo", "ellipse": "elipse", "diamond": "losango"}
_FORMAS_REDONDAS: Final = frozenset({"elipse", "losango"})

_LADO_MINIMO: Final = 4.0
_ASPECTO_REDONDO_MINIMO: Final = 0.7
_ASPECTO_REDONDO_MAXIMO: Final = 1.43
_ASPECTO_DIAGONAIS_MINIMO: Final = 0.8
_ASPECTO_DIAGONAIS_MAXIMO: Final = 1.25
_ASPECTO_MAXIMO_PADRAO: Final = 2.5

_INSET_ROTULO: Final = 0.05

_RAZAO_INTERNA_MINIMA: Final = 0.65
_RAZAO_INTERNA_MAXIMA: Final = 0.98
_DESVIO_INTERNA: Final = 0.1
_CANAL_CINZA_MINIMO: Final = 0.15
_CANAL_CINZA_MAXIMO: Final = 0.9
_AMPLITUDE_CINZA: Final = 0.12

_AREA_MARCA: Final = 0.06
_VAO_LINHA_MARCA: Final = 0.55

_PONTAS_TRIANGULO: Final = 3
_CASAS_TRIANGULO: Final = 2
_COBERTURA_TRIANGULO: Final = 0.5
_DESVIO_TOPO_TRIANGULO: Final = 0.18
_DESVIO_BASE_TRIANGULO_X: Final = 0.15
_DESVIO_BASE_TRIANGULO_Y: Final = 0.15

_TOLERANCIA_MINIMA_DIAGONAL: Final = 1.5
_TOLERANCIA_RELATIVA_DIAGONAL: Final = 0.12

_RAZAO_BARRA_MINIMA: Final = 0.45
_RAZAO_BARRA_MAXIMA: Final = 0.85
_DESVIO_BARRA: Final = 0.16
_ALTURA_BARRA: Final = 0.12
_VAO_BARRA: Final = 0.6
_FOLGA_BARRA: Final = 1.0

_PONTOS_NO_LOSANGO: Final = 3
_RAZAO_PONTO_MINIMA: Final = 0.06
_RAZAO_PONTO_MAXIMA: Final = 0.3
_DISTANCIA_PONTO: Final = 0.85


def _lados(caixa: Caixa) -> tuple[float, float]:
    return caixa[2] - caixa[0], caixa[3] - caixa[1]


def _centro(caixa: Caixa) -> tuple[float, float]:
    return (caixa[0] + caixa[2]) / 2, (caixa[1] + caixa[3]) / 2


def _moldura_ok(moldura: Moldura, gramatica: Mapping[str, Any]) -> bool:
    if moldura.forma != _FORMAS.get(gramatica["frame"]):
        return False
    largura, altura = _lados(moldura.caixa)
    if max(largura, altura) > gramatica["max_span"] or min(largura, altura) < _LADO_MINIMO:
        return False
    aspecto = largura / altura
    if moldura.forma in _FORMAS_REDONDAS:
        return _ASPECTO_REDONDO_MINIMO <= aspecto <= _ASPECTO_REDONDO_MAXIMO
    if gramatica["kind"] == "framed_diagonals":
        return _ASPECTO_DIAGONAIS_MINIMO <= aspecto <= _ASPECTO_DIAGONAIS_MAXIMO
    maximo = gramatica.get("max_aspect", _ASPECTO_MAXIMO_PADRAO)
    return bool(1 / maximo <= aspecto <= maximo)


def _rotulo_na_moldura(contexto: ContextoGramatica, caixa: Caixa, rotulo: str) -> bool:
    """Palavra `inteira` traz a caixa do span: fora da caixa interna, falha fechado (R-4)."""
    inset = min(_lados(caixa)) * _INSET_ROTULO
    interna = (caixa[0] + inset, caixa[1] + inset, caixa[2] - inset, caixa[3] - inset)
    return any(
        palavra.texto == rotulo and contem(interna, palavra.caixa)
        for palavra in contexto.grade_palavras.consultar(interna)
    )


def _aninhada(externa: Caixa, interna: Caixa, minimo: float, maximo: float, desvio: float) -> bool:
    """Interna contida, em proporção com a externa e centrada nela."""
    largura, altura = _lados(externa)
    largura_interna, altura_interna = _lados(interna)
    return (
        contem(externa, interna)
        and minimo <= largura_interna / largura <= maximo
        and minimo <= altura_interna / altura <= maximo
        and abs(interna[0] + interna[2] - externa[0] - externa[2]) <= largura * desvio
        and abs(interna[1] + interna[3] - externa[1] - externa[3]) <= altura * desvio
    )


def _eh_cinza(cor: Cor | None) -> bool:
    return (
        cor is not None
        and all(_CANAL_CINZA_MINIMO <= canal <= _CANAL_CINZA_MAXIMO for canal in cor)
        and max(cor) - min(cor) <= _AMPLITUDE_CINZA
    )


def _moldura_interna_cinza(contexto: ContextoGramatica, externa: Moldura, rotulo: str) -> bool:
    caminhos = contexto.pagina.modelo.caminhos
    for interna in contexto.grade_molduras.consultar(externa.caixa):
        if (
            interna.forma == "retangulo"
            and interna.caminho != externa.caminho
            and _aninhada(
                externa.caixa,
                interna.caixa,
                _RAZAO_INTERNA_MINIMA,
                _RAZAO_INTERNA_MAXIMA,
                _DESVIO_INTERNA,
            )
            and _eh_cinza(caminhos[interna.caminho].estilo.preenchimento)
            and _rotulo_na_moldura(contexto, interna.caixa, rotulo)
        ):
            return True
    return False


def _itens_pagos(contexto: ContextoGramatica, posicao: int) -> Iterator[ItemCaminho]:
    """Itens do caminho, a 1 do orçamento cada: a grade só cobra o caminho, que pode ser denso."""
    for subcaminho in contexto.pagina.modelo.caminhos[posicao].subcaminhos:
        contexto.orcamento.gastar(1 + len(subcaminho))
        yield from subcaminho


def _linha_longa(contexto: ContextoGramatica, caixa: Caixa, posicao: int) -> bool:
    largura, altura = _lados(caixa)
    for item in _itens_pagos(contexto, posicao):
        if item.tipo != "l":
            continue
        (ax, ay), (bx, by) = item.pontos
        caixa_linha = (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))
        if (
            abs(ax - bx) >= largura * _VAO_LINHA_MARCA
            and abs(ay - by) >= altura * _VAO_LINHA_MARCA
            and intersecta(caixa, caixa_linha)
        ):
            return True
    return False


def _marca_de_proposta(contexto: ContextoGramatica, moldura: Moldura) -> bool:
    caixa = moldura.caixa
    largura, altura = _lados(caixa)
    area = largura * altura
    caminhos = contexto.pagina.modelo.caminhos
    for posicao in contexto.grade_caminhos.consultar(caixa):
        limites = contexto.caixas_caminhos[posicao]
        if posicao == moldura.caminho or not intersecta(caixa, limites):
            continue
        lado_x, lado_y = _lados(limites)
        if (
            caminhos[posicao].estilo.preenchimento is not None
            and contem(caixa, limites)
            and lado_x * lado_y >= area * _AREA_MARCA
        ):
            return True
        if _linha_longa(contexto, caixa, posicao):
            return True
    return False


def _triangulo_em_pe(contexto: ContextoGramatica, posicao: int, moldura: Caixa) -> bool:
    """Caminho de 1 subcaminho com 3 `l`, de ponta para cima, cobrindo a moldura."""
    subcaminhos = contexto.pagina.modelo.caminhos[posicao].subcaminhos
    if len(subcaminhos) != 1 or len(subcaminhos[0]) != _PONTAS_TRIANGULO:
        return False
    if any(item.tipo != "l" for item in subcaminhos[0]):
        return False
    limites = contexto.caixas_caminhos[posicao]
    largura, altura = _lados(limites)
    largura_moldura, altura_moldura = _lados(moldura)
    if not contem(moldura, limites):
        return False
    if (
        largura < largura_moldura * _COBERTURA_TRIANGULO
        or altura < altura_moldura * _COBERTURA_TRIANGULO
    ):
        return False
    pontas = {
        (round(x, _CASAS_TRIANGULO), round(y, _CASAS_TRIANGULO))
        for item in subcaminhos[0]
        for x, y in item.pontos
    }
    if len(pontas) != _PONTAS_TRIANGULO:
        return False
    topo = min(pontas, key=lambda ponta: ponta[1])
    esquerda, direita = sorted((p for p in pontas if p != topo), key=lambda ponta: ponta[0])
    return (
        abs(topo[0] - _centro(limites)[0]) <= largura * _DESVIO_TOPO_TRIANGULO
        and abs(esquerda[1] - direita[1]) <= altura * _DESVIO_BASE_TRIANGULO_Y
        and abs(esquerda[0] - limites[0]) <= largura * _DESVIO_BASE_TRIANGULO_X
        and abs(direita[0] - limites[2]) <= largura * _DESVIO_BASE_TRIANGULO_X
    )


def _triangulo_na_moldura(contexto: ContextoGramatica, caixa: Caixa, preenchimento: str) -> bool:
    caminhos = contexto.pagina.modelo.caminhos
    for posicao in contexto.grade_caminhos.consultar(caixa):
        solido = caminhos[posicao].estilo.preenchimento is not None
        if solido == (preenchimento == "solid") and _triangulo_em_pe(contexto, posicao, caixa):
            return True
    return False


def _palavra_na_moldura(caixa: Caixa, palavra: Palavra) -> bool:
    """O centro decide, como no motor; a palavra `inteira` recusa também por sobreposição (R-4)."""
    return ponto_em(caixa, _centro(palavra.caixa)) or (
        palavra.inteira and sobrepoe(caixa, palavra.caixa)
    )


def _moldura_tem_texto(contexto: ContextoGramatica, caixa: Caixa) -> bool:
    return any(
        _palavra_na_moldura(caixa, palavra) for palavra in contexto.grade_palavras.consultar(caixa)
    )


def _diagonais(contexto: ContextoGramatica, caixa: Caixa) -> int:
    x0, y0, x1, y1 = caixa
    pares = (((x0, y0), (x1, y1)), ((x1, y0), (x0, y1)))
    tolerancia = max(
        _TOLERANCIA_MINIMA_DIAGONAL, min(_lados(caixa)) * _TOLERANCIA_RELATIVA_DIAGONAL
    )
    segmentos = contexto.grade_segmentos.consultar(caixa)
    return sum(
        any(
            (math.dist(s.a, inicio) <= tolerancia and math.dist(s.b, fim) <= tolerancia)
            or (math.dist(s.a, fim) <= tolerancia and math.dist(s.b, inicio) <= tolerancia)
            for s in segmentos
        )
        for inicio, fim in pares
    )


def _barra_central(contexto: ContextoGramatica, externa: Caixa, interna: Caixa) -> bool:
    largura, altura = _lados(interna)
    meio_y = _centro(interna)[1]
    folga_y = altura * _ALTURA_BARRA
    esquerda, direita = externa[0] - _FOLGA_BARRA, externa[2] + _FOLGA_BARRA
    consulta = (esquerda, meio_y - folga_y, direita, meio_y + folga_y)
    return any(
        abs(s.a[1] - meio_y) <= folga_y
        and abs(s.b[1] - meio_y) <= folga_y
        and abs(s.a[0] - s.b[0]) >= largura * _VAO_BARRA
        and min(s.a[0], s.b[0]) >= esquerda
        and max(s.a[0], s.b[0]) <= direita
        for s in contexto.grade_segmentos.consultar(consulta)
    )


def _retangulos_com_barra(contexto: ContextoGramatica, caixa: Caixa) -> bool:
    return any(
        interna.forma == "retangulo"
        and _aninhada(caixa, interna.caixa, _RAZAO_BARRA_MINIMA, _RAZAO_BARRA_MAXIMA, _DESVIO_BARRA)
        and _barra_central(contexto, caixa, interna.caixa)
        for interna in contexto.grade_molduras.consultar(caixa)
    )


def _ponto_do_losango(losango: Caixa, ponto: Caixa) -> bool:
    largura, altura = _lados(losango)
    largura_ponto, altura_ponto = _lados(ponto)
    if not (
        contem(losango, ponto)
        and _RAZAO_PONTO_MINIMA <= largura_ponto / largura <= _RAZAO_PONTO_MAXIMA
        and _RAZAO_PONTO_MINIMA <= altura_ponto / altura <= _RAZAO_PONTO_MAXIMA
    ):
        return False
    centro_x, centro_y = _centro(ponto)
    meio_x, meio_y = _centro(losango)
    return abs(centro_x - meio_x) / (largura / 2) + abs(centro_y - meio_y) / (altura / 2) < (
        _DISTANCIA_PONTO
    )


def _losango_tres_pontos(contexto: ContextoGramatica, caixa: Caixa) -> bool:
    pontos = sum(
        candidata.forma == "elipse" and _ponto_do_losango(caixa, candidata.caixa)
        for candidata in contexto.grade_molduras.consultar(caixa)
    )
    return pontos == _PONTOS_NO_LOSANGO


def _casa_rotulo(
    contexto: ContextoGramatica, gramatica: Mapping[str, Any], moldura: Moldura
) -> bool:
    rotulo = gramatica["label"]
    return (
        _rotulo_na_moldura(contexto, moldura.caixa, rotulo)
        and (not gramatica.get("empty_interior") or not _marca_de_proposta(contexto, moldura))
        and (not gramatica.get("nested_frame") or _moldura_interna_cinza(contexto, moldura, rotulo))
    )


def _casa_triangulo(
    contexto: ContextoGramatica, gramatica: Mapping[str, Any], moldura: Moldura
) -> bool:
    return _triangulo_na_moldura(contexto, moldura.caixa, gramatica["fill"])


def _casa_diagonais(
    contexto: ContextoGramatica, gramatica: Mapping[str, Any], moldura: Moldura
) -> bool:
    return (
        not _moldura_tem_texto(contexto, moldura.caixa)
        and _diagonais(contexto, moldura.caixa) >= gramatica["min_diagonals"]
    )


def _casa_barra(
    contexto: ContextoGramatica, _gramatica: Mapping[str, Any], moldura: Moldura
) -> bool:
    return _retangulos_com_barra(contexto, moldura.caixa)


def _casa_losango(
    contexto: ContextoGramatica, _gramatica: Mapping[str, Any], moldura: Moldura
) -> bool:
    return _losango_tres_pontos(contexto, moldura.caixa)


_CASADORES: Final[Mapping[str, Callable[[ContextoGramatica, Mapping[str, Any], Moldura], bool]]] = {
    "label_in_frame": _casa_rotulo,
    "triangle_in_frame": _casa_triangulo,
    "framed_diagonals": _casa_diagonais,
    "nested_rectangles_bar": _casa_barra,
    "diamond_three_dots": _casa_losango,
}


def casa_moldura(
    contexto: ContextoGramatica, gramatica: Mapping[str, Any], moldura: Moldura
) -> bool:
    """A moldura satisfaz a gramática? `ValueError` em `kind` que não é de moldura."""
    casador = _CASADORES.get(gramatica.get("kind", ""))
    if casador is None:
        raise ValueError(f"Gramática de moldura desconhecida: {gramatica.get('kind')!r}.")
    return _moldura_ok(moldura, gramatica) and casador(contexto, gramatica, moldura)
