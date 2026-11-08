"""Ataque ao X perto do símbolo (R-E06.3.3.2.1-2) e à guarda de contexto (R-3), pelo testador.

Páginas puras do modelo, sem PyMuPDF, nas duas gramáticas (`stem_bars` e `rect_diagonal`). Tudo
é relativo à escala do símbolo (a maior barra da haste, o lado maior do retângulo): o cruzamento
do X fica a `d` vezes a escala do centro do pictograma, e os braços medem frações dela. Cada
negativo traz o controle com o critério desligado (`_CRUZAMENTO_X` infinito): o mesmo desenho
marcaria, então é só o critério que o recusa. Nada vem de folha real.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Final, Literal, TypeVar

import pytest
from tests.fixtures.symbol_grammars.paginas import (
    circulo_bezier,
    linha,
    pagina_gramatica,
    poligono,
    texto,
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
    MarcasDaPagina,
    tem_x,
)
from zeny_project_handler.adapters.analysis.drawing_model.grammar_rect_diagonal import (
    retangulos_candidatos,
)
from zeny_project_handler.adapters.analysis.drawing_model.grammar_stem import hastes_candidatas
from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa, Caminho, Ponto
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    ContextoGramatica,
    PaginaGramatica,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import casar_variantes

Gramatica = Literal["haste", "bt"]
_GRAMATICAS: Final[tuple[Gramatica, ...]] = ("haste", "bt")

_C: Final[Ponto] = (150.0, 150.0)
# A escala das duas gramáticas no desenho base: a maior barra de `DECRESCENTES` e o lado maior
# de `CORPO`; com o fator `k`, ela vira `k` vezes isto.
_ESCALA_BASE: Final = 8.0
# Meio braço do X, relativo à escala: curto (braço de 2 vezes a escala), longo (2,9 vezes, que
# alcança a janela do pictograma a partir do vizinho medido) e no limite de 3 vezes.
_MEIO_CURTO: Final = 1.0
_MEIO_LONGO: Final = 1.45
_MEIO_NO_LIMITE: Final = 1.49
# O vizinho mais perto medido nas folhas cruza a 1,82 vez a escala do centro do pictograma.
_VIZINHO: Final = 1.85
# Envolvente do retângulo (raio em pt no desenho base) e X próprio dele, como em `rect_diagonal`.
_RAIO_ENVOLVENTE_BT: Final = 7.0
_MEIO_X_BT: Final = 5.0

T = TypeVar("T")


# --- desenho -----------------------------------------------------------------------------------


def _direcao(graus: float) -> Ponto:
    r = math.radians(graus)
    return math.cos(r), math.sin(r)


def _transformar(k: float, graus: float) -> Callable[[Ponto], Ponto]:
    """Ponto local (eixo do símbolo em y, desenho base) para a página: escala `k` e giro."""
    cos, sin = _direcao(graus)

    def t(p: Ponto) -> Ponto:
        return _C[0] + k * (p[0] * cos - p[1] * sin), _C[1] + k * (p[0] * sin + p[1] * cos)

    return t


def _simbolo(
    gramatica: Gramatica,
    *,
    k: float = 1.0,
    graus: float = 0.0,
    envolvente: bool = False,
    barras: Sequence[float] = DECRESCENTES,
) -> list[Caminho]:
    """A haste com barras de `stem_bars` ou o retângulo com diagonal de `rect_diagonal`."""
    t = _transformar(k, graus)
    if gramatica == "haste":
        ponta = -HASTE / 2
        caminhos = [linha(t((0.0, HASTE / 2)), t((0.0, ponta)))]
        for i, comprimento in enumerate(barras):
            y = ponta - i * LACUNA
            caminhos.append(linha(t((-comprimento / 2, y)), t((comprimento / 2, y))))
        if envolvente:
            raio = max(barras) * 0.8 + len(barras) * LACUNA / 2
            meio_barras = t((0.0, ponta - (len(barras) - 1) * LACUNA / 2))
            caminhos.append(circulo_bezier(meio_barras, raio * k))
        return caminhos
    maior, menor = CORPO
    cantos = [(-menor / 2, -maior / 2), (menor / 2, -maior / 2)]
    cantos += [(menor / 2, maior / 2), (-menor / 2, maior / 2)]
    caminhos = [
        poligono([t(p) for p in cantos]),
        linha(t((-menor, maior / 4)), t((menor, -maior / 4))),
    ]
    if envolvente:
        caminhos.append(circulo_bezier(_C, _RAIO_ENVOLVENTE_BT * k))
    return caminhos


def _eixo(graus: float) -> float:
    """Ângulo, em graus, do eixo do símbolo na página (o y local girado)."""
    return 90.0 + graus


def _braco(cruzamento: Ponto, graus: float, antes: float, depois: float) -> Caminho:
    """Braço vermelho na direção `graus` que passa pelo `cruzamento`, `antes` e `depois` dele."""
    u = _direcao(graus)
    a = (cruzamento[0] - antes * u[0], cruzamento[1] - antes * u[1])
    b = (cruzamento[0] + depois * u[0], cruzamento[1] + depois * u[1])
    return linha(a, b, cor=VERMELHO)


def _x(cruzamento: Ponto, meio: float, graus: float = 0.0) -> list[Caminho]:
    """Dois braços vermelhos a 45 graus do eixo, de meio comprimento `meio` (pt), cruzando nos
    meios."""
    return [_braco(cruzamento, _eixo(graus) + desvio, meio, meio) for desvio in (45.0, -45.0)]


def _x_proprio(
    gramatica: Gramatica,
    *,
    k: float = 1.0,
    graus: float = 0.0,
    barras: Sequence[float] = DECRESCENTES,
) -> list[Caminho]:
    """O X das fixtures: no meio das barras da haste, ou no centro do retângulo."""
    t = _transformar(k, graus)
    if gramatica == "haste":
        meio_barras = t((0.0, -HASTE / 2 - (len(barras) - 1) * LACUNA / 2))
        return _x(meio_barras, max(barras) * 0.9 * math.sqrt(2) * k, graus)
    return _x(_C, _MEIO_X_BT * math.sqrt(2) * k, graus)


def _deslocado(ponto: Ponto, distancia: float, graus: float) -> Ponto:
    u = _direcao(graus)
    return ponto[0] + distancia * u[0], ponto[1] + distancia * u[1]


def _centro(caixa: Caixa) -> Ponto:
    return (caixa[0] + caixa[2]) / 2, (caixa[1] + caixa[3]) / 2


def _glifo() -> list[Any]:
    """Uma palavra de glifo longe do símbolo: o perfil de escala da página, sem os mínimos
    absolutos que recusariam a haste reduzida à metade."""
    return [texto("A", (10.0, 10.0, 12.0, 12.0), origem="glifo")]


# --- leitura -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Leitura:
    pictograma: Caixa
    x: bool
    # As posições, entre os caminhos extras, dos braços que a gramática leu como X.
    bracos: frozenset[int]


def _pagina(simbolo: Sequence[Caminho], extras: Sequence[Caminho], glifo: bool) -> PaginaGramatica:
    return pagina_gramatica([*simbolo, *extras], _glifo() if glifo else ())


def _ler(
    gramatica: Gramatica,
    simbolo: Sequence[Caminho],
    extras: Sequence[Caminho] = (),
    *,
    glifo: bool = False,
) -> _Leitura:
    contexto = contexto_gramaticas(_pagina(simbolo, extras, glifo))
    posicoes = frozenset(range(len(simbolo), len(simbolo) + len(extras)))
    if gramatica == "haste":
        (haste,) = hastes_candidatas(contexto)
        assert haste.pictograma is not None
        bracos = frozenset() if haste.x is None else frozenset(s.caminho for s in haste.x)
        return _Leitura(haste.pictograma, haste.x is not None, bracos)
    (achado,) = retangulos_candidatos(contexto)
    return _Leitura(achado.caixa, achado.x, frozenset(achado.componentes) & posicoes)


def _sem_criterio(monkeypatch: pytest.MonkeyPatch, ler: Callable[[], T]) -> T:
    """A mesma leitura com o critério desligado: só o cruzamento perto deixa de ser exigido."""
    with monkeypatch.context() as m:
        m.setattr(grammar_marcas, "_CRUZAMENTO_X", math.inf)
        return ler()


def _x_a(
    gramatica: Gramatica,
    simbolo: Sequence[Caminho],
    distancia: float,
    direcao: float,
    meio: float,
    *,
    k: float = 1.0,
    graus: float = 0.0,
    glifo: bool = False,
) -> list[Caminho]:
    """X de meio braço `meio` cruzando a `distancia` do centro do pictograma lido sem ele, as
    duas em vezes a escala, na direção `direcao` (graus, relativa ao símbolo girado)."""
    escala = _ESCALA_BASE * k
    centro = _centro(_ler(gramatica, simbolo, glifo=glifo).pictograma)
    cruzamento = _deslocado(centro, distancia * escala, graus + direcao)
    return _x(cruzamento, meio * escala, graus)


# --- borda do critério nas duas gramáticas -----------------------------------------------------


@pytest.mark.parametrize("direcao", [0.0, 90.0, 225.0], ids=["ao-lado", "ao-longo", "na-diagonal"])
@pytest.mark.parametrize(
    ("distancia", "marca"), [(0.97, True), (1.03, False)], ids=["dentro", "fora"]
)
@pytest.mark.parametrize("gramatica", _GRAMATICAS)
def test_cruzamento_logo_dentro_do_criterio_marca_e_logo_fora_nao(
    gramatica: Gramatica,
    distancia: float,
    marca: bool,
    direcao: float,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simbolo = _simbolo(gramatica)
    extras = _x_a(gramatica, simbolo, distancia, direcao, _MEIO_CURTO)

    assert _sem_criterio(monkeypatch, lambda: _ler(gramatica, simbolo, extras)).x
    assert _ler(gramatica, simbolo, extras).x is marca


@pytest.mark.parametrize("graus", [90.0, 30.0], ids=["girado-90", "girado-30"])
@pytest.mark.parametrize(
    ("distancia", "marca"), [(0.95, True), (1.05, False)], ids=["dentro", "fora"]
)
@pytest.mark.parametrize("gramatica", _GRAMATICAS)
def test_criterio_acompanha_o_simbolo_girado(
    gramatica: Gramatica,
    distancia: float,
    marca: bool,
    graus: float,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simbolo = _simbolo(gramatica, graus=graus)
    extras = _x_a(gramatica, simbolo, distancia, 0.0, _MEIO_CURTO, graus=graus)

    assert _sem_criterio(monkeypatch, lambda: _ler(gramatica, simbolo, extras)).x
    assert _ler(gramatica, simbolo, extras).x is marca


# --- X de vizinho que atravessa o pictograma ----------------------------------------------------


@pytest.mark.parametrize("distancia", [1.2, _VIZINHO], ids=["logo-fora", "vizinho-medido"])
@pytest.mark.parametrize("envolvente", [False, True], ids=["sem-envolvente", "com-envolvente"])
@pytest.mark.parametrize("gramatica", _GRAMATICAS)
def test_braco_de_vizinho_atravessa_o_centro_do_pictograma_mas_cruza_fora_e_nao_marca(
    gramatica: Gramatica,
    envolvente: bool,
    distancia: float,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Um braço passa pelo centro do pictograma (e o ultrapassa); o cruzamento fica fora."""
    simbolo = _simbolo(gramatica, envolvente=envolvente)
    centro = _centro(_ler(gramatica, simbolo).pictograma)
    escala = _ESCALA_BASE
    inclinado = _eixo(0.0) - 45.0
    cruzamento = _deslocado(centro, distancia * escala, inclinado)
    # O braço que atravessa vai do outro lado do centro até o cruzamento, que fica a 0,68 dele:
    # dentro da faixa dos meios do braço, com o comprimento abaixo de 3 vezes a escala.
    antes = (distancia + 0.1) * escala
    comprimento = antes / 0.68
    atravessa = _braco(cruzamento, inclinado + 180.0, comprimento - antes, antes)
    outro = _braco(cruzamento, inclinado + 90.0, comprimento / 2, comprimento / 2)
    extras = [atravessa, outro]

    assert _sem_criterio(monkeypatch, lambda: _ler(gramatica, simbolo, extras)).x
    assert not _ler(gramatica, simbolo, extras).x


