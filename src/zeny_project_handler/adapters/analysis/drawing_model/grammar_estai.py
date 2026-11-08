"""Gramática do estai (haste com garfo, `forked_stem`) sobre a página do modelo de desenho.

Cada traço fino, contínuo e de cor de símbolo é semente de haste. Uma ponta dela é o vértice do
garfo quando ali chegam exatamente mais dois traços da mesma cor, abertos para longe da haste
(dentes a cerca de 15 a 40 graus dela, um de cada lado). O desenho que continua além do vértice ou
das pontas dos dentes (ramal de condutor, pé de galinha de cerca) não é garfo. A envolvente e o X
vêm de `grammar_marcas`; quem tem X é o grupo de retirada, com ou sem círculo (R-E06.3.4-1). Garfo
verde ou vermelho sem marca não se afirma existente: sai sem casamento (R-E06.3.4-2). A caixa
(R-E06.3.4-3, alternativa de melhor IoU no laboratório) une o pictograma (a envolvente da cor do
garfo ou, sem ela, o próprio garfo) e a haste inteira; o X fica de fora.

Só o garfo verde com círculo da mesma cor é "instalar" (R-E06.3.4-2): preto ou vermelho com círculo
é recusado. Cada X e cada envolvente é de um garfo só, o mais próximo. Seta fechada, cota com duas
extensões, chevrons em linha, linha de chamada saindo de texto e haste com garfo nas duas pontas
não são estai.
"""

from __future__ import annotations

import math
from collections import Counter
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
_CELULA_VERTICE: Final = _TOLERANCIA_VERTICE
_MESMO_GARFO: Final = 0.5
_MESMO_TRACO: Final = 0.35
_BRANCO: Final = 0.9
_VERDE: Final = "#008000"
_SEM_MARCA: Final = "sem_marca"
# Contorno com mais trechos que isto, ou fechado, é envolvente ou moldura, não condutor.
_TRECHOS_DE_CONTORNO: Final = 6
_FECHAMENTO: Final = 0.5
# Cota: extensão perpendicular, mais longa que a abertura do garfo, com o meio perto da ponta.
_EXTENSAO_DE_COTA: Final = 1.5
_PERPENDICULAR: Final = 0.3
_MEIO_DA_EXTENSAO: Final = 4.0
# Seta fechada: a tampa liga as pontas dos dentes, com esta folga e relativa à abertura.
_TAMPA: Final = (0.5, 0.08)
_PREENCHE_TRIANGULO: Final = 0.7
# Chevrons: outro vértice sobre o eixo, à frente, até este múltiplo da haste.
_ALCANCE_CHEVRON: Final = 2.5
_DESVIO_DO_EIXO: Final = 0.5
_ALCANCE_TEXTO: Final = 0.5
_MESMA_DIRECAO: Final = math.cos(math.radians(15))


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
        vistos = [
            raio
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for raio in self._celulas.get((cx + dx, cy + dy), ())
        ]
        # Cada raio examinado paga, perto ou não: o trabalho é o das células percorridas.
        self._orcamento.gastar(len(vistos))
        return [raio for raio in vistos if math.dist(raio.perto, ponto) <= _TOLERANCIA_VERTICE]


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


