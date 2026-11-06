"""Núcleo puro das gramáticas de símbolos sobre a página do modelo de desenho.

Sem PyMuPDF: um índice por grade e um orçamento de consultas determinístico substituem os laços
sobre a página inteira do motor `declarative_symbols`, de quem os limiares são copiados.
"""

from __future__ import annotations

import math
import re
from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final, Generic, Literal, TypeVar

from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Arco,
    Caixa,
    Caminho,
    Circulo,
    ItemCaminho,
    PaginaModelo,
    Polilinha,
    Ponto,
    TextoModelo,
)

T = TypeVar("T")

LIMITE_CONSULTAS_PAGINA: Final = 2_000_000

_CELULA: Final = 16.0
_MAXIMO_CELULAS: Final = 64
_MARGEM_PAGINA: Final = 16.0
_TOLERANCIA_ALINHAMENTO: Final = 0.01
_LADO_MINIMO_LOSANGO: Final = 4.0
_TOLERANCIA_MINIMA_LOSANGO: Final = 1.0
_TOLERANCIA_RELATIVA_LOSANGO: Final = 0.08
_PONTAS_POR_CANTO: Final = 2
_TOLERANCIA_HORIZONTAL_GRAUS: Final = 1.0
_LACUNA_MINIMA_COLADOS: Final = 0.5
_LACUNA_RELATIVA_COLADOS: Final = 0.2
_SOBREPOSICAO_VERTICAL_COLADOS: Final = 0.5

_FONTES_CONSUMIDAS: Final = frozenset(
    {
        "modelo.caminhos_falhou",
        "modelo.primitivas_falhou",
        "modelo.textos_nativos_falhou",
        "modelo.textos_shx_falhou",
        "modelo.glifos_falhou",
    }
)
_GLIFOS_LIMITADOS: Final = "modelo.glifos_limitados"

_PALAVRA: Final = re.compile(r"\S+")

_Forma = Literal["retangulo", "elipse", "losango"]
_Lado = tuple[Ponto, Ponto]


class TetoGramaticasExcedido(Exception):  # noqa: N818
    """A página gastou mais consultas que o limite, ou tem texto de glifo parcial."""


