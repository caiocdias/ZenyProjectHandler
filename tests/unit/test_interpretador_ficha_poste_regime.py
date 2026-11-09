"""Vínculos do poste pendente por disputa de sítio no regime de texto (E07.2.2.1)."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest
from tests.unit.test_ancoragem_poste import (
    EXECUCAO,
    PAGINA,
    _atributos,
    _disco,
    _ponto,
    _poste,
    _solicitacao_relacoes,
)

from zeny_project_handler.adapters.interpretation.ancoragem_poste import (
    ancorar_postes_no_desenho,
)
from zeny_project_handler.adapters.interpretation.ficha_poste import InterpretadorFichaPoste
from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento
from zeny_project_handler.domain.values import GeometriaDocumento


def _disputa() -> tuple[tuple[PropostaElemento, ...], tuple[PropostaElemento, ...]]:
    """Dois postes disputam um só disco; a saída real da ancoragem os deixa pendentes."""
    originais = (_poste("a", "P1", 0.30, 0.30), _poste("b", "P2", 0.34, 0.30))
    resultado = ancorar_postes_no_desenho(originais, (_disco("d1", 0.32, 0.30),))
    assert all(_atributos(item)["associacao_pendente"] == "poste_disco" for item in resultado)
    return originais, resultado


def _estrutura(categoria: CategoriaElemento = CategoriaElemento.ESTRUTURA_MT) -> PropostaElemento:
    return replace(_poste("e", "P1", 0.36, 0.30, codigo="N1"), categoria=categoria)


def _relacoes(
    catalogo: CatalogoTecnico, elementos: tuple[PropostaElemento, ...]
) -> list[tuple[str, UUID, UUID]]:
    solicitacao = _solicitacao_relacoes(catalogo)
    relacoes = InterpretadorFichaPoste(solicitacao.registro)._gerar_relacoes(
        EXECUCAO, elementos, solicitacao
    )
    return [
        (item.tipo_relacao, item.origem_referencia_id, item.destino_referencia_id)
        for item in relacoes
    ]


def test_versao_do_interpretador() -> None:
    assert InterpretadorFichaPoste.versao == "27.0"


@pytest.mark.parametrize(
    ("categoria", "tipo_relacao"),
    [
        pytest.param(CategoriaElemento.ESTRUTURA_MT, "INSTALADA_EM", id="estrutura-mt"),
        pytest.param(CategoriaElemento.EQUIPAMENTO, "INSTALADO_EM", id="equipamento"),
    ],
)
def test_poste_pendente_por_disputa_recebe_a_relacao_de_texto(
    catalogo_inicial: CatalogoTecnico, categoria: CategoriaElemento, tipo_relacao: str
) -> None:
    _, resultado = _disputa()
    origem = _estrutura(categoria)

    relacoes = _relacoes(catalogo_inicial, (*resultado, origem))

    assert relacoes == [(tipo_relacao, origem.id, resultado[0].id)]


def test_poste_pendente_por_disputa_nao_recebe_relacao_fora_do_regime_de_texto(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    _, resultado = _disputa()
    cabo = replace(
        _poste("c", "P1", 0.5, 0.5),
        categoria=CategoriaElemento.CABO,
        geometria=GeometriaDocumento.polilinha(PAGINA, (_ponto(0.29, 0.30), _ponto(0.31, 0.30))),
        atributos_sugeridos=(),
    )

    assert _relacoes(catalogo_inicial, (*resultado, cabo)) == []


def test_pendencia_de_outro_valor_segue_sem_relacao_no_regime_de_texto(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    pendente = _poste(
        "a",
        "P1",
        0.30,
        0.30,
        extras=(("associacao_pendente", "poste_mesmo_identificador"),),
    )

    assert _relacoes(catalogo_inicial, (pendente, _estrutura())) == []


def test_proposta_original_do_pendente_segue_com_pendencia_e_geometria(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    _, resultado = _disputa()
    antes = tuple(resultado)

    _relacoes(catalogo_inicial, (*resultado, _estrutura()))

    assert resultado == antes
    for item in resultado:
        assert _atributos(item)["associacao_pendente"] == "poste_disco"
        assert "poste_texto_centro" not in _atributos(item)


def test_leituras_empilhadas_do_p_pendente_que_empatam_ficam_sem_relacao(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    originais = (
        _poste("a1", "P1", 0.30, 0.29),
        _poste("a2", "P1", 0.30, 0.31, codigo="12-300"),
        _poste("b", "P2", 0.34, 0.30),
    )
    resultado = ancorar_postes_no_desenho(originais, (_disco("d1", 0.32, 0.30),))
    pilha = tuple(
        item for item in resultado if _atributos(item)["identificador_operacional"] == "P1"
    )
    assert len(pilha) == 2
    assert all(_atributos(item).get("associacao_pendente") == "poste_disco" for item in pilha)
    origem = replace(_estrutura(), geometria=_poste("e", "P1", 0.36, 0.30).geometria)

    assert _relacoes(catalogo_inicial, (*resultado, origem)) == []
