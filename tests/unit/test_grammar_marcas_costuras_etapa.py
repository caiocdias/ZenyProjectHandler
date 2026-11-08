# mypy: disable-error-code="no-untyped-call"
"""Costuras entre as Tasks da E06.3.3.2.1, pelo testador de etapa.

Cada Task teve o seu testador; aqui se atacam os encontros entre elas:

1. envolvente de subcaminho (Task 1) x X perto do símbolo (Task 3): com envolvente, a âncora do
   critério do X é o centro dela, nas duas gramáticas;
2. envolvente de subcaminho no caminho do retângulo (Task 1) x haste que sai da borda (Task 4);
3. cor da diagonal (Task 4) x X (Task 3): o X de outra cor sobre o BT continua X próprio, e o
   braço dele não vira diagonal;
4. concordância de situação (Task 2) x variantes das Tasks 1, 3 e 4, de ponta a ponta pelo
   método `modelo` do benchmark, sobre um PDF sintético;
5. guarda de contexto (Task 3) x marcas compartilhadas pelas duas gramáticas no casador.

Desenho autoral, relativo à escala do símbolo (a maior barra da haste e o lado maior do corpo do
BT, 8 pt nos dois): nada vem de folha real.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final, Literal

import pymupdf
import pytest
import scripts.benchmark_simbolos_ficha as bench
from tests.fixtures.symbol_grammars import stem_bars
from tests.fixtures.symbol_grammars.paginas import (
    circulo_bezier,
    estilo,
    linha,
    pagina_gramatica,
    poligono,
)
from tests.fixtures.symbol_grammars.rect_diagonal import CASOS_RECT_DIAGONAL, CORPO
from tests.fixtures.symbol_grammars.stem_bars import (
    ALTERNADAS,
    CASOS_HASTE,
    DECRESCENTES,
    HASTE,
    LACUNA,
    VERMELHO,
)

from zeny_project_handler.adapters.analysis.drawing_model import grammar_marcas
from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import (
    Contorno,
    MarcasDaPagina,
)
from zeny_project_handler.adapters.analysis.drawing_model.grammar_rect_diagonal import (
    retangulos_candidatos,
)
from zeny_project_handler.adapters.analysis.drawing_model.grammar_stem import hastes_candidatas
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caixa,
    Caminho,
    Cor,
    Ponto,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    ContextoGramatica,
    GradeEspacial,
    PaginaGramatica,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import casar_variantes

Gramatica = Literal["haste", "bt"]
Origem = Literal["nenhuma", "bezier", "subcaminho", "mesmo-caminho"]

_C: Final[Ponto] = (150.0, 150.0)
# A escala das duas gramáticas: a maior barra de `DECRESCENTES` e o lado maior de `CORPO`.
_ESCALA: Final = 8.0
_LADOS: Final = 72
_PRETO: Final[Cor] = (0.0, 0.0, 0.0)
_VERDE: Final[Cor] = (0.0, 0.5, 0.0)
_RAIO_BT: Final = 7.0
# Meio braço de um X de vizinho que alcança a janela do pictograma (braço de 2,9 vezes a escala).
_MEIO_LONGO: Final = 1.45 * _ESCALA


# --- desenho ------------------------------------------------------------------------------------


def _gira(ponto: Ponto, graus: float, centro: Ponto = _C) -> Ponto:
    r = math.radians(graus)
    dx, dy = ponto[0] - centro[0], ponto[1] - centro[1]
    return (
        centro[0] + dx * math.cos(r) - dy * math.sin(r),
        centro[1] + dx * math.sin(r) + dy * math.cos(r),
    )


def _elipse(
    centro: Ponto, a: float, b: float, *, graus: float = 0.0, lados: int = _LADOS
) -> list[Ponto]:
    """Vértices da elipse de semieixos `a` (em x) e `b` (em y), girada `graus` em torno dela."""
    pontos = [
        (
            centro[0] + a * math.cos(2 * math.pi * k / lados),
            centro[1] + b * math.sin(2 * math.pi * k / lados),
        )
        for k in range(lados)
    ]
    return [_gira(p, graus, centro) for p in pontos]


def _encostados(vertices: Sequence[Ponto], centro: Ponto) -> list[Caminho]:
    """Dois traços que saem de vértices opostos para fora: a polilinha da elipse se parte, e a
    envolvente só pode vir do subcaminho."""
    tracos = []
    for indice in (len(vertices) // 8, len(vertices) // 8 + len(vertices) // 2):
        v = vertices[indice]
        dx, dy = v[0] - centro[0], v[1] - centro[1]
        norma = math.hypot(dx, dy)
        tracos.append(linha(v, (v[0] + 3.0 * dx / norma, v[1] + 3.0 * dy / norma)))
    return tracos


def _envolvente(origem: Origem, centro: Ponto, raio: float) -> list[Caminho]:
    """A envolvente circular em caminho próprio: Béziers ou subcaminho de retas partido."""
    if origem == "bezier":
        return [circulo_bezier(centro, raio)]
    if origem == "subcaminho":
        vertices = _elipse(centro, raio, raio)
        return [poligono(vertices), *_encostados(vertices, centro)]
    return []


@dataclass(frozen=True, slots=True)
class Simbolo:
    caminhos: list[Caminho]
    centro_envolvente: Ponto
    raio_envolvente: float


def _haste(origem: Origem, barras: Sequence[float] = DECRESCENTES) -> Simbolo:
    """Haste vertical (0) com as barras (1..n) acima da ponta, como em `stem_bars`."""
    cx, cy = _C
    ponta = cy - HASTE / 2
    caminhos = [linha((cx, cy + HASTE / 2), (cx, ponta))]
    for i, comprimento in enumerate(barras):
        y = ponta - i * LACUNA
        caminhos.append(linha((cx - comprimento / 2, y), (cx + comprimento / 2, y)))
    raio = max(barras) * 0.8 + len(barras) * LACUNA / 2
    meio = (cx, ponta - (len(barras) - 1) * LACUNA / 2)
    return Simbolo([*caminhos, *_envolvente(origem, meio, raio)], meio, raio)


def _cantos(centro: Ponto = _C, graus: float = 0.0) -> list[Ponto]:
    cx, cy = centro
    maior, menor = CORPO
    cantos = [(cx - menor / 2, cy - maior / 2), (cx + menor / 2, cy - maior / 2)]
    cantos += [(cx + menor / 2, cy + maior / 2), (cx - menor / 2, cy + maior / 2)]
    return [_gira(p, graus, centro) for p in cantos]


def _diagonal(centro: Ponto = _C, graus: float = 0.0, cor: Cor = _PRETO) -> Caminho:
    cx, cy = centro
    maior, menor = CORPO
    a, b = (cx - menor, cy + maior / 4), (cx + menor, cy - maior / 4)
    return linha(_gira(a, graus, centro), _gira(b, graus, centro), cor=cor)


def _bt(
    origem: Origem,
    *,
    centro_envolvente: Ponto = _C,
    raio: float = _RAIO_BT,
    cor: Cor = _PRETO,
) -> Simbolo:
    """Retângulo (0) e diagonal (1), em `_C`; a envolvente vem depois, salvo `mesmo-caminho`,
    em que ela é o segundo subcaminho do caminho do retângulo."""
    retangulo = poligono(_cantos(), cor=cor)
    if origem == "mesmo-caminho":
        oval = poligono(_elipse(centro_envolvente, raio, raio), cor=cor)
        retangulo = Caminho((*retangulo.subcaminhos, *oval.subcaminhos), estilo(cor), "traco", 0)
    caminhos = [retangulo, _diagonal(cor=cor), *_envolvente(origem, centro_envolvente, raio)]
    return Simbolo(caminhos, centro_envolvente, raio)


def _simbolo(gramatica: Gramatica, origem: Origem) -> Simbolo:
    return _haste(origem) if gramatica == "haste" else _bt(origem)


def _braco(cruzamento: Ponto, graus: float, meio: float, cor: Cor = VERMELHO) -> Caminho:
    u = math.cos(math.radians(graus)), math.sin(math.radians(graus))
    return linha(
        (cruzamento[0] - meio * u[0], cruzamento[1] - meio * u[1]),
        (cruzamento[0] + meio * u[0], cruzamento[1] + meio * u[1]),
        cor=cor,
    )


def _x(cruzamento: Ponto, meio: float, cor: Cor = VERMELHO) -> list[Caminho]:
    """Dois braços a 45 graus do eixo vertical dos símbolos, cruzando nos meios."""
    return [_braco(cruzamento, graus, meio, cor) for graus in (45.0, 135.0)]


def _deslocado(ponto: Ponto, distancia: float, graus: float) -> Ponto:
    r = math.radians(graus)
    return ponto[0] + distancia * math.cos(r), ponto[1] + distancia * math.sin(r)


def _x_proprio(gramatica: Gramatica, simbolo: Simbolo) -> list[Caminho]:
    """O X das fixtures: sobre as barras (no centro da envolvente) ou no centro do corpo."""
    if gramatica == "haste":
        return _x(simbolo.centro_envolvente, max(DECRESCENTES) * 0.9 * math.sqrt(2))
    return _x(_C, 5.0 * math.sqrt(2))


# --- leitura ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Leitura:
    envolvente: Contorno | None
    caixa: Caixa
    x: bool
    # Posições dos caminhos lidos como braços do X.
    bracos: frozenset[int]
    componentes: tuple[int, ...]


def _ler(gramatica: Gramatica, caminhos: Sequence[Caminho]) -> Leitura:
    contexto = contexto_gramaticas(pagina_gramatica(caminhos))
    if gramatica == "haste":
        (haste,) = hastes_candidatas(contexto)
        assert haste.pictograma is not None
        bracos = frozenset() if haste.x is None else frozenset(s.caminho for s in haste.x)
        return Leitura(haste.envolvente, haste.pictograma, haste.x is not None, bracos, ())
    marcas = MarcasDaPagina(contexto)
    (achado,) = retangulos_candidatos(contexto, marcas=marcas)
    contornos = list(marcas.contornos.consultar(achado.caixa))
    achada = next((c for c in contornos if c.caixa == achado.caixa), None)
    vermelhos = frozenset(
        i for i, c in enumerate(caminhos) if c.estilo.cor == VERMELHO and i in achado.componentes
    )
    return Leitura(
        achada if achado.envolvente else None,
        achado.caixa,
        achado.x,
        vermelhos if achado.x else frozenset(),
        achado.componentes,
    )


def _pares(casos: Sequence[tuple[str, Mapping[str, Any]]]) -> list[tuple[Any, Any]]:
    return [
        ({"family_id": "autoral"}, {"id": v, "recognition": {"status": "enabled", "grammar": g}})
        for v, g in casos
    ]


def _casos(gramatica: Gramatica) -> Sequence[tuple[str, Mapping[str, Any]]]:
    return CASOS_HASTE if gramatica == "haste" else CASOS_RECT_DIAGONAL


def _variantes(gramatica: Gramatica, caminhos: Sequence[Caminho]) -> list[tuple[str, Any]]:
    return [
        (str(c.variante["id"]), c.componentes)
        for c in casar_variantes(pagina_gramatica(caminhos), _pares(_casos(gramatica)))
    ]


def _sem_criterio(monkeypatch: pytest.MonkeyPatch, ler: Callable[[], Leitura]) -> Leitura:
    with monkeypatch.context() as m:
        m.setattr(grammar_marcas, "_CRUZAMENTO_X", math.inf)
        return ler()


def _centro(caixa: Caixa) -> Ponto:
    return (caixa[0] + caixa[2]) / 2, (caixa[1] + caixa[3]) / 2


# --- 1. envolvente de subcaminho x X perto do símbolo --------------------------------------------

_ORIGENS_COM_ENVOLVENTE: Final = [
    pytest.param("haste", "bezier", id="haste-bezier"),
    pytest.param("haste", "subcaminho", id="haste-subcaminho"),
    pytest.param("bt", "bezier", id="bt-bezier"),
    pytest.param("bt", "subcaminho", id="bt-subcaminho"),
    pytest.param("bt", "mesmo-caminho", id="bt-mesmo-caminho"),
]
_COM_X: Final[Mapping[Gramatica, str]] = {
    "haste": "cemig-eo-r3-s19-v003",
    "bt": "cemig-eo-r3-s21-v003",
}
_SEM_X: Final[Mapping[Gramatica, str]] = {
    "haste": "cemig-eo-r3-s19-v002",
    "bt": "cemig-eo-r3-s21-v002",
}


@pytest.mark.parametrize(("gramatica", "origem"), _ORIGENS_COM_ENVOLVENTE)
def test_x_proprio_vence_o_x_de_vizinho_que_cruza_logo_fora_da_envolvente(
    gramatica: Gramatica, origem: Origem, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O X de vizinho cruza a um quarto da escala fora da borda e vem antes na página: sem o
    critério ele seria o primeiro par; com o critério, os braços lidos são os do X próprio."""
    simbolo = _simbolo(gramatica, origem)
    cruzamento = _deslocado(
        simbolo.centro_envolvente, simbolo.raio_envolvente + 0.25 * _ESCALA, 0.0
    )
    vizinho = _x(cruzamento, _MEIO_LONGO)
    proprio = _x_proprio(gramatica, simbolo)
    caminhos = [*simbolo.caminhos, *vizinho, *proprio]
    n = len(simbolo.caminhos)

    sem_criterio = _sem_criterio(monkeypatch, lambda: _ler(gramatica, caminhos))
    lido = _ler(gramatica, caminhos)

    assert sem_criterio.bracos == {n, n + 1}
    assert lido.envolvente is not None
    assert lido.x
    assert lido.bracos == {n + 2, n + 3}
    assert [v for v, _ in _variantes(gramatica, caminhos)] == [_COM_X[gramatica]]


