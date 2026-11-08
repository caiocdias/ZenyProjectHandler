"""Gramática do estai (haste com garfo, `forked_stem`) sobre a página do modelo de desenho.

Cada traço fino, contínuo e de cor de símbolo é semente de haste. Uma ponta dela é o vértice do
garfo quando ali chegam exatamente mais dois traços da mesma cor, abertos para longe da haste
(dentes a cerca de 15 a 40 graus dela, um de cada lado). O desenho que continua além do vértice ou
das pontas dos dentes (ramal de condutor, pé de galinha de cerca) não é garfo. A envolvente e o X
vêm de `grammar_marcas`; quem tem X é o grupo de retirada, com ou sem círculo (R-E06.3.4-1). Garfo
verde ou vermelho sem marca não se afirma existente: sai sem casamento (R-E06.3.4-2). A caixa
(R-E06.3.4-3, alternativa de melhor IoU no laboratório) une o pictograma (a envolvente da cor do
garfo ou, sem ela, o próprio garfo) e a haste inteira; o X fica de fora.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import (
    Contorno,
    MarcasDaPagina,
    _mesma_cor,
    angulo,
    cor_canonica,
    envolvente,
    marcas_do_contexto,
    tem_x,
    um_traco,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caixa,
    Caminho,
    Cor,
    PaginaModelo,
    Ponto,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    _MARGEM_PAGINA,
    ContextoGramatica,
    GradeEspacial,
    OrcamentoConsultas,
    PaginaGramatica,
    Segmento,
)

# Haste: comprimento por origem predominante do texto da página (o símbolo das folhas de glifo
# é menor que o das folhas de texto nativo ou SHX).
_HASTE: Final[Mapping[str, tuple[float, float]]] = {
    "glifo": (4.0, 20.0),
    "shx": (10.0, 24.0),
    "nativo": (10.0, 24.0),
}
_ESPESSURA_MAXIMA: Final = 0.5
_TRACOS_CONTINUOS: Final = frozenset({"", "[]", "[]0"})
_CINZA_DIFERENCA: Final = 0.05
_CINZA_LIMITE: Final = 0.4
# Dentes: comprimento relativo à haste e ângulo em relação ao prolongamento dela.
_DENTE_RELATIVO: Final = (0.55, 1.0)
_RAZAO_DENTES: Final = 1.15
_ANGULO_DENTE: Final = (math.radians(15), math.radians(40))
_DIFERENCA_DENTES: Final = math.radians(10)
_TOLERANCIA_VERTICE: Final = 0.1
_CELULA_VERTICE: Final = 0.25
_MESMO_GARFO: Final = 0.5
_MESMO_TRACO: Final = 0.35
_BRANCO: Final = 0.9


@dataclass(frozen=True, slots=True)
class CandidatoEstai:
    """Estai lido uma vez por página; as variantes só filtram esta classificação."""

    contexto: ContextoGramatica
    caixa: Caixa
    caminho_ancora: int
    componentes: tuple[int, ...]
    enclosure: str
    removal_mark: bool


@dataclass(frozen=True, slots=True)
class _Garfo:
    haste: Segmento
    dentes: tuple[Segmento, Segmento]
    vertice: Ponto
    base: Ponto
    pontas: tuple[Ponto, Ponto]
    cor: Cor | None
    escala: float


@dataclass(frozen=True, slots=True)
class _Traco:
    segmento: Segmento
    comprimento: float


@dataclass(frozen=True, slots=True)
class _Raio:
    traco: _Traco
    perto: Ponto
    longe: Ponto


class _Pontas:
    """Índice das pontas dos traços finos; cada raio devolvido gasta 1, como a grade."""

    def __init__(self, orcamento: OrcamentoConsultas) -> None:
        self._orcamento = orcamento
        self._celulas: dict[tuple[int, int], list[_Raio]] = {}

    @staticmethod
    def _chave(ponto: Ponto) -> tuple[int, int]:
        return math.floor(ponto[0] / _CELULA_VERTICE), math.floor(ponto[1] / _CELULA_VERTICE)

    def inserir(self, traco: _Traco) -> None:
        s = traco.segmento
        for perto, longe in ((s.a, s.b), (s.b, s.a)):
            self._orcamento.gastar()
            self._celulas.setdefault(self._chave(perto), []).append(_Raio(traco, perto, longe))

    def em(self, ponto: Ponto) -> list[_Raio]:
        cx, cy = self._chave(ponto)
        achados = [
            raio
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for raio in self._celulas.get((cx + dx, cy + dy), ())
            if math.dist(raio.perto, ponto) <= _TOLERANCIA_VERTICE
        ]
        self._orcamento.gastar(len(achados))
        return achados


def _traco_continuo(caminho: Caminho) -> bool:
    return caminho.estilo.tracejado.replace(" ", "") in _TRACOS_CONTINUOS


def _preto_ou_cinza(cor: Cor | None) -> bool:
    return cor is not None and max(cor) - min(cor) <= _CINZA_DIFERENCA and max(cor) < _CINZA_LIMITE


def _cor_de_estai(cor: Cor | None) -> bool:
    """Preto, cinza, verde ou vermelho; o roxo e o branco (wipeout) nunca são garfo."""
    return _preto_ou_cinza(cor) or cor_canonica(cor, None) in ("#FF0000", "#008000")


def _fino_e_de_cor(pagina: PaginaGramatica, caminho: int) -> bool:
    modelo = pagina.modelo
    desenho = modelo.caminhos[caminho]
    return (
        caminho not in pagina.glifos_lidos
        and caminho not in pagina.translucidos
        and desenho.tipo == "traco"
        and um_traco(modelo, caminho)
        and desenho.estilo.espessura <= _ESPESSURA_MAXIMA
        and _traco_continuo(desenho)
        and _cor_de_estai(desenho.estilo.cor)
    )


def _tracos_finos(contexto: ContextoGramatica, perfil: tuple[float, float]) -> list[_Traco]:
    minimo = perfil[0] * _DENTE_RELATIVO[0]
    tracos: list[_Traco] = []
    for segmento in contexto.grade_segmentos.itens:
        comprimento = math.dist(segmento.a, segmento.b)
        if minimo <= comprimento <= perfil[1] and _fino_e_de_cor(contexto.pagina, segmento.caminho):
            tracos.append(_Traco(segmento, comprimento))
    return tracos


def _mesmo_estilo(modelo: PaginaModelo, a: int, b: int) -> bool:
    primeiro, segundo = modelo.caminhos[a].estilo, modelo.caminhos[b].estilo
    return primeiro.camada == segundo.camada and _mesma_cor(primeiro.cor, segundo.cor)


def _unitario(de: Ponto, para: Ponto) -> tuple[float, float] | None:
    dx, dy = para[0] - de[0], para[1] - de[1]
    norma = math.hypot(dx, dy)
    return None if norma <= 0 else (dx / norma, dy / norma)


def _desvio(extensao: tuple[float, float], direcao: tuple[float, float]) -> float:
    """Ângulo com sinal de `direcao` em relação à `extensao`, em (-pi, pi]."""
    return math.atan2(
        extensao[0] * direcao[1] - extensao[1] * direcao[0],
        extensao[0] * direcao[0] + extensao[1] * direcao[1],
    )


def _abre_para_longe(haste: _Traco, vertice: Ponto, base: Ponto, dentes: Sequence[_Raio]) -> bool:
    extensao = _unitario(base, vertice)
    primeiro, segundo = (_unitario(vertice, dente.longe) for dente in dentes)
    if extensao is None or primeiro is None or segundo is None:
        return False
    desvios = _desvio(extensao, primeiro), _desvio(extensao, segundo)
    comprimentos = sorted(dente.traco.comprimento for dente in dentes)
    return (
        desvios[0] * desvios[1] < 0
        and all(_ANGULO_DENTE[0] <= abs(d) <= _ANGULO_DENTE[1] for d in desvios)
        and abs(abs(desvios[0]) - abs(desvios[1])) <= _DIFERENCA_DENTES
        and comprimentos[1] <= comprimentos[0] * _RAZAO_DENTES
        and comprimentos[0] >= haste.comprimento * _DENTE_RELATIVO[0]
        and comprimentos[1] <= haste.comprimento * _DENTE_RELATIVO[1]
    )


def _em_torno(ponto: Ponto, folga: float) -> Caixa:
    return (ponto[0] - folga, ponto[1] - folga, ponto[0] + folga, ponto[1] + folga)


def _mesmo_traco(a: Segmento, b: Segmento) -> bool:
    """O mesmo traço redesenhado, nos dois sentidos, com diferença de décimos de ponto."""
    tolerancia = _MESMO_TRACO
    return (math.dist(a.a, b.a) <= tolerancia and math.dist(a.b, b.b) <= tolerancia) or (
        math.dist(a.a, b.b) <= tolerancia and math.dist(a.b, b.a) <= tolerancia
    )


def _continua_em(
    contexto: ContextoGramatica, garfo: _Garfo, ponto: Ponto, adiante: tuple[float, float]
) -> bool:
    """Outro traço solto da cor do garfo termina no `ponto` e segue `adiante`.

    O lado da envolvente (caminho de muitas retas) passa pelo vértice e não é continuação. O
    condutor que passa pelo ponto sem terminar nele também não, nem o dente de outro estai que
    chega à mesma ponta vindo de trás (estais vizinhos).
    """
    modelo = contexto.pagina.modelo
    proprios = (garfo.haste, *garfo.dentes)
    for s in contexto.grade_segmentos.consultar(_em_torno(ponto, _TOLERANCIA_VERTICE)):
        if (
            s in proprios
            or not um_traco(modelo, s.caminho)
            or any(_mesmo_traco(s, proprio) for proprio in proprios)
            or not _mesmo_estilo(modelo, s.caminho, garfo.haste.caminho)
        ):
            continue
        for perto, longe in ((s.a, s.b), (s.b, s.a)):
            if (
                math.dist(perto, ponto) <= _TOLERANCIA_VERTICE
                and (longe[0] - ponto[0]) * adiante[0] + (longe[1] - ponto[1]) * adiante[1] > 0
            ):
                return True
    return False


def _caixa_de(pontos: Sequence[Ponto]) -> Caixa:
    return (
        min(p[0] for p in pontos),
        min(p[1] for p in pontos),
        max(p[0] for p in pontos),
        max(p[1] for p in pontos),
    )


def _dentro_do_triangulo(p: Ponto, a: Ponto, b: Ponto, c: Ponto) -> bool:
    def giro(o: Ponto, u: Ponto, v: Ponto) -> float:
        return (u[0] - o[0]) * (v[1] - o[1]) - (u[1] - o[1]) * (v[0] - o[0])

    sinais = giro(a, b, p), giro(b, c, p), giro(c, a, p)
    return all(s >= 0 for s in sinais) or all(s <= 0 for s in sinais)


def _tem_texto_dentro(contexto: ContextoGramatica, garfo: _Garfo) -> bool:
    triangulo = (garfo.vertice, *garfo.pontas)
    a, b, c = triangulo
    return any(
        _dentro_do_triangulo(
            ((palavra.caixa[0] + palavra.caixa[2]) / 2, (palavra.caixa[1] + palavra.caixa[3]) / 2),
            a,
            b,
            c,
        )
        for palavra in contexto.grade_palavras.consultar(_caixa_de(triangulo))
    )


def _coberto_por_wipeout(contexto: ContextoGramatica, garfo: _Garfo) -> bool:
    """Preenchimento branco opaco desenhado depois, por cima do garfo inteiro: não aparece."""
    modelo = contexto.pagina.modelo
    pontos = (garfo.vertice, *garfo.pontas)
    ordem = max(modelo.caminhos[s.caminho].ordem for s in (garfo.haste, *garfo.dentes))
    for posicao in contexto.grade_caminhos.consultar(_caixa_de(pontos)):
        desenho = modelo.caminhos[posicao]
        branco = desenho.estilo.preenchimento
        caixa = contexto.caixas_caminhos[posicao]
        if (
            desenho.ordem > ordem
            and desenho.tipo != "traco"
            and branco is not None
            and min(branco) >= _BRANCO
            and posicao not in contexto.pagina.translucidos
            and all(caixa[0] <= x <= caixa[2] and caixa[1] <= y <= caixa[3] for x, y in pontos)
        ):
            return True
    return False


def _garfo_em(
    contexto: ContextoGramatica, pontas: _Pontas, haste: _Traco, vertice: Ponto, base: Ponto
) -> _Garfo | None:
    modelo = contexto.pagina.modelo
    s = haste.segmento
    raios: list[_Raio] = []
    for raio in pontas.em(vertice):
        outro = raio.traco.segmento
        if (
            outro != s
            and not _mesmo_traco(outro, s)
            and _mesmo_estilo(modelo, outro.caminho, s.caminho)
            and not any(_mesmo_traco(outro, r.traco.segmento) for r in raios)
        ):
            raios.append(raio)
            if len(raios) > 2:
                return None
    if len(raios) != 2 or not _abre_para_longe(haste, vertice, base, raios):
        return None
    garfo = _Garfo(
        s,
        (raios[0].traco.segmento, raios[1].traco.segmento),
        vertice,
        base,
        (raios[0].longe, raios[1].longe),
        modelo.caminhos[s.caminho].estilo.cor,
        (raios[0].traco.comprimento + raios[1].traco.comprimento) / 2,
    )
    extensao = _unitario(base, vertice)
    direcoes = (_unitario(vertice, ponta) for ponta in garfo.pontas)
    if (
        extensao is None
        or _continua_em(contexto, garfo, vertice, extensao)
        or any(
            d is None or _continua_em(contexto, garfo, ponta, d)
            for ponta, d in zip(garfo.pontas, direcoes, strict=True)
        )
        or _tem_texto_dentro(contexto, garfo)
        or _coberto_por_wipeout(contexto, garfo)
    ):
        return None
    return garfo


def _garfos(contexto: ContextoGramatica, perfil: tuple[float, float]) -> list[_Garfo]:
    tracos = _tracos_finos(contexto, perfil)
    pontas = _Pontas(contexto.orcamento)
    for traco in tracos:
        pontas.inserir(traco)
    achados: list[_Garfo] = []
    for haste in tracos:
        contexto.orcamento.gastar()
        if not perfil[0] <= haste.comprimento <= perfil[1]:
            continue
        s = haste.segmento
        for vertice, base in ((s.a, s.b), (s.b, s.a)):
            garfo = _garfo_em(contexto, pontas, haste, vertice, base)
            if garfo is not None:
                achados.append(garfo)
    return achados


def _centro(pontos: Sequence[Ponto]) -> Ponto:
    return (sum(p[0] for p in pontos) / len(pontos), sum(p[1] for p in pontos) / len(pontos))


def _chave_de_cor(cor: Cor | None) -> object:
    """A chave do grupo de `_mesma_cor`: cor canônica, ou os canais de um tom fora delas."""
    return cor_canonica(cor, None) or (None if cor is None else tuple(round(c, 2) for c in cor))


class _ContornosPorCor:
    """Os contornos de cada cor numa grade própria, para que a envolvente seja sempre a menor
    da cor do garfo, e não a de outro desenho (Review Focus 5). Cada grade é paga uma vez."""

    def __init__(self, contexto: ContextoGramatica, contornos: GradeEspacial[Contorno]) -> None:
        self._contexto = contexto
        self._contornos = contornos
        self._grades: dict[object, GradeEspacial[Contorno]] = {}

    def da_cor(self, cor: Cor | None) -> GradeEspacial[Contorno]:
        chave = _chave_de_cor(cor)
        if chave not in self._grades:
            modelo = self._contexto.pagina.modelo
            limites: Caixa = (
                -_MARGEM_PAGINA,
                -_MARGEM_PAGINA,
                modelo.largura + _MARGEM_PAGINA,
                modelo.altura + _MARGEM_PAGINA,
            )
            # O filtro percorre todos os contornos da página, uma vez por cor de garfo.
            self._contexto.orcamento.gastar(len(self._contornos.itens))
            da_cor = (
                (c.caixa, c)
                for c in self._contornos.itens
                if _mesma_cor(modelo.caminhos[c.caminhos[0]].estilo.cor, cor)
            )
            self._grades[chave] = GradeEspacial(da_cor, limites, self._contexto.orcamento)
        return self._grades[chave]


def _classificar(
    contexto: ContextoGramatica, contornos: _ContornosPorCor, garfo: _Garfo
) -> tuple[CandidatoEstai, tuple[int, int]] | None:
    """O candidato do garfo (a envolvente da cor dele e o X) e a prioridade na deduplicação."""
    proprios = (garfo.haste, *garfo.dentes)
    caminhos = frozenset(s.caminho for s in proprios)
    exigidos = (garfo.vertice, *garfo.pontas)
    achada = envolvente(
        contornos.da_cor(garfo.cor), exigidos, garfo.escala, _centro(exigidos), caminhos
    )
    pictograma = _caixa_de(exigidos) if achada is None else achada.caixa
    x = tem_x(contexto, pictograma, garfo.escala, angulo(garfo.haste), frozenset(proprios))
    if x is None and achada is None and not _preto_ou_cinza(garfo.cor):
        return None
    ancora = garfo.haste.caminho
    outros = {d.caminho for d in garfo.dentes}
    if achada is not None:
        outros.update(achada.caminhos)
    if x is not None:
        outros.update(braco.caminho for braco in x)
    cantos = ((pictograma[0], pictograma[1]), (pictograma[2], pictograma[3]))
    caixa = _caixa_de((*cantos, garfo.haste.a, garfo.haste.b))
    candidato = CandidatoEstai(
        contexto,
        caixa,
        ancora,
        tuple(sorted(outros - {ancora})),
        "none" if achada is None else "ellipse",
        x is not None,
    )
    return candidato, (int(x is not None), int(achada is not None))


def _deduplicar(
    lidos: Sequence[tuple[_Garfo, CandidatoEstai, tuple[int, int]]],
    orcamento: OrcamentoConsultas,
) -> tuple[CandidatoEstai, ...]:
    """Um garfo por vértice: o desenho sobreposto em duas cores é um estai só.

    Fica o da marca mais forte, o X antes da envolvente, e o mais antigo na ordem do caminho.
    """
    escolhidos: list[tuple[_Garfo, CandidatoEstai]] = []
    por_celula: dict[tuple[int, int], list[int]] = {}
    ordem = sorted(lidos, key=lambda item: (-item[2][0], -item[2][1], item[1].caminho_ancora))
    for garfo, candidato, _ in ordem:
        cx = math.floor(garfo.vertice[0] / _MESMO_GARFO)
        cy = math.floor(garfo.vertice[1] / _MESMO_GARFO)
        vizinhos = [
            i
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for i in por_celula.get((cx + dx, cy + dy), ())
        ]
        orcamento.gastar(1 + len(vizinhos))
        if any(
            math.dist(escolhidos[i][0].vertice, garfo.vertice) <= _MESMO_GARFO for i in vizinhos
        ):
            continue
        por_celula.setdefault((cx, cy), []).append(len(escolhidos))
        escolhidos.append((garfo, candidato))
    return tuple(candidato for _, candidato in escolhidos)


def estai_candidatos(
    contexto: ContextoGramatica, *, marcas: MarcasDaPagina | None = None
) -> tuple[CandidatoEstai, ...]:
    """Os estais da página, cada um classificado uma vez (R-E06.3.4-5)."""
    marcas = marcas_do_contexto(contexto, marcas)
    garfos = _garfos(contexto, _HASTE[marcas.origem])
    if not garfos:
        return ()
    contornos = _ContornosPorCor(contexto, marcas.contornos)
    lidos: list[tuple[_Garfo, CandidatoEstai, tuple[int, int]]] = []
    for garfo in garfos:
        contexto.orcamento.gastar()
        classificado = _classificar(contexto, contornos, garfo)
        if classificado is not None:
            lidos.append((garfo, *classificado))
    return _deduplicar(lidos, contexto.orcamento)


def casa_estai(
    contexto: ContextoGramatica,
    gramatica: Mapping[str, Any],
    *,
    candidatos: tuple[CandidatoEstai, ...],
) -> list[tuple[Caixa, int, tuple[int, ...]]]:
    """(caixa, caminho da haste, demais caminhos) dos candidatos que são desta variante.

    Com `removal_mark`, o grupo é o do X, com ou sem círculo: X vence a envolvente. Cada candidato
    examinado gasta 1.
    """
    if any(candidato.contexto is not contexto for candidato in candidatos):
        raise ValueError("Candidato de estai de outro contexto de gramáticas.")
    quer_x = bool(gramatica["removal_mark"])
    enclosure = str(gramatica["enclosure"])
    limite = float(gramatica["max_span"])
    achados: list[tuple[Caixa, int, tuple[int, ...]]] = []
    for candidato in candidatos:
        contexto.orcamento.gastar()
        caixa = candidato.caixa
        if (
            candidato.removal_mark == quer_x
            and (quer_x or candidato.enclosure == enclosure)
            and max(caixa[2] - caixa[0], caixa[3] - caixa[1]) <= limite
        ):
            achados.append((caixa, candidato.caminho_ancora, candidato.componentes))
    return achados