@pytest.mark.parametrize("gramatica", _GRAMATICAS)
def test_x_de_vizinho_recusado_paga_os_mesmos_pares_que_sem_o_criterio(
    gramatica: Gramatica, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Os pares da janela são pagos antes do laço: o critério não muda o gasto da página."""
    simbolo = _simbolo(gramatica)
    extras = _x_a(gramatica, simbolo, _VIZINHO, 0.0, _MEIO_LONGO)

    def gasto() -> int:
        contexto = contexto_gramaticas(_pagina(simbolo, extras, glifo=False))
        _candidatos(gramatica)(contexto)
        return contexto.orcamento.gasto

    assert gasto() == _sem_criterio(monkeypatch, gasto)


# --- braços longos, dois X e escala -------------------------------------------------------------


@pytest.mark.parametrize("gramatica", _GRAMATICAS)
def test_x_de_bracos_no_limite_de_comprimento_cruzando_no_centro_marca(
    gramatica: Gramatica,
) -> None:
    simbolo = _simbolo(gramatica)
    extras = _x_a(gramatica, simbolo, 0.0, 0.0, _MEIO_NO_LIMITE)

    assert _ler(gramatica, simbolo, extras).x


@pytest.mark.parametrize("gramatica", _GRAMATICAS)
def test_dois_x_um_longe_e_outro_perto_marca_com_os_bracos_do_perto(
    gramatica: Gramatica, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O X de vizinho vem antes na página (e na grade): é o primeiro par examinado."""
    simbolo = _simbolo(gramatica)
    longe = _x_a(gramatica, simbolo, _VIZINHO, 0.0, _MEIO_LONGO)
    perto = _x_proprio(gramatica)
    extras = [*longe, *perto]
    posicoes_longe = frozenset(range(len(simbolo), len(simbolo) + 2))
    posicoes_perto = frozenset(range(len(simbolo) + 2, len(simbolo) + 4))

    sozinho_longe = _sem_criterio(monkeypatch, lambda: _ler(gramatica, simbolo, longe))
    lido = _ler(gramatica, simbolo, extras)

    assert sozinho_longe.bracos == posicoes_longe
    assert lido.x
    assert lido.bracos == posicoes_perto


@pytest.mark.parametrize(
    ("distancia", "marca"),
    [(0.3, True), (0.95, True), (1.05, False), (_VIZINHO, False)],
    ids=["perto", "dentro-da-borda", "fora-da-borda", "vizinho"],
)
@pytest.mark.parametrize("k", [0.5, 1.0, 2.0], ids=["metade", "base", "dobro"])
@pytest.mark.parametrize("gramatica", _GRAMATICAS)
def test_mesma_decisao_com_o_desenho_inteiro_em_outra_escala(
    gramatica: Gramatica, k: float, distancia: float, marca: bool
) -> None:
    """Símbolo e X escalados juntos: o critério é relativo à escala, então a decisão é a mesma."""
    simbolo = _simbolo(gramatica, k=k)
    extras = _x_a(gramatica, simbolo, distancia, 0.0, _MEIO_LONGO, k=k, glifo=True)

    assert _ler(gramatica, simbolo, extras, glifo=True).x is marca


# --- a diagonal do BT não é braço de X ----------------------------------------------------------


def test_diagonal_do_bt_e_um_traco_solto_cruzando_nela_nao_formam_x() -> None:
    """O traço solto, preto como a diagonal, cruza-a no meio a 86 graus e tem comprimento
    parecido; não passa além dos lados longos, então não é segunda diagonal."""
    maior = CORPO[0]
    # 30 graus do eixo, do outro lado da diagonal; a lateral de cada ponta fica dentro do lado
    # longo mais a folga de "passar além".
    meio = 0.8125 * _ESCALA_BASE / 2
    u = _direcao(_eixo(0.0) - 30.0)
    traco = linha(
        (_C[0] - meio * u[0], _C[1] - meio * u[1]), (_C[0] + meio * u[0], _C[1] + meio * u[1])
    )
    simbolo = _simbolo("bt")
    pagina = _pagina(simbolo, [traco], glifo=False)
    contexto = contexto_gramaticas(pagina)
    (achado,) = retangulos_candidatos(contexto)

    # Controle: sem a diagonal entre os próprios, ela e o traço formam um X perto do centro.
    par = tem_x(contexto, achado.caixa, maior, math.radians(_eixo(0.0)), frozenset())
    assert par is not None
    assert {s.caminho for s in par} == {1, 2}
    assert not achado.x


# --- variantes: envolvente com X próprio e com X de vizinho -------------------------------------


_Casos = Sequence[tuple[str, Mapping[str, Any]]]


def _pares(casos: _Casos) -> list[tuple[Any, Any]]:
    return [
        ({"family_id": "autoral"}, {"id": v, "recognition": {"status": "enabled", "grammar": g}})
        for v, g in casos
    ]


def _variantes(gramatica: Gramatica, caminhos: Sequence[Caminho]) -> set[str]:
    casos = CASOS_HASTE if gramatica == "haste" else CASOS_RECT_DIAGONAL
    return {
        str(c.variante["id"]) for c in casar_variantes(pagina_gramatica(caminhos), _pares(casos))
    }


_CASOS_VARIANTE: Final = [
    pytest.param("haste", DECRESCENTES, True, "s19-v003", "s19-v002", id="haste3-envolvente"),
    pytest.param("haste", ALTERNADAS, True, "s21-v007", "s21-v006", id="haste4-envolvente"),
    pytest.param("bt", DECRESCENTES, True, "s21-v003", "s21-v002", id="bt-envolvente"),
    pytest.param("haste", DECRESCENTES, False, "s19-v004", "s19-v001", id="haste3-sem-envolvente"),
    pytest.param("haste", ALTERNADAS, False, "s21-v008", "s21-v005", id="haste4-sem-envolvente"),
    pytest.param("bt", DECRESCENTES, False, "s21-v004", "s21-v001", id="bt-sem-envolvente"),
]


@pytest.mark.parametrize(("gramatica", "barras", "envolvente", "com_x", "sem_x"), _CASOS_VARIANTE)
def test_x_proprio_casa_a_variante_com_retirada(
    gramatica: Gramatica, barras: Sequence[float], envolvente: bool, com_x: str, sem_x: str
) -> None:
    simbolo = _simbolo(gramatica, envolvente=envolvente, barras=barras)
    extras = _x_proprio(gramatica, barras=barras)

    assert _variantes(gramatica, [*simbolo, *extras]) == {f"cemig-eo-r3-{com_x}"}


@pytest.mark.parametrize(("gramatica", "barras", "envolvente", "com_x", "sem_x"), _CASOS_VARIANTE)
def test_x_de_vizinho_casa_a_variante_sem_retirada(
    gramatica: Gramatica,
    barras: Sequence[float],
    envolvente: bool,
    com_x: str,
    sem_x: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simbolo = _simbolo(gramatica, envolvente=envolvente, barras=barras)
    centro = _centro(_ler(gramatica, simbolo).pictograma)
    extras = _x(_deslocado(centro, _VIZINHO * _ESCALA_BASE, 0.0), _MEIO_LONGO * _ESCALA_BASE)
    caminhos = [*simbolo, *extras]

    assert _sem_criterio(monkeypatch, lambda: _variantes(gramatica, caminhos)) == {
        f"cemig-eo-r3-{com_x}"
    }
    assert _variantes(gramatica, caminhos) == {f"cemig-eo-r3-{sem_x}"}


# --- guarda de contexto -------------------------------------------------------------------------


def _candidatos(gramatica: Gramatica) -> Callable[..., tuple[object, ...]]:
    return hastes_candidatas if gramatica == "haste" else retangulos_candidatos


@pytest.mark.parametrize("gramatica", _GRAMATICAS)
def test_marcas_de_outro_contexto_da_mesma_pagina_levantam(gramatica: Gramatica) -> None:
    pagina = _pagina(_simbolo(gramatica), (), glifo=False)
    contexto, outro = contexto_gramaticas(pagina), contexto_gramaticas(pagina)

    with pytest.raises(ValueError, match="contexto"):
        _candidatos(gramatica)(contexto, marcas=MarcasDaPagina(outro))


@pytest.mark.parametrize("gramatica", _GRAMATICAS)
def test_marcas_de_outro_contexto_levantam_mesmo_sem_simbolo_na_pagina(
    gramatica: Gramatica,
) -> None:
    """A guarda não depende de haver candidato: a página só tem um traço solto."""
    pagina = pagina_gramatica([linha((10.0, 10.0), (12.0, 10.0))])
    contexto, outro = contexto_gramaticas(pagina), contexto_gramaticas(pagina)

    assert _candidatos(gramatica)(contexto) == ()
    with pytest.raises(ValueError, match="contexto"):
        _candidatos(gramatica)(contexto, marcas=MarcasDaPagina(outro))


@pytest.mark.parametrize("gramatica", _GRAMATICAS)
def test_marcas_recusadas_nao_gastam_o_orcamento_do_contexto_delas(gramatica: Gramatica) -> None:
    contexto = contexto_gramaticas(_pagina(_simbolo(gramatica, envolvente=True), (), glifo=False))
    outro: ContextoGramatica = contexto_gramaticas(
        _pagina(_simbolo(gramatica, envolvente=True), (), glifo=False)
    )
    marcas = MarcasDaPagina(outro)
    antes = outro.orcamento.gasto

    with pytest.raises(ValueError, match="contexto"):
        _candidatos(gramatica)(contexto, marcas=marcas)

    assert outro.orcamento.gasto == antes


def _deslocar_caminho(caminho: Caminho, desvio: Ponto) -> Caminho:
    return replace(
        caminho,
        subcaminhos=tuple(
            tuple(
                replace(
                    item, pontos=tuple((p[0] + desvio[0], p[1] + desvio[1]) for p in item.pontos)
                )
                for item in subcaminho
            )
            for subcaminho in caminho.subcaminhos
        ),
    )


def test_as_mesmas_marcas_servem_as_duas_gramaticas_do_contexto() -> None:
    """Haste e retângulo na mesma página, com as marcas compartilhadas como no casador."""
    haste = _simbolo("haste", envolvente=True)
    bt = [
        _deslocar_caminho(c, (0.0, 80.0))
        for c in [*_simbolo("bt", envolvente=True), *_x_proprio("bt")]
    ]
    pagina = pagina_gramatica([*haste, *bt])
    contexto = contexto_gramaticas(pagina)
    marcas = MarcasDaPagina(contexto)

    hastes = hastes_candidatas(contexto, marcas=marcas)
    retangulos = retangulos_candidatos(contexto, marcas=marcas)

    assert hastes == hastes_candidatas(contexto_gramaticas(pagina))
    assert retangulos == retangulos_candidatos(contexto_gramaticas(pagina))
    assert [(h.envolvente is not None, h.x is not None) for h in hastes] == [(True, False)]
    assert [(r.envolvente, r.x) for r in retangulos] == [(True, True)]


def test_contexto_das_marcas_nao_se_troca_nem_se_apaga() -> None:
    contexto = contexto_gramaticas(_pagina(_simbolo("haste"), (), glifo=False))
    marcas = MarcasDaPagina(contexto)

    with pytest.raises(AttributeError):
        marcas.contexto = contexto_gramaticas(_pagina(_simbolo("haste"), (), glifo=False))  # type: ignore[misc]
    with pytest.raises(AttributeError):
        del marcas.contexto

    assert marcas.contexto is contexto
    assert len(hastes_candidatas(contexto, marcas=marcas)) == 1