@pytest.mark.parametrize(("gramatica", "origem"), _ORIGENS_COM_ENVOLVENTE)
def test_x_de_vizinho_logo_fora_da_envolvente_sozinho_nao_marca(
    gramatica: Gramatica, origem: Origem
) -> None:
    simbolo = _simbolo(gramatica, origem)
    cruzamento = _deslocado(
        simbolo.centro_envolvente, simbolo.raio_envolvente + 0.25 * _ESCALA, 0.0
    )
    caminhos = [*simbolo.caminhos, *_x(cruzamento, _MEIO_LONGO)]

    assert [v for v, _ in _variantes(gramatica, caminhos)] == [_SEM_X[gramatica]]


def _haste_com_x_longe_das_barras(origem: Origem) -> list[Caminho]:
    """X a 0,8 vez a escala do centro da envolvente, para o lado oposto ao da haste: a 1,3 vez
    a escala do centro do pictograma sem envolvente (barras e trecho da haste)."""
    simbolo = _haste(origem)
    cruzamento = _deslocado(simbolo.centro_envolvente, 0.8 * _ESCALA, -90.0)
    return [*simbolo.caminhos, *_x(cruzamento, _ESCALA)]


def _bt_com_x_longe_do_corpo(origem: Origem) -> list[Caminho]:
    """Envolvente deslocada 2,5 pt para a esquerda do corpo e X a 0,8 vez a escala à esquerda
    do centro dela: a 1,1 vez a escala do centro do corpo."""
    centro = (_C[0] - 2.5, _C[1])
    simbolo = _bt(origem, centro_envolvente=centro)
    cruzamento = _deslocado(centro, 0.8 * _ESCALA, 180.0)
    return [*simbolo.caminhos, *_x(cruzamento, _ESCALA)]


