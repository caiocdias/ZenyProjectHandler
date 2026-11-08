"""Gramática do retângulo atravessado por uma diagonal (PARA_RAIOS_BT) sobre o modelo.

A diagonal vem primeiro (laboratório da E06.3.3.1, H-2): cada `Segmento` de comprimento
plausível é uma semente que consulta o índice dos quadriláteros fechados da página. O
quadrilátero precisa ter a proporção do corpo do para-raios (lado maior/menor entre 2 e 4,5, como
o legado), e a diagonal, da cor canônica do retângulo, tem de cruzá-lo pelos lados longos, perto
do centro, e passar além dele.
Um retângulo com duas diagonais assim (TORRE_AT, moldura riscada) ou com texto no miolo (moldura
de rótulo) não casa, nem um quadrilátero maior que o corpo de BT (célula de tabela). Ganchos
nas pontas e a haste de ligação, que sai do corpo ou da borda da envolvente, são opcionais e
entram nos componentes, como os lados do retângulo montado de vários caminhos. A caixa do
casamento é o pictograma (R-E06.3.3.1-3): a envolvente, quando há, senão o retângulo unido à
diagonal e aos ganchos. A envolvente, o X e o sinal da página vêm de `grammar_marcas`; o perfil
por origem fica aqui.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import (
    Contorno,
    MarcasDaPagina,
    _mesma_cor,
    angulo,
    cruzamentos_da_borda,
    envolvente,
    marcas_do_contexto,
    tem_x,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caixa,
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

# Corpo: proporção, ângulo reto e paralelogramo, relativos aos lados.
_PROPORCAO: Final = (2.0, 4.5)
_PERPENDICULAR: Final = 0.1
_PARALELOGRAMO: Final = 0.05
# Lado maior máximo (pt), em qualquer perfil (R-E06.3.3.2.1-5): 2 vezes o maior lado de corpo
# dos PARA_RAIOS_BT lidos nas 16 folhas da rodada de fichas, 8,58 pt. Acima disso, o
# quadrilátero é célula de tabela ou moldura, não corpo de para-raios.
_LADO_MAIOR_MAXIMO: Final = 2 * 8.58
# Diagonal: inclinação sobre o eixo (rad), desvio do centro relativo ao lado maior, quanto passa
# além dos lados longos relativo ao lado menor e comprimento relativo ao lado maior.
_ANGULO_DIAGONAL: Final = (0.4, 1.2)
_CENTRO_RELATIVO: Final = 0.25
_ALEM_RELATIVO: Final = 0.05
_COMPRIMENTO_DIAGONAL: Final = (0.5, 1.5)
# Ganchos (relativos à diagonal) e haste de ligação (tolerância na ponta relativa ao lado menor;
# desvio do eixo, em rad).
_GANCHO_RELATIVO: Final = 0.6
_PONTA_RELATIVA: Final = 0.15
_HASTE_ANGULO: Final = 0.2


@dataclass(frozen=True, slots=True)
class Perfil:
    """Tolerâncias de um perfil de página; o padrão são os mínimos absolutos do legado."""

    lado_maior_minimo: float = 3.0
    lado_menor_minimo: float = 0.8
    tolerancia_minima: float = 0.02


_PERFIL_PADRAO: Final = Perfil()
_PERFIL_ESCALA: Final = Perfil(lado_maior_minimo=1.5, lado_menor_minimo=0.4)
_PERFIS: Final[Mapping[str, Perfil]] = {
    "glifo": _PERFIL_ESCALA,
    "shx": _PERFIL_PADRAO,
    "nativo": _PERFIL_PADRAO,
}


@dataclass(frozen=True, slots=True)
class Quadrilatero:
    """Retângulo (girado ou não) de proporção de corpo de para-raios."""

    caixa: Caixa
    origens: tuple[int, ...]
    centro: Ponto
    eixo: Ponto
    maior: float
    menor: float

    @property
    def caminho(self) -> int:
        """A âncora: o primeiro caminho de que o retângulo é feito."""
        return self.origens[0]


@dataclass(frozen=True, slots=True)
class RetanguloDiagonal:
    """Retângulo, diagonal, ganchos e haste de ligação já lidos, com envolvente e X."""

    caixa: Caixa
    caminho: int
    componentes: tuple[int, ...]
    envolvente: bool
    x: bool


def _quadrilatero(
    pontos: tuple[Ponto, ...], origens: tuple[int, ...], perfil: Perfil
) -> Quadrilatero | None:
    p0, p1, p2, p3 = pontos
    s0 = (p1[0] - p0[0], p1[1] - p0[1])
    s1 = (p2[0] - p1[0], p2[1] - p1[1])
    c0, c1 = math.hypot(*s0), math.hypot(*s1)
    maior, menor = max(c0, c1), min(c0, c1)
    if (
        menor < perfil.lado_menor_minimo
        or maior < perfil.lado_maior_minimo
        or maior > _LADO_MAIOR_MAXIMO
    ):
        return None
    if not _PROPORCAO[0] <= maior / menor <= _PROPORCAO[1]:
        return None
    if abs(s0[0] * s1[0] + s0[1] * s1[1]) > _PERPENDICULAR * c0 * c1:
        return None
    fecho = math.dist((p0[0] + p2[0], p0[1] + p2[1]), (p1[0] + p3[0], p1[1] + p3[1]))
    if fecho > _PARALELOGRAMO * maior + perfil.tolerancia_minima:
        return None
    caixa = _caixa_de_pontos(pontos)
    if caixa is None:
        return None
    longo = s0 if c0 >= c1 else s1
    eixo = longo[0] / maior, longo[1] / maior
    centro = sum(p[0] for p in pontos) / 4, sum(p[1] for p in pontos) / 4
    return Quadrilatero(caixa, origens, centro, eixo, maior, menor)


def _quadrilateros(modelo: PaginaModelo, perfil: Perfil) -> list[Quadrilatero]:
    achados: dict[tuple[float, ...], Quadrilatero] = {}

    def somar(pontos: tuple[Ponto, ...], origens: tuple[int, ...]) -> None:
        quad = _quadrilatero(pontos, origens, perfil)
        if quad is not None:
            chave = (*(round(v, 1) for v in quad.caixa), round(quad.maior, 1), round(quad.menor, 1))
            achados.setdefault(chave, quad)

    for posicao, caminho in enumerate(modelo.caminhos):
        for subcaminho in caminho.subcaminhos:
            if len(subcaminho) == 4 and all(item.tipo == "l" for item in subcaminho):
                pontos = tuple(item.pontos[0] for item in subcaminho)
                fecha = math.dist(subcaminho[-1].pontos[1], pontos[0]) <= 0.05
                if fecha:
                    somar(pontos, (posicao,))
    for primitiva in modelo.primitivas:
        if isinstance(primitiva, Polilinha) and primitiva.fechada and primitiva.origens:
            pontos = primitiva.pontos
            if len(pontos) == 5 and pontos[0] == pontos[-1]:
                pontos = pontos[:4]
            if len(pontos) == 4:
                somar(pontos, primitiva.origens)
    return list(achados.values())


def _local(quad: Quadrilatero, ponto: Ponto) -> tuple[float, float]:
    dx, dy = ponto[0] - quad.centro[0], ponto[1] - quad.centro[1]
    return dx * quad.eixo[0] + dy * quad.eixo[1], -dx * quad.eixo[1] + dy * quad.eixo[0]


def _cruza(quad: Quadrilatero, segmento: Segmento, perfil: Perfil) -> bool:
    """A diagonal cruza o retângulo pelos lados longos, perto do centro, e passa além dele."""
    ua, va = _local(quad, segmento.a)
    ub, vb = _local(quad, segmento.b)
    meio = quad.menor / 2
    alem = meio + max(perfil.tolerancia_minima, quad.menor * _ALEM_RELATIVO)
    if not ((va >= alem and vb <= -alem) or (vb >= alem and va <= -alem)):
        return False
    dv = vb - va
    for lado in (meio, -meio):
        u = ua + (ub - ua) * (lado - va) / dv
        if abs(u) > quad.maior / 2:
            return False
    um, vm = (ua + ub) / 2, (va + vb) / 2
    if math.hypot(um, vm) > quad.maior * _CENTRO_RELATIVO:
        return False
    if (
        not _COMPRIMENTO_DIAGONAL[0]
        <= math.dist(segmento.a, segmento.b) / quad.maior
        <= (_COMPRIMENTO_DIAGONAL[1])
    ):
        return False
    inclinacao = math.atan2(abs(vb - va), abs(ub - ua))
    return _ANGULO_DIAGONAL[0] <= inclinacao <= _ANGULO_DIAGONAL[1]


def _chave(segmento: Segmento) -> tuple[float, ...]:
    pontos = sorted((segmento.a, segmento.b))
    return tuple(round(v, 1) for p in pontos for v in p)


def _ganchos(contexto: ContextoGramatica, diagonal: Segmento, comprimento: float) -> list[Segmento]:
    achados: list[Segmento] = []
    raio = max(0.05, comprimento * 0.02)
    for ponta in (diagonal.a, diagonal.b):
        janela = (ponta[0] - raio, ponta[1] - raio, ponta[0] + raio, ponta[1] + raio)
        for s in contexto.grade_segmentos.consultar(janela):
            if (
                s != diagonal
                and s.caminho == diagonal.caminho
                and math.dist(s.a, s.b) <= comprimento * _GANCHO_RELATIVO
                and min(math.dist(s.a, ponta), math.dist(s.b, ponta)) <= raio
            ):
                achados.append(s)
    return achados


def _bordas_no_eixo(quad: Quadrilatero, contorno: Contorno) -> list[Ponto]:
    """Onde o eixo do corpo, pelo centro do retângulo, cruza a elipse (girada) do contorno."""
    return cruzamentos_da_borda(contorno, quad.centro, quad.eixo)


def _haste_de_ligacao(
    contexto: ContextoGramatica, quad: Quadrilatero, achada: Contorno | None
) -> Segmento | None:
    """Traço alinhado ao corpo, que sai do meio de uma das pontas do retângulo ou, com
    envolvente, de onde o eixo do corpo cruza a borda dela (R-E06.3.3.1-3); a mais longa."""
    escolhida: Segmento | None = None
    tolerancia = max(0.1, quad.menor * _PONTA_RELATIVA)
    pontas = [
        (
            quad.centro[0] + sinal * quad.eixo[0] * quad.maior / 2,
            quad.centro[1] + sinal * quad.eixo[1] * quad.maior / 2,
        )
        for sinal in (1, -1)
    ]
    if achada is not None:
        pontas += _bordas_no_eixo(quad, achada)
    for ponta in pontas:
        janela = (
            ponta[0] - tolerancia,
            ponta[1] - tolerancia,
            ponta[0] + tolerancia,
            ponta[1] + tolerancia,
        )
        for s in contexto.grade_segmentos.consultar(janela):
            if s.caminho in quad.origens:
                continue
            perto = min(math.dist(s.a, ponta), math.dist(s.b, ponta)) <= tolerancia
            alinhada = abs(math.sin(angulo(s) - math.atan2(quad.eixo[1], quad.eixo[0]))) <= (
                math.sin(_HASTE_ANGULO)
            )
            if (
                perto
                and alinhada
                and (escolhida is None or math.dist(s.a, s.b) > math.dist(escolhida.a, escolhida.b))
            ):
                escolhida = s
    return escolhida


def _ler(
    contexto: ContextoGramatica,
    marcas: MarcasDaPagina,
    quad: Quadrilatero,
    diagonal: Segmento,
) -> RetanguloDiagonal:
    comprimento = math.dist(diagonal.a, diagonal.b)
    ganchos = _ganchos(contexto, diagonal, comprimento)
    pontos = [diagonal.a, diagonal.b, *(p for g in ganchos for p in (g.a, g.b))]
    cantos = _cantos(quad)
    uniao = _caixa_de_pontos([*pontos, *cantos]) or quad.caixa
    ancora = quad.centro
    achada = envolvente(
        marcas.contornos, [*pontos, *cantos], quad.maior, ancora, frozenset(quad.origens)
    )
    haste = _haste_de_ligacao(contexto, quad, achada)
    proprios = frozenset({diagonal, *ganchos, *([] if haste is None else [haste])})
    caixa = uniao
    caminhos = {*quad.origens, diagonal.caminho, *(g.caminho for g in ganchos)}
    if haste is not None:
        caminhos.add(haste.caminho)
    if achada is not None:
        caixa = achada.caixa
        caminhos.update(achada.caminhos)
    eixo = math.atan2(quad.eixo[1], quad.eixo[0]) % math.pi
    # Os lados do retângulo também são traços: o X nunca os usa.
    lados = frozenset(
        s
        for s in contexto.grade_segmentos.consultar(uniao)
        if s.caminho in quad.origens or s.caminho == diagonal.caminho
    )
    x = tem_x(contexto, caixa, quad.maior, eixo, proprios | lados)
    if x is not None:
        caminhos.update(braco.caminho for braco in x)
    return RetanguloDiagonal(
        caixa,
        quad.caminho,
        tuple(sorted(caminhos - {quad.caminho})),
        achada is not None,
        x is not None,
    )


def _cantos(quad: Quadrilatero) -> list[Ponto]:
    ux, uy = quad.eixo
    a, b = quad.maior / 2, quad.menor / 2
    cx, cy = quad.centro
    return [
        (cx + sa * a * ux - sb * b * uy, cy + sa * a * uy + sb * b * ux)
        for sa in (1, -1)
        for sb in (1, -1)
    ]


def retangulos_candidatos(
    contexto: ContextoGramatica, *, marcas: MarcasDaPagina | None = None
) -> tuple[RetanguloDiagonal, ...]:
    """Todos os retângulos com diagonal da página, já lidos (envolvente e X).

    `marcas` são as da página, compartilhadas com outras gramáticas; sem elas, são criadas
    aqui; marcas de outro contexto levantam `ValueError`. Gasta 1 por quadrilátero indexado, as
    consultas às grades (quadriláteros, segmentos e palavras) e, se há achado, os contornos das
    marcas, pagos uma vez por página. Sem quadrilátero na página, não gasta nada.
    """
    marcas = marcas_do_contexto(contexto, marcas)
    modelo = contexto.pagina.modelo
    perfil = _PERFIS[marcas.origem]
    quadrilateros = _quadrilateros(modelo, perfil)
    if not quadrilateros:
        return ()
    limites = (
        -_MARGEM_PAGINA,
        -_MARGEM_PAGINA,
        modelo.largura + _MARGEM_PAGINA,
        modelo.altura + _MARGEM_PAGINA,
    )
    grade = GradeEspacial(((q.caixa, q) for q in quadrilateros), limites, contexto.orcamento)
    menor_comprimento = min(q.maior for q in quadrilateros) * _COMPRIMENTO_DIAGONAL[0]
    maior_comprimento = max(q.maior for q in quadrilateros) * _COMPRIMENTO_DIAGONAL[1]
    achados: dict[int, dict[tuple[float, ...], Segmento]] = {}
    por_id = {id(q): q for q in quadrilateros}
    caminhos = modelo.caminhos
    for semente in contexto.grade_segmentos.itens:
        comprimento = math.dist(semente.a, semente.b)
        if not menor_comprimento <= comprimento <= maior_comprimento:
            continue
        x0, x1 = sorted((semente.a[0], semente.b[0]))
        y0, y1 = sorted((semente.a[1], semente.b[1]))
        cor = caminhos[semente.caminho].estilo.cor
        for quad in grade.consultar((x0, y0, x1, y1)):
            # A diagonal tem a cor canônica do retângulo, como no legado (R-E06.3.3.2.1-5): nas
            # 16 folhas, os 23 candidatos têm a mesma; um traço de outra cor não é a diagonal.
            if _cruza(quad, semente, perfil) and _mesma_cor(cor, caminhos[quad.caminho].estilo.cor):
                achados.setdefault(id(quad), {}).setdefault(_chave(semente), semente)
    resultado: list[RetanguloDiagonal] = []
    for chave_quad, diagonais in achados.items():
        # Duas diagonais no mesmo retângulo (TORRE_AT, moldura riscada): ambíguo, recusa.
        if len(diagonais) != 1:
            continue
        if _tem_texto(contexto, por_id[chave_quad]):
            continue
        resultado.append(_ler(contexto, marcas, por_id[chave_quad], next(iter(diagonais.values()))))
    return tuple(resultado)


def _tem_texto(contexto: ContextoGramatica, quad: Quadrilatero) -> bool:
    """Moldura de rótulo: há uma palavra com o centro dentro da caixa do retângulo."""
    caixa = quad.caixa
    return any(
        caixa[0] <= (p.caixa[0] + p.caixa[2]) / 2 <= caixa[2]
        and caixa[1] <= (p.caixa[1] + p.caixa[3]) / 2 <= caixa[3]
        for p in contexto.grade_palavras.consultar(caixa)
    )


def casa_retangulos_diagonal(
    contexto: ContextoGramatica,
    gramatica: Mapping[str, Any],
    *,
    candidatos: tuple[RetanguloDiagonal, ...] | None = None,
) -> list[tuple[Caixa, int, tuple[int, ...]]]:
    """(caixa do pictograma, caminho do retângulo, demais caminhos) de cada achado da variante.

    `candidatos` são os `retangulos_candidatos` da página, já calculados por quem casa várias
    variantes; sem eles, são calculados aqui. Cada candidato examinado gasta 1 do orçamento.
    """
    achados = retangulos_candidatos(contexto) if candidatos is None else candidatos
    quer_elipse = gramatica["enclosure"] == "ellipse"
    quer_x = bool(gramatica["removal_mark"])
    limite = float(gramatica["max_span"])
    resultado: list[tuple[Caixa, int, tuple[int, ...]]] = []
    for achado in achados:
        contexto.orcamento.gastar()
        caixa = achado.caixa
        if (
            achado.envolvente != quer_elipse
            or achado.x != quer_x
            or max(caixa[2] - caixa[0], caixa[3] - caixa[1]) > limite
        ):
            continue
        resultado.append((caixa, achado.caminho, achado.componentes))
    return resultado
