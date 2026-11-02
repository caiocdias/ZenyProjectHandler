"""Formato versionado da ficha do poste e sua validação (schema + regras semânticas)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from scripts.curation_reference import validar_esquema
from scripts.ficha_poste import CAMINHO_ESQUEMA, carregar_ficha, validar_ficha

SHA = "a" * 64


def _ficha_completa() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "tipo": "referencia",
        "pdf_sha256": SHA,
        "escopo_anotacao": {"tipo": "completo"},
        "postes": [
            {
                "id": "P1",
                "pagina": 1,
                "bbox": [0.10, 0.10, 0.12, 0.12],
                "identificador": "123",
                "estruturas": ["N1", "M1"],
                "poste": "DT 11/300",
                "coordenada": {"leste": 700000.5, "norte": 7800000.25, "zona": "23K"},
                "simbolos": [
                    {
                        "id": "S1",
                        "classe": "ESTAI",
                        "bbox": [0.10, 0.12, 0.14, 0.16],
                        "atributos_extras": {"nota": "x"},
                    }
                ],
                "pendentes": [],
                "atributos_extras": {"nota": "x"},
            },
            {
                "id": "P2",
                "pagina": 1,
                "bbox": [0.50, 0.50, 0.50, 0.50],
                "identificador": None,
                "estruturas": [],
                "poste": None,
                "coordenada": None,
                "simbolos": [],
                "pendentes": ["simbolos"],
            },
        ],
        "vaos": [
            {
                "de": "P1",
                "para": "P2",
                "comprimento_m": 35.5,
                "cabo": "3x1/0",
                "pendentes": [],
                "atributos_extras": {"nota": "x"},
            }
        ],
        "atributos_extras": {"nota": "x"},
    }


def _predicao() -> dict[str, Any]:
    ficha = _ficha_completa()
    ficha["tipo"] = "predicao"
    ficha["gerador"] = {"versao_extracao": "v1"}
    return ficha


def _regional() -> dict[str, Any]:
    ficha = _ficha_completa()
    ficha["escopo_anotacao"] = {
        "tipo": "regional",
        "regioes": [{"pagina": 1, "bbox": [0.0, 0.0, 0.6, 0.6]}],
    }
    return ficha


def _com_erros(ficha: dict[str, Any]) -> list[str]:
    erros = validar_ficha(ficha)
    assert erros, "esperava ao menos um erro"
    return erros


def test_ficha_completa_e_valida() -> None:
    assert validar_ficha(_ficha_completa()) == []


def test_schema_carrega_e_usa_so_palavras_suportadas() -> None:
    esquema = json.loads(CAMINHO_ESQUEMA.read_text(encoding="utf-8"))
    assert validar_esquema(_ficha_completa(), esquema) == []
    assert esquema["$id"] == "urn:zeny:benchmark:ficha-poste:1"


def _extra_raiz(f: dict[str, Any]) -> None:
    f["extra"] = 1


def _extra_poste(f: dict[str, Any]) -> None:
    f["postes"][0]["extra"] = 1


def _extra_vao(f: dict[str, Any]) -> None:
    f["vaos"][0]["extra"] = 1


def _extra_simbolo(f: dict[str, Any]) -> None:
    f["postes"][0]["simbolos"][0]["extra"] = 1


def _extra_coordenada(f: dict[str, Any]) -> None:
    f["postes"][0]["coordenada"]["extra"] = 1


def _extra_escopo(f: dict[str, Any]) -> None:
    f["escopo_anotacao"]["extra"] = 1


@pytest.mark.parametrize(
    "alterar",
    [_extra_raiz, _extra_poste, _extra_vao, _extra_simbolo, _extra_coordenada, _extra_escopo],
)
def test_campo_extra_e_recusado(alterar: Any) -> None:
    ficha = _ficha_completa()
    alterar(ficha)
    assert any("não permitido" in erro for erro in _com_erros(ficha))


def test_atributos_extras_e_gerador_aceitam_qualquer_chave() -> None:
    ficha = _predicao()
    ficha["gerador"] = {"qualquer": [1, {"a": None}], "outra": "x"}
    ficha["atributos_extras"] = {"k": {"n": [1, 2]}, "z": None}
    ficha["postes"][0]["atributos_extras"] = {"a": 1, "b": [True]}
    ficha["vaos"][0]["atributos_extras"] = {"a": {"b": 2}}
    ficha["postes"][0]["simbolos"][0]["atributos_extras"] = {"qualquer": "coisa"}
    assert validar_ficha(ficha) == []


def test_schema_version_booleano_e_recusado() -> None:
    ficha = _ficha_completa()
    ficha["schema_version"] = True
    assert _com_erros(ficha)


@pytest.mark.parametrize(
    "caminho",
    [
        ("pdf_sha256",),
        ("postes",),
        ("postes", 0, "estruturas"),
        ("postes", 0, "pendentes"),
        ("vaos", 0, "cabo"),
        ("postes", 0, "simbolos", 0, "id"),
    ],
)
def test_campo_obrigatorio_ausente_e_recusado(caminho: tuple[Any, ...]) -> None:
    ficha = _ficha_completa()
    alvo: Any = ficha
    for passo in caminho[:-1]:
        alvo = alvo[passo]
    del alvo[caminho[-1]]
    assert any("obrigatório ausente" in erro for erro in _com_erros(ficha))


def test_pendente_invalido_ou_repetido_e_recusado() -> None:
    invalido = _ficha_completa()
    invalido["postes"][0]["pendentes"] = ["altura"]
    assert _com_erros(invalido)
    repetido = _ficha_completa()
    repetido["vaos"][0]["pendentes"] = ["cabo", "cabo"]
    assert any("repetid" in erro for erro in _com_erros(repetido))
    repetido_poste = _ficha_completa()
    repetido_poste["postes"][0]["pendentes"] = ["simbolos", "simbolos"]
    assert any("repetid" in erro for erro in _com_erros(repetido_poste))


def test_vao_com_poste_inexistente_ou_laco_e_recusado() -> None:
    inexistente = _ficha_completa()
    inexistente["vaos"][0]["para"] = "P9"
    assert any("P9" in erro for erro in _com_erros(inexistente))
    de_inexistente = _ficha_completa()
    de_inexistente["vaos"][0]["de"] = "P8"
    assert any("P8" in erro for erro in _com_erros(de_inexistente))
    laco = _ficha_completa()
    laco["vaos"][0]["para"] = "P1"
    assert any("diferentes" in erro for erro in _com_erros(laco))


def test_id_de_poste_ou_de_simbolo_repetido_e_recusado() -> None:
    poste = _ficha_completa()
    poste["postes"][1]["id"] = "P1"
    assert any("poste" in erro and "repetido" in erro for erro in _com_erros(poste))
    simbolo = _ficha_completa()
    outro = copy.deepcopy(simbolo["postes"][0]["simbolos"][0])
    simbolo["postes"][1]["simbolos"] = [outro]
    assert any("símbolo" in erro and "repetido" in erro for erro in _com_erros(simbolo))


@pytest.mark.parametrize(
    "bbox",
    [[0.5, 0.1, 0.4, 0.2], [0.1, 0.5, 0.2, 0.4], [0.1, 0.1, 1.2, 0.2], [-0.1, 0.1, 0.2, 0.2]],
)
def test_bbox_invertida_ou_fora_de_0_1_e_recusada(bbox: list[float]) -> None:
    ficha = _ficha_completa()
    ficha["postes"][1]["bbox"] = bbox
    assert _com_erros(ficha)
    ficha = _ficha_completa()
    ficha["postes"][0]["simbolos"][0]["bbox"] = bbox
    assert _com_erros(ficha)


@pytest.mark.parametrize("bbox", [[0.1, 0.1, 0.1, 0.2], [0.1, 0.1, 0.2, 0.1], [0.3, 0.3, 0.3, 0.3]])
def test_bbox_de_simbolo_sem_area_e_recusada(bbox: list[float]) -> None:
    ficha = _ficha_completa()
    ficha["postes"][0]["simbolos"][0]["bbox"] = bbox
    assert any("área" in erro for erro in _com_erros(ficha))


def test_bbox_de_poste_em_ponto_e_valida() -> None:
    ficha = _ficha_completa()
    assert ficha["postes"][1]["bbox"][0] == ficha["postes"][1]["bbox"][2]
    assert validar_ficha(ficha) == []


def test_classe_fora_do_inventario_e_recusada() -> None:
    ficha = _ficha_completa()
    ficha["postes"][0]["simbolos"][0]["classe"] = "PARA-RAIOS"
    assert any("inventário" in erro for erro in _com_erros(ficha))


@pytest.mark.parametrize(
    "classe",
    [
        "POSTE",
        "POSTE_AT",
        "ESTRUTURA_POSTE_MT",
        "ESTRUTURA_POSTE_AT",
        "RASCUNHO_EXISTENTE_POSTE_DT",
    ],
)
def test_classe_do_proprio_poste_e_recusada_como_simbolo(classe: str) -> None:
    ficha = _ficha_completa()
    ficha["postes"][0]["simbolos"][0]["classe"] = classe
    assert any("próprio poste" in erro for erro in _com_erros(ficha))


def test_estai_com_poste_no_nome_e_simbolo_valido() -> None:
    ficha = _ficha_completa()
    ficha["postes"][0]["simbolos"][0]["classe"] = "RASCUNHO_EXISTENTE_ESTAI_POSTE_A_POSTE"
    assert validar_ficha(ficha) == []


def test_escopo_regional_exige_regioes_e_completo_as_proibe() -> None:
    assert validar_ficha(_regional()) == []
    sem_regioes = _regional()
    del sem_regioes["escopo_anotacao"]["regioes"]
    assert any("regioes" in erro for erro in _com_erros(sem_regioes))
    vazias = _regional()
    vazias["escopo_anotacao"]["regioes"] = []
    assert any("regioes" in erro for erro in _com_erros(vazias))
    completo = _ficha_completa()
    completo["escopo_anotacao"]["regioes"] = [{"pagina": 1, "bbox": [0.0, 0.0, 1.0, 1.0]}]
    assert any("regioes" in erro for erro in _com_erros(completo))


def test_regiao_com_bbox_invertida_e_recusada() -> None:
    ficha = _regional()
    ficha["escopo_anotacao"]["regioes"][0]["bbox"] = [0.6, 0.0, 0.0, 0.6]
    assert _com_erros(ficha)


def test_predicao_exige_escopo_completo_e_gerador() -> None:
    assert validar_ficha(_predicao()) == []
    sem_gerador = _predicao()
    del sem_gerador["gerador"]
    assert any("gerador" in erro for erro in _com_erros(sem_gerador))
    regional = _predicao()
    regional["escopo_anotacao"] = _regional()["escopo_anotacao"]
    assert any("completo" in erro for erro in _com_erros(regional))


def test_poste_de_referencia_regional_fora_das_regioes_e_recusado() -> None:
    ficha = _regional()
    ficha["postes"][1]["bbox"] = [0.9, 0.9, 0.9, 0.9]
    assert any("P2" in erro and "regiões" in erro for erro in _com_erros(ficha))
    outra_pagina = _regional()
    outra_pagina["postes"][1]["pagina"] = 2
    assert any("P2" in erro for erro in _com_erros(outra_pagina))


def test_dois_vaos_no_mesmo_par_sao_validos() -> None:
    ficha = _ficha_completa()
    segundo = copy.deepcopy(ficha["vaos"][0])
    segundo["cabo"] = "1x2/0"
    ficha["vaos"].append(segundo)
    assert validar_ficha(ficha) == []


def test_carregar_ficha_devolve_dados(tmp_path: Path) -> None:
    arquivo = tmp_path / "ficha.json"
    arquivo.write_text(json.dumps(_ficha_completa(), ensure_ascii=False), encoding="utf-8")
    assert carregar_ficha(arquivo) == _ficha_completa()


def test_carregar_ficha_levanta_com_erros(tmp_path: Path) -> None:
    ficha = _ficha_completa()
    ficha["extra"] = 1
    ficha["postes"][0]["extra"] = 1
    arquivo = tmp_path / "ficha.json"
    arquivo.write_text(json.dumps(ficha), encoding="utf-8")
    with pytest.raises(ValueError, match="não permitido") as info:
        carregar_ficha(arquivo)
    assert "; " in str(info.value)


def test_carregar_ficha_recusa_raiz_que_nao_e_objeto(tmp_path: Path) -> None:
    arquivo = tmp_path / "ficha.json"
    arquivo.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        carregar_ficha(arquivo)


def test_pdf_sha256_com_quebra_de_linha_final_e_recusado() -> None:
    ficha = _ficha_completa()
    ficha["pdf_sha256"] = SHA + "\n"
    assert any("pdf_sha256" in erro for erro in _com_erros(ficha))


def _poste_id(f: dict[str, Any], valor: str) -> None:
    f["postes"][0]["id"] = valor


def _simbolo_id(f: dict[str, Any], valor: str) -> None:
    f["postes"][0]["simbolos"][0]["id"] = valor


def _identificador(f: dict[str, Any], valor: str) -> None:
    f["postes"][0]["identificador"] = valor


def _poste_texto(f: dict[str, Any], valor: str) -> None:
    f["postes"][0]["poste"] = valor


def _estrutura(f: dict[str, Any], valor: str) -> None:
    f["postes"][0]["estruturas"] = ["N1", valor]


def _classe(f: dict[str, Any], valor: str) -> None:
    f["postes"][0]["simbolos"][0]["classe"] = valor


def _cabo(f: dict[str, Any], valor: str) -> None:
    f["vaos"][0]["cabo"] = valor


def _de(f: dict[str, Any], valor: str) -> None:
    f["vaos"][0]["de"] = valor


def _para(f: dict[str, Any], valor: str) -> None:
    f["vaos"][0]["para"] = valor


@pytest.mark.parametrize(
    "alterar",
    [_poste_id, _simbolo_id, _identificador, _poste_texto, _estrutura, _classe, _cabo, _de, _para],
)
@pytest.mark.parametrize("valor", [" ", " \t\n"])
def test_texto_em_branco_e_recusado(alterar: Any, valor: str) -> None:
    ficha = _ficha_completa()
    alterar(ficha, valor)
    assert any("em branco" in erro for erro in _com_erros(ficha))