@pytest.mark.parametrize(("gramatica", "origem"), _ORIGENS_COM_ENVOLVENTE)
def test_ancora_do_criterio_do_x_e_o_centro_da_envolvente(
    gramatica: Gramatica, origem: Origem
) -> None:
    """Com a envolvente (de qualquer origem), o X a 0,8 vez a escala do centro dela marca; o
    mesmo desenho sem a envolvente não marca, porque o centro do pictograma volta ao corpo."""
    montar = _haste_com_x_longe_das_barras if gramatica == "haste" else _bt_com_x_longe_do_corpo
    com = _ler(gramatica, montar(origem))
    sem = _ler(gramatica, montar("nenhuma"))

    assert com.envolvente is not None
    assert _centro(com.caixa) == pytest.approx(_centro(com.envolvente.caixa), abs=0.01)
    assert com.x
    assert sem.envolvente is None
    assert not sem.x


@pytest.mark.parametrize(
    ("gramatica", "origem", "alcance", "dentro_da_envolvente", "marca"),
    [
        # Haste: a envolvente (raio de 1,27 vez a escala) passa do alcance do critério.
        pytest.param("haste", "subcaminho", 0.9, True, True, id="haste-dentro-a-0_9"),
        pytest.param("haste", "subcaminho", 1.1, True, False, id="haste-dentro-a-1_1"),
        # BT: a envolvente (raio de 0,875 vez a escala) fica dentro do alcance.
        pytest.param("bt", "mesmo-caminho", 0.95, False, True, id="bt-fora-a-0_95"),
        pytest.param("bt", "mesmo-caminho", 1.1, False, False, id="bt-fora-a-1_1"),
    ],
)
def test_x_perto_da_borda_segue_o_centro_da_envolvente_e_nao_a_borda(
    gramatica: Gramatica,
    origem: Origem,
    alcance: float,
    dentro_da_envolvente: bool,
    marca: bool,
) -> None:
    """Caracterização (R-E06.3.3.2.1-2): o critério é a distância ao centro, até 1 vez a escala,
    e não a borda. O X que cruza dentro da envolvente da haste, mas a mais de 1 vez a escala do
    centro, não marca; o que cruza logo fora da envolvente do BT, a menos de 1 vez, marca."""
    simbolo = _simbolo(gramatica, origem)
    cruzamento = _deslocado(simbolo.centro_envolvente, alcance * _ESCALA, 0.0)
    caminhos = [*simbolo.caminhos, *_x(cruzamento, _ESCALA)]

    assert (alcance * _ESCALA < simbolo.raio_envolvente) is dentro_da_envolvente
    assert _ler(gramatica, caminhos).x is marca


