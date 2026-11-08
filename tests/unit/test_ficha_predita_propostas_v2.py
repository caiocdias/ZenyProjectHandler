"""Fonte ``propostas-v2`` da ficha predita: estruturas, código de cabo e estai."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from scripts.benchmark_ficha_poste import VERSAO_EXTRACAO_PROPOSTAS_V2
from scripts.ficha_poste import validar_ficha
from scripts.ficha_predita_propostas import ficha_predita_propostas
from tests.unit.test_ficha_predita_propostas import SHA_QUALQUER, _Cena

from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, EstadoRevisao

POSTE = CategoriaElemento.POSTE
ESTRUTURA_MT = CategoriaElemento.ESTRUTURA_MT
EQUIPAMENTO = CategoriaElemento.EQUIPAMENTO
CABO = CategoriaElemento.CABO
V1 = "propostas-v1"


def _ficha(cena: _Cena, versao: str = VERSAO_EXTRACAO_PROPOSTAS_V2) -> dict[str, Any]:
    variante = cena.variante()
    # A Task 4 lê ``variante["extraction"]``: a cena sempre o fornece, ainda que vazio.
    variante["extraction"] = {}
    return ficha_predita_propostas(variante, SHA_QUALQUER, native_only=True, versao=versao)


def _poste(cena: _Cena, x: float = 0.2) -> PropostaElemento:
    return cena.elemento(POSTE, codigo="POSTE", x=x, atributos={"identificador_operacional": "P"})


def _estai(cena: _Cena, suporte: object) -> PropostaElemento:
    return cena.elemento(
        EQUIPAMENTO,
        atributos={"simbolo_classe": "ESTAI", "suporte_proposta_id": suporte},
    )


def _simbolos(ficha: dict[str, Any]) -> list[str]:
    return [s["classe"] for poste in ficha["postes"] for s in poste["simbolos"]]


def test_v2_usa_token_com_qualificador(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    poste = _poste(cena)
    com_token = cena.elemento(ESTRUTURA_MT, codigo="U4", atributos={"token_estrutura": "U4(1)"})
    sem_token = cena.elemento(ESTRUTURA_MT, codigo="N3")
    sem_nada = cena.elemento(ESTRUTURA_MT)
    for estrutura in (com_token, sem_token, sem_nada):
        cena.relacao(estrutura, poste, "INSTALADA_EM")

    ficha = _ficha(cena)

    assert validar_ficha(ficha) == []
    assert ficha["gerador"]["versao_extracao"] == "propostas-v2"
    assert ficha["postes"][0]["estruturas"] == ["N3", "U4(1)"]


def test_v2_normaliza_espaco_apos_hifen(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    cabo = cena.elemento(CABO, codigo="N-   (1N2)  AB")
    cena.relacao(cabo, p1, "CONECTA")
    cena.relacao(cabo, p2, "CONECTA")

    assert _ficha(cena)["vaos"][0]["cabo"] == "N-(1N2) AB"
    assert _ficha(cena, V1)["vaos"][0]["cabo"] == "N-   (1N2)  AB"


def test_v2_rejeitada_fica_fora(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    poste = _poste(cena)
    estrutura = cena.elemento(
        ESTRUTURA_MT,
        codigo="N3",
        estado=EstadoRevisao.REJEITADA,
        atributos={"token_estrutura": "N3(1)"},
    )
    estai = cena.elemento(
        EQUIPAMENTO,
        estado=EstadoRevisao.REJEITADA,
        atributos={"simbolo_classe": "ESTAI", "suporte_proposta_id": str(poste.id)},
    )
    cena.relacao(estrutura, poste, "INSTALADA_EM")

    ficha = _ficha(cena)

    assert ficha["postes"][0]["estruturas"] == []
    assert _simbolos(ficha) == []
    assert estai.id not in {s["id"] for p in ficha["postes"] for s in p["simbolos"]}


def test_v2_estai_entra_pelo_suporte_do_poste(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    _estai(cena, str(p2.id))

    ficha = _ficha(cena)

    por_id = {poste["id"]: poste for poste in ficha["postes"]}
    assert _simbolos(ficha) == ["ESTAI"]
    assert [s["classe"] for s in por_id[str(p2.id)]["simbolos"]] == ["ESTAI"]
    assert por_id[str(p1.id)]["simbolos"] == []
    assert "simbolos_de_poste_fora_da_ficha" not in ficha["atributos_extras"]


def test_v2_estai_com_relacao_vale_a_relacao(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    estai = _estai(cena, str(p2.id))
    cena.relacao(estai, p1, "INSTALADO_EM")

    por_id = {poste["id"]: poste for poste in _ficha(cena)["postes"]}

    assert [s["classe"] for s in por_id[str(p1.id)]["simbolos"]] == ["ESTAI"]
    assert por_id[str(p2.id)]["simbolos"] == []


def test_v2_estai_com_suporte_fora_da_ficha_nao_entra_no_vizinho(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    _poste(cena)
    _estai(cena, str(uuid4()))

    ficha = _ficha(cena)

    assert _simbolos(ficha) == []
    assert ficha["atributos_extras"]["simbolos_de_poste_fora_da_ficha"] == 1


@pytest.mark.parametrize("suporte", ["nao-e-uuid", "", None, 7, "  "])
def test_v2_estai_com_suporte_invalido_nao_entra(
    catalogo_inicial: CatalogoTecnico, suporte: object
) -> None:
    cena = _Cena(catalogo_inicial)
    _poste(cena)
    _estai(cena, suporte)

    ficha = _ficha(cena)

    assert _simbolos(ficha) == []
    assert ficha["atributos_extras"]["simbolos_de_poste_fora_da_ficha"] == 1


def test_v1_continua_igual(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    estrutura = cena.elemento(ESTRUTURA_MT, codigo="U4", atributos={"token_estrutura": "U4(1)"})
    cena.relacao(estrutura, p1, "INSTALADA_EM")
    _estai(cena, str(p2.id))
    cabo = cena.elemento(CABO, codigo="N- (1N2)")
    cena.relacao(cabo, p1, "CONECTA")
    cena.relacao(cabo, p2, "CONECTA")

    padrao = ficha_predita_propostas(cena.variante(), SHA_QUALQUER, native_only=True)
    v1 = _ficha(cena, V1)

    assert v1 == padrao
    assert v1["gerador"]["versao_extracao"] == "propostas-v1"
    assert v1["postes"][0]["estruturas"] == ["U4"]
    assert _simbolos(v1) == []
    assert v1["atributos_extras"]["simbolos_de_poste_fora_da_ficha"] == 1
    assert v1["vaos"][0]["cabo"] == "N- (1N2)"


def test_versao_desconhecida_e_recusada(catalogo_inicial: CatalogoTecnico) -> None:
    with pytest.raises(ValueError, match="versao desconhecida"):
        _ficha(_Cena(catalogo_inicial), "propostas-v9")
