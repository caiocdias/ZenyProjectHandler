"""Gramática da haste com barras (ATERRAMENTO e PARA_RAIOS_MT) sobre a página do modelo.

Cada `Segmento` de comprimento plausível de haste é uma semente que consulta a grade de segmentos
numa janela proporcional a ele, como `_ground_and_mt_arrester_matches` do analisador legado. As
tolerâncias vêm de um perfil escolhido por um sinal da própria página, a origem predominante dos
textos do modelo (R-E06.3.2-10): nas páginas de texto em glifo o símbolo é pequeno (haste de 4 a
6 pt), abaixo dos mínimos absolutos do legado, e as tolerâncias passam a ser relativas à haste.
A alternativa descartada é o `PerfilFamilia` do documento (ADR 0016): o método roda por página e a
família é do documento. A caixa do casamento é o pictograma (R-E06.3.2-3).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import pairwise
from typing import Any, Final

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
    OrcamentoConsultas,
    Segmento,
    _caixa_de_pontos,
)

_HASTE_MAXIMA: Final = 24.0
_ENVOLVENTE: Final = (0.95, 3.06)
# Envolvente achatada numa polilinha fechada: vértices bastantes e todos perto da elipse da caixa.
_VERTICES_MINIMOS_ELIPSE: Final = 8
_DESVIO_RAIO_ELIPSE: Final = 0.2
_ORIGENS: Final = ("glifo", "shx", "nativo")

# Barras: posição ao longo da haste, desvio do centro da primeira e lacunas, relativos a ela.
_ALCANCE_BARRAS: Final = (0.35, 1.35)
_LATERAL_RELATIVA_JANELA: Final = 0.3
_BARRA_MAXIMA_RELATIVA: Final = 1.5
_LATERAL_RELATIVA_BARRA: Final = 0.2
_DESVIO_PRIMEIRA_BARRA: Final = 0.15
_PRIMEIRA_E_A_MAIOR: Final = 0.9
_MESMA_POSICAO: Final = 0.01

# X de retirada: braços de comprimento relativo à maior barra, cruzando perto dos meios.
_MARGEM_X: Final = 0.5
_BRACO_X: Final = (0.8, 3.0)
_ANGULO_BRACO_X: Final = (math.radians(25), math.radians(65))
_MEIO_DO_BRACO: Final = (0.3, 0.7)
_RAZAO_BRACOS: Final = 1.3
_ABERTURA_X: Final = math.radians(45)
_TOLERANCIA_COR: Final = 0.02


@dataclass(frozen=True, slots=True)
class Perfil:
    """Tolerâncias de um perfil de página; os padrões são os limiares absolutos do legado."""

    haste_minima: float = 6.0
    barra_minima: float = 1.0
    lateral_relativa: float = 0.0
    barra_inicial: tuple[float, float] = (0.45, 0.85)
    angulo: float = math.radians(11)
    lateral_minima: float = 1.5
    razao_afunilamento: float = 1.1
    lacuna_minima: float = 0.1
    lacuna_maxima: float = 0.45


_PERFIL_PADRAO: Final = Perfil()
_PERFIL_ESCALA: Final = Perfil(
    haste_minima=1.5, barra_minima=0.5, lateral_minima=0.0, lateral_relativa=0.1
)
_PERFIS: Final[Mapping[str, Perfil]] = {
    "glifo": _PERFIL_ESCALA,
    "shx": _PERFIL_PADRAO,
    "nativo": _PERFIL_PADRAO,
}


def origem_predominante(modelo: PaginaModelo) -> str:
    """Origem de texto mais frequente da página; sem texto, "nativo". Empate: a maior no nome."""
    contagem: Counter[str] = Counter(texto.origem for texto in modelo.textos)
    if not contagem:
        return "nativo"
    return max(_ORIGENS, key=lambda origem: (contagem[origem], origem))


def perfil_da_pagina(modelo: PaginaModelo) -> Perfil:
    return _PERFIS[origem_predominante(modelo)]


@dataclass(frozen=True, slots=True)
class _Reta:
    segmento: Segmento
    centro: Ponto
    angulo: float
    comprimento: float
    cor: str
    camada: str


@dataclass(frozen=True, slots=True)
class _Contorno:
    """Envolvente candidata: elipse do índice de molduras ou polilinha fechada elíptica."""

    caixa: Caixa
    caminhos: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Haste:
    """Haste e barras já validadas e a leitura delas, feita uma vez por página: envolvente,
    pictograma (a caixa do casamento) e braços do X."""

    haste: Segmento
    barras: tuple[Segmento, ...]
    ponta: Ponto
    base: Ponto
    maior_barra: float
    caixa_barras: Caixa
    envolvente: _Contorno | None = None
    pictograma: Caixa | None = None
    x: tuple[Segmento, Segmento] | None = None


def _cor_canonica(cor: Cor | None, preenchimento: Cor | None) -> str | None:
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


def _reta(segmento: Segmento, cor: str, camada: str) -> _Reta | None:
    dx, dy = segmento.b[0] - segmento.a[0], segmento.b[1] - segmento.a[1]
    comprimento = math.hypot(dx, dy)
    if comprimento <= 0:
        return None
    return _Reta(
        segmento,
        ((segmento.a[0] + segmento.b[0]) / 2, (segmento.a[1] + segmento.b[1]) / 2),
        math.atan2(dy, dx) % math.pi,
        comprimento,
        cor,
        camada,
    )


def _diferenca_angular(a: float, b: float) -> float:
    d = abs(a - b) % math.pi
    return min(d, math.pi - d)


def _angulo(segmento: Segmento) -> float:
    return math.atan2(segmento.b[1] - segmento.a[1], segmento.b[0] - segmento.a[0]) % math.pi


def _posicao(origem: Ponto, alvo: Ponto, eixo: Ponto, normal: Ponto) -> tuple[float, float]:
    dx, dy = alvo[0] - origem[0], alvo[1] - origem[1]
    return dx * eixo[0] + dy * eixo[1], dx * normal[0] + dy * normal[1]


def _janela(reta: _Reta, perfil: Perfil) -> Caixa:
    """Caixa que cobre os centros candidatos a barra ao longo da haste, dos dois lados."""
    comp = reta.comprimento
    lateral = max(
        perfil.lateral_minima, perfil.lateral_relativa * comp, comp * _LATERAL_RELATIVA_JANELA
    )
    alcance = comp * _ALCANCE_BARRAS[1]
    eixo = math.cos(reta.angulo), math.sin(reta.angulo)
    meio_x = abs(eixo[0]) * alcance + abs(eixo[1]) * lateral
    meio_y = abs(eixo[1]) * alcance + abs(eixo[0]) * lateral
    return (
        reta.centro[0] - meio_x,
        reta.centro[1] - meio_y,
        reta.centro[0] + meio_x,
        reta.centro[1] + meio_y,
    )


def _decrescentes(barras: Sequence[_Reta], razao: float) -> bool:
    return all(maior.comprimento > menor.comprimento * razao for maior, menor in pairwise(barras))


def _alternadas(barras: Sequence[_Reta], razao: float) -> bool:
    comp = [b.comprimento for b in barras]
    return (
        len(comp) == 4
        and comp[0] > comp[1] * razao
        and comp[2] > comp[1] * razao
        and comp[2] > comp[3] * razao
    )


def _afunila_ou_alterna(barras: Sequence[_Reta], razao: float) -> bool:
    """As formas do inventário: 3 decrescentes ou 4 alternadas (longa, curta, longa, curta).

    Quatro decrescentes não é nenhuma delas e é recusada (fail-closed)."""
    if len(barras) == 3:
        return _decrescentes(barras, razao)
    return _alternadas(barras, razao)


def _assinatura(
    haste: _Reta, barras: Sequence[_Reta], eixo: Ponto, normal: Ponto, p: Perfil
) -> bool:
    """O afunilamento terminal (`_ground_bar_signature`), não só a contagem de traços."""
    if len(barras) < 3:
        return False
    comp = haste.comprimento
    desloc = [abs(_posicao(haste.centro, b.centro, eixo, normal)[0]) for b in barras]
    if abs(desloc[0] - comp / 2) > comp * _DESVIO_PRIMEIRA_BARRA:
        return False
    if not comp * p.barra_inicial[0] <= barras[0].comprimento <= comp * p.barra_inicial[1]:
        return False
    if barras[0].comprimento < max(b.comprimento for b in barras) * _PRIMEIRA_E_A_MAIOR:
        return False
    if not _afunila_ou_alterna(barras, p.razao_afunilamento):
        return False
    return all(
        comp * p.lacuna_minima <= direita - esquerda <= comp * p.lacuna_maxima
        for esquerda, direita in pairwise(desloc)
    )


def _recortar(barras: list[_Reta], perfil: Perfil) -> list[_Reta]:
    """Fica com as barras do símbolo: as 4 alternadas do começo, senão as 3 decrescentes.

    Quatro decrescentes ficam inteiras, para a assinatura recusá-las: as 3 primeiras não são
    um aterramento com um traço a mais."""
    razao = perfil.razao_afunilamento
    quatro = barras[:4]
    if len(quatro) == 4 and (_alternadas(quatro, razao) or _decrescentes(quatro, razao)):
        return quatro
    if len(barras) >= 3 and _decrescentes(barras[:3], razao):
        return barras[:3]
    return barras


def _alterna(haste: Haste) -> bool:
    comp = [math.dist(b.a, b.b) for b in haste.barras]
    return len(comp) == 4 and comp[2] > comp[1]


def _barras_do_lado(
    haste: _Reta, candidatos: Sequence[_Reta], eixo: Ponto, normal: Ponto, perfil: Perfil
) -> list[list[_Reta]]:
    """Traços perpendiculares de mesma cor e camada, separados pelo lado da haste."""
    por_lado: dict[int, list[_Reta]] = {-1: [], 1: []}
    comp = haste.comprimento
    for cand in candidatos:
        if cand.segmento == haste.segmento or (cand.cor, cand.camada) != (haste.cor, haste.camada):
            continue
        if abs(_diferenca_angular(haste.angulo, cand.angulo) - math.pi / 2) > perfil.angulo:
            continue
        desloc, lateral = _posicao(haste.centro, cand.centro, eixo, normal)
        limite_lateral = max(
            perfil.lateral_minima,
            perfil.lateral_relativa * comp,
            cand.comprimento * _LATERAL_RELATIVA_BARRA,
        )
        if (
            abs(lateral) <= limite_lateral
            and comp * _ALCANCE_BARRAS[0] <= abs(desloc) <= comp * _ALCANCE_BARRAS[1]
            and cand.comprimento <= comp * _BARRA_MAXIMA_RELATIVA
        ):
            por_lado[1 if desloc > 0 else -1].append(cand)
    return list(por_lado.values())


def _selecionar_barras(
    haste: _Reta, barras: list[_Reta], eixo: Ponto, normal: Ponto
) -> list[_Reta]:
    """Uma barra por posição (a mais centrada no eixo), da mais próxima da ponta em diante."""
    comp = haste.comprimento

    def pos(b: _Reta) -> tuple[float, float]:
        return _posicao(haste.centro, b.centro, eixo, normal)

    escolhidas: list[_Reta] = []
    for barra in sorted(barras, key=lambda b: (abs(pos(b)[1]), -b.comprimento)):
        if not any(abs(pos(o)[0] - pos(barra)[0]) <= comp * _MESMA_POSICAO for o in escolhidas):
            escolhidas.append(barra)
    escolhidas.sort(key=lambda b: abs(pos(b)[0]))
    if escolhidas:
        primeira = min(escolhidas, key=lambda b: (abs(abs(pos(b)[0]) - comp / 2), -b.comprimento))
        escolhidas = escolhidas[escolhidas.index(primeira) :]
    return escolhidas


def _um_traco(modelo: PaginaModelo, caminho: int) -> bool:
    """Caminho de um subcaminho com um item só: a haste, as barras e os braços do X são traços
    soltos, e o lado de um contorno (moldura, caixa do poste) não conta como nenhum deles."""
    subcaminhos = modelo.caminhos[caminho].subcaminhos
    return len(subcaminhos) == 1 and len(subcaminhos[0]) == 1


class _Estilos:
    """Cor canônica e camada de cada caminho, lidas uma vez por página."""

    def __init__(self, modelo: PaginaModelo) -> None:
        self._modelo = modelo
        self._cache: dict[int, tuple[str, str] | None] = {}

    def reta(self, segmento: Segmento) -> _Reta | None:
        """A reta do segmento, se o caminho dele é um traço só de cor do legado."""
        info = self._estilo(segmento.caminho)
        return None if info is None else _reta(segmento, *info)

    def _estilo(self, caminho: int) -> tuple[str, str] | None:
        if caminho not in self._cache:
            desenho = self._modelo.caminhos[caminho]
            cor = _cor_canonica(desenho.estilo.cor, desenho.estilo.preenchimento)
            unico = _um_traco(self._modelo, caminho)
            estilo = None if cor is None or not unico else (cor, desenho.estilo.camada)
            self._cache[caminho] = estilo
        return self._cache[caminho]


def hastes_candidatas(contexto: ContextoGramatica) -> tuple[Haste, ...]:
    """Todas as hastes com barras da página, já lidas (envolvente, pictograma e X).

    Gasta 1 por semente, as consultas às grades e, se há haste, o índice das envolventes.
    """
    perfil = perfil_da_pagina(contexto.pagina.modelo)
    estilos = _Estilos(contexto.pagina.modelo)
    sementes = [
        reta
        for segmento in contexto.grade_segmentos.itens
        if (reta := estilos.reta(segmento)) is not None
        and perfil.haste_minima <= reta.comprimento <= _HASTE_MAXIMA
    ]
    achados: list[Haste] = []
    for haste in sementes:
        contexto.orcamento.gastar()
        eixo = math.cos(haste.angulo), math.sin(haste.angulo)
        normal = -eixo[1], eixo[0]
        retas = [
            reta
            for segmento in contexto.grade_segmentos.consultar(_janela(haste, perfil))
            if (reta := estilos.reta(segmento)) is not None
            and reta.comprimento >= perfil.barra_minima
        ]
        for lado in _barras_do_lado(haste, retas, eixo, normal, perfil):
            barras = _recortar(_selecionar_barras(haste, lado, eixo, normal), perfil)
            if _assinatura(haste, barras, eixo, normal, perfil):
                achados.append(_montar(haste, barras))
    escolhidas = _deduplicar(achados, contexto.orcamento)
    if not escolhidas:
        return ()
    contornos = _contornos(contexto)
    return tuple(_ler(contexto, contornos, haste) for haste in escolhidas)


def _ler(contexto: ContextoGramatica, contornos: GradeEspacial[_Contorno], haste: Haste) -> Haste:
    envolvente = _envolvente(contornos, haste)
    pictograma = _pictograma(haste, None if envolvente is None else envolvente.caixa)
    x = _tem_x(contexto, haste, pictograma)
    return replace(haste, envolvente=envolvente, pictograma=pictograma, x=x)


def _montar(haste: _Reta, barras: Sequence[_Reta]) -> Haste:
    ponta, base = sorted(
        (haste.segmento.a, haste.segmento.b), key=lambda p: math.dist(p, barras[0].centro)
    )
    pontos = [p for b in barras for p in (b.segmento.a, b.segmento.b)]
    caixa = (
        min(x for x, _ in pontos),
        min(y for _, y in pontos),
        max(x for x, _ in pontos),
        max(y for _, y in pontos),
    )
    return Haste(
        haste.segmento,
        tuple(b.segmento for b in barras),
        ponta,
        base,
        max(b.comprimento for b in barras),
        caixa,
    )


def _deduplicar(achados: list[Haste], orcamento: OrcamentoConsultas) -> tuple[Haste, ...]:
    """Uma leitura por haste e por tipo (3 ou 4 barras), como `_deduplicate_matches`.

    Só se comparam leituras que dividem um traço (índice por membro): cada leitura gasta 1, e
    cada comparação com uma escolhida, mais 1.
    """
    escolhidos: list[Haste] = []
    por_membro: dict[Segmento, list[int]] = {}
    for achado in sorted(achados, key=lambda h: (-len(h.barras), h.ponta, h.base)):
        membros = {achado.haste, *achado.barras}
        vizinhos = sorted({i for membro in membros for i in por_membro.get(membro, ())})
        orcamento.gastar(1 + len(vizinhos))
        if any(
            (e.haste == achado.haste or len({e.haste, *e.barras} & membros) >= 2)
            and (len(e.barras) >= 4) == (len(achado.barras) >= 4)
            for e in (escolhidos[i] for i in vizinhos)
        ):
            continue
        for membro in membros:
            por_membro.setdefault(membro, []).append(len(escolhidos))
        escolhidos.append(achado)
    return tuple(escolhidos)


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


def _contornos(contexto: ContextoGramatica) -> GradeEspacial[_Contorno]:
    """Índice das envolventes da página: as elipses das molduras (Béziers e círculos) e as
    polilinhas fechadas elípticas; cada polilinha fechada examinada gasta 1."""
    modelo = contexto.pagina.modelo
    contornos = [
        _Contorno(moldura.caixa, (moldura.caminho,))
        for moldura in contexto.molduras
        if moldura.forma == "elipse"
    ]
    fechadas = [p for p in modelo.primitivas if isinstance(p, Polilinha) and p.fechada]
    contexto.orcamento.gastar(len(fechadas))
    for polilinha in fechadas:
        caixa = _elipse_poligonal(polilinha)
        if caixa is not None:
            contornos.append(_Contorno(caixa, tuple(sorted(set(polilinha.origens)))))
    limites = (
        -_MARGEM_PAGINA,
        -_MARGEM_PAGINA,
        modelo.largura + _MARGEM_PAGINA,
        modelo.altura + _MARGEM_PAGINA,
    )
    return GradeEspacial(((c.caixa, c) for c in contornos), limites, contexto.orcamento)


def _envolvente(contornos: GradeEspacial[_Contorno], haste: Haste) -> _Contorno | None:
    """A menor elipse que contém a ponta e as barras, como `_enclosing_outline` do legado."""
    minimo, maximo = _ENVOLVENTE
    longa = haste.maior_barra
    proprios = {haste.haste.caminho, *(b.caminho for b in haste.barras)}
    tolerancia = max(0.01, longa * 0.02)
    exigidos = (haste.ponta, *(p for b in haste.barras for p in (b.a, b.b)))
    alcance = longa * maximo
    janela = (
        haste.ponta[0] - alcance,
        haste.ponta[1] - alcance,
        haste.ponta[0] + alcance,
        haste.ponta[1] + alcance,
    )
    opcoes: list[tuple[float, tuple[int, ...], _Contorno]] = []
    for contorno in contornos.consultar(janela):
        caixa = contorno.caixa
        diametro = max(caixa[2] - caixa[0], caixa[3] - caixa[1])
        if (
            proprios.isdisjoint(contorno.caminhos)
            and minimo * longa <= diametro <= maximo * longa
            and all(_dentro_da_elipse(caixa, p, tolerancia) for p in exigidos)
        ):
            opcoes.append((diametro, contorno.caminhos, contorno))
    if not opcoes:
        return None
    return min(opcoes, key=lambda opcao: (opcao[0], opcao[1]))[2]


def _pictograma(haste: Haste, envolvente: Caixa | None) -> Caixa:
    """`_symbol_footprint`: envolvente e barras, ou barras e o trecho da haste até a maior barra."""
    barras = haste.caixa_barras
    if envolvente is not None:
        return (
            min(envolvente[0], barras[0]),
            min(envolvente[1], barras[1]),
            max(envolvente[2], barras[2]),
            max(envolvente[3], barras[3]),
        )
    vao = max(math.dist(haste.ponta, haste.base), 1e-9)
    trecho = round(min(haste.maior_barra, vao), 9)
    inicio = (
        haste.ponta[0] + (haste.base[0] - haste.ponta[0]) / vao * trecho,
        haste.ponta[1] + (haste.base[1] - haste.ponta[1]) / vao * trecho,
    )
    return (
        min(barras[0], haste.ponta[0], inicio[0]),
        min(barras[1], haste.ponta[1], inicio[1]),
        max(barras[2], haste.ponta[0], inicio[0]),
        max(barras[3], haste.ponta[1], inicio[1]),
    )


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


def _formam_x(primeiro: Segmento, segundo: Segmento, contexto: ContextoGramatica) -> bool:
    cruz = _intersecao(primeiro, segundo)
    if cruz is None:
        return False
    c1, c2 = math.dist(primeiro.a, primeiro.b), math.dist(segundo.a, segundo.b)
    caminhos = contexto.pagina.modelo.caminhos
    return (
        all(_MEIO_DO_BRACO[0] <= t <= _MEIO_DO_BRACO[1] for t in cruz)
        and max(c1, c2) <= min(c1, c2) * _RAZAO_BRACOS
        and _diferenca_angular(_angulo(primeiro), _angulo(segundo)) >= _ABERTURA_X
        and _mesma_cor(caminhos[primeiro.caminho].estilo.cor, caminhos[segundo.caminho].estilo.cor)
    )


def _mesma_cor(a: Cor | None, b: Cor | None) -> bool:
    """Mesma cor canônica do legado; fora delas, canais a no máximo `_TOLERANCIA_COR`."""
    canonica_a, canonica_b = _cor_canonica(a, None), _cor_canonica(b, None)
    if canonica_a is not None or canonica_b is not None:
        return canonica_a == canonica_b
    if a is None or b is None:
        return a is b
    return all(abs(x - y) <= _TOLERANCIA_COR for x, y in zip(a, b, strict=True))


def _tem_x(
    contexto: ContextoGramatica, haste: Haste, pictograma: Caixa
) -> tuple[Segmento, Segmento] | None:
    """Dois braços soltos de mesma cor e comprimento parecido que se cruzam perto dos meios."""
    longa = haste.maior_barra
    margem = longa * _MARGEM_X
    janela = (
        pictograma[0] - margem,
        pictograma[1] - margem,
        pictograma[2] + margem,
        pictograma[3] + margem,
    )
    eixo = _angulo(haste.haste)
    proprios = {haste.haste, *haste.barras}
    bracos = [
        s
        for s in contexto.grade_segmentos.consultar(janela)
        if s not in proprios
        and _um_traco(contexto.pagina.modelo, s.caminho)
        and longa * _BRACO_X[0] <= math.dist(s.a, s.b) <= longa * _BRACO_X[1]
        and _ANGULO_BRACO_X[0] <= _diferenca_angular(_angulo(s), eixo) <= _ANGULO_BRACO_X[1]
    ]
    # Cada par examinado é uma consulta: muitas diagonais longas na janela pagam o produto.
    contexto.orcamento.gastar(len(bracos) * (len(bracos) - 1) // 2)
    for i, primeiro in enumerate(bracos):
        for segundo in bracos[i + 1 :]:
            if _formam_x(primeiro, segundo, contexto):
                return primeiro, segundo
    return None


def casa_hastes(
    contexto: ContextoGramatica,
    gramatica: Mapping[str, Any],
    *,
    candidatas: tuple[Haste, ...] | None = None,
) -> list[tuple[Caixa, int, tuple[int, ...]]]:
    """(caixa do pictograma, caminho da haste, demais caminhos) de cada haste da variante.

    `candidatas` são as `hastes_candidatas` da página, já calculadas por quem casa várias
    variantes; sem elas, são calculadas aqui. Cada haste examinada gasta 1 do orçamento.
    """
    hastes = hastes_candidatas(contexto) if candidatas is None else candidatas
    quatro = int(gramatica["bars"]) == 4
    quer_elipse = gramatica["enclosure"] == "ellipse"
    quer_x = bool(gramatica["removal_mark"])
    limite = float(gramatica["max_span"])
    achados: list[tuple[Caixa, int, tuple[int, ...]]] = []
    for haste in hastes:
        contexto.orcamento.gastar()
        pictograma = haste.pictograma
        if (
            pictograma is None
            or _alterna(haste) != quatro
            or (haste.envolvente is not None) != quer_elipse
            or (haste.x is not None) != quer_x
            or max(pictograma[2] - pictograma[0], pictograma[3] - pictograma[1]) > limite
        ):
            continue
        ancora = haste.haste.caminho
        outros = {b.caminho for b in haste.barras}
        if haste.envolvente is not None:
            outros.update(haste.envolvente.caminhos)
        if haste.x is not None:
            outros.update(braco.caminho for braco in haste.x)
        achados.append((pictograma, ancora, tuple(sorted(outros - {ancora}))))
    return achados