class FonteGramaticaFalhou(Exception):  # noqa: N818
    """Uma fonte que o núcleo consome falhou: a página vazia seria uma não detecção falsa."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo


@dataclass(frozen=True, slots=True)
class PaginaGramatica:
    """A página do modelo e o que falta nela; `indices_crus` e `translucidos` falam da posição
    do caminho em `modelo.caminhos`."""

    modelo: PaginaModelo
    indices_crus: tuple[int, ...]
    translucidos: frozenset[int]

    def __post_init__(self) -> None:
        if len(self.indices_crus) != len(self.modelo.caminhos):
            raise ValueError("indices_crus precisa ter um índice por caminho do modelo.")


class OrcamentoConsultas:
    """Contador determinístico de trabalho da página."""

    def __init__(self, limite: int) -> None:
        self._limite = limite
        self.gasto = 0

    def gastar(self, quantidade: int = 1) -> None:
        self.gasto += quantidade
        if self.gasto > self._limite:
            raise TetoGramaticasExcedido(
                f"Gasto de {self.gasto} consultas acima do limite de {self._limite}."
            )


class GradeEspacial(Generic[T]):
    """Índice por células, que devolve candidatos: quem consulta confere a geometria.

    Só indexa a parte da caixa dentro de `limites`, e uma caixa que cobriria mais de
    `_MAXIMO_CELULAS` células vai para `_grandes`, percorrida em toda consulta: coordenada
    enorme não multiplica entradas na grade.
    """

    def __init__(
        self, itens: Iterable[tuple[Caixa, T]], limites: Caixa, orcamento: OrcamentoConsultas
    ) -> None:
        self._limites = limites
        self._orcamento = orcamento
        self._itens: list[T] = []
        self._celulas: dict[tuple[int, int], list[int]] = {}
        self._grandes: list[int] = []
        for caixa, item in itens:
            recorte = self._recortar(caixa)
            if recorte is None:
                continue
            orcamento.gastar()
            indice = len(self._itens)
            self._itens.append(item)
            celulas = _celulas_de(recorte)
            if celulas is None:
                self._grandes.append(indice)
                continue
            for celula in celulas:
                self._celulas.setdefault(celula, []).append(indice)

    def _recortar(self, caixa: Caixa) -> Caixa | None:
        x0, y0 = max(caixa[0], self._limites[0]), max(caixa[1], self._limites[1])
        x1, y1 = min(caixa[2], self._limites[2]), min(caixa[3], self._limites[3])
        return (x0, y0, x1, y1) if x0 <= x1 and y0 <= y1 else None

    def _candidatos(self, caixa: Caixa) -> Sequence[int]:
        recorte = self._recortar(caixa)
        if recorte is None:
            return self._grandes
        celulas = _celulas_de(recorte)
        if celulas is None:
            return range(len(self._itens))
        candidatos = {i for celula in celulas for i in self._celulas.get(celula, ())}
        candidatos.update(self._grandes)
        return sorted(candidatos)

    def consultar(self, caixa: Caixa) -> list[T]:
        """Candidatos em ordem de inserção, sem repetir; cada um gasta 1 do orçamento."""
        candidatos = self._candidatos(caixa)
        self._orcamento.gastar(len(candidatos))
        return [self._itens[indice] for indice in candidatos]


def _celulas_de(caixa: Caixa) -> list[tuple[int, int]] | None:
    """Células da caixa já recortada, ou None acima do teto."""
    x0, y0, x1, y1 = (math.floor(valor / _CELULA) for valor in caixa)
    if (x1 - x0 + 1) * (y1 - y0 + 1) > _MAXIMO_CELULAS:
        return None
    return [(cx, cy) for cx in range(x0, x1 + 1) for cy in range(y0, y1 + 1)]


@dataclass(frozen=True, slots=True)
class Moldura:
    forma: _Forma
    caixa: Caixa
    caminho: int


@dataclass(frozen=True, slots=True)
class Segmento:
    a: Ponto
    b: Ponto
    caminho: int


@dataclass(frozen=True, slots=True)
class Palavra:
    """A caixa é a do span inteiro (R-E06.2.1-4); `inteira` marca o span que tem mais que a
    palavra, com várias palavras ou espaços nas pontas, e a palavra de spans fundidos."""

    texto: str
    caixa: Caixa
    inteira: bool


@dataclass(frozen=True, slots=True)
class ContextoGramatica:
    pagina: PaginaGramatica
    orcamento: OrcamentoConsultas
    molduras: tuple[Moldura, ...]
    grade_molduras: GradeEspacial[Moldura]
    grade_palavras: GradeEspacial[Palavra]
    grade_segmentos: GradeEspacial[Segmento]
    grade_caminhos: GradeEspacial[int]
    caixas_caminhos: Mapping[int, Caixa]


def _tem_area(caixa: Caixa) -> bool:
    return caixa[0] < caixa[2] and caixa[1] < caixa[3]


def contem(externa: Caixa, interna: Caixa) -> bool:
    """Borda fechada; caixa de lado 0 não contém nada, mas pode estar contida."""
    return (
        _tem_area(externa)
        and externa[0] <= interna[0]
        and externa[1] <= interna[1]
        and interna[2] <= externa[2]
        and interna[3] <= externa[3]
    )


def intersecta(a: Caixa, b: Caixa) -> bool:
    """Comparação estrita, como `Rect.intersects`: encostar não conta, nem caixa de lado 0."""
    return (
        _tem_area(a)
        and _tem_area(b)
        and a[0] < b[2]
        and b[0] < a[2]
        and a[1] < b[3]
        and b[1] < a[3]
    )


def sobrepoe(a: Caixa, b: Caixa) -> bool:
    """Sobreposição fechada, das guardas: encostar conta e caixa de lado 0 também, ao contrário
    de `intersecta`."""
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def ponto_em(caixa: Caixa, ponto: Ponto) -> bool:
    """Borda fechada."""
    return caixa[0] <= ponto[0] <= caixa[2] and caixa[1] <= ponto[1] <= caixa[3]


def _caixa_de_pontos(pontos: Iterable[Ponto]) -> Caixa | None:
    """Caixa dos pontos; None sem pontos ou com coordenada não finita."""
    lista = list(pontos)
    if not lista or not all(math.isfinite(x) and math.isfinite(y) for x, y in lista):
        return None
    xs = [x for x, _ in lista]
    ys = [y for _, y in lista]
    return (min(xs), min(ys), max(xs), max(ys))


# --- molduras e segmentos -----------------------------------------------------------------


def _encadeados(lados: Sequence[_Lado], tolerancia: float) -> bool:
    """Cada lado começa onde o anterior termina, e o último volta ao primeiro."""
    return all(
        math.dist(lado[1], lados[(i + 1) % len(lados)][0]) <= tolerancia
        for i, lado in enumerate(lados)
    )


def _lados_alternam_eixos(lados: Sequence[_Lado]) -> bool:
    horizontais = [abs(b[1] - a[1]) <= _TOLERANCIA_ALINHAMENTO for a, b in lados]
    verticais = [abs(b[0] - a[0]) <= _TOLERANCIA_ALINHAMENTO for a, b in lados]
    return (horizontais[0] and verticais[1] and horizontais[2] and verticais[3]) or (
        verticais[0] and horizontais[1] and verticais[2] and horizontais[3]
    )


def _tolerancia_losango(caixa: Caixa) -> float:
    menor_lado = min(caixa[2] - caixa[0], caixa[3] - caixa[1])
    return max(_TOLERANCIA_MINIMA_LOSANGO, menor_lado * _TOLERANCIA_RELATIVA_LOSANGO)


def _is_diamond(pontas: Sequence[Ponto], caixa: Caixa) -> bool:
    if caixa[2] - caixa[0] < _LADO_MINIMO_LOSANGO or caixa[3] - caixa[1] < _LADO_MINIMO_LOSANGO:
        return False
    meio_x, meio_y = (caixa[0] + caixa[2]) / 2, (caixa[1] + caixa[3]) / 2
    cantos = ((meio_x, caixa[1]), (caixa[2], meio_y), (meio_x, caixa[3]), (caixa[0], meio_y))
    tolerancia = _tolerancia_losango(caixa)
    return all(
        sum(math.dist(ponta, canto) <= tolerancia for ponta in pontas) == _PONTAS_POR_CANTO
        for canto in cantos
    )


def _forma_dos_lados(lados: Sequence[_Lado], caixa: Caixa) -> _Forma | None:
    """Forma de 4 lados: "fechado" é retângulo em 0,01 pt, e losango na tolerância do motor."""
    if _encadeados(lados, _TOLERANCIA_ALINHAMENTO) and _lados_alternam_eixos(lados):
        return "retangulo"
    pontas = [ponto for lado in lados for ponto in lado]
    if _encadeados(lados, _tolerancia_losango(caixa)) and _is_diamond(pontas, caixa):
        return "losango"
    return None


def _moldura_de_lados(lados: Sequence[_Lado], caminho: int, pagina: Caixa) -> Moldura | None:
    caixa = _caixa_de_pontos(ponto for lado in lados for ponto in lado)
    if caixa is None or not intersecta(caixa, pagina):
        return None
    forma = _forma_dos_lados(lados, caixa)
    return None if forma is None else Moldura(forma, caixa, caminho)


def _moldura_do_subcaminho(
    subcaminho: Sequence[ItemCaminho], caminho: int, pagina: Caixa
) -> Moldura | None:
    if len(subcaminho) != 4 or any(item.tipo != "l" for item in subcaminho):
        return None
    return _moldura_de_lados(
        [(item.pontos[0], item.pontos[1]) for item in subcaminho], caminho, pagina
    )


def _elipse_do_caminho(caminho: Caminho, posicao: int, pagina: Caixa) -> Moldura | None:
    itens = [item for subcaminho in caminho.subcaminhos for item in subcaminho]
    if len(itens) != 4 or any(item.tipo != "c" for item in itens):
        return None
    caixa = _caixa_de_pontos(ponto for item in itens for ponto in item.pontos)
    if caixa is None or not intersecta(caixa, pagina):
        return None
    return Moldura("elipse", caixa, posicao)


def _moldura_da_primitiva(primitiva: Polilinha | Circulo | Arco, pagina: Caixa) -> Moldura | None:
    if isinstance(primitiva, Polilinha):
        if not primitiva.fechada or len(primitiva.pontos) != 4 or not primitiva.origens:
            return None
        pontos = primitiva.pontos
        lados = [(ponto, pontos[(i + 1) % 4]) for i, ponto in enumerate(pontos)]
        return _moldura_de_lados(lados, primitiva.origens[0], pagina)
    if isinstance(primitiva, Circulo):
        return _elipse_do_circulo(primitiva, pagina)
    return None


def _elipse_do_circulo(circulo: Circulo, pagina: Caixa) -> Moldura | None:
    if circulo.raio <= 0 or not circulo.origens:
        return None
    cx, cy = circulo.centro
    raio = circulo.raio
    caixa = _caixa_de_pontos(((cx - raio, cy - raio), (cx + raio, cy + raio)))
    if caixa is None or not intersecta(caixa, pagina):
        return None
    return Moldura("elipse", caixa, circulo.origens[0])


def _segmentos_do_subcaminho(subcaminho: Iterable[ItemCaminho], posicao: int) -> Iterable[Segmento]:
    for item in subcaminho:
        if item.tipo == "l" and _caixa_de_pontos(item.pontos) is not None:
            yield Segmento(item.pontos[0], item.pontos[1], posicao)


def _molduras_e_segmentos(modelo: PaginaModelo) -> tuple[tuple[Moldura, ...], list[Segmento]]:
    pagina: Caixa = (0.0, 0.0, modelo.largura, modelo.altura)
    molduras: list[Moldura] = []
    segmentos: list[Segmento] = []
    for posicao, caminho in enumerate(modelo.caminhos):
        for subcaminho in caminho.subcaminhos:
            moldura = _moldura_do_subcaminho(subcaminho, posicao, pagina)
            if moldura is None:
                segmentos.extend(_segmentos_do_subcaminho(subcaminho, posicao))
            else:
                molduras.append(moldura)
        elipse = _elipse_do_caminho(caminho, posicao, pagina)
        if elipse is not None:
            molduras.append(elipse)
    # Só o que veio do caminho descarta a primitiva (R-E06.2.1-10): duas primitivas de um
    # mesmo caminho são desenhos distintos, e a deduplicação por caixa é de `casar_variantes`.
    vindas_de_caminho = {(moldura.forma, moldura.caminho) for moldura in molduras}
    for primitiva in modelo.primitivas:
        moldura = _moldura_da_primitiva(primitiva, pagina)
        if moldura is None:
            continue
        if not all((moldura.forma, origem) in vindas_de_caminho for origem in primitiva.origens):
            molduras.append(moldura)
    return tuple(molduras), segmentos


# --- palavras -----------------------------------------------------------------------------


def _distancia_angular(rotacao: float, alvo: float) -> float:
    """Distância em graus; `rotacao` não finita dá nan, que nenhuma tolerância aceita."""
    return abs((rotacao - alvo + 180.0) % 360.0 - 180.0)


def _pode_colar(texto: TextoModelo) -> bool:
    return (
        texto.origem == "nativo"
        and _distancia_angular(texto.rotacao, 0.0) <= _TOLERANCIA_HORIZONTAL_GRAUS
        and all(math.isfinite(valor) for valor in texto.bbox)
        and _tem_area(texto.bbox)
        and bool(texto.texto)
    )


def _lacuna_maxima(altura: float) -> float:
    return max(_LACUNA_MINIMA_COLADOS, altura * _LACUNA_RELATIVA_COLADOS)


def _colados(esquerdo: TextoModelo, direito: TextoModelo) -> bool:
    """Lacuna em módulo, porque o `words` da PyMuPDF também junta o que se sobrepõe."""
    a, b = esquerdo.bbox, direito.bbox
    menor_altura = min(a[3] - a[1], b[3] - b[1])
    return (
        esquerdo.rotacao == direito.rotacao
        and abs(b[0] - a[2]) <= _lacuna_maxima(menor_altura)
        and min(a[3], b[3]) - max(a[1], b[1]) >= menor_altura * _SOBREPOSICAO_VERTICAL_COLADOS
        and not esquerdo.texto[-1].isspace()
        and not direito.texto[0].isspace()
    )


def _unir(cadeia: Sequence[TextoModelo]) -> TextoModelo:
    caixas = [texto.bbox for texto in cadeia]
    return replace(
        cadeia[0],
        texto="".join(texto.texto for texto in cadeia),
        bbox=(
            min(caixa[0] for caixa in caixas),
            min(caixa[1] for caixa in caixas),
            max(caixa[2] for caixa in caixas),
            max(caixa[3] for caixa in caixas),
        ),
        altura=max(texto.altura for texto in cadeia),
    )


def _de_menor_lacuna(textos: Sequence[TextoModelo], colados: Sequence[int], x0: float) -> int:
    return min(colados, key=lambda esquerdo: abs(x0 - textos[esquerdo].bbox[2]))


def _proximo_colado(
    textos: Sequence[TextoModelo], candidatos: Sequence[int], orcamento: OrcamentoConsultas
) -> dict[int, int]:
    """Para cada span, o span colado à direita dele: o de menor lacuna em módulo ainda livre.

    A ordem de leitura, pelo início da caixa e, no empate, pela posição na página, é estrita: só
    quem vem antes pode ser o esquerdo, e por isso a cadeia não fecha ciclo, mesmo com lacuna
    negativa, e um span contido na ponta do outro funde, como no `words` da PyMuPDF.

    Ordenados pela borda direita, só os de borda na janela da lacuna são visitados, a 1 do
    orçamento cada, antes de comparar. O gasto cresce onde as bordas se acumulam: colunas
    alinhadas, com a mesma borda em cada linha, gastam linhas por span, e não só a página hostil.
    """
    orcamento.gastar(len(candidatos))
    por_borda = sorted(candidatos, key=lambda posicao: (textos[posicao].bbox[2], posicao))
    bordas = [textos[posicao].bbox[2] for posicao in por_borda]
    por_leitura = sorted(candidatos, key=lambda posicao: (textos[posicao].bbox[0], posicao))
    ordem = {posicao: lugar for lugar, posicao in enumerate(por_leitura)}
    proximo: dict[int, int] = {}
    for posicao in por_leitura:
        direito = textos[posicao]
        x0, y0, _, y1 = direito.bbox
        folga = _lacuna_maxima(y1 - y0)
        inicio = bisect_left(bordas, x0 - folga)
        fim = bisect_right(bordas, x0 + folga)
        orcamento.gastar(fim - inicio)
        colados = [
            esquerdo
            for esquerdo in por_borda[inicio:fim]
            if ordem[esquerdo] < ordem[posicao]
            and esquerdo not in proximo
            and _colados(textos[esquerdo], direito)
        ]
        if colados:
            proximo[_de_menor_lacuna(textos, colados, x0)] = posicao
    return proximo


def _fundir_spans_colados(
    textos: Sequence[TextoModelo], orcamento: OrcamentoConsultas
) -> list[tuple[TextoModelo, bool]]:
    """Spans `nativo` horizontais colados viram um texto só, e o `bool` diz quem foi fundido.

    A tolerância é folga acima do que o `words` da PyMuPDF junta, sem emular a heurística dele
    (R-E06.2.1-4): onde o motor lê duas palavras e a fusão lê uma, o núcleo perde recall e não
    afirma nada a mais. Limitação: rotacionado não é fundido, e `shx` e `glifo` também não. O
    texto unido fica na posição do primeiro span da cadeia, e o resto da lista mantém a ordem.
    """
    candidatos = [posicao for posicao, texto in enumerate(textos) if _pode_colar(texto)]
    proximo = _proximo_colado(textos, candidatos, orcamento)
    seguintes = set(proximo.values())
    fundidos: list[tuple[TextoModelo, bool]] = []
    for posicao, texto in enumerate(textos):
        if posicao in seguintes:
            continue
        cadeia = [texto]
        while posicao in proximo:
            posicao = proximo[posicao]
            cadeia.append(textos[posicao])
        fundidos.append((_unir(cadeia), True) if len(cadeia) > 1 else (texto, False))
    return fundidos


def _palavras_do_texto(texto: TextoModelo, *, fundido: bool) -> list[Palavra]:
    """Palavras do span, todas com a caixa dele (R-E06.2.1-4), em qualquer origem e rotação.

    Nenhum span é repartido: por caracteres, a caixa só seria exata em largura fixa, e falso
    positivo é pior que perda de recall. `inteira` diz se o texto do span tem mais que a palavra
    ou se veio de spans fundidos, cuja caixa pode ser maior que a palavra que o motor lê.
    """
    if not all(math.isfinite(valor) for valor in texto.bbox):
        return []
    return [
        Palavra(trecho.group().upper(), texto.bbox, fundido or trecho.group() != texto.texto)
        for trecho in _PALAVRA.finditer(texto.texto)
    ]


# --- contexto -----------------------------------------------------------------------------


def _verificar_fontes(diagnosticos: Sequence[str]) -> None:
    """R-E06.2.1-8: a falha de fonte vem antes, porque o teto não seria tentado de novo."""
    for codigo in diagnosticos:
        if codigo in _FONTES_CONSUMIDAS:
            raise FonteGramaticaFalhou(codigo)
    if _GLIFOS_LIMITADOS in diagnosticos:
        raise TetoGramaticasExcedido("Texto de glifo parcial deixaria as guardas abertas.")


def _caixas_de_caminhos(caminhos: Sequence[Caminho]) -> dict[int, Caixa]:
    caixas: dict[int, Caixa] = {}
    for posicao, caminho in enumerate(caminhos):
        caixa = _caixa_de_pontos(
            ponto
            for subcaminho in caminho.subcaminhos
            for item in subcaminho
            for ponto in item.pontos
        )
        if caixa is not None:
            caixas[posicao] = caixa
    return caixas


def _caixa_do_segmento(segmento: Segmento) -> Caixa:
    x0, x1 = sorted((segmento.a[0], segmento.b[0]))
    y0, y1 = sorted((segmento.a[1], segmento.b[1]))
    return (x0, y0, x1, y1)


def contexto_gramaticas(
    pagina: PaginaGramatica, *, limite: int = LIMITE_CONSULTAS_PAGINA
) -> ContextoGramatica:
    """Índices da página; gasta 1 do orçamento por item indexado, para a página gigante
    também estourar aqui."""
    modelo = pagina.modelo
    _verificar_fontes(modelo.diagnosticos)
    orcamento = OrcamentoConsultas(limite)
    limites: Caixa = (
        -_MARGEM_PAGINA,
        -_MARGEM_PAGINA,
        modelo.largura + _MARGEM_PAGINA,
        modelo.altura + _MARGEM_PAGINA,
    )
    molduras, segmentos = _molduras_e_segmentos(modelo)
    textos = _fundir_spans_colados(modelo.textos, orcamento)
    palavras = (
        palavra
        for texto, fundido in textos
        for palavra in _palavras_do_texto(texto, fundido=fundido)
    )
    caixas_caminhos = _caixas_de_caminhos(modelo.caminhos)
    return ContextoGramatica(
        pagina=pagina,
        orcamento=orcamento,
        molduras=molduras,
        grade_molduras=GradeEspacial(((m.caixa, m) for m in molduras), limites, orcamento),
        grade_palavras=GradeEspacial(((p.caixa, p) for p in palavras), limites, orcamento),
        grade_segmentos=GradeEspacial(
            ((_caixa_do_segmento(s), s) for s in segmentos), limites, orcamento
        ),
        grade_caminhos=GradeEspacial(
            ((caixa, posicao) for posicao, caixa in caixas_caminhos.items()), limites, orcamento
        ),
        caixas_caminhos=caixas_caminhos,
    )
