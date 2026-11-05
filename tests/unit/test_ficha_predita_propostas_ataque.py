"""Ataque à Task 1 da E15 (gerador ``propostas-v1``): bordas, entradas hostis e regressões.

Complementa ``test_ficha_predita_propostas.py`` sem alterá-lo. Os testes que falham aqui documentam
defeitos do gerador (``scripts/ficha_predita_propostas.py``); nenhum foi ajustado para passar.
"""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from scripts import benchmark_ficha_poste
from scripts.benchmark_ficha_poste import (
    VERSAO_EXTRACAO,
    _gerador,
    executar,
    ficha_predita,
    main,
)
from scripts.ficha_poste import validar_ficha
from scripts.ficha_predita_propostas import CHAVES_PENDENCIA
from tests.unit.test_benchmark_ficha_poste import _referencia_sintetica
from tests.unit.test_ficha_predita_propostas import (
    CABO,
    EQUIPAMENTO,
    ESTRUTURA_MT,
    POSTE,
    RAIZ,
    SHA_QUALQUER,
    _Cena,
    _cena_completa,
)

from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, EstadoRevisao
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

ESTRUTURA_BT = CategoriaElemento.ESTRUTURA_BT


def _ficha_sem_cair(cena: _Cena) -> dict[str, Any] | None:
    """Ficha da cena, ou ``None`` se o gerador recusou a entrada com ``ValueError`` explícito.

    Qualquer outra exceção (``InvalidOperation``, ``KeyError``, ``AttributeError``...) escapa e
    reprova o teste: entrada hostil não pode derrubar o benchmark com erro cru.
    """
    try:
        return cena.ficha()
    except ValueError:
        return None


def _dois_postes_e_cabo(
    catalogo: CatalogoTecnico,
    *,
    atributos_p1: dict[str, Any] | None = None,
    atributos_p2: dict[str, Any] | None = None,
    atributos_cabo: dict[str, Any] | None = None,
) -> _Cena:
    cena = _Cena(catalogo)
    p1 = cena.elemento(POSTE, codigo="POSTE", atributos=atributos_p1)
    p2 = cena.elemento(POSTE, codigo="POSTE", x=0.6, atributos=atributos_p2)
    cabo = cena.elemento(CABO, codigo="ABC", atributos=atributos_cabo)
    cena.relacao(cabo, p1, "CONECTA")
    cena.relacao(cabo, p2, "CONECTA")
    return cena


# ---------------------------------------------------------------------------------------------
# Vínculos: só a relação certa, na direção certa, para poste da ficha
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("origem", "tipo", "chave"),
    [
        pytest.param(
            "estrutura",
            "INSTALADO_EM",
            "estruturas_sem_poste",
            id="estrutura-com-tipo-de-equipamento",
        ),
        pytest.param("estrutura", "CONECTA", "estruturas_sem_poste", id="estrutura-com-conecta"),
        pytest.param(
            "equipamento",
            "INSTALADA_EM",
            "simbolos_de_poste_fora_da_ficha",
            id="equipamento-com-tipo-de-estrutura",
        ),
        pytest.param("cabo", "INSTALADA_EM", "cabos_sem_vao", id="cabo-com-instalada-em"),
        pytest.param("cabo", "conecta", "cabos_sem_vao", id="conecta-em-minuscula"),
    ],
)
def test_tipo_de_relacao_errado_nao_vincula(
    catalogo_inicial: CatalogoTecnico, origem: str, tipo: str, chave: str
) -> None:
    cena = _Cena(catalogo_inicial)
    p1 = cena.elemento(POSTE, codigo="POSTE")
    p2 = cena.elemento(POSTE, codigo="POSTE", x=0.6)
    peca = {
        "estrutura": lambda: cena.elemento(ESTRUTURA_MT, codigo="N3"),
        "equipamento": lambda: cena.elemento(EQUIPAMENTO, atributos={"simbolo_classe": "ESTAI"}),
        "cabo": lambda: cena.elemento(CABO, codigo="ABC"),
    }[origem]()
    cena.relacao(peca, p1, tipo)
    if origem == "cabo":
        cena.relacao(peca, p2, tipo)

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert ficha["vaos"] == []
    assert all(not poste["estruturas"] and not poste["simbolos"] for poste in ficha["postes"])
    assert ficha["atributos_extras"][chave] == 1