# --- 2. envolvente de subcaminho no caminho do retângulo x haste da borda ------------------------


def _bt_com_haste_da_borda(
    *,
    a: float = _RAIO_BT,
    b: float = _RAIO_BT,
    graus: float = 0.0,
    lados_separados: bool = False,
    com_x: bool = False,
) -> list[Caminho]:
    """BT girado `graus` com a envolvente elíptica (semieixo `b` ao longo do corpo) como
    subcaminho do caminho do retângulo e a haste saindo da borda dela, no eixo.

    Posições: retângulo (0, ou 0 a 3 com `lados_separados`, a envolvente no terceiro lado),
    diagonal, haste e os braços do X.
    """
    cantos = _cantos(graus=graus)
    oval = poligono(_elipse(_C, a, b, graus=graus))
    if lados_separados:
        lados = [linha(p, q) for p, q in zip(cantos, [*cantos[1:], cantos[0]], strict=True)]
        lados[2] = Caminho((*lados[2].subcaminhos, *oval.subcaminhos), estilo(), "traco", 0)
    else:
        lados = [Caminho((*poligono(cantos).subcaminhos, *oval.subcaminhos), estilo(), "traco", 0)]
    cx, cy = _C
    borda, fim = _gira((cx, cy - b), graus), _gira((cx, cy - b - 10.0), graus)
    caminhos = [*lados, _diagonal(graus=graus), linha(borda, fim)]
    if com_x:
        caminhos += [_braco(_C, graus + g, 5.0 * math.sqrt(2)) for g in (45.0, 135.0)]
    return caminhos


