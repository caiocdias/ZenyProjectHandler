"""Ataque à habilitação de v017 e v019 (`disc_mark`): conjunto habilitado, faixa, estado, versão.

Só dados versionados: pacotes de símbolos, inventário e versão do método. Nenhum PDF.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

import pytest
from scripts.audit_symbol_packages import audit

from zeny_project_handler.adapters.analysis import model_symbols
from zeny_project_handler.adapters.analysis.declarative_symbols import carregar_pacotes
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import carregar_tabela_glifos

_RAIZ: Final = Path(__file__).resolve().parents[2]
_INVENTARIO: Final = _RAIZ / "docs" / "data" / "inventario-simbologia-v1.json"
_FUSIVEL: Final = "cemig-eo-r3-s20-v017"
_CAIXA_DUPLA: Final = "cemig-eo-r3-s20-v019"
_HABILITADAS: Final = {_FUSIVEL, _CAIXA_DUPLA}
_DA_FAMILIA: Final = "family-f02-20"


def _variantes() -> dict[str, dict[str, Any]]:
    return {
        variante["id"]: variante
        for pacote in carregar_pacotes()
        for variante in pacote["variants"]
        if pacote["family_id"] == _DA_FAMILIA
    }


def _inventario() -> dict[str, dict[str, Any]]:
    dados = json.loads(_INVENTARIO.read_text(encoding="utf-8"))
    return {variante["id"]: variante for variante in dados["variants"]}


def test_so_v017_e_v019_estao_habilitadas_na_familia_20() -> None:
    habilitadas = {
        identificador
        for identificador, variante in _variantes().items()
        if variante["recognition"]["status"] == "enabled"
    }

    assert habilitadas == _HABILITADAS


def test_nenhuma_outra_variante_de_nenhum_pacote_usa_disc_mark() -> None:
    usam = {
        variante["id"]
        for pacote in carregar_pacotes()
        for variante in pacote["variants"]
        if variante["recognition"].get("grammar", {}).get("kind") == "disc_mark"
    }

    assert usam == _HABILITADAS


@pytest.mark.parametrize(
    "identificador",
    sorted(set(_variantes()) - _HABILITADAS),
)
def test_as_demais_da_familia_20_seguem_pendentes_com_o_motivo(identificador: str) -> None:
    reconhecimento = _variantes()[identificador]["recognition"]

    assert reconhecimento["status"] == "pending"
    assert str(reconhecimento["reason"]).strip() != ""
    assert "grammar" not in reconhecimento


@pytest.mark.parametrize("identificador", sorted(_HABILITADAS))
def test_habilitada_nao_carrega_motivo_de_pendencia(identificador: str) -> None:
    reconhecimento = _variantes()[identificador]["recognition"]

    assert "reason" not in reconhecimento
    assert reconhecimento["negative_examples"]


@pytest.mark.parametrize(
    ("identificador", "conteudo"), [(_FUSIVEL, "fuse_curve"), (_CAIXA_DUPLA, "double_box")]
)
def test_gramatica_das_habilitadas_e_a_do_laboratorio(identificador: str, conteudo: str) -> None:
    variante = _variantes()[identificador]

    assert variante["class_code"] == "EQUIPAMENTO_INTERRUPCAO"
    assert variante["recognition"]["grammar"] == {
        "kind": "disc_mark",
        "fill": "red",
        "content": conteudo,
        "min_span": 4.5,
        "max_span": 15,
    }


def test_estado_de_operacao_fechado_so_nas_habilitadas_e_as_abertas_nao_estao_habilitadas() -> None:
    inventario = _inventario()
    habilitadas = {
        identificador
        for identificador, variante in _variantes().items()
        if variante["recognition"]["status"] == "enabled"
    }

    assert {inventario[i]["operating_state"] for i in habilitadas} == {"Fechado"}
    # A cor vermelha só afirma "Fechado"; as irmãs "Aberto" (verde) não podem sair da pendência.
    abertas = {
        i for i, v in inventario.items() if i in _variantes() and v["operating_state"] == "Aberto"
    }
    assert {"cemig-eo-r3-s20-v018", "cemig-eo-r3-s20-v020"} <= abertas
    assert abertas.isdisjoint(habilitadas)


def test_versao_do_metodo_e_1_6_0_e_entra_na_identidade_do_perfil() -> None:
    pacotes = carregar_pacotes()
    tabela = carregar_tabela_glifos()
    perfil = model_symbols.perfil_pacotes_modelo(pacotes, tabela)

    assert model_symbols._VERSAO == "1.6.0"
    assert perfil.metodo_id == "declarative-drawing-model"
    assert perfil.versao == "1.6.0"
    assert "EQUIPAMENTO_INTERRUPCAO" in perfil.classes_suportadas
    assert replace(perfil, versao="1.5.0").assinatura() != perfil.assinatura()


def test_identidade_do_perfil_muda_ao_desligar_uma_das_variantes() -> None:
    pacotes = copy.deepcopy(carregar_pacotes())
    tabela = carregar_tabela_glifos()
    ligado = model_symbols.perfil_pacotes_modelo(tuple(pacotes), tabela)
    for pacote in pacotes:
        for variante in pacote["variants"]:
            if variante["id"] == _FUSIVEL:
                variante["recognition"] = {
                    "status": "pending",
                    "reason": "desligada no teste",
                    "negative_examples": variante["recognition"]["negative_examples"],
                }

    desligado = model_symbols.perfil_pacotes_modelo(tuple(pacotes), tabela)

    assert desligado.assinatura() != ligado.assinatura()


def test_auditoria_dos_pacotes_sem_erros() -> None:
    relatorio = audit()

    assert relatorio["errors"] == []
    assert relatorio["enabled"] == 54
    assert relatorio["pending"] == 369