def test_relacao_na_direcao_inversa_nao_vincula(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    poste = cena.elemento(POSTE, codigo="POSTE")
    estrutura = cena.elemento(ESTRUTURA_MT, codigo="N3")
    cena.relacao(poste, estrutura, "INSTALADA_EM")  # poste -> estrutura: origem errada

    ficha = cena.ficha()

    assert ficha["postes"][0]["estruturas"] == []
    assert ficha["atributos_extras"]["estruturas_sem_poste"] == 1


def test_estrutura_bt_tambem_entra(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    poste = cena.elemento(POSTE, codigo="POSTE")
    cena.relacao(cena.elemento(ESTRUTURA_BT, codigo="B1"), poste, "INSTALADA_EM")

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert ficha["postes"][0]["estruturas"] == ["B1"]
    assert "estruturas_sem_poste" not in ficha["atributos_extras"]


def test_estrutura_ligada_a_poste_rejeitado_conta_como_sem_poste(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    rejeitado = cena.elemento(POSTE, codigo="POSTE", estado=EstadoRevisao.REJEITADA)
    cena.relacao(cena.elemento(ESTRUTURA_MT, codigo="N3"), rejeitado, "INSTALADA_EM")

    ficha = cena.ficha()

    assert ficha["postes"] == []
    assert ficha["atributos_extras"]["estruturas_sem_poste"] == 1


def test_estrutura_e_equipamento_em_ponto_de_entrega_nao_vinculam(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    entrega = cena.elemento(POSTE, codigo="POSTE", atributos={"tipo_ponto_rede": "ENTREGA"})
    cena.relacao(cena.elemento(ESTRUTURA_MT, codigo="N3"), entrega, "INSTALADA_EM")
    equipamento = cena.elemento(EQUIPAMENTO, atributos={"simbolo_classe": "ESTAI"})
    cena.relacao(equipamento, entrega, "INSTALADO_EM")

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert ficha["postes"] == []
    assert ficha["atributos_extras"]["postes_entrega"] == 1
    assert ficha["atributos_extras"]["estruturas_sem_poste"] == 1
    assert ficha["atributos_extras"]["simbolos_de_poste_fora_da_ficha"] == 1


def test_entrega_rejeitada_nao_conta_como_entrega(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    cena.elemento(POSTE, codigo="POSTE", atributos={"identificador_operacional": "P1"})
    cena.elemento(
        POSTE,
        codigo="POSTE",
        x=0.6,
        estado=EstadoRevisao.REJEITADA,
        atributos={"tipo_ponto_rede": "ENTREGA"},
    )

    ficha = cena.ficha()

    assert len(ficha["postes"]) == 1
    assert "postes_entrega" not in ficha["atributos_extras"]


def test_proposta_rejeitada_sem_vinculo_nao_entra_nas_contagens(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    cena.elemento(POSTE, codigo="POSTE")
    cena.elemento(ESTRUTURA_MT, codigo="N3", estado=EstadoRevisao.REJEITADA)
    cena.elemento(CABO, codigo="ABC", estado=EstadoRevisao.REJEITADA)
    cena.elemento(EQUIPAMENTO, estado=EstadoRevisao.REJEITADA)  # sem classe, mas rejeitado
    cena.elemento(
        EQUIPAMENTO, estado=EstadoRevisao.REJEITADA, atributos={"simbolo_classe": "ESTAI"}
    )

    ficha = cena.ficha()

    assert ficha["atributos_extras"] == {
        "equipamentos_sem_simbolo": 0,
        "simbolos_sem_area": 0,
        "simbolos_fora_do_inventario": 0,
    }


@pytest.mark.parametrize(
    "rejeitada",
    ["INSTALADA_EM", "INSTALADO_EM"],
)
def test_relacao_rejeitada_nao_vincula_estrutura_nem_equipamento(
    catalogo_inicial: CatalogoTecnico, rejeitada: str
) -> None:
    cena = _Cena(catalogo_inicial)
    poste = cena.elemento(POSTE, codigo="POSTE")
    estrutura = cena.elemento(ESTRUTURA_MT, codigo="N3")
    equipamento = cena.elemento(EQUIPAMENTO, atributos={"simbolo_classe": "ESTAI"})
    estado = EstadoRevisao.REJEITADA
    cena.relacao(
        estrutura,
        poste,
        "INSTALADA_EM",
        estado=estado if rejeitada == "INSTALADA_EM" else EstadoRevisao.PROPOSTA,
    )
    cena.relacao(
        equipamento,
        poste,
        "INSTALADO_EM",
        estado=estado if rejeitada == "INSTALADO_EM" else EstadoRevisao.PROPOSTA,
    )

    (poste_ficha,) = cena.ficha()["postes"]

    assert bool(poste_ficha["estruturas"]) is (rejeitada != "INSTALADA_EM")
    assert bool(poste_ficha["simbolos"]) is (rejeitada != "INSTALADO_EM")


def test_cabo_com_tres_postes_distintos_nao_vira_vao(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _dois_postes_e_cabo(catalogo_inicial)
    terceiro = cena.elemento(POSTE, codigo="POSTE", x=0.8)
    cena.relacao(cena.elementos[2], terceiro, "CONECTA")

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert ficha["vaos"] == []
    assert ficha["atributos_extras"]["cabos_sem_vao"] == 1


def test_cabo_com_tres_conecta_e_uma_rejeitada_vira_vao(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _dois_postes_e_cabo(catalogo_inicial)
    terceiro = cena.elemento(POSTE, codigo="POSTE", x=0.8)
    cena.relacao(cena.elementos[2], terceiro, "CONECTA", estado=EstadoRevisao.REJEITADA)

    ficha = cena.ficha()

    assert len(ficha["vaos"]) == 1
    assert "cabos_sem_vao" not in ficha["atributos_extras"]


def test_conecta_conflitante_e_presente_e_nao_gera_pendencia(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1 = cena.elemento(POSTE, codigo="POSTE")
    p2 = cena.elemento(POSTE, codigo="POSTE", x=0.6)
    cabo = cena.elemento(CABO, codigo="ABC", atributos={"comprimento_m": 10})
    cena.relacao(cabo, p1, "CONECTA", estado=EstadoRevisao.CONFLITANTE)
    cena.relacao(cabo, p2, "CONECTA", estado=EstadoRevisao.CONFLITANTE)

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    (vao,) = ficha["vaos"]
    assert vao["pendentes"] == []


def test_relacoes_repetidas_para_o_mesmo_par_dao_um_vao_com_extremos_distintos(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _dois_postes_e_cabo(catalogo_inicial)
    cabo, p1, p2 = cena.elementos[2], cena.elementos[0], cena.elementos[1]
    cena.relacao(cabo, p1, "CONECTA")  # outra relação (outro id) para o mesmo destino
    cena.relacao(cabo, p2, "CONECTA")

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    (vao,) = ficha["vaos"]
    assert {vao["de"], vao["para"]} == {str(p1.id), str(p2.id)}


def test_estrutura_com_duas_relacoes_aparece_uma_vez_so(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1 = cena.elemento(POSTE, codigo="POSTE")
    p2 = cena.elemento(POSTE, codigo="POSTE", x=0.6)
    estrutura = cena.elemento(ESTRUTURA_MT, codigo="N3")
    cena.relacao(estrutura, p1, "INSTALADA_EM")
    cena.relacao(estrutura, p2, "INSTALADA_EM")

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert sum(len(poste["estruturas"]) for poste in ficha["postes"]) == 1


def test_equipamento_com_duas_relacoes_tem_id_de_simbolo_unico(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1 = cena.elemento(POSTE, codigo="POSTE")
    p2 = cena.elemento(POSTE, codigo="POSTE", x=0.6)
    equipamento = cena.elemento(EQUIPAMENTO, atributos={"simbolo_classe": "ESTAI"})
    cena.relacao(equipamento, p1, "INSTALADO_EM")
    cena.relacao(equipamento, p2, "INSTALADO_EM")

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []  # ids de símbolo repetidos reprovariam aqui
    ids = [s["id"] for poste in ficha["postes"] for s in poste["simbolos"]]
    assert ids == [str(equipamento.id)]


def test_dois_cabos_entre_o_mesmo_par_dao_dois_vaos_validos(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _dois_postes_e_cabo(catalogo_inicial)
    segundo = cena.elemento(CABO, codigo="XYZ")
    cena.relacao(segundo, cena.elementos[0], "CONECTA")
    cena.relacao(segundo, cena.elementos[1], "CONECTA")

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert sorted(vao["cabo"] for vao in ficha["vaos"]) == ["ABC", "XYZ"]


def test_ficha_vazia_e_valida(catalogo_inicial: CatalogoTecnico) -> None:
    ficha = _Cena(catalogo_inicial).ficha()

    assert validar_ficha(ficha) == []
    assert ficha["postes"] == [] and ficha["vaos"] == []


def test_ordem_das_relacoes_na_entrada_nao_muda_o_vao(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _dois_postes_e_cabo(catalogo_inicial)
    (direto,) = cena.ficha()["vaos"]
    cena.relacoes.reverse()

    (invertido,) = cena.ficha()["vaos"]

    assert (invertido["de"], invertido["para"]) == (direto["de"], direto["para"])


def test_gerador_nao_muda_a_entrada_e_e_deterministico(catalogo_inicial: CatalogoTecnico) -> None:
    cena, _ = _cena_completa(catalogo_inicial)
    variante = cena.variante()
    antes = (variante["semantic"].elementos, variante["semantic"].relacoes)

    primeira = cena.ficha()
    segunda = cena.ficha()

    assert primeira == segunda
    assert json.dumps(primeira, sort_keys=True) == json.dumps(segunda, sort_keys=True)
    json.dumps(primeira, allow_nan=False)  # JSON estrito: nada de NaN/Infinity
    assert (variante["semantic"].elementos, variante["semantic"].relacoes) == antes


# ---------------------------------------------------------------------------------------------
# Pendência
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("chave", CHAVES_PENDENCIA)
def test_cada_chave_de_pendencia_marca_o_poste(
    catalogo_inicial: CatalogoTecnico, chave: str
) -> None:
    cena = _Cena(catalogo_inicial)
    cena.elemento(POSTE, codigo="POSTE", atributos={"identificador_operacional": "P1", chave: True})

    (poste,) = cena.ficha()["postes"]

    assert poste["pendentes"] == ["coordenada", "identificador", "poste"]
    assert poste["identificador"] == "P1"


@pytest.mark.parametrize("valor", [False, None, 0, ""], ids=["false", "none", "zero", "vazio"])
def test_chave_de_pendencia_falsa_nao_marca(catalogo_inicial: CatalogoTecnico, valor: Any) -> None:
    cena = _Cena(catalogo_inicial)
    cena.elemento(POSTE, codigo="POSTE", atributos=dict.fromkeys(CHAVES_PENDENCIA, valor))

    (poste,) = cena.ficha()["postes"]

    assert poste["pendentes"] == []


def test_pendencia_de_um_poste_nao_vaza_para_o_outro_nem_para_o_vao_anotado(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _dois_postes_e_cabo(catalogo_inicial, atributos_cabo={"comprimento_m": 12})
    cena.elementos[0] = replace(cena.elementos[0], estado_revisao=EstadoRevisao.CONFLITANTE)

    ficha = cena.ficha()

    p1, p2 = ficha["postes"]
    assert p1["pendentes"] == ["coordenada", "identificador", "poste"]
    assert p2["pendentes"] == []
    assert ficha["vaos"][0]["pendentes"] == []


def test_pendentes_sem_repeticao_e_em_ordem_quando_varias_fontes_marcam(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    poste = cena.elemento(POSTE, codigo="POSTE", estado=EstadoRevisao.CONFLITANTE)
    outro = cena.elemento(POSTE, codigo="POSTE", x=0.6, estado=EstadoRevisao.CONFLITANTE)
    for codigo in ("N3", "N1"):
        estrutura = cena.elemento(ESTRUTURA_MT, codigo=codigo, estado=EstadoRevisao.CONFLITANTE)
        cena.relacao(estrutura, poste, "INSTALADA_EM")
    for _ in range(2):
        equipamento = cena.elemento(
            EQUIPAMENTO, estado=EstadoRevisao.CONFLITANTE, atributos={"simbolo_classe": "ESTAI"}
        )
        cena.relacao(equipamento, poste, "INSTALADO_EM")
    cabo = cena.elemento(CABO, codigo="ABC", estado=EstadoRevisao.CONFLITANTE)
    cena.relacao(cabo, poste, "CONECTA")
    cena.relacao(cabo, outro, "CONECTA")

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert ficha["postes"][0]["pendentes"] == [
        "coordenada",
        "estruturas",
        "identificador",
        "poste",
        "simbolos",
    ]
    assert ficha["vaos"][0]["pendentes"] == ["cabo", "comprimento_m"]


def test_estrutura_pendente_ligada_a_poste_da_ficha_nao_marca_outro_poste(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1 = cena.elemento(POSTE, codigo="POSTE")
    p2 = cena.elemento(POSTE, codigo="POSTE", x=0.6)
    estrutura = cena.elemento(ESTRUTURA_MT, codigo="N3", estado=EstadoRevisao.CONFLITANTE)
    cena.relacao(estrutura, p2, "INSTALADA_EM")

    ficha = cena.ficha()

    assert ficha["postes"][0]["pendentes"] == []
    assert ficha["postes"][1]["pendentes"] == ["estruturas"]
    assert p1.id != p2.id


# ---------------------------------------------------------------------------------------------
# Comprimento: Decimal e quantize
# ---------------------------------------------------------------------------------------------


def _vao_por_coordenadas(
    catalogo: CatalogoTecnico,
    leste_2: object,
    norte_2: object,
    leste_1: object = 0,
    norte_1: object = 0,
) -> dict[str, Any]:
    cena = _dois_postes_e_cabo(
        catalogo,
        atributos_p1={"coordenada_leste": leste_1, "coordenada_norte": norte_1},
        atributos_p2={"coordenada_leste": leste_2, "coordenada_norte": norte_2},
    )
    ficha = cena.ficha()
    assert validar_ficha(ficha) == []
    (vao,) = ficha["vaos"]
    assert isinstance(vao, dict)
    return vao


@pytest.mark.parametrize(
    ("leste", "esperado"),
    [
        pytest.param(2.675, 2.68, id="2-675-arredonda-para-par-vizinho-em-decimal"),
        pytest.param(1.005, 1.0, id="1-005-meio-para-par"),
        pytest.param(0.125, 0.12, id="0-125-meio-para-par"),
        pytest.param(7.5, 7.5, id="sem-casas-extras"),
    ],
)
def test_comprimento_por_coordenadas_usa_decimal_e_quantize_de_centimetro(
    catalogo_inicial: CatalogoTecnico, leste: float, esperado: float
) -> None:
    # Em float, round(2.675, 2) == 2.67; o quantize em Decimal(str(...)) dá 2.68 (como a promoção).
    vao = _vao_por_coordenadas(catalogo_inicial, leste, 0)

    assert vao["comprimento_m"] == esperado
    assert vao["atributos_extras"]["origem_comprimento"] == "COORDENADAS"


def test_comprimento_por_coordenadas_utm_nao_perde_precisao(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    vao = _vao_por_coordenadas(
        catalogo_inicial, 700003.123, 7800004.456, leste_1=700000.123, norte_1=7800000.456
    )

    assert vao["comprimento_m"] == 5.0


def test_comprimento_por_coordenadas_aceita_texto_numerico(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    vao = _vao_por_coordenadas(catalogo_inicial, "3", "4")

    assert vao["comprimento_m"] == 5.0


def test_comprimento_anotado_numerico_em_texto_vale(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _dois_postes_e_cabo(catalogo_inicial, atributos_cabo={"comprimento_m": " 35.5 "})

    (vao,) = cena.ficha()["vaos"]

    assert vao["comprimento_m"] == 35.5
    assert vao["atributos_extras"]["origem_comprimento"] == "ANOTACAO_DESENHO"


def test_comprimento_anotado_vence_as_coordenadas(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _dois_postes_e_cabo(
        catalogo_inicial,
        atributos_p1={"coordenada_leste": 0, "coordenada_norte": 0},
        atributos_p2={"coordenada_leste": 3, "coordenada_norte": 4},
        atributos_cabo={"comprimento_m": 99},
    )

    (vao,) = cena.ficha()["vaos"]

    assert vao["comprimento_m"] == 99.0
    assert vao["atributos_extras"]["origem_comprimento"] == "ANOTACAO_DESENHO"


@pytest.mark.parametrize(
    "anotado", [-5, "-1", 0.0, "0"], ids=["neg", "neg-texto", "zero", "zero-texto"]
)
def test_comprimento_anotado_nao_positivo_cai_nas_coordenadas(
    catalogo_inicial: CatalogoTecnico, anotado: Any
) -> None:
    cena = _dois_postes_e_cabo(
        catalogo_inicial,
        atributos_p1={"coordenada_leste": 0, "coordenada_norte": 0},
        atributos_p2={"coordenada_leste": 3, "coordenada_norte": 4},
        atributos_cabo={"comprimento_m": anotado},
    )

    (vao,) = cena.ficha()["vaos"]

    assert vao["comprimento_m"] == 5.0
    assert vao["atributos_extras"]["origem_comprimento"] == "COORDENADAS"


def test_coordenadas_coincidentes_nao_dao_comprimento(catalogo_inicial: CatalogoTecnico) -> None:
    vao = _vao_por_coordenadas(catalogo_inicial, 10, 10, leste_1=10, norte_1=10)

    assert vao["comprimento_m"] is None
    assert vao["atributos_extras"]["origem_comprimento"] is None


def test_coordenada_so_com_um_eixo_nao_gera_coordenada_nem_comprimento(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _dois_postes_e_cabo(
        catalogo_inicial,
        atributos_p1={"coordenada_leste": 0},
        atributos_p2={"coordenada_leste": 3, "coordenada_norte": 4},
    )

    ficha = cena.ficha()

    assert ficha["postes"][0]["coordenada"] is None
    assert ficha["vaos"][0]["comprimento_m"] is None


def test_comprimento_por_coordenada_de_poste_pendente_por_chave_marca_comprimento(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _dois_postes_e_cabo(
        catalogo_inicial,
        atributos_p1={"coordenada_leste": 0, "coordenada_norte": 0, "associacao_pendente": True},
        atributos_p2={"coordenada_leste": 3, "coordenada_norte": 4},
    )

    (vao,) = cena.ficha()["vaos"]

    assert vao["comprimento_m"] == 5.0
    assert vao["pendentes"] == ["comprimento_m"]


# ---------------------------------------------------------------------------------------------
# Entradas hostis
# ---------------------------------------------------------------------------------------------

COORDENADAS_HOSTIS = [
    pytest.param("abc", id="texto"),
    pytest.param("", id="texto-vazio"),
    pytest.param(True, id="booleano"),
    pytest.param([1, 2], id="lista"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="infinito"),
    pytest.param("NaN", id="nan-em-texto"),
    pytest.param("Infinity", id="infinito-em-texto"),
]


@pytest.mark.parametrize("valor", COORDENADAS_HOSTIS)
def test_coordenada_hostil_do_poste_nao_derruba_nem_vaza_nao_numerico(
    catalogo_inicial: CatalogoTecnico, valor: object
) -> None:
    cena = _Cena(catalogo_inicial)
    cena.elemento(
        POSTE, codigo="POSTE", atributos={"coordenada_leste": valor, "coordenada_norte": 5}
    )

    ficha = _ficha_sem_cair(cena)

    if ficha is not None:
        assert validar_ficha(ficha) == []
        json.dumps(ficha, allow_nan=False)  # NaN/Infinity não são JSON válido


@pytest.mark.parametrize("valor", COORDENADAS_HOSTIS)
def test_coordenada_hostil_no_calculo_do_comprimento_nao_derruba(
    catalogo_inicial: CatalogoTecnico, valor: object
) -> None:
    cena = _dois_postes_e_cabo(
        catalogo_inicial,
        atributos_p1={"coordenada_leste": 0, "coordenada_norte": 0},
        atributos_p2={"coordenada_leste": valor, "coordenada_norte": 4},
    )

    ficha = _ficha_sem_cair(cena)

    if ficha is not None:
        assert validar_ficha(ficha) == []
        json.dumps(ficha, allow_nan=False)
        comprimento = ficha["vaos"][0]["comprimento_m"]
        assert comprimento is None or comprimento == comprimento  # nunca NaN


def test_coordenada_astronomica_nao_derruba_o_quantize(catalogo_inicial: CatalogoTecnico) -> None:
    # Decimal tem 28 dígitos de contexto: quantize(0.01) de ~1e40 levanta InvalidOperation.
    cena = _dois_postes_e_cabo(
        catalogo_inicial,
        atributos_p1={"coordenada_leste": 0, "coordenada_norte": 0},
        atributos_p2={"coordenada_leste": 1e40, "coordenada_norte": 0},
    )

    ficha = _ficha_sem_cair(cena)

    if ficha is not None:
        assert validar_ficha(ficha) == []
        json.dumps(ficha, allow_nan=False)


@pytest.mark.parametrize(
    "anotado",
    ["abc", "NaN", "Infinity", "-Infinity", "sNaN", [1, 2], {"a": 1}, True],
    ids=["texto", "nan", "infinito", "menos-infinito", "snan", "lista", "dict", "booleano"],
)
def test_comprimento_anotado_hostil_nao_derruba_nem_vaza_nao_numerico(
    catalogo_inicial: CatalogoTecnico, anotado: Any
) -> None:
    cena = _dois_postes_e_cabo(catalogo_inicial, atributos_cabo={"comprimento_m": anotado})

    ficha = _ficha_sem_cair(cena)

    if ficha is not None:
        assert validar_ficha(ficha) == []
        json.dumps(ficha, allow_nan=False)


@pytest.mark.parametrize(
    "identificador",
    [
        pytest.param(7, id="inteiro"),
        pytest.param(["P1"], id="lista"),
        pytest.param({"a": 1}, id="dict"),
    ],
)
def test_identificador_de_tipo_inesperado_vira_texto_valido(
    catalogo_inicial: CatalogoTecnico, identificador: object
) -> None:
    cena = _Cena(catalogo_inicial)
    cena.elemento(POSTE, codigo="POSTE", atributos={"identificador_operacional": identificador})

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert isinstance(ficha["postes"][0]["identificador"], str)


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [("   ", None), ("\t\n", None), (" P1\n", "P1"), ("", None)],
    ids=["espacos", "tab-quebra", "aparado", "vazio"],
)
def test_identificador_em_branco_vira_nulo_e_aparado(
    catalogo_inicial: CatalogoTecnico, bruto: str, esperado: str | None
) -> None:
    cena = _Cena(catalogo_inicial)
    cena.elemento(POSTE, codigo="POSTE", atributos={"identificador_operacional": bruto})

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert ficha["postes"][0]["identificador"] == esperado


def test_codigo_observado_em_branco_nao_vira_texto_em_branco(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    poste = cena.elemento(POSTE, codigo="   ")
    cena.relacao(cena.elemento(ESTRUTURA_MT, codigo="  "), poste, "INSTALADA_EM")
    cabo = cena.elemento(CABO, codigo="\t")
    outro = cena.elemento(POSTE, codigo=" ", x=0.6)
    cena.relacao(cabo, poste, "CONECTA")
    cena.relacao(cabo, outro, "CONECTA")

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []


@pytest.mark.parametrize(
    "classe",
    [5, True, ["ESTAI"], {"a": 1}, "", "   "],
    ids=["inteiro", "booleano", "lista", "dict", "vazio", "espacos"],
)
def test_simbolo_classe_de_tipo_inesperado_e_contado_sem_derrubar(
    catalogo_inicial: CatalogoTecnico, classe: object
) -> None:
    cena = _Cena(catalogo_inicial)
    poste = cena.elemento(POSTE, codigo="POSTE")
    cena.relacao(
        cena.elemento(EQUIPAMENTO, atributos={"simbolo_classe": classe}), poste, "INSTALADO_EM"
    )

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert ficha["postes"][0]["simbolos"] == []
    assert ficha["atributos_extras"]["simbolos_fora_do_inventario"] == 1


def test_simbolo_classe_none_conta_como_equipamento_sem_simbolo(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    poste = cena.elemento(POSTE, codigo="POSTE")
    cena.relacao(
        cena.elemento(EQUIPAMENTO, atributos={"simbolo_classe": None}), poste, "INSTALADO_EM"
    )

    ficha = cena.ficha()

    assert ficha["atributos_extras"]["equipamentos_sem_simbolo"] == 1
    assert ficha["postes"][0]["simbolos"] == []


def test_tipo_ponto_rede_de_tipo_inesperado_nao_derruba(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    for valor in (None, 5, ["ENTREGA"], {"a": 1}):
        cena.elemento(POSTE, codigo="POSTE", atributos={"tipo_ponto_rede": valor})

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert len(ficha["postes"]) == 4


def test_geometria_de_pagina_desconhecida_nao_vira_keyerror(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    cena.elemento(POSTE, codigo="POSTE", atributos={"identificador_operacional": "P1"})
    sem_pagina = cena.elemento(POSTE, codigo="POSTE", x=0.6)
    desconhecida = GeometriaDocumento.caixa(
        uuid4(),
        PontoNormalizado(Decimal("0.1"), Decimal("0.1")),
        PontoNormalizado(Decimal("0.2"), Decimal("0.2")),
    )
    cena.elementos[1] = replace(sem_pagina, geometria=desconhecida)

    ficha = _ficha_sem_cair(cena)

    if ficha is not None:
        assert validar_ficha(ficha) == []
        assert all(poste["pagina"] >= 1 for poste in ficha["postes"])


def test_pagina_do_poste_segue_o_numero_da_pagina_do_documento(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    documento = cena.projeto.documentos[0]
    pagina_1 = documento.paginas[0]
    pagina_2 = replace(pagina_1, id=uuid4(), numero=2)
    cena.projeto = replace(
        cena.projeto,
        documentos=(replace(documento, paginas=(pagina_1, pagina_2)),),
        ordem_leitura_paginas=(pagina_1.id, pagina_2.id),
    )
    primeiro = cena.elemento(POSTE, codigo="POSTE")
    segundo = cena.elemento(POSTE, codigo="POSTE", x=0.6)
    cena.elementos[1] = replace(
        segundo,
        geometria=GeometriaDocumento.caixa(
            pagina_2.id,
            PontoNormalizado(Decimal("0.6"), Decimal("0.4")),
            PontoNormalizado(Decimal("0.65"), Decimal("0.45")),
        ),
    )

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert [(poste["id"], poste["pagina"]) for poste in ficha["postes"]] == [
        (str(primeiro.id), 1),
        (str(segundo.id), 2),
    ]


# ---------------------------------------------------------------------------------------------
# Imports, default e CLI
# ---------------------------------------------------------------------------------------------


def _python_isolado(codigo: str) -> subprocess.CompletedProcess[str]:
    ambiente = dict(os.environ)
    ambiente["PYTHONPATH"] = os.pathsep.join([str(RAIZ), str(RAIZ / "src")])
    return subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=RAIZ,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.parametrize(
    "ordem",
    [
        pytest.param(
            "import scripts.ficha_predita_propostas, scripts.benchmark_ficha_poste",
            id="propostas-primeiro",
        ),
        pytest.param(
            "import scripts.benchmark_ficha_poste, scripts.ficha_predita_propostas",
            id="benchmark-primeiro",
        ),
        pytest.param("import scripts.ficha_predita_propostas", id="so-propostas"),
        pytest.param("import scripts.benchmark_ficha_poste", id="so-benchmark"),
    ],
)
def test_importar_em_qualquer_ordem_nao_forma_ciclo(ordem: str) -> None:
    resultado = _python_isolado(ordem)

    assert resultado.returncode == 0, resultado.stderr


def test_benchmark_nao_importa_o_gerador_de_propostas_no_topo() -> None:
    resultado = _python_isolado(
        "import sys, scripts.benchmark_ficha_poste;"
        "assert 'scripts.ficha_predita_propostas' not in sys.modules"
    )

    assert resultado.returncode == 0, resultado.stderr


def test_default_do_projeto_promovido_segue_inalterado() -> None:
    assert VERSAO_EXTRACAO == "projeto-promovido-v1"
    assert (
        inspect.signature(executar).parameters["versao_extracao"].default == "projeto-promovido-v1"
    )
    assert (
        inspect.signature(_gerador).parameters["versao_extracao"].default == "projeto-promovido-v1"
    )


def test_ficha_predita_do_projeto_promovido_ignora_as_propostas(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena, _ = _cena_completa(catalogo_inicial)
    variante = cena.variante()
    antes = ficha_predita(variante, SHA_QUALQUER, native_only=False)
    cena.ficha()  # roda o gerador novo na mesma variante

    depois = ficha_predita(variante, SHA_QUALQUER, native_only=False)

    assert antes == depois
    assert depois["gerador"]["versao_extracao"] == "projeto-promovido-v1"
    assert depois["gerador"]["native_only"] is False


@pytest.mark.parametrize("native_only", [True, False])
def test_gerador_das_propostas_propaga_native_only_e_versoes(
    catalogo_inicial: CatalogoTecnico, native_only: bool
) -> None:
    from scripts.ficha_predita_propostas import ficha_predita_propostas

    cena, _ = _cena_completa(catalogo_inicial)

    ficha = ficha_predita_propostas(cena.variante(), SHA_QUALQUER, native_only=native_only)

    assert ficha["pdf_sha256"] == SHA_QUALQUER
    assert ficha["escopo_anotacao"] == {"tipo": "completo"}
    assert ficha["gerador"] == {
        "versao_extracao": "propostas-v1",
        "analisador_versao": "a1",
        "analisador_assinatura": "assinatura",
        "interpretador_versao": "i1",
        "registro_assinatura": "registro",
        "native_only": native_only,
    }


@pytest.mark.parametrize(
    "versao",
    ["", "PROPOSTAS-V1", " propostas-v1", "propostas-v1 ", "propostas", "projeto-promovido-v2"],
    ids=["vazia", "maiuscula", "espaco-antes", "espaco-depois", "sem-sufixo", "v2"],
)
def test_executar_recusa_versao_fora_da_lista_antes_de_tocar_em_arquivos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, versao: str
) -> None:
    def falha(*_: Any, **__: Any) -> dict[str, Any]:
        raise AssertionError("o analisador não deveria rodar")

    monkeypatch.setattr(benchmark_ficha_poste, "run_variant", falha)

    with pytest.raises(ValueError, match="versao_extracao desconhecida"):
        executar(
            tmp_path / "inexistente.pdf",
            tmp_path / "inexistente.json",
            tmp_path / "saida",
            native_only=True,
            runtime_directory=tmp_path / "runtime",
            versao_extracao=versao,
        )

    assert not (tmp_path / "saida").exists()


def test_cli_recusa_versao_desconhecida_sem_rodar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    chamadas: list[object] = []
    monkeypatch.setattr(benchmark_ficha_poste, "executar", lambda *a, **k: chamadas.append(k))

    with pytest.raises(SystemExit) as saida:
        main(
            [
                str(tmp_path / "x.pdf"),
                "--referencia",
                str(tmp_path / "r.json"),
                "--saida",
                str(tmp_path / "s"),
                "--versao-extracao",
                "propostas-v9",
            ]
        )

    assert saida.value.code == 2
    assert chamadas == []
    assert "propostas-v9" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("extras", "esperada"),
    [
        pytest.param([], VERSAO_EXTRACAO, id="sem-flag"),
        pytest.param(
            ["--versao-extracao", "projeto-promovido-v1"],
            VERSAO_EXTRACAO,
            id="flag-explicito-padrao",
        ),
        pytest.param(["--versao-extracao", "propostas-v1"], "propostas-v1", id="propostas"),
    ],
)
def test_cli_repassa_a_versao_certa_a_executar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extras: list[str], esperada: str
) -> None:
    recebidos: list[dict[str, Any]] = []

    def espiao(*_: Any, **kwargs: Any) -> dict[str, Any]:
        recebidos.append(kwargs)
        return {}

    monkeypatch.setattr(benchmark_ficha_poste, "executar", espiao)

    codigo = main(
        [
            str(tmp_path / "x.pdf"),
            "--referencia",
            str(tmp_path / "r.json"),
            "--saida",
            str(tmp_path / "s"),
            *extras,
        ]
    )

    assert codigo == 0
    (kwargs,) = recebidos
    assert kwargs.get("versao_extracao", VERSAO_EXTRACAO) == esperada


def test_executar_com_propostas_grava_ficha_e_avaliacao_consistentes(
    catalogo_inicial: CatalogoTecnico, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cena, _ = _cena_completa(catalogo_inicial)
    monkeypatch.setattr(benchmark_ficha_poste, "run_variant", lambda *_, **__: cena.variante())
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-sintetico")
    referencia = tmp_path / "ref.json"
    referencia.write_text(
        json.dumps(_referencia_sintetica(sha256(pdf.read_bytes()).hexdigest())), encoding="utf-8"
    )

    resultado = executar(
        pdf,
        referencia,
        tmp_path / "saida",
        native_only=True,
        runtime_directory=tmp_path / "runtime",
        versao_extracao="propostas-v1",
    )

    ficha = json.loads((tmp_path / "saida" / "ficha-predita.json").read_text(encoding="utf-8"))
    assert validar_ficha(ficha) == []
    assert ficha["pdf_sha256"] == sha256(pdf.read_bytes()).hexdigest()
    assert ficha["gerador"]["versao_extracao"] == "propostas-v1"
    assert (tmp_path / "saida" / "avaliacao.json").is_file()
    assert resultado is not None