@pytest.mark.parametrize(
    ("com_x", "variante"),
    [(False, "cemig-eo-r3-s21-v002"), (True, "cemig-eo-r3-s21-v003")],
    ids=["v002", "v003"],
)
@pytest.mark.parametrize(
    ("a", "b"), [(_RAIO_BT, _RAIO_BT), (4.5, 6.3)], ids=["circulo", "oval-ao-longo-do-corpo"]
)
@pytest.mark.parametrize("lados_separados", [False, True], ids=["um-caminho", "lados-soltos"])
def test_envolvente_no_caminho_do_retangulo_fica_e_a_haste_da_borda_entra(
    lados_separados: bool, a: float, b: float, com_x: bool, variante: str
) -> None:
    """O contorno de subcaminho tem o caminho do retângulo (em `origens`) e não é descartado; a
    haste é achada a partir da borda dele e entra nos componentes, com os braços do X."""
    caminhos = _bt_com_haste_da_borda(a=a, b=b, lados_separados=lados_separados, com_x=com_x)
    n_lados = 4 if lados_separados else 1
    esperados = tuple(range(1, len(caminhos)))

    assert _variantes("bt", caminhos) == [(variante, esperados)]
    lido = _ler("bt", caminhos)
    assert lido.envolvente is not None
    assert lido.envolvente.origem == "subcaminho"
    assert lido.envolvente.caminhos == ((2,) if lados_separados else (0,))
    assert lido.caixa == pytest.approx((_C[0] - a, _C[1] - b, _C[0] + a, _C[1] + b), abs=0.01)
    assert n_lados + 1 in lido.componentes


@pytest.mark.parametrize("graus", [0.0, 30.0, 45.0, 60.0, 90.0], ids=lambda g: f"{g:g}-graus")
def test_haste_da_borda_da_envolvente_eliptica_girada_com_o_corpo_entra(graus: float) -> None:
    """O oval (semieixos 4,5 e 6,3, o maior ao longo do corpo, proporção de 1,4) gira com o BT.
    A haste sai da borda real dele, no eixo do corpo, e deve entrar nos componentes (R-5)."""
    caminhos = _bt_com_haste_da_borda(a=4.5, b=6.3, graus=graus)

    assert _variantes("bt", caminhos) == [("cemig-eo-r3-s21-v002", (1, 2))]


# --- 3. cor da diagonal x X ---------------------------------------------------------------------


def _bt_com_x_curto(cor_corpo: Cor, cor_x: Cor, origem: Origem) -> list[Caminho]:
    """Braços de 1,2 vez o lado maior pelo centro: pela geometria, passariam por diagonais."""
    simbolo = _bt(origem, cor=cor_corpo)
    meio = 1.2 * CORPO[0] / 2
    return [*simbolo.caminhos, *_x(_C, meio, cor_x)]


