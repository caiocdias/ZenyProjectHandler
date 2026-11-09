"""Associação símbolo → poste: raio pela caixa do símbolo e sítios em disputa (E07.2.2.1)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from tests.unit.test_ancoragem_poste import PAGINA, _disco, _ponto, _poste

from zeny_project_handler.adapters.interpretation.ancoragem_poste import (
    ancorar_postes_no_desenho,
)
from zeny_project_handler.application.interpretation_pipeline import (
    SYMBOL_SEMANTICS_VERSION,
    _symbol_support,
)
from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

_Candidatos = tuple[tuple[float, PropostaElemento], ...]


def _simbolo(x0: float, y0: float, x1: float, y1: float) -> GeometriaDocumento:
    return GeometriaDocumento.caixa(PAGINA, _ponto(x0, y0), _ponto(x1, y1))


def _em_ponto(chave: str, x: str, y: str) -> PropostaElemento:
    return replace(
        _poste(chave, chave.upper(), 0.5, 0.5),
        geometria=GeometriaDocumento.ponto(PAGINA, PontoNormalizado(Decimal(x), Decimal(y))),
    )


def _pendencia_com_sitios(sitios: str) -> tuple[tuple[str, str], ...]:
    return (("associacao_pendente", "poste_disco"), ("poste_disco_sitios", sitios))


def _ids(candidatos: _Candidatos) -> list[object]:
    return [item.id for _, item in candidatos]


def test_versao_da_semantica_de_simbolos() -> None:
    assert SYMBOL_SEMANTICS_VERSION == "e07-2-2-symbol-support-3"


def test_poste_longe_do_centro_mas_junto_da_caixa_e_suporte() -> None:
    poste = _em_ponto("a", "0.28", "0.30")

    suporte, candidatos = _symbol_support(_simbolo(0.29, 0.29, 0.35, 0.31), "base", (poste,))

    assert suporte == poste
    assert _ids(candidatos) == [poste.id]


@pytest.mark.parametrize(
    ("caixa_x0", "caixa_x1", "alcanca"),
    [
        pytest.param(0.02, 0.04, True, id="igual-ao-raio"),
        pytest.param(0.0201, 0.0211, False, id="logo-acima-do-raio"),
    ],
)
def test_limite_do_raio_pela_caixa_do_simbolo(
    caixa_x0: float, caixa_x1: float, alcanca: bool
) -> None:
    poste = _em_ponto("a", "0", "0.30")

    suporte, candidatos = _symbol_support(
        _simbolo(caixa_x0, 0.29, caixa_x1, 0.31), "base", (poste,)
    )

    assert suporte == (poste if alcanca else None)
    assert _ids(candidatos) == ([poste.id] if alcanca else [])


def test_simbolo_entre_postes_quase_equidistantes_fica_pendente() -> None:
    esquerda = _em_ponto("a", "0.28", "0.30")
    direita = _em_ponto("b", "0.373", "0.30")

    suporte, candidatos = _symbol_support(
        _simbolo(0.29, 0.29, 0.36, 0.31), "base", (esquerda, direita)
    )

    assert suporte is None
    assert set(_ids(candidatos)) == {esquerda.id, direita.id}


def test_diferenca_acima_da_margem_decide_pelo_poste_mais_proximo() -> None:
    esquerda = _em_ponto("a", "0.28", "0.30")
    direita = _em_ponto("b", "0.376", "0.30")

    suporte, candidatos = _symbol_support(
        _simbolo(0.29, 0.29, 0.36, 0.31), "base", (esquerda, direita)
    )

    assert suporte == esquerda
    assert _ids(candidatos) == [esquerda.id, direita.id]


def test_simbolo_colado_a_disco_disputado_nao_migra_para_o_vizinho() -> None:
    primeiro = _poste("a", "P1", 0.30, 0.30)
    segundo = _poste("b", "P2", 0.34, 0.30)
    vizinho = _poste("c", "P3", 0.32, 0.316)
    ancorados = ancorar_postes_no_desenho(
        (primeiro, segundo, vizinho),
        (_disco("disputado", 0.32, 0.30), _disco("do-vizinho", 0.32, 0.315)),
    )

    suporte, candidatos = _symbol_support(_simbolo(0.318, 0.298, 0.322, 0.302), "base", ancorados)

    assert suporte is None
    assert set(_ids(candidatos)) == {primeiro.id, segundo.id, vizinho.id}


def test_vizinho_empatado_com_o_disco_disputado_tambem_nao_leva_o_simbolo() -> None:
    pendente = _poste("a", "P1", 0.30, 0.30)
    outro_pendente = _poste("b", "P2", 0.34, 0.30)
    vizinho = _poste("c", "P3", 0.32, 0.316)
    ancorados = ancorar_postes_no_desenho(
        (pendente, outro_pendente, vizinho),
        (_disco("disputado", 0.32, 0.30), _disco("do-vizinho", 0.32, 0.315)),
    )

    # A caixa fica mais perto do disco do vizinho, com o disputado dentro da margem.
    suporte, candidatos = _symbol_support(_simbolo(0.318, 0.308, 0.322, 0.309), "base", ancorados)

    assert suporte is None
    assert _ids(candidatos)[0] == vizinho.id
    assert len(candidatos) == 3


def test_poste_disputado_nao_e_candidato_pela_posicao_do_texto() -> None:
    poste = _poste("a", "P1", 0.30, 0.30)
    ancorados = ancorar_postes_no_desenho(
        (poste,), (_disco("d1", 0.26, 0.30), _disco("d2", 0.342, 0.30))
    )

    suporte, candidatos = _symbol_support(_simbolo(0.299, 0.299, 0.301, 0.301), "base", ancorados)

    assert suporte is None
    assert candidatos == ()


def test_sitio_mais_proximo_do_pendente_e_o_que_conta() -> None:
    poste = _poste("a", "P1", 0.30, 0.30)
    ancorados = ancorar_postes_no_desenho(
        (poste,), (_disco("d1", 0.26, 0.30), _disco("d2", 0.342, 0.30))
    )

    suporte, candidatos = _symbol_support(_simbolo(0.341, 0.299, 0.343, 0.301), "base", ancorados)

    assert suporte is None
    assert [(round(distancia, 6), item.id) for distancia, item in candidatos] == [(0.0, poste.id)]


def test_poste_pendente_sem_sitio_registrado_nao_e_candidato() -> None:
    poste = _poste("a", "P1", 0.30, 0.30, extras=(("associacao_pendente", "poste_disco"),))

    suporte, candidatos = _symbol_support(_simbolo(0.299, 0.299, 0.301, 0.301), "base", (poste,))

    assert suporte is None
    assert candidatos == ()


def test_pendente_por_sitio_tomado_nao_tira_o_suporte_do_vencedor() -> None:
    vencedor = _poste("a", "P1", 0.335, 0.30)
    perdedor = _poste("b", "P2", 0.365, 0.30)
    ancorados = ancorar_postes_no_desenho(
        (vencedor, perdedor), (_disco("d1", 0.30, 0.30), _disco("d2", 0.345, 0.30))
    )
    posicionado = next(item for item in ancorados if item.id == vencedor.id)

    suporte, candidatos = _symbol_support(_simbolo(0.344, 0.299, 0.346, 0.301), "base", ancorados)

    assert suporte == posicionado
    assert _ids(candidatos) == [vencedor.id]


def test_outra_pendencia_segue_candidata_pela_posicao_do_texto() -> None:
    poste = _poste("a", "P1", 0.30, 0.30, extras=(("associacao_pendente", "outra_causa"),))

    suporte, candidatos = _symbol_support(_simbolo(0.299, 0.299, 0.301, 0.301), "base", (poste,))

    assert suporte == poste
    assert _ids(candidatos) == [poste.id]


def test_sitio_nao_numerico_nao_desordena_os_candidatos_validos() -> None:
    longe = _em_ponto("a", "0.30", "0.311")
    com_nan = _poste("b", "P2", 0.5, 0.5, extras=_pendencia_com_sitios("nan,nan"))
    perto = _em_ponto("c", "0.30", "0.30")

    suporte, candidatos = _symbol_support(
        _simbolo(0.299, 0.299, 0.301, 0.301), "base", (longe, com_nan, perto)
    )

    assert suporte == perto
    assert _ids(candidatos) == [perto.id, longe.id]
