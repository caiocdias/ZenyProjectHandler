"""Ataques aos itens herdados do BT (Task 4, E06.3.3.2.1, R-5) em `rect_diagonal`.

Retângulo de vários caminhos (âncora em `origens[0]`, os demais nos componentes e fora do X e
da envolvente), lado maior máximo de 2 vezes 8,58 pt, haste que sai da borda da envolvente e o
toco curto da outra ponta (caracterização). Páginas sintéticas do modelo, sem folha real.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Any, Final

import pytest
from tests.fixtures.symbol_grammars.paginas import (
    circulo_bezier,
    linha,
    pagina_gramatica,
    poligono,
    texto,
)
from tests.fixtures.symbol_grammars.rect_diagonal import (
    CASOS_RECT_DIAGONAL,
    desenhar_positivo,
    pagina_desenhada,
)

from zeny_project_handler.adapters.analysis.drawing_model import grammar_rect_diagonal
from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import (
    envolvente,
    tem_x,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caixa,
    Caminho,
    ItemCaminho,
    Polilinha,
    Ponto,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    PaginaGramatica,
    Segmento,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import (
    CasamentoGramatica,
    casar_variantes,
)

_VARIANTES: Final = [variante for variante, _ in CASOS_RECT_DIAGONAL]
_V001, _V002, _V003, _V004 = _VARIANTES
_CENTRO: Final[Ponto] = (100.0, 100.0)
_CORPO: Final = (8.0, 3.0)
_RAIO: Final = 7.0
_HASTE: Final = 10.0
_LADO_MAIOR_MAXIMO: Final = 2 * 8.58


def _pares() -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    return [
        (
            {"family_id": "autoral"},
            {"id": variante, "recognition": {"status": "enabled", "grammar": gramatica}},
        )
        for variante, gramatica in CASOS_RECT_DIAGONAL
    ]


def _casamentos(pagina: PaginaGramatica) -> tuple[CasamentoGramatica, ...]:
    return casar_variantes(pagina, _pares())


def _variantes(pagina: PaginaGramatica) -> list[str]:
    return [str(c.variante["id"]) for c in _casamentos(pagina)]


def _gira(ponto: Ponto, graus: float, centro: Ponto = _CENTRO) -> Ponto:
    r = math.radians(graus)
    dx, dy = ponto[0] - centro[0], ponto[1] - centro[1]
    return (
        centro[0] + dx * math.cos(r) - dy * math.sin(r),
        centro[1] + dx * math.sin(r) + dy * math.cos(r),
    )


def _cantos(
    corpo: tuple[float, float] = _CORPO, centro: Ponto = _CENTRO, graus: float = 0.0
) -> list[Ponto]:
    """Corpo com o lado maior na vertical, girado `graus` em torno de `centro`."""
    cx, cy = centro
    meio_h, meio_l = corpo[0] / 2, corpo[1] / 2
    cantos = [
        (cx - meio_l, cy - meio_h),
        (cx + meio_l, cy - meio_h),
        (cx + meio_l, cy + meio_h),
        (cx - meio_l, cy + meio_h),
    ]
    return [_gira(p, graus, centro) for p in cantos]


def _diagonal(
    corpo: tuple[float, float] = _CORPO, centro: Ponto = _CENTRO, graus: float = 0.0
) -> tuple[Ponto, Ponto]:
    """Cruza os lados longos perto do centro e passa além deles (como a fixture PyMuPDF)."""
    cx, cy = centro
    meio_h, meio_l = corpo[0] / 2, corpo[1] / 2
    a = (cx - 2 * meio_l, cy + meio_h / 2)
    b = (cx + 2 * meio_l, cy - meio_h / 2)
    return _gira(a, graus, centro), _gira(b, graus, centro)


def _bt(
    corpo: tuple[float, float] = _CORPO, centro: Ponto = _CENTRO, graus: float = 0.0
) -> list[Caminho]:
    """Retângulo (posição 0) e diagonal (posição 1)."""
    return [poligono(_cantos(corpo, centro, graus)), linha(*_diagonal(corpo, centro, graus))]


def _poligonal(pontos: Sequence[Ponto]) -> Caminho:
    """Um caminho aberto de retas consecutivas."""
    itens = tuple(ItemCaminho("l", (a, b)) for a, b in pairwise(pontos))
    return Caminho((itens,), linha(pontos[0], pontos[1]).estilo, "traco", 0)


def _polilinha_fechada(pagina: PaginaGramatica) -> Polilinha:
    [polilinha] = [
        p
        for p in pagina.modelo.primitivas
        if isinstance(p, Polilinha) and p.fechada and len(set(p.pontos)) == 4
    ]
    return polilinha


# --- retângulo de vários caminhos ----------------------------------------------------------


def _lados_soltos_fora_de_ordem() -> PaginaGramatica:
    """Diagonal primeiro, os quatro lados fora de ordem e um traço alheio no meio deles."""
    c0, c1, c2, c3 = _cantos()
    caminhos = [
        linha(*_diagonal()),
        linha(c2, c3),
        linha((20.0, 20.0), (20.0, 40.0)),
        linha(c0, c1),
        linha(c3, c0),
        linha(c1, c2),
    ]
    return pagina_gramatica(caminhos)


def test_retangulo_de_lados_soltos_fora_de_ordem_tem_a_ancora_em_origens_0() -> None:
    pagina = _lados_soltos_fora_de_ordem()
    origens = _polilinha_fechada(pagina).origens
    assert sorted(origens) == [1, 3, 4, 5]

    [casamento] = _casamentos(pagina)
    assert casamento.variante["id"] == _V001
    assert casamento.caminho == origens[0]


def test_retangulo_de_lados_soltos_poe_os_demais_lados_nos_componentes_sem_repetir() -> None:
    """Todos os lados que não são a âncora entram; a âncora e o traço alheio (2) ficam fora."""
    pagina = _lados_soltos_fora_de_ordem()
    origens = _polilinha_fechada(pagina).origens

    [casamento] = _casamentos(pagina)
    componentes = casamento.componentes
    assert componentes == tuple(sorted({0, *origens} - {origens[0]}))
    assert len(set(componentes)) == len(componentes)
    assert casamento.caminho not in componentes
    assert 2 not in componentes


def test_retangulo_de_dois_caminhos_em_l_poe_o_outro_l_nos_componentes() -> None:
    c0, c1, c2, c3 = _cantos()
    caminhos = [_poligonal([c0, c1, c2]), linha(*_diagonal()), _poligonal([c2, c3, c0])]
    pagina = pagina_gramatica(caminhos)
    origens = _polilinha_fechada(pagina).origens
    assert sorted(origens) == [0, 2]

    [casamento] = _casamentos(pagina)
    assert casamento.caminho == origens[0]
    assert casamento.componentes == tuple(sorted({1, *origens} - {origens[0]}))


@pytest.mark.parametrize("graus", [30.0, 90.0], ids=["30", "90"])
@pytest.mark.parametrize(
    ("variante", "esperados"),
    [(_V001, (1, 2, 3, 4)), (_V002, (1, 2, 3, 4, 5)), (_V003, (1, 2, 3, 4, 5, 6, 7))],
)
def test_retangulo_de_quatro_caminhos_girado_casa_a_variante_com_os_lados(
    variante: str, esperados: tuple[int, ...], graus: float
) -> None:
    """Girado (coordenadas float32 do PyMuPDF), os quatro lados ainda fecham o retângulo."""
    pagina = pagina_desenhada(
        lambda p: desenhar_positivo(p, variante, graus=graus, lados_separados=True)
    )

    [casamento] = _casamentos(pagina)
    assert casamento.variante["id"] == variante
    assert casamento.caminho == 0
    assert casamento.componentes == esperados


def test_lados_do_retangulo_de_varios_caminhos_entram_nos_proprios_do_x(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vistos: list[frozenset[Segmento]] = []

    def espiao(
        contexto: Any, pictograma: Caixa, escala: float, eixo: float, proprios: frozenset[Segmento]
    ) -> Any:
        vistos.append(proprios)
        return tem_x(contexto, pictograma, escala, eixo, proprios)

    monkeypatch.setattr(grammar_rect_diagonal, "tem_x", espiao)
    pagina = _lados_soltos_fora_de_ordem()
    origens = _polilinha_fechada(pagina).origens

    _casamentos(pagina)
    [proprios] = vistos
    assert {s.caminho for s in proprios} >= set(origens)


def test_lados_do_retangulo_de_varios_caminhos_nao_contam_como_envolvente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vistos: list[frozenset[int]] = []

    def espiao(
        contornos: Any, exigidos: Any, escala: float, ancora: Ponto, proprios: frozenset[int]
    ) -> Any:
        vistos.append(proprios)
        return envolvente(contornos, exigidos, escala, ancora, proprios)

    monkeypatch.setattr(grammar_rect_diagonal, "envolvente", espiao)
    pagina = _lados_soltos_fora_de_ordem()
    origens = _polilinha_fechada(pagina).origens

    _casamentos(pagina)
    assert vistos == [frozenset(origens)]


# --- lado maior máximo --------------------------------------------------------------------


def _textos(origem: str | None) -> tuple[Any, ...]:
    """Texto longe do símbolo, só para fixar o perfil da página pela origem predominante."""
    return () if origem is None else (texto("LIVRE", (5.0, 5.0, 30.0, 12.0), origem),)  # type: ignore[arg-type]


_ORIGENS: Final = [None, "nativo", "shx", "glifo"]


@pytest.mark.parametrize("graus", [0.0, 30.0], ids=["0", "30"])
@pytest.mark.parametrize("origem", _ORIGENS, ids=str)
def test_lado_maior_logo_abaixo_do_maximo_casa_em_todo_perfil(
    origem: str | None, graus: float
) -> None:
    corpo = (_LADO_MAIOR_MAXIMO - 0.01, 5.0)
    pagina = pagina_gramatica(_bt(corpo, graus=graus), _textos(origem))

    assert _variantes(pagina) == [_V001]


@pytest.mark.parametrize("graus", [0.0, 30.0], ids=["0", "30"])
@pytest.mark.parametrize("origem", _ORIGENS, ids=str)
def test_lado_maior_logo_acima_do_maximo_nao_casa_em_nenhum_perfil(
    origem: str | None, graus: float
) -> None:
    corpo = (_LADO_MAIOR_MAXIMO + 0.01, 5.0)
    pagina = pagina_gramatica(_bt(corpo, graus=graus), _textos(origem))

    assert _variantes(pagina) == []


def test_celula_de_tabela_riscada_ao_lado_de_um_bt_casa_so_o_bt() -> None:
    """Grade de células 24 por 8 pt (proporção de corpo) com a do meio da primeira linha riscada
    pelo centro, de lado longo a lado longo e além deles; um BT fora da grade."""
    celulas = [
        poligono([(x0, y0), (x0 + 24.0, y0), (x0 + 24.0, y0 + 8.0), (x0, y0 + 8.0)])
        for x0 in (40.0, 64.0, 88.0)
        for y0 in (180.0, 188.0)
    ]
    risco = linha((70.0, 190.0), (82.0, 178.0))
    pagina = pagina_gramatica([*_bt(), *celulas, risco])

    [casamento] = _casamentos(pagina)
    assert casamento.variante["id"] == _V001
    assert casamento.caminho == 0
    assert casamento.componentes == (1,)


@pytest.mark.parametrize(
    ("origem", "abaixo", "acima"),
    [(None, (2.9, 1.0), (3.1, 1.0)), ("glifo", (1.4, 0.5), (1.6, 0.5))],
    ids=["padrao", "glifo"],
)
def test_lado_maior_minimo_de_cada_perfil_nao_muda_com_o_maximo(
    origem: str | None, abaixo: tuple[float, float], acima: tuple[float, float]
) -> None:
    assert _variantes(pagina_gramatica(_bt(abaixo), _textos(origem))) == []
    assert _variantes(pagina_gramatica(_bt(acima), _textos(origem))) == [_V001]


# --- haste que sai da borda da envolvente ---------------------------------------------------


def _com_envolvente(
    haste: tuple[Ponto, Ponto] | None,
    *,
    centro_corpo: Ponto = _CENTRO,
    raio: float = _RAIO,
    extras: Sequence[Caminho] = (),
) -> PaginaGramatica:
    """Retângulo (0), diagonal (1), envolvente de raio `raio` em `_CENTRO` (2) e haste (3)."""
    caminhos = [*_bt(centro=centro_corpo), circulo_bezier(_CENTRO, raio)]
    if haste is not None:
        caminhos.append(linha(*haste))
    return pagina_gramatica([*caminhos, *extras])


def _componentes_v002(pagina: PaginaGramatica) -> tuple[int, ...]:
    [casamento] = _casamentos(pagina)
    assert casamento.variante["id"] == _V002
    return casamento.componentes


@pytest.mark.parametrize("sinal", [-1, 1], ids=["topo", "base"])
def test_haste_que_sai_de_qualquer_borda_da_envolvente_no_eixo_entra(sinal: int) -> None:
    cx, cy = _CENTRO
    borda = (cx, cy + sinal * _RAIO)
    pagina = _com_envolvente((borda, (cx, borda[1] + sinal * _HASTE)))

    assert _componentes_v002(pagina) == (1, 2, 3)


def test_haste_da_borda_com_corpo_fora_do_centro_da_envolvente_sai_da_borda_real() -> None:
    """Corpo deslocado 2,5 pt de lado: o eixo dele cruza o círculo a 6,54 pt do centro, não a 7.

    Quem tomasse o ponto da borda como centro mais raio ao longo do eixo erraria por 0,46 pt,
    acima da tolerância de 0,45 pt na ponta.
    """
    cx, cy = _CENTRO
    lateral = 2.5
    borda_y = cy - math.sqrt(_RAIO**2 - lateral**2)
    pagina = _com_envolvente(
        ((cx + lateral, borda_y), (cx + lateral, borda_y - _HASTE)),
        centro_corpo=(cx + lateral, cy),
    )

    assert _componentes_v002(pagina) == (1, 2, 3)


@pytest.mark.parametrize(
    ("desvio", "entra"),
    [(0.1, True), (0.3, False)],
    ids=["0_1_rad_alinhada", "0_3_rad_desalinhada"],
)
def test_haste_da_borda_so_entra_alinhada_ao_corpo(desvio: float, entra: bool) -> None:
    cx, cy = _CENTRO
    borda = (cx, cy - _RAIO)
    fim = (cx + _HASTE * math.sin(desvio), borda[1] - _HASTE * math.cos(desvio))
    pagina = _com_envolvente((borda, fim))

    assert _componentes_v002(pagina) == ((1, 2, 3) if entra else (1, 2))


def test_traco_alinhado_que_encosta_na_envolvente_fora_do_eixo_nao_e_haste() -> None:
    """Paralelo ao corpo, mas a 1 pt de lado do eixo: encosta no círculo longe da ponta."""
    cx, cy = _CENTRO
    lado = 1.0
    borda_y = cy - math.sqrt(_RAIO**2 - lado**2)
    pagina = _com_envolvente(((cx + lado, borda_y), (cx + lado, borda_y - _HASTE)))

    assert _componentes_v002(pagina) == (1, 2)


def test_traco_no_eixo_que_comeca_longe_da_borda_da_envolvente_nao_e_haste() -> None:
    cx, cy = _CENTRO
    inicio = cy - _RAIO - 0.8
    pagina = _com_envolvente(((cx, inicio), (cx, inicio - _HASTE)))

    assert _componentes_v002(pagina) == (1, 2)


@pytest.mark.parametrize(("variante", "esperados"), [(_V001, (1,)), (_V004, (1, 3, 4))])
def test_sem_envolvente_traco_no_eixo_longe_do_corpo_nao_e_haste(
    variante: str, esperados: tuple[int, ...]
) -> None:
    """O traço que sairia da borda de raio 7 fica solto sem a envolvente: não entra."""
    pagina = pagina_desenhada(lambda p: desenhar_positivo(p, variante, haste_da_envolvente=True))

    [casamento] = _casamentos(pagina)
    assert casamento.variante["id"] == variante
    assert casamento.componentes == esperados


@pytest.mark.parametrize("sinal", [-1, 1], ids=["topo", "base"])
def test_sem_envolvente_haste_de_qualquer_ponta_do_corpo_continua_entrando(sinal: int) -> None:
    cx, cy = _CENTRO
    ponta = (cx, cy + sinal * _CORPO[0] / 2)
    pagina = pagina_gramatica([*_bt(), linha(ponta, (cx, ponta[1] + sinal * _HASTE))])

    [casamento] = _casamentos(pagina)
    assert casamento.variante["id"] == _V001
    assert casamento.componentes == (1, 2)


# --- caracterização (verde): o toco curto da outra ponta ------------------------------------


def test_caracterizacao_toco_curto_da_outra_ponta_ate_a_envolvente_fica_fora() -> None:
    """Haste longa da ponta de cima atravessando a envolvente e um toco de 1 pt da ponta de
    baixo até a borda. A busca devolve uma haste só, a mais longa: o toco fica fora dos
    componentes (Task 4, preocupação 3 do relatório; não é defeito desta tarefa). Se a regra
    passar a "todas as hastes alinhadas", atualize."""
    cx, cy = _CENTRO
    meio = _CORPO[0] / 2
    raio = meio + 1.0
    longa = linha((cx, cy - meio), (cx, cy - meio - _HASTE))
    toco = linha((cx, cy + meio), (cx, cy + raio))
    pagina = pagina_gramatica([*_bt(), circulo_bezier(_CENTRO, raio), longa, toco])

    assert _componentes_v002(pagina) == (1, 2, 3)