@pytest.mark.parametrize("origem", ["nenhuma", "mesmo-caminho"], ids=["sem-env", "env-subcaminho"])
@pytest.mark.parametrize(
    ("cor_corpo", "cor_x"),
    [(_PRETO, VERMELHO), (_VERDE, VERMELHO), (_VERDE, _PRETO), (VERMELHO, _PRETO)],
    ids=["preto-vermelho", "verde-vermelho", "verde-preto", "vermelho-preto"],
)
def test_x_curto_de_outra_cor_e_x_proprio_e_a_diagonal_continua_a_do_corpo(
    cor_corpo: Cor, cor_x: Cor, origem: Origem
) -> None:
    """O X curto de outra cor canônica sai como X (v004 ou v003), com os dois braços nos
    componentes; a caixa e a envolvente são as do BT sem X, ou seja, a diagonal lida é a do
    corpo, e não um braço."""
    caminhos = _bt_com_x_curto(cor_corpo, cor_x, origem)
    sem_x = _bt(origem, cor=cor_corpo).caminhos
    n = len(sem_x)
    variante = "cemig-eo-r3-s21-v003" if origem == "mesmo-caminho" else "cemig-eo-r3-s21-v004"

    lido = _ler("bt", caminhos)
    base = _ler("bt", sem_x)

    assert lido.x
    assert lido.caixa == base.caixa
    assert set(lido.componentes) == {*base.componentes, n, n + 1}
    assert _variantes("bt", caminhos) == [(variante, tuple(sorted({*base.componentes, n, n + 1})))]


# --- 4. concordância de situação de ponta a ponta -------------------------------------------------

_LARGURA: Final = 300.0
_BT_PDF: Final[Ponto] = (90.0, 150.0)
_HASTE_PDF: Final[Ponto] = (210.0, 150.0)


def _bt_no_pdf(pagina: pymupdf.Page, x: bool) -> Caixa:
    """Retângulo e oval de 72 retas no mesmo caminho, a diagonal à parte e, com `x`, o X
    próprio vermelho. Devolve a caixa do oval."""
    cx, cy = _BT_PDF
    maior, menor = CORPO
    forma = pagina.new_shape()
    cantos = [(cx - menor / 2, cy - maior / 2), (cx + menor / 2, cy - maior / 2)]
    cantos += [(cx + menor / 2, cy + maior / 2), (cx - menor / 2, cy + maior / 2)]
    forma.draw_polyline([*cantos, cantos[0]])
    oval = _elipse(_BT_PDF, _RAIO_BT, _RAIO_BT)
    forma.draw_polyline([*oval, oval[0]])
    forma.finish(color=_PRETO, width=0.5)
    forma.commit()
    pagina.draw_line((cx - menor, cy + maior / 4), (cx + menor, cy - maior / 4), color=_PRETO)
    if x:
        meio = 5.0
        for sinal in (1, -1):
            a, b = (cx - meio, cy - sinal * meio), (cx + meio, cy + sinal * meio)
            pagina.draw_line(a, b, color=VERMELHO, width=0.5)
    return (cx - _RAIO_BT, cy - _RAIO_BT, cx + _RAIO_BT, cy + _RAIO_BT)


def _haste_no_pdf(pagina: pymupdf.Page, x: bool) -> Caixa:
    """Haste de 4 barras com o oval de 40 retas partido por dois traços encostados. Devolve a
    caixa do oval."""
    desenho = stem_bars.desenhar_haste(
        pagina, ALTERNADAS, _HASTE_PDF, envolvente=True, x=x, contorno=(1.0,) * 40
    )
    assert desenho.envolvente is not None
    x0, y0, x1, y1 = desenho.envolvente
    centro = ((x0 + x1) / 2, (y0 + y1) / 2)
    vertices = _elipse(centro, (x1 - x0) / 2, (y1 - y0) / 2, lados=40)
    for traco in _encostados(vertices, centro):
        ((item,),) = traco.subcaminhos
        pagina.draw_line(item.pontos[0], item.pontos[1], color=_PRETO, width=0.5)
    return desenho.envolvente


def _x_de_vizinho_no_pdf(pagina: pymupdf.Page, centro: Ponto) -> None:
    cruzamento = _deslocado(centro, 1.85 * _ESCALA, 0.0)
    for graus in (45.0, 135.0):
        braco = _braco(cruzamento, graus, _MEIO_LONGO)
        ((item,),) = braco.subcaminhos
        pagina.draw_line(item.pontos[0], item.pontos[1], color=VERMELHO, width=0.5)


def _pdf(
    caminho: Path, desenhar: Callable[[pymupdf.Page], tuple[Caixa, Caixa]]
) -> tuple[Path, Caixa, Caixa]:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=_LARGURA, height=_LARGURA)
        caixa_bt, caixa_haste = desenhar(pagina)
        documento.save(caminho)
    return caminho, caixa_bt, caixa_haste


def _normalizada(caixa: Caixa) -> list[float]:
    return [v / _LARGURA for v in caixa]