def _contorno(caminho: Caminho) -> bool:
    """Envolvente ou moldura (fechada, ou de muitos trechos), ou caminho de vários subcaminhos.

    Um condutor em polilinha aberta, de poucos trechos, não é contorno: pode ser a continuação.
    """
    if len(caminho.subcaminhos) != 1:
        return True
    itens = caminho.subcaminhos[0]
    if len(itens) == 1:
        return False
    return len(itens) > _TRECHOS_DE_CONTORNO or (
        math.dist(itens[0].pontos[0], itens[-1].pontos[-1]) <= _FECHAMENTO
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
            or _contorno(modelo.caminhos[s.caminho])
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


def _aneis(caminho: Caminho) -> list[list[Ponto]]:
    """Os pontos de cada subcaminho, na ordem; curvas entram pelos pontos de controle."""
    return [[ponto for item in sub for ponto in item.pontos] for sub in caminho.subcaminhos]


def _dentro_do_caminho(ponto: Ponto, aneis: Sequence[Sequence[Ponto]]) -> bool:
    """Regra par-ímpar sobre todos os anéis: a área pintada do preenchimento, não a caixa."""
    dentro = False
    for anel in aneis:
        for (x1, y1), (x2, y2) in zip(anel, (*anel[1:], anel[0]), strict=True):
            if (y1 > ponto[1]) != (y2 > ponto[1]) and (
                ponto[0] < (x2 - x1) * (ponto[1] - y1) / (y2 - y1) + x1
            ):
                dentro = not dentro
    return dentro


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
            aneis = _aneis(desenho)
            # Cada aresta examinada paga: a máscara de muitos vértices não sai de graça.
            contexto.orcamento.gastar(sum(len(anel) for anel in aneis) * len(pontos))
            if all(_dentro_do_caminho(ponto, aneis) for ponto in pontos):
                return True
    return False


def _cota_com_extensoes(contexto: ContextoGramatica, garfo: _Garfo) -> bool:
    """Uma linha de extensão perpendicular em cada ponta do eixo é cota, não estai."""
    modelo = contexto.pagina.modelo
    direcao = _unitario(garfo.base, garfo.vertice)
    if direcao is None:
        return False
    abertura = math.dist(*garfo.pontas)
    proprios = (garfo.haste, *garfo.dentes)
    camada = modelo.caminhos[garfo.haste.caminho].estilo.camada

    def tem_extensao(ponta: Ponto) -> bool:
        for s in contexto.grade_segmentos.consultar(_em_torno(ponta, _MEIO_DA_EXTENSAO)):
            unitario = _unitario(s.a, s.b)
            meio = ((s.a[0] + s.b[0]) / 2, (s.a[1] + s.b[1]) / 2)
            if (
                s not in proprios
                and unitario is not None
                and modelo.caminhos[s.caminho].estilo.camada == camada
                and math.dist(s.a, s.b) >= abertura * _EXTENSAO_DE_COTA
                and abs(direcao[0] * unitario[0] + direcao[1] * unitario[1]) < _PERPENDICULAR
                and math.dist(meio, ponta) <= _MEIO_DA_EXTENSAO
            ):
                return True
        return False

    return tem_extensao(garfo.base) and tem_extensao(garfo.vertice)


def _seta_fechada(contexto: ContextoGramatica, garfo: _Garfo) -> bool:
    """Uma tampa entre as pontas dos dentes, ou o triângulo preenchido, fecha a seta."""
    modelo = contexto.pagina.modelo
    primeira, segunda = garfo.pontas
    folga = max(_TAMPA[0], math.dist(primeira, segunda) * _TAMPA[1])
    proprios = (garfo.haste, *garfo.dentes)
    for s in contexto.grade_segmentos.consultar(_em_torno(primeira, folga)):
        if s not in proprios and (
            (math.dist(s.a, primeira) <= folga and math.dist(s.b, segunda) <= folga)
            or (math.dist(s.b, primeira) <= folga and math.dist(s.a, segunda) <= folga)
        ):
            return True
    triangulo = _caixa_de((garfo.vertice, *garfo.pontas))
    for posicao in contexto.grade_caminhos.consultar(triangulo):
        caixa = contexto.caixas_caminhos[posicao]
        if (
            modelo.caminhos[posicao].estilo.preenchimento is not None
            and all(
                triangulo[i] - folga <= caixa[i] and caixa[i + 2] <= triangulo[i + 2] + folga
                for i in (0, 1)
            )
            and all(
                caixa[i + 2] - caixa[i] >= _PREENCHE_TRIANGULO * (triangulo[i + 2] - triangulo[i])
                for i in (0, 1)
            )
        ):
            return True
    return False


def _chevron_a_frente(contexto: ContextoGramatica, pontas: _Pontas, garfo: _Garfo) -> bool:
    """Outro vértice de dois traços sobre o eixo, à frente: chevrons em linha, não estai."""
    modelo = contexto.pagina.modelo
    extensao = _unitario(garfo.base, garfo.vertice)
    if extensao is None:
        return False
    vertice = garfo.vertice
    alcance = math.dist(garfo.base, vertice) * _ALCANCE_CHEVRON
    fim = (vertice[0] + extensao[0] * alcance, vertice[1] + extensao[1] * alcance)
    proprios = (garfo.haste, *garfo.dentes)
    for s in contexto.grade_segmentos.consultar(_caixa_de((vertice, fim))):
        if s in proprios or not _mesmo_estilo(modelo, s.caminho, garfo.haste.caminho):
            continue
        for ponto in (s.a, s.b):
            dx, dy = ponto[0] - vertice[0], ponto[1] - vertice[1]
            ao_longo = dx * extensao[0] + dy * extensao[1]
            desvio = abs(dx * extensao[1] - dy * extensao[0])
            if not (_DESVIO_DO_EIXO < ao_longo <= alcance and desvio <= _DESVIO_DO_EIXO):
                continue
            direcoes = {
                (round(r.longe[0], 1), round(r.longe[1], 1))
                for r in pontas.em(ponto)
                if r.traco.segmento not in proprios
                and _mesmo_estilo(modelo, r.traco.segmento.caminho, garfo.haste.caminho)
            }
            if len(direcoes) >= 2:
                return True
    return False


def _nasce_em_texto(contexto: ContextoGramatica, garfo: _Garfo) -> bool:
    """A haste que nasce dentro da caixa de um texto é linha de chamada, não estai."""
    x, y = garfo.base
    return any(
        palavra.caixa[0] - _ALCANCE_TEXTO <= x <= palavra.caixa[2] + _ALCANCE_TEXTO
        and palavra.caixa[1] - _ALCANCE_TEXTO <= y <= palavra.caixa[3] + _ALCANCE_TEXTO
        for palavra in contexto.grade_palavras.consultar(_em_torno(garfo.base, _ALCANCE_TEXTO))
    )


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
        or _nasce_em_texto(contexto, garfo)
        or _seta_fechada(contexto, garfo)
        or _cota_com_extensoes(contexto, garfo)
        or _chevron_a_frente(contexto, pontas, garfo)
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
    # Um traço com garfo nas duas pontas é cota de setas, não dois estais sobre a mesma haste.
    hastes = Counter(garfo.haste for garfo in achados)
    return [garfo for garfo in achados if hastes[garfo.haste] == 1]


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


@dataclass(frozen=True, slots=True)
class _Marca:
    """Um X ou uma envolvente que um garfo reivindica: os caminhos dela e o centro."""

    caminhos: frozenset[int]
    centro: Ponto
    segmentos: frozenset[Segmento]


@dataclass(frozen=True, slots=True)
class _Leitura:
    garfo: _Garfo
    candidato: CandidatoEstai
    prioridade: tuple[int, int, int]
    x: _Marca | None
    circulo: _Marca | None


def _classificar(
    contexto: ContextoGramatica,
    contornos: _ContornosPorCor,
    garfo: _Garfo,
    perdidos: frozenset[Segmento],
    sem_circulo: bool,
) -> _Leitura:
    """A leitura do garfo: a envolvente da cor dele, o X e a prioridade na deduplicação.

    Os braços de X em `perdidos` são de um garfo mais próximo e não contam; `sem_circulo` tira a
    envolvente que outro garfo mais próximo ficou. Só o garfo verde com círculo verde é "instalar";
    preto ou vermelho com círculo e garfo colorido sem marca ficam como `sem_marca` (R-E06.3.4-2).
    """
    proprios = (garfo.haste, *garfo.dentes)
    caminhos = frozenset(s.caminho for s in proprios)
    exigidos = (garfo.vertice, *garfo.pontas)
    achada = (
        None
        if sem_circulo
        else envolvente(
            contornos.da_cor(garfo.cor), exigidos, garfo.escala, _centro(exigidos), caminhos
        )
    )
    pictograma = _caixa_de(exigidos) if achada is None else achada.caixa
    x = tem_x(
        contexto,
        pictograma,
        garfo.escala,
        angulo(garfo.haste),
        frozenset(proprios) | perdidos,
    )
    verde = cor_canonica(garfo.cor, None) == _VERDE
    ancora = garfo.haste.caminho
    outros = {d.caminho for d in garfo.dentes}
    if achada is not None and (verde or x is not None):
        outros.update(achada.caminhos)
    if x is not None:
        outros.update(braco.caminho for braco in x)
    cantos = ((pictograma[0], pictograma[1]), (pictograma[2], pictograma[3]))
    caixa = _caixa_de((*cantos, garfo.haste.a, garfo.haste.b))
    ha_circulo = achada is not None
    if x is None and (
        (not ha_circulo and not _preto_ou_cinza(garfo.cor)) or (ha_circulo and not verde)
    ):
        enclosure = _SEM_MARCA
    else:
        enclosure = "ellipse" if ha_circulo else "none"
    candidato = CandidatoEstai(
        contexto,
        caixa,
        ancora,
        tuple(sorted(outros - {ancora})),
        enclosure,
        x is not None,
    )
    marca_x = None
    if x is not None:
        pontos = [p for braco in x for p in (braco.a, braco.b)]
        marca_x = _Marca(frozenset(b.caminho for b in x), _centro(pontos), frozenset(x))
    circulo = None
    if achada is not None and enclosure == "ellipse":
        c = achada.caixa
        circulo = _Marca(
            frozenset(achada.caminhos), ((c[0] + c[2]) / 2, (c[1] + c[3]) / 2), frozenset()
        )
    prioridade = (int(x is not None), int(enclosure == "ellipse"), int(enclosure != _SEM_MARCA))
    return _Leitura(garfo, candidato, prioridade, marca_x, circulo)


def _mesmo_desenho(a: _Garfo, b: _Garfo) -> bool:
    """Mesmo vértice e mesma direção da haste: o desenho sobreposto em duas cores."""
    ua, ub = _unitario(a.base, a.vertice), _unitario(b.base, b.vertice)
    return (
        math.dist(a.vertice, b.vertice) <= _MESMO_GARFO
        and ua is not None
        and ub is not None
        and ua[0] * ub[0] + ua[1] * ub[1] >= _MESMA_DIRECAO
    )


def _deduplicar(
    lidos: Sequence[_Leitura], orcamento: OrcamentoConsultas
) -> tuple[CandidatoEstai, ...]:
    """Um garfo por vértice e direção: o desenho sobreposto em duas cores é um estai só.

    Fica o da marca mais forte, o X antes da envolvente, e o mais antigo na ordem do caminho.
    """
    escolhidos: list[_Garfo] = []
    candidatos: list[CandidatoEstai] = []
    por_celula: dict[tuple[int, int], list[int]] = {}
    ordem = sorted(
        lidos, key=lambda item: ([-n for n in item.prioridade], item.candidato.caminho_ancora)
    )
    for leitura in ordem:
        garfo = leitura.garfo
        cx = math.floor(garfo.vertice[0] / _MESMO_GARFO)
        cy = math.floor(garfo.vertice[1] / _MESMO_GARFO)
        vizinhos = [
            i
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for i in por_celula.get((cx + dx, cy + dy), ())
        ]
        orcamento.gastar(1 + len(vizinhos))
        if any(_mesmo_desenho(escolhidos[i], garfo) for i in vizinhos):
            continue
        por_celula.setdefault((cx, cy), []).append(len(escolhidos))
        escolhidos.append(garfo)
        candidatos.append(leitura.candidato)
    return tuple(candidatos)


def _centro_do_garfo(garfo: _Garfo) -> Ponto:
    return _centro((garfo.vertice, *garfo.pontas))


def _disputar(lidos: Sequence[_Leitura], perdas: list[tuple[frozenset[Segmento], bool]]) -> bool:
    """Cada X e cada envolvente é do garfo mais próximo; devolve se algum garfo perdeu marca.

    O desempate é o caminho da haste, o mais antigo. O que cada perdedor perdeu fica em `perdas`
    (braços de X, e se perdeu a envolvente) para ser lido de novo sem a marca.
    """
    pretensoes: dict[tuple[bool, frozenset[int]], list[tuple[float, int, int]]] = {}
    for i, leitura in enumerate(lidos):
        for marca, eh_x in ((leitura.x, True), (leitura.circulo, False)):
            if marca is not None:
                distancia = math.dist(marca.centro, _centro_do_garfo(leitura.garfo))
                pretensoes.setdefault((eh_x, marca.caminhos), []).append(
                    (distancia, leitura.candidato.caminho_ancora, i)
                )
    mudou = False
    for (eh_x, _), pretendentes in pretensoes.items():
        pretendentes.sort()
        for _, _, i in pretendentes[1:]:
            segmentos, sem_circulo = perdas[i]
            marca_x = lidos[i].x
            if eh_x and marca_x is not None:
                perdas[i] = (segmentos | marca_x.segmentos, sem_circulo)
            else:
                perdas[i] = (segmentos, True)
            mudou = True
    return mudou


def estai_candidatos(
    contexto: ContextoGramatica, *, marcas: MarcasDaPagina | None = None
) -> tuple[CandidatoEstai, ...]:
    """Os estais da página, cada um classificado uma vez (R-E06.3.4-5)."""
    marcas = marcas_do_contexto(contexto, marcas)
    garfos = _garfos(contexto, _HASTE[marcas.origem])
    if not garfos:
        return ()
    contornos = _ContornosPorCor(contexto, marcas.contornos)
    perdas: list[tuple[frozenset[Segmento], bool]] = [(frozenset(), False)] * len(garfos)
    lidos: list[_Leitura] = []
    for garfo in garfos:
        contexto.orcamento.gastar()
        lidos.append(_classificar(contexto, contornos, garfo, frozenset(), False))
    # Cada rodada tira as marcas de quem perdeu a disputa; só esses garfos são lidos de novo, e a
    # perda só cresce, então a disputa termina.
    while True:
        antes = list(perdas)
        if not _disputar(lidos, perdas):
            break
        for i, (segmentos, sem_circulo) in enumerate(perdas):
            if perdas[i] != antes[i]:
                contexto.orcamento.gastar()
                lidos[i] = _classificar(contexto, contornos, garfos[i], segmentos, sem_circulo)
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
