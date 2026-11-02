"""Ataques à validação da ficha do poste: entradas que o brief proíbe e que não podem passar."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from scripts.ficha_poste import carregar_ficha, validar_ficha

Alterar = Callable[[dict[str, Any]], None]

SHA = "b" * 64
NAN = float("nan")
INF = float("inf")


def _base() -> dict[str, Any]:
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
                "estruturas": ["N1"],
                "poste": "DT 11/300",
                "coordenada": {"leste": 700000.5, "norte": 7800000.25, "zona": "23K"},
                "simbolos": [{"id": "S1", "classe": "ESTAI", "bbox": [0.10, 0.12, 0.14, 0.16]}],
                "pendentes": [],
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
            {"de": "P1", "para": "P2", "comprimento_m": 35.5, "cabo": "3x1/0", "pendentes": []}
        ],
    }


def _def(caminho: tuple[Any, ...], valor: Any) -> Alterar:
    def alterar(ficha: dict[str, Any]) -> None:
        alvo: Any = ficha
        for passo in caminho[:-1]:
            alvo = alvo[passo]
        alvo[caminho[-1]] = valor

    return alterar


def _recusada(alterar: Alterar) -> list[str]:
    ficha = _base()
    alterar(ficha)
    erros = validar_ficha(ficha)
    assert erros, "a ficha deveria ser recusada"
    return erros


def _aceita(alterar: Alterar) -> None:
    ficha = _base()
    alterar(ficha)
    assert validar_ficha(ficha) == []


def test_base_do_ataque_e_valida() -> None:
    assert validar_ficha(_base()) == []


@pytest.mark.parametrize(
    "alterar",
    [
        _def(("postes", 0, "pagina"), True),
        _def(("postes", 0, "pagina"), False),
        _def(("postes", 0, "pagina"), 1.5),
        _def(("postes", 0, "pagina"), 1.0),
        _def(("postes", 0, "pagina"), 0),
        _def(("postes", 0, "pagina"), -1),
        _def(("postes", 0, "pagina"), "1"),
        _def(("postes", 0, "bbox"), [True, 0, 1, 1]),
        _def(("postes", 0, "bbox"), [0, 0, 1, False]),
        _def(("postes", 0, "simbolos", 0, "bbox"), [True, 0, 1, 1]),
        _def(("vaos", 0, "comprimento_m"), False),
        _def(("vaos", 0, "comprimento_m"), True),
        _def(("postes", 0, "coordenada", "leste"), True),
        _def(("postes", 0, "coordenada", "norte"), False),
    ],
    ids=lambda a: "",
)
def test_booleano_ou_tipo_errado_onde_se_espera_numero_e_recusado(alterar: Alterar) -> None:
    _recusada(alterar)


def test_pagina_de_regiao_booleana_e_recusada() -> None:
    def alterar(ficha: dict[str, Any]) -> None:
        ficha["escopo_anotacao"] = {
            "tipo": "regional",
            "regioes": [{"pagina": True, "bbox": [0.0, 0.0, 1.0, 1.0]}],
        }

    _recusada(alterar)


def test_bbox_de_regiao_booleana_e_recusada() -> None:
    def alterar(ficha: dict[str, Any]) -> None:
        ficha["escopo_anotacao"] = {
            "tipo": "regional",
            "regioes": [{"pagina": 1, "bbox": [False, 0.0, 1.0, 1.0]}],
        }

    _recusada(alterar)


@pytest.mark.parametrize("valor", [NAN, INF, -INF], ids=["nan", "inf", "-inf"])
@pytest.mark.parametrize("posicao", [0, 1, 2, 3])
def test_nan_e_infinito_em_bbox_de_poste_sao_recusados(valor: float, posicao: int) -> None:
    bbox = [0.1, 0.1, 0.2, 0.2]
    bbox[posicao] = valor
    _recusada(_def(("postes", 0, "bbox"), bbox))


@pytest.mark.parametrize("valor", [NAN, INF, -INF], ids=["nan", "inf", "-inf"])
@pytest.mark.parametrize("posicao", [0, 1, 2, 3])
def test_nan_e_infinito_em_bbox_de_simbolo_sao_recusados(valor: float, posicao: int) -> None:
    bbox = [0.1, 0.1, 0.2, 0.2]
    bbox[posicao] = valor
    _recusada(_def(("postes", 0, "simbolos", 0, "bbox"), bbox))


@pytest.mark.parametrize("valor", [NAN, INF, -INF], ids=["nan", "inf", "-inf"])
def test_nan_e_infinito_em_bbox_de_regiao_sao_recusados(valor: float) -> None:
    def alterar(ficha: dict[str, Any]) -> None:
        ficha["escopo_anotacao"] = {
            "tipo": "regional",
            "regioes": [{"pagina": 1, "bbox": [0.0, 0.0, valor, 1.0]}],
        }

    _recusada(alterar)


@pytest.mark.parametrize("valor", [NAN, INF, -INF], ids=["nan", "inf", "-inf"])
@pytest.mark.parametrize("campo", ["leste", "norte"])
def test_nan_e_infinito_em_coordenada_sao_recusados(valor: float, campo: str) -> None:
    _recusada(_def(("postes", 0, "coordenada", campo), valor))


@pytest.mark.parametrize("valor", [NAN, INF], ids=["nan", "inf"])
def test_nan_e_infinito_em_comprimento_sao_recusados(valor: float) -> None:
    _recusada(_def(("vaos", 0, "comprimento_m"), valor))


def test_nan_lido_de_arquivo_json_e_recusado(tmp_path: Path) -> None:
    ficha = _base()
    ficha["postes"][0]["bbox"] = [NAN, 0.1, 0.2, 0.2]
    arquivo = tmp_path / "ficha.json"
    arquivo.write_text(json.dumps(ficha), encoding="utf-8")  # grava o literal NaN
    with pytest.raises(ValueError):
        carregar_ficha(arquivo)


def test_pendente_fora_do_enum_no_vao_e_recusado() -> None:
    _recusada(_def(("vaos", 0, "pendentes"), ["altura"]))


def test_pendente_de_vao_no_poste_e_de_poste_no_vao_sao_recusados() -> None:
    _recusada(_def(("postes", 0, "pendentes"), ["cabo"]))
    _recusada(_def(("vaos", 0, "pendentes"), ["identificador"]))


def test_pendentes_repetido_com_outros_valores_e_recusado() -> None:
    erros = _recusada(_def(("postes", 0, "pendentes"), ["poste", "coordenada", "poste"]))
    assert any("repetid" in erro for erro in erros)


def test_pendentes_com_valores_distintos_e_aceito() -> None:
    _aceita(
        _def(
            ("postes", 0, "pendentes"),
            ["identificador", "estruturas", "poste", "coordenada", "simbolos"],
        )
    )
    _aceita(_def(("vaos", 0, "pendentes"), ["comprimento_m", "cabo"]))


def test_pendentes_que_nao_e_lista_e_recusado() -> None:
    _recusada(_def(("postes", 0, "pendentes"), "simbolos"))
    _recusada(_def(("postes", 0, "pendentes"), None))


@pytest.mark.parametrize(
    "bbox",
    [[0.3, 0.3, 0.3, 0.3], [0.2, 0.2, 0.2, 0.4], [0.2, 0.2, 0.4, 0.2]],
    ids=["ponto", "linha vertical", "linha horizontal"],
)
def test_simbolo_com_bbox_degenerada_e_recusado(bbox: list[float]) -> None:
    erros = _recusada(_def(("postes", 0, "simbolos", 0, "bbox"), bbox))
    assert any("símbolo" in erro or "área" in erro for erro in erros)


@pytest.mark.parametrize(
    "bbox",
    [[0.4, 0.1, 0.2, 0.2], [0.1, 0.4, 0.2, 0.2], [0.4, 0.4, 0.2, 0.2]],
    ids=["x invertido", "y invertido", "ambos"],
)
def test_bbox_invertida_de_simbolo_e_de_poste_e_recusada(bbox: list[float]) -> None:
    _recusada(_def(("postes", 0, "simbolos", 0, "bbox"), bbox))
    _recusada(_def(("postes", 0, "bbox"), bbox))


@pytest.mark.parametrize(
    "bbox", [[0.1, 0.1, 0.2], [0.1, 0.1, 0.2, 0.2, 0.3], [], None, "abcd", ["a", 0, 1, 1]]
)
def test_bbox_com_forma_errada_e_recusada(bbox: Any) -> None:
    _recusada(_def(("postes", 0, "bbox"), bbox))
    _recusada(_def(("postes", 0, "simbolos", 0, "bbox"), bbox))


def test_bbox_nos_limites_0_e_1_e_aceita() -> None:
    _aceita(_def(("postes", 1, "bbox"), [0.0, 0.0, 1.0, 1.0]))
    _aceita(_def(("postes", 1, "bbox"), [1.0, 1.0, 1.0, 1.0]))
    _aceita(_def(("postes", 0, "simbolos", 0, "bbox"), [0, 0, 1, 1]))


@pytest.mark.parametrize(
    "classe",
    ["estai", "Estai", "ESTAI ", " ESTAI", "ES TAI", "ESTAI\n", "", "ESTAI_INEXISTENTE"],
)
def test_classe_de_simbolo_mal_formada_ou_fora_do_inventario_e_recusada(classe: str) -> None:
    _recusada(_def(("postes", 0, "simbolos", 0, "classe"), classe))


@pytest.mark.parametrize(
    "classe",
    [
        "poste",
        "POSTE ",
        "RASCUNHO_EXISTENTE_POSTE_MT",
        "RASCUNHO_PROJETADO_POSTE_DT",
        "RASCUNHO_REMOVER_POSTE_DT",
    ],
)
def test_variacoes_da_classe_do_poste_nunca_passam_como_simbolo(classe: str) -> None:
    # Qualquer coisa que o inventário não tenha é recusada; o que tenha e case com a regra do poste
    # também. Aqui só afirmamos que nenhuma variação passa em silêncio: se a classe existe no
    # inventário e casa RASCUNHO_X_POSTE_Y, deve ser recusada; se não existe, também.
    _recusada(_def(("postes", 0, "simbolos", 0, "classe"), classe))


@pytest.mark.parametrize(
    "alterar",
    [
        _def(("postes", 0, "id"), ""),
        _def(("postes", 0, "simbolos", 0, "id"), ""),
        _def(("vaos", 0, "de"), ""),
        _def(("vaos", 0, "para"), ""),
        _def(("postes", 0, "identificador"), ""),
        _def(("postes", 0, "poste"), ""),
        _def(("postes", 0, "estruturas"), [""]),
        _def(("vaos", 0, "cabo"), ""),
        _def(("postes", 0, "coordenada", "zona"), ""),
        _def(("postes", 0, "simbolos", 0, "classe"), ""),
    ],
    ids=lambda a: "",
)
def test_texto_vazio_e_recusado(alterar: Alterar) -> None:
    _recusada(alterar)


def test_ids_vazios_repetidos_nao_passam() -> None:
    def alterar(ficha: dict[str, Any]) -> None:
        ficha["postes"][0]["id"] = ""
        ficha["postes"][1]["id"] = ""
        ficha["vaos"][0]["de"] = ""
        ficha["vaos"][0]["para"] = ""

    _recusada(alterar)


def test_texto_nulo_onde_nao_e_permitido_e_recusado() -> None:
    _recusada(_def(("postes", 0, "id"), None))
    _recusada(_def(("postes", 0, "simbolos", 0, "classe"), None))
    _recusada(_def(("vaos", 0, "de"), None))
    _recusada(_def(("postes", 0, "estruturas"), [None]))
    _recusada(_def(("postes", 0, "estruturas"), None))
    _recusada(_def(("postes", 0, "simbolos"), None))


def test_vao_de_um_poste_para_ele_mesmo_e_recusado() -> None:
    erros = _recusada(_def(("vaos", 0, "para"), "P1"))
    assert any("diferentes" in erro for erro in erros)
    erros = _recusada(
        lambda f: f["vaos"][0].update({"de": "P2", "para": "P2"}),
    )
    assert any("diferentes" in erro for erro in erros)


def test_vao_para_poste_inexistente_com_id_parecido_e_recusado() -> None:
    _recusada(_def(("vaos", 0, "para"), "p2"))
    _recusada(_def(("vaos", 0, "para"), "P2 "))


@pytest.mark.parametrize(
    "sha",
    [
        "A" * 64,
        "a" * 63,
        "a" * 65,
        "g" * 64,
        ("a" * 63) + "A",
        " " + "a" * 63,
        "a" * 64 + " ",
        "a" * 64 + "\n",
        "",
        None,
        123,
    ],
    ids=[
        "maiusculas",
        "63",
        "65",
        "nao hexa",
        "uma maiuscula",
        "espaco antes",
        "espaco depois",
        "quebra de linha final",
        "vazio",
        "nulo",
        "numero",
    ],
)
def test_pdf_sha256_fora_do_formato_e_recusado(sha: Any) -> None:
    _recusada(_def(("pdf_sha256",), sha))


@pytest.mark.parametrize(
    "versao", [1.0, 1.5, 2, 0, "1", None, False, True, [1]], ids=lambda v: repr(v)
)
def test_schema_version_diferente_de_inteiro_1_e_recusado(versao: Any) -> None:
    _recusada(_def(("schema_version",), versao))


def test_schema_version_float_1_0_lido_de_json_e_recusado(tmp_path: Path) -> None:
    ficha = _base()
    arquivo = tmp_path / "ficha.json"
    texto = json.dumps(ficha).replace('"schema_version": 1,', '"schema_version": 1.0,')
    assert '"schema_version": 1.0' in texto
    arquivo.write_text(texto, encoding="utf-8")
    with pytest.raises(ValueError):
        carregar_ficha(arquivo)


def test_schema_version_ausente_e_recusado() -> None:
    ficha = _base()
    del ficha["schema_version"]
    assert validar_ficha(ficha)


def test_referencia_sem_gerador_e_valida_e_com_gerador_tambem() -> None:
    ficha = _base()
    assert "gerador" not in ficha
    assert validar_ficha(ficha) == []
    ficha["gerador"] = {"versao_extracao": "v1"}
    assert validar_ficha(ficha) == []


def test_predicao_sem_gerador_e_invalida() -> None:
    ficha = _base()
    ficha["tipo"] = "predicao"
    erros = validar_ficha(ficha)
    assert any("gerador" in erro for erro in erros)


def test_predicao_com_gerador_vazio_e_valida() -> None:
    ficha = _base()
    ficha["tipo"] = "predicao"
    ficha["gerador"] = {}
    assert validar_ficha(ficha) == []


@pytest.mark.parametrize("gerador", [None, [], "v1", 1, True])
def test_gerador_que_nao_e_objeto_e_recusado(gerador: Any) -> None:
    ficha = _base()
    ficha["tipo"] = "predicao"
    ficha["gerador"] = gerador
    assert validar_ficha(ficha)
    ref = _base()
    ref["gerador"] = gerador
    assert validar_ficha(ref)


@pytest.mark.parametrize("extras", [[], [1], "x", 1, None, True], ids=lambda v: repr(v))
@pytest.mark.parametrize(
    "caminho",
    [
        ("atributos_extras",),
        ("postes", 0, "atributos_extras"),
        ("vaos", 0, "atributos_extras"),
        ("postes", 0, "simbolos", 0, "atributos_extras"),
    ],
    ids=["raiz", "poste", "vao", "simbolo"],
)
def test_atributos_extras_que_nao_e_objeto_e_recusado(
    caminho: tuple[Any, ...], extras: Any
) -> None:
    _recusada(_def(caminho, extras))


def test_tipo_da_ficha_fora_do_enum_e_recusado() -> None:
    for tipo in ("Referencia", "REFERENCIA", "predição", "", None, 1):
        _recusada(_def(("tipo",), tipo))


def test_escopo_tipo_fora_do_enum_e_recusado() -> None:
    for tipo in ("Completo", "parcial", "", None):
        _recusada(_def(("escopo_anotacao", "tipo"), tipo))


@pytest.mark.parametrize("pagina", [1, 2])
def test_regional_com_poste_em_pagina_sem_regiao_e_recusado(pagina: int) -> None:
    def alterar(ficha: dict[str, Any]) -> None:
        ficha["escopo_anotacao"] = {
            "tipo": "regional",
            "regioes": [{"pagina": 3, "bbox": [0.0, 0.0, 1.0, 1.0]}],
        }
        ficha["postes"][0]["pagina"] = pagina
        ficha["postes"][1]["pagina"] = pagina

    erros = _recusada(alterar)
    assert any("P1" in erro for erro in erros)
    assert any("P2" in erro for erro in erros)


def test_regional_com_poste_na_pagina_certa_mas_fora_da_bbox_e_recusado() -> None:
    def alterar(ficha: dict[str, Any]) -> None:
        ficha["escopo_anotacao"] = {
            "tipo": "regional",
            "regioes": [{"pagina": 1, "bbox": [0.0, 0.0, 0.3, 0.3]}],
        }

    erros = _recusada(alterar)
    assert any("P2" in erro for erro in erros)
    assert not any("P1" in erro for erro in erros)


def test_regional_aceita_poste_na_borda_da_regiao_e_centro_dentro_com_bbox_saindo() -> None:
    def alterar(ficha: dict[str, Any]) -> None:
        ficha["escopo_anotacao"] = {
            "tipo": "regional",
            "regioes": [{"pagina": 1, "bbox": [0.0, 0.0, 0.5, 0.5]}],
        }
        ficha["postes"][0]["bbox"] = [0.4, 0.4, 0.6, 0.6]  # centro 0.5,0.5 na borda
        ficha["postes"][1]["bbox"] = [0.2, 0.2, 0.2, 0.2]

    _aceita(alterar)


def test_regional_com_varias_paginas_exige_regiao_da_pagina_de_cada_poste() -> None:
    def alterar(ficha: dict[str, Any]) -> None:
        ficha["escopo_anotacao"] = {
            "tipo": "regional",
            "regioes": [
                {"pagina": 1, "bbox": [0.0, 0.0, 0.6, 0.6]},
                {"pagina": 2, "bbox": [0.0, 0.0, 0.6, 0.6]},
            ],
        }
        ficha["postes"][1]["pagina"] = 2

    _aceita(alterar)

    def pagina_sem_regiao(ficha: dict[str, Any]) -> None:
        alterar(ficha)
        ficha["postes"][1]["pagina"] = 3

    _recusada(pagina_sem_regiao)


def test_regional_com_regiao_de_bbox_fora_de_0_1_e_recusada() -> None:
    def alterar(ficha: dict[str, Any]) -> None:
        ficha["escopo_anotacao"] = {
            "tipo": "regional",
            "regioes": [{"pagina": 1, "bbox": [0.0, 0.0, 1.5, 1.0]}],
        }

    _recusada(alterar)


def _escopo_regional(pagina: Any = 1, regioes: Any = None) -> Alterar:
    def alterar(ficha: dict[str, Any]) -> None:
        lista = (
            regioes if regioes is not None else [{"pagina": pagina, "bbox": [0.0, 0.0, 1.0, 1.0]}]
        )
        ficha["escopo_anotacao"] = {"tipo": "regional", "regioes": lista}

    return alterar


@pytest.mark.parametrize("pagina", [0, -1, 1.5, "1", None])
def test_regiao_de_pagina_invalida_e_recusada(pagina: Any) -> None:
    _recusada(_escopo_regional(pagina=pagina))


@pytest.mark.parametrize("regioes", [{}, "x", 1])
def test_regioes_que_nao_e_lista_e_recusado(regioes: Any) -> None:
    _recusada(_escopo_regional(regioes=regioes))


def test_regioes_nula_e_recusado() -> None:
    _recusada(_def(("escopo_anotacao", "regioes"), None))


def test_predicao_regional_e_recusada_mesmo_com_gerador() -> None:
    ficha = _base()
    ficha["tipo"] = "predicao"
    ficha["gerador"] = {"v": 1}
    ficha["escopo_anotacao"] = {
        "tipo": "regional",
        "regioes": [{"pagina": 1, "bbox": [0.0, 0.0, 1.0, 1.0]}],
    }
    assert any("completo" in erro for erro in validar_ficha(ficha))


def test_predicao_com_poste_fora_de_regioes_nao_e_cobrada_pela_regra_da_referencia() -> None:
    ficha = _base()
    ficha["tipo"] = "predicao"
    ficha["gerador"] = {"v": 1}
    assert validar_ficha(ficha) == []


def test_coordenada_incompleta_ou_de_tipo_errado_e_recusada() -> None:
    _recusada(lambda f: f["postes"][0]["coordenada"].pop("norte"))
    _recusada(lambda f: f["postes"][0]["coordenada"].pop("leste"))
    _recusada(_def(("postes", 0, "coordenada"), []))
    _recusada(_def(("postes", 0, "coordenada"), "700000,7800000"))
    _recusada(_def(("postes", 0, "coordenada", "leste"), "700000"))
    _recusada(_def(("postes", 0, "coordenada", "norte"), None))


def test_coordenada_sem_zona_ou_com_zona_nula_e_valida() -> None:
    _aceita(lambda f: f["postes"][0]["coordenada"].pop("zona"))
    _aceita(_def(("postes", 0, "coordenada", "zona"), None))


def test_comprimento_negativo_e_recusado_e_zero_e_nulo_sao_validos() -> None:
    _recusada(_def(("vaos", 0, "comprimento_m"), -0.01))
    _aceita(_def(("vaos", 0, "comprimento_m"), 0))
    _aceita(_def(("vaos", 0, "comprimento_m"), None))
    _aceita(_def(("vaos", 0, "cabo"), None))


def test_postes_e_vaos_que_nao_sao_listas_ou_itens_nao_objeto_sao_recusados() -> None:
    _recusada(_def(("postes",), {}))
    _recusada(_def(("vaos",), None))
    _recusada(_def(("postes",), [None]))
    _recusada(_def(("vaos",), ["P1"]))


def test_ficha_sem_postes_nem_vaos_e_valida_mas_vao_sem_postes_nao() -> None:
    def vazia(ficha: dict[str, Any]) -> None:
        ficha["postes"] = []
        ficha["vaos"] = []

    _aceita(vazia)
    _recusada(lambda f: f.update(postes=[]))


def test_simbolos_do_mesmo_id_em_postes_diferentes_sao_recusados() -> None:
    def alterar(ficha: dict[str, Any]) -> None:
        ficha["postes"][1]["simbolos"] = [copy.deepcopy(ficha["postes"][0]["simbolos"][0])]

    erros = _recusada(alterar)
    assert any("símbolo" in erro and "repetido" in erro for erro in erros)