def _ficha(caixa_bt: Caixa, caixa_haste: Caixa, situacao_bt: str, situacao_mt: str) -> Any:
    def simbolo(classe: str, caixa: Caixa, situacao: str) -> dict[str, Any]:
        return {
            "classe": classe,
            "bbox": _normalizada(caixa),
            "atributos_extras": {"situacao": situacao},
        }

    return {
        "pdf_sha256": "sintetico",
        "escopo_anotacao": {"tipo": "completo"},
        "regioes": [],
        "postes": [
            {
                "pagina": 1,
                "bbox": [0.1, 0.1, 0.2, 0.2],
                "pendentes": [],
                "simbolos": [
                    simbolo("PARA_RAIOS_BT", caixa_bt, situacao_bt),
                    simbolo("PARA_RAIOS_MT", caixa_haste, situacao_mt),
                ],
            }
        ],
    }


def _concordancia(pdf: Path, ficha: Any) -> Any:
    registro = bench.medir_pdf(
        pdf, ficha, "sintetico", ["modelo"], classes_avaliadas=["PARA_RAIOS_BT", "PARA_RAIOS_MT"]
    )
    bloco = registro["metodos"]["modelo"]
    assert bloco["situacao"] == "ok", bloco
    assert bloco["centro"]["geral"]["tp"] == 2, bloco["centro"]
    return bloco["centro"]["concordancia_situacao"]


@pytest.mark.parametrize(
    ("x", "situacao_bt", "situacao_mt"),
    [
        (False, "Proposto Instalar (verde, oval)", "proposto_instalar"),
        (True, "proposto substituir; com X", "Proposto Substituir (oval e X)"),
    ],
    ids=["v002-v006", "v003-v007"],
)
def test_bt_e_haste_com_envolvente_de_subcaminho_concordam_com_a_ficha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    x: bool,
    situacao_bt: str,
    situacao_mt: str,
) -> None:
    """De ponta a ponta pelo método `modelo`: o oval no caminho do retângulo e o oval partido da
    haste dão a variante com envolvente, cuja situação concorda com a da ficha. Controle: sem a
    leitura do subcaminho (o comportamento de antes da Task 1), as duas discordam."""

    def desenhar(pagina: pymupdf.Page) -> tuple[Caixa, Caixa]:
        return _bt_no_pdf(pagina, x), _haste_no_pdf(pagina, x)

    pdf, caixa_bt, caixa_haste = _pdf(tmp_path / "pagina-sintetica", desenhar)
    ficha = _ficha(caixa_bt, caixa_haste, situacao_bt, situacao_mt)

    concordancia = _concordancia(pdf, ficha)
    with monkeypatch.context() as m:
        m.setattr(grammar_marcas, "_contornos_de_subcaminhos", lambda *_: [])
        antes = _concordancia(pdf, ficha)

    assert concordancia["geral"]["concordantes"] == 2
    assert concordancia["geral"]["discordantes"] == 0
    assert concordancia["por_classe"]["PARA_RAIOS_BT"]["concordantes"] == 1
    assert concordancia["por_classe"]["PARA_RAIOS_MT"]["concordantes"] == 1
    assert antes["geral"]["concordantes"] == 0
    assert antes["geral"]["discordantes"] == 2


