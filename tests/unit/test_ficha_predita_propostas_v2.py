"""Fonte ``propostas-v2`` da ficha predita: estruturas, código de cabo e estai."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from scripts.benchmark_ficha_poste import VERSAO_EXTRACAO_PROPOSTAS_V2
from scripts.ficha_poste import validar_ficha
from scripts.ficha_predita_propostas import ficha_predita_propostas
from tests.unit.test_ficha_predita_propostas import SHA_QUALQUER, _Cena, _decimal

from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    OrigemComprimentoVao,
    SituacaoProjeto,
)
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

POSTE = CategoriaElemento.POSTE
ESTRUTURA_MT = CategoriaElemento.ESTRUTURA_MT
EQUIPAMENTO = CategoriaElemento.EQUIPAMENTO
CABO = CategoriaElemento.CABO
V1 = "propostas-v1"


def _ficha(
    cena: _Cena,
    versao: str = VERSAO_EXTRACAO_PROPOSTAS_V2,
    rotulos: dict[UUID, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """``rotulos`` mapeia o id da evidÃªncia de rÃ³tulo para o canto (x, y) da caixa dela."""
    variante = cena.variante()
    evidencias = tuple(
        SimpleNamespace(
            id=evidencia_id,
            geometria=GeometriaDocumento.caixa(
                cena.pagina_id,
                PontoNormalizado(_decimal(x), _decimal(y)),
                PontoNormalizado(_decimal(x + 0.05), _decimal(y + 0.05)),
            ),
        )
        for evidencia_id, (x, y) in (rotulos or {}).items()
    )
    variante["extraction"] = SimpleNamespace(evidencias=evidencias)
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


def _cabo(
    cena: _Cena,
    codigo: str | None,
    p1: PropostaElemento,
    p2: PropostaElemento,
    rotulo: tuple[UUID, float, float] | None = None,
    *,
    situacao: SituacaoProjeto = SituacaoProjeto.EXISTENTE,
    atributos: dict[str, Any] | None = None,
) -> PropostaElemento:
    extras = dict(atributos or {})
    if rotulo is not None:
        extras["evidencia_rotulo_id"] = str(rotulo[0])
    cabo = cena.elemento(CABO, codigo=codigo, atributos=extras)
    cena.elementos[-1] = cabo = replace(cabo, situacao_projeto=situacao)
    cena.relacao(cabo, p1, "CONECTA")
    cena.relacao(cabo, p2, "CONECTA")
    return cabo


def _rotulos(*rotulos: tuple[UUID, float, float]) -> dict[UUID, tuple[float, float]]:
    return {rotulo[0]: (rotulo[1], rotulo[2]) for rotulo in rotulos}


@pytest.mark.parametrize("inverter", [False, True])
def test_v2_une_cabos_do_mesmo_par_em_vao_composto_de_cima_para_baixo(
    catalogo_inicial: CatalogoTecnico, inverter: bool
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    alto, baixo = (uuid4(), 0.3, 0.1), (uuid4(), 0.3, 0.5)
    pares = [("B", baixo), ("A", alto)]
    for codigo, rotulo in pares[:: -1 if inverter else 1]:
        _cabo(cena, codigo, p1, p2, rotulo)

    ficha = _ficha(cena, rotulos=_rotulos(alto, baixo))

    assert [vao["cabo"] for vao in ficha["vaos"]] == ["A / B"]


def test_v2_desempata_rotulos_na_mesma_linha_por_x(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    esquerda, direita = (uuid4(), 0.1, 0.3), (uuid4(), 0.5, 0.3)
    _cabo(cena, "A", p1, p2, direita)
    _cabo(cena, "B", p1, p2, esquerda)

    ficha = _ficha(cena, rotulos=_rotulos(esquerda, direita))

    assert [vao["cabo"] for vao in ficha["vaos"]] == ["B / A"]


def test_v2_cabo_sem_rotulo_vem_depois(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    rotulo = (uuid4(), 0.9, 0.9)
    _cabo(cena, "A", p1, p2)
    _cabo(cena, "C", p1, p2, (uuid4(), 0.1, 0.1))  # evidência inexistente na extração
    _cabo(cena, "B", p1, p2, rotulo)

    ficha = _ficha(cena, rotulos=_rotulos(rotulo))

    assert [vao["cabo"] for vao in ficha["vaos"]] == ["B / A / C"]


def test_v2_cabo_repetido_no_mesmo_par_nao_duplica(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    _cabo(cena, "N- (1N2)", p1, p2)
    _cabo(cena, "N-(1N2)", p2, p1)

    assert [vao["cabo"] for vao in _ficha(cena)["vaos"]] == ["N-(1N2)"]


def test_v2_codigo_ausente_nao_entra_na_uniao(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    _cabo(cena, None, p1, p2)
    _cabo(cena, "  ", p1, p2)
    _cabo(cena, "A", p1, p2)

    assert [vao["cabo"] for vao in _ficha(cena)["vaos"]] == ["A"]


def test_v2_cabos_sem_codigo_geram_vao_sem_cabo(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    _cabo(cena, None, p1, p2)

    assert [vao["cabo"] for vao in _ficha(cena)["vaos"]] == [None]


def test_v2_cabo_com_extremo_unico_nao_vira_vao(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    _cabo(cena, "A", p1, p1)
    _cabo(cena, "B", p1, p2)

    ficha = _ficha(cena)

    assert [vao["cabo"] for vao in ficha["vaos"]] == ["B"]
    assert ficha["atributos_extras"]["cabos_sem_vao"] == 1


def test_v2_situacoes_diferentes_no_mesmo_par_nao_se_fundem(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    _cabo(cena, "A", p1, p2)
    _cabo(cena, "B", p1, p2, situacao=SituacaoProjeto.INSTALAR)

    assert sorted(vao["cabo"] for vao in _ficha(cena)["vaos"]) == ["A", "B"]


def test_v2_par_sem_ordem_funde_a_b_e_b_a(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    _cabo(cena, "A", p1, p2)
    _cabo(cena, "B", p2, p1)

    ficha = _ficha(cena)

    assert [vao["cabo"] for vao in ficha["vaos"]] == ["A / B"]
    assert {ficha["vaos"][0]["de"], ficha["vaos"][0]["para"]} == {str(p1.id), str(p2.id)}


def test_v2_prefere_comprimento_anotado_no_vao_composto(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1 = cena.elemento(
        POSTE, codigo="POSTE", atributos={"coordenada_leste": 0, "coordenada_norte": 0}
    )
    p2 = cena.elemento(
        POSTE, codigo="POSTE", x=0.6, atributos={"coordenada_leste": 30, "coordenada_norte": 40}
    )
    primeiro, segundo = (uuid4(), 0.1, 0.1), (uuid4(), 0.1, 0.5)
    _cabo(cena, "A", p1, p2, primeiro)
    _cabo(cena, "B", p1, p2, segundo, atributos={"comprimento_m": "12.5"})

    vao = _ficha(cena, rotulos=_rotulos(primeiro, segundo))["vaos"][0]

    assert vao["cabo"] == "A / B"
    assert vao["comprimento_m"] == 12.5
    assert vao["atributos_extras"]["origem_comprimento"] == (
        OrigemComprimentoVao.ANOTACAO_DESENHO.value
    )


def test_v2_sem_anotado_usa_primeiro_comprimento_e_une_pendentes(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1 = cena.elemento(
        POSTE, codigo="POSTE", atributos={"coordenada_leste": 0, "coordenada_norte": 0}
    )
    p2 = cena.elemento(
        POSTE, codigo="POSTE", x=0.6, atributos={"coordenada_leste": 30, "coordenada_norte": 40}
    )
    _cabo(cena, "A", p1, p2, atributos={"revisao_tecnica_pendente": True})
    _cabo(cena, "B", p1, p2)

    vao = _ficha(cena)["vaos"][0]

    assert vao["comprimento_m"] == 50.0
    assert vao["atributos_extras"]["origem_comprimento"] == OrigemComprimentoVao.COORDENADAS.value
    assert vao["pendentes"] == ["cabo", "comprimento_m"]


def test_v1_nao_une_cabos_do_mesmo_par(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    _cabo(cena, "A", p1, p2)
    _cabo(cena, "B", p1, p2)

    assert [vao["cabo"] for vao in _ficha(cena, V1)["vaos"]] == ["A", "B"]