def test_x_de_vizinho_nao_faz_a_situacao_discordar_da_ficha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BT e haste com envolvente, sem X próprio, cada um com um X de vizinho a 1,85 vez a escala.
    A ficha diz "proposto instalar": concorda. Controle: sem o critério do X perto (o
    comportamento de antes da Task 3), o X de vizinho vira retirada e as duas discordam."""

    def desenhar(pagina: pymupdf.Page) -> tuple[Caixa, Caixa]:
        caixa_bt = _bt_no_pdf(pagina, x=False)
        caixa_haste = _haste_no_pdf(pagina, x=False)
        _x_de_vizinho_no_pdf(pagina, _centro(caixa_bt))
        _x_de_vizinho_no_pdf(pagina, _centro(caixa_haste))
        return caixa_bt, caixa_haste

    pdf, caixa_bt, caixa_haste = _pdf(tmp_path / "pagina-sintetica", desenhar)
    ficha = _ficha(caixa_bt, caixa_haste, "proposto instalar", "Proposto_Instalar")

    concordancia = _concordancia(pdf, ficha)
    with monkeypatch.context() as m:
        m.setattr(grammar_marcas, "_CRUZAMENTO_X", math.inf)
        sem_criterio = _concordancia(pdf, ficha)

    assert concordancia["geral"]["concordantes"] == 2
    assert concordancia["geral"]["discordantes"] == 0
    assert sem_criterio["geral"]["concordantes"] == 0
    assert sem_criterio["geral"]["discordantes"] == 2


# --- 5. guarda de contexto x marcas compartilhadas -----------------------------------------------


def _deslocar(caminhos: Sequence[Caminho], dy: float) -> list[Caminho]:
    return [
        replace(
            c,
            subcaminhos=tuple(
                tuple(
                    replace(item, pontos=tuple((p[0], p[1] + dy) for p in item.pontos))
                    for item in sub
                )
                for sub in c.subcaminhos
            ),
        )
        for c in caminhos
    ]


def _pagina_com(haste: bool, bt: bool) -> PaginaGramatica:
    caminhos: list[Caminho] = []
    if haste:
        caminhos += _haste("subcaminho").caminhos
    if bt:
        caminhos += _deslocar(_bt("mesmo-caminho").caminhos, 80.0)
    # Um oval de subcaminho solto: sem símbolo, ninguém deve pagar os contornos por ele.
    caminhos.append(poligono(_elipse((40.0, 40.0), 8.0, 8.0)))
    return pagina_gramatica(caminhos)


def _espiao_de_contornos(monkeypatch: pytest.MonkeyPatch) -> list[ContextoGramatica]:
    chamadas: list[ContextoGramatica] = []
    original = grammar_marcas._contornos

    def espiao(contexto: ContextoGramatica) -> GradeEspacial[Contorno]:
        chamadas.append(contexto)
        return original(contexto)

    monkeypatch.setattr(grammar_marcas, "_contornos", espiao)
    return chamadas


@pytest.mark.parametrize(
    ("haste", "bt", "variantes", "chamadas"),
    [
        (True, True, {"cemig-eo-r3-s19-v002", "cemig-eo-r3-s21-v002"}, 1),
        (True, False, {"cemig-eo-r3-s19-v002"}, 1),
        (False, True, {"cemig-eo-r3-s21-v002"}, 1),
        (False, False, set(), 0),
    ],
    ids=["haste-e-bt", "so-haste", "so-bt", "nenhum"],
)
def test_casador_paga_os_contornos_uma_vez_por_pagina_para_as_duas_gramaticas(
    haste: bool,
    bt: bool,
    variantes: set[str],
    chamadas: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pagina = _pagina_com(haste, bt)
    espiao = _espiao_de_contornos(monkeypatch)

    casamentos = casar_variantes(pagina, _pares([*CASOS_HASTE, *CASOS_RECT_DIAGONAL]))

    assert {str(c.variante["id"]) for c in casamentos} == variantes
    assert len(espiao) == chamadas
    assert len({id(contexto) for contexto in espiao}) == chamadas


def test_casador_com_marcas_compartilhadas_da_o_mesmo_que_cada_gramatica_sozinha() -> None:
    pagina = _pagina_com(haste=True, bt=True)

    juntos = casar_variantes(pagina, _pares([*CASOS_HASTE, *CASOS_RECT_DIAGONAL]))
    so_haste = casar_variantes(pagina, _pares(CASOS_HASTE))
    so_bt = casar_variantes(pagina, _pares(CASOS_RECT_DIAGONAL))

    def chave(c: Any) -> tuple[Any, ...]:
        return (str(c.variante["id"]), c.caixa, c.caminho, c.componentes)

    assert sorted(map(chave, juntos)) == sorted(map(chave, [*so_haste, *so_bt]))


def test_marcas_ja_pagas_de_outro_contexto_sao_recusadas_sem_gastar_nem_recalcular(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """As marcas de A já leram os contornos (pela haste). Passadas ao BT de B, da mesma página,
    levantam antes de gastar o orçamento de B; depois continuam servindo a A, sem recalcular."""
    pagina = _pagina_com(haste=True, bt=True)
    espiao = _espiao_de_contornos(monkeypatch)
    contexto_a, contexto_b = contexto_gramaticas(pagina), contexto_gramaticas(pagina)
    marcas = MarcasDaPagina(contexto_a)
    hastes_candidatas(contexto_a, marcas=marcas)
    gasto_a, gasto_b = contexto_a.orcamento.gasto, contexto_b.orcamento.gasto

    with pytest.raises(ValueError, match="contexto"):
        retangulos_candidatos(contexto_b, marcas=marcas)
    with pytest.raises(ValueError, match="contexto"):
        hastes_candidatas(contexto_b, marcas=marcas)

    assert (contexto_a.orcamento.gasto, contexto_b.orcamento.gasto) == (gasto_a, gasto_b)
    retangulos = retangulos_candidatos(contexto_a, marcas=marcas)
    assert [(r.envolvente, r.x) for r in retangulos] == [(True, False)]
    assert espiao == [contexto_a]
