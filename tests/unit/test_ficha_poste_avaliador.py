"""Avaliador determinístico de fichas por poste: métricas, casamento, escopo e determinismo."""

from __future__ import annotations

import copy
import random
from typing import Any

import pytest
from scripts.ficha_poste_avaliador import (
    PROTOCOLO_FICHA,
    avaliar,
    casar_postes,
    normalizar_texto,
)

SHA = "a" * 64
OUTRO_SHA = "b" * 64
U = 1 / 32  # unidade binária exata: IoU sem ruído de ponto flutuante nos casos de empate


def _simbolo(identificador: str, bbox: list[float], classe: str = "ESTAI") -> dict[str, Any]:
    return {"id": identificador, "classe": classe, "bbox": bbox}


def _poste(
    identificador: str,
    x: float,
    y: float = 0.1,
    *,
    nome: str | None = "1",
    estruturas: list[str] | None = None,
    poste: str | None = "DT 11/300",
    coordenada: dict[str, Any] | None = None,
    simbolos: list[dict[str, Any]] | None = None,
    pendentes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": identificador,
        "pagina": 1,
        "bbox": [x, y, x, y],
        "identificador": nome,
        "estruturas": ["N1", "M1"] if estruturas is None else estruturas,
        "poste": poste,
        "coordenada": {"leste": 700000.0, "norte": 7800000.0, "zona": "23K"}
        if coordenada is None
        else coordenada,
        "simbolos": [] if simbolos is None else simbolos,
        "pendentes": [] if pendentes is None else pendentes,
    }


def _vao(
    de: str,
    para: str,
    comprimento: float | None = 40.0,
    cabo: str | None = "MT",
    pendentes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "de": de,
        "para": para,
        "comprimento_m": comprimento,
        "cabo": cabo,
        "pendentes": [] if pendentes is None else pendentes,
    }


def _ficha(
    postes: list[dict[str, Any]],
    vaos: list[dict[str, Any]],
    *,
    tipo: str = "referencia",
    regioes: list[dict[str, Any]] | None = None,
    sha: str = SHA,
) -> dict[str, Any]:
    ficha: dict[str, Any] = {
        "schema_version": 1,
        "tipo": tipo,
        "pdf_sha256": sha,
        "escopo_anotacao": {"tipo": "completo"}
        if regioes is None
        else {"tipo": "regional", "regioes": regioes},
        "postes": postes,
        "vaos": vaos,
    }
    if tipo == "predicao":
        ficha["gerador"] = {"versao_extracao": "v1"}
    return ficha


def _tres_postes() -> list[dict[str, Any]]:
    return [
        _poste("P1", 0.1, simbolos=[_simbolo("S1", [0.10, 0.20, 0.14, 0.24])]),
        _poste("P2", 0.3, simbolos=[_simbolo("S2", [0.30, 0.20, 0.34, 0.24])]),
        _poste("P3", 0.5, simbolos=[_simbolo("S3", [0.50, 0.20, 0.54, 0.24])]),
    ]


def _dois_vaos() -> list[dict[str, Any]]:
    return [_vao("P1", "P2", 40.0, "MT"), _vao("P2", "P3", 30.0, "BT")]


def _referencia() -> dict[str, Any]:
    return _ficha(_tres_postes(), _dois_vaos())


def _como_predicao(ficha: dict[str, Any]) -> dict[str, Any]:
    """Cópia da ficha como predição, com todos os ids renomeados (Q + id)."""
    predicao = copy.deepcopy(ficha)
    predicao["tipo"] = "predicao"
    predicao["gerador"] = {"versao_extracao": "v1"}
    for poste in predicao["postes"]:
        poste["id"] = "Q" + poste["id"]
        for simbolo in poste["simbolos"]:
            simbolo["id"] = "Q" + simbolo["id"]
    for vao in predicao["vaos"]:
        vao["de"] = "Q" + vao["de"]
        vao["para"] = "Q" + vao["para"]
    return predicao


def _acerto_total() -> tuple[dict[str, Any], dict[str, Any]]:
    referencia = _referencia()
    return referencia, _como_predicao(referencia)


def test_acerto_total_tem_todas_as_metricas_em_um() -> None:
    referencia, predicao = _acerto_total()
    relatorio = avaliar(referencia, predicao)
    for bloco in (relatorio["postes"], relatorio["vaos"], relatorio["simbolos"]):
        assert bloco["precisao"] == 1.0
        assert bloco["recall"] == 1.0
        assert (bloco["fp"], bloco["fn"]) == (0, 0)
    assert relatorio["postes"]["tp"] == 3
    assert relatorio["vaos"]["tp"] == 2
    assert relatorio["simbolos"]["tp"] == 3
    for campo in ("identificador", "estruturas", "poste", "coordenada"):
        assert relatorio["campos"][campo]["taxa"] == 1.0
        assert relatorio["campos"][campo]["total"] == 3
    assert relatorio["vaos"]["comprimento"]["taxa"] == 1.0
    assert relatorio["vaos"]["cabo"]["taxa"] == 1.0
    assert relatorio["nao_casados"] == {"referencia": [], "predicao": []}
    assert relatorio["simbolos_nao_casados"] == {"referencia": [], "predicao": []}
    assert [par["referencia"] for par in relatorio["pares"]] == ["P1", "P2", "P3"]
    assert relatorio["pares"][0]["predicao"] == "QP1"
    assert relatorio["pares"][0]["distancia"] == 0.0
    assert relatorio["pdf_sha256"] == SHA
    assert relatorio["escopo"] == "completo"
    assert relatorio["protocolo"] == PROTOCOLO_FICHA


def test_chaves_do_relatorio_sao_as_do_protocolo() -> None:
    relatorio = avaliar(*_acerto_total())
    assert set(relatorio) == {
        "schema_version",
        "protocolo",
        "pdf_sha256",
        "escopo",
        "gerador_predicao",
        "postes",
        "campos",
        "vaos",
        "simbolos",
        "pares",
        "nao_casados",
        "simbolos_nao_casados",
    }
    assert set(relatorio["postes"]) == {"tp", "fp", "fn", "precisao", "recall"}
    assert set(relatorio["campos"]) == {"identificador", "estruturas", "poste", "coordenada"}
    assert set(relatorio["campos"]["poste"]) == {
        "acertos",
        "total",
        "taxa",
        "erros_com_pendencia",
        "erros_sem_pendencia",
    }
    assert set(relatorio["vaos"]) == {
        "tp",
        "fp",
        "fn",
        "precisao",
        "recall",
        "comprimento",
        "cabo",
    }
    assert set(relatorio["pares"][0]) == {"referencia", "predicao", "distancia", "campos"}


def test_simbolo_no_poste_vizinho_conta_fp_e_fn() -> None:
    referencia, predicao = _acerto_total()
    simbolo = predicao["postes"][0]["simbolos"].pop()
    predicao["postes"][1]["simbolos"].append(simbolo)
    relatorio = avaliar(referencia, predicao)
    assert (relatorio["simbolos"]["tp"], relatorio["simbolos"]["fp"]) == (2, 1)
    assert relatorio["simbolos"]["fn"] == 1
    assert relatorio["simbolos"]["precisao"] == pytest.approx(2 / 3)
    assert relatorio["simbolos_nao_casados"] == {"referencia": ["S1"], "predicao": ["QS1"]}
    assert (relatorio["postes"]["tp"], relatorio["postes"]["fp"], relatorio["postes"]["fn"]) == (
        3,
        0,
        0,
    )


def test_simbolos_de_postes_nao_casados_contam_fp_e_fn() -> None:
    referencia = _ficha([_poste("P1", 0.1, simbolos=[_simbolo("S1", [0.1, 0.2, 0.14, 0.24])])], [])
    predicao = _ficha(
        [_poste("Q1", 0.8, simbolos=[_simbolo("QS1", [0.8, 0.2, 0.84, 0.24])])],
        [],
        tipo="predicao",
    )
    relatorio = avaliar(referencia, predicao)
    assert (relatorio["postes"]["tp"], relatorio["postes"]["fp"], relatorio["postes"]["fn"]) == (
        0,
        1,
        1,
    )
    assert (relatorio["simbolos"]["tp"], relatorio["simbolos"]["fp"]) == (0, 1)
    assert relatorio["simbolos"]["fn"] == 1
    assert relatorio["simbolos_nao_casados"] == {"referencia": ["S1"], "predicao": ["QS1"]}
    assert relatorio["nao_casados"] == {"referencia": ["P1"], "predicao": ["Q1"]}


def test_poste_ausente_reduz_recall_e_vao_vira_fn() -> None:
    referencia, predicao = _acerto_total()
    predicao["postes"].pop()
    predicao["vaos"].pop()
    relatorio = avaliar(referencia, predicao)
    assert (relatorio["postes"]["tp"], relatorio["postes"]["fp"], relatorio["postes"]["fn"]) == (
        2,
        0,
        1,
    )
    assert relatorio["postes"]["recall"] == pytest.approx(2 / 3)
    assert relatorio["postes"]["precisao"] == 1.0
    assert (relatorio["vaos"]["tp"], relatorio["vaos"]["fp"], relatorio["vaos"]["fn"]) == (1, 0, 1)
    assert relatorio["nao_casados"] == {"referencia": ["P3"], "predicao": []}
    assert relatorio["simbolos_nao_casados"]["referencia"] == ["S3"]


def test_vao_com_comprimento_errado_casa_mas_erra_comprimento() -> None:
    referencia = _ficha([_poste("P1", 0.1), _poste("P2", 0.3)], [_vao("P1", "P2", 40.0)])
    predicao = _ficha(
        [_poste("Q1", 0.1), _poste("Q2", 0.3)], [_vao("Q1", "Q2", 35.0)], tipo="predicao"
    )
    vaos = avaliar(referencia, predicao)["vaos"]
    assert vaos["tp"] == 1
    assert (vaos["fp"], vaos["fn"]) == (0, 0)
    assert vaos["comprimento"] == {
        "acertos": 0,
        "total": 1,
        "taxa": 0.0,
        "erros_com_pendencia": 0,
        "erros_sem_pendencia": 1,
    }
    assert vaos["cabo"]["taxa"] == 1.0


def test_comprimento_dentro_da_tolerancia_acerta() -> None:
    referencia = _ficha([_poste("P1", 0.1), _poste("P2", 0.3)], [_vao("P1", "P2", 40.0)])
    predicao = _ficha(
        [_poste("Q1", 0.1), _poste("Q2", 0.3)], [_vao("Q1", "Q2", 40.1)], tipo="predicao"
    )
    assert avaliar(referencia, predicao)["vaos"]["comprimento"]["acertos"] == 1
    predicao["vaos"][0]["comprimento_m"] = 40.11
    assert avaliar(referencia, predicao)["vaos"]["comprimento"]["acertos"] == 0


def test_dois_vaos_no_mesmo_par_casam_por_cabo() -> None:
    postes_ref = [_poste("P1", 0.1), _poste("P2", 0.3)]
    referencia = _ficha(postes_ref, [_vao("P1", "P2", 40.0, "MT"), _vao("P1", "P2", 60.0, "BT")])
    # Comprimentos trocados e ordem trocada: só o cabo identifica o par certo.
    predicao = _ficha(
        [_poste("Q1", 0.1), _poste("Q2", 0.3)],
        [_vao("Q2", "Q1", 40.0, "BT"), _vao("Q1", "Q2", 60.0, "MT")],
        tipo="predicao",
    )
    vaos = avaliar(referencia, predicao)["vaos"]
    assert vaos["tp"] == 2
    assert (vaos["fp"], vaos["fn"]) == (0, 0)
    assert vaos["cabo"]["taxa"] == 1.0
    assert vaos["comprimento"]["acertos"] == 0


def test_vao_a_mais_no_par_e_fp_e_a_menos_e_fn() -> None:
    postes = [_poste("P1", 0.1), _poste("P2", 0.3)]
    um_vao = _ficha(postes, [_vao("P1", "P2")])
    dois_vaos = _ficha(
        [_poste("Q1", 0.1), _poste("Q2", 0.3)],
        [_vao("Q1", "Q2"), _vao("Q1", "Q2", 40.0, "BT")],
        tipo="predicao",
    )
    vaos = avaliar(um_vao, dois_vaos)["vaos"]
    assert (vaos["tp"], vaos["fp"], vaos["fn"]) == (1, 1, 0)
    referencia_dois = _ficha(postes, [_vao("P1", "P2"), _vao("P1", "P2", 40.0, "BT")])
    predicao_um = _ficha(
        [_poste("Q1", 0.1), _poste("Q2", 0.3)], [_vao("Q1", "Q2")], tipo="predicao"
    )
    vaos = avaliar(referencia_dois, predicao_um)["vaos"]
    assert (vaos["tp"], vaos["fp"], vaos["fn"]) == (1, 0, 1)


def test_vao_entre_postes_trocados_no_casamento_nao_casa() -> None:
    referencia = _ficha([_poste("P1", 0.1), _poste("P2", 0.3)], [_vao("P1", "P2")])
    predicao = _ficha(
        [_poste("Q1", 0.1), _poste("Q2", 0.3), _poste("Q3", 0.6)],
        [_vao("Q1", "Q3")],
        tipo="predicao",
    )
    vaos = avaliar(referencia, predicao)["vaos"]
    assert (vaos["tp"], vaos["fp"], vaos["fn"]) == (0, 1, 1)


def _regioes_esquerda() -> list[dict[str, Any]]:
    return [{"pagina": 1, "bbox": [0.0, 0.0, 0.4, 0.4]}]


def test_referencia_regional_ignora_predicao_fora_das_regioes() -> None:
    referencia = _ficha(
        [_poste("P1", 0.1), _poste("P2", 0.3)],
        [_vao("P1", "P2")],
        regioes=_regioes_esquerda(),
    )
    predicao = _ficha(
        [
            _poste("Q1", 0.1),
            _poste("Q2", 0.3),
            _poste("Q3", 0.5, simbolos=[_simbolo("QS3", [0.5, 0.2, 0.54, 0.24])]),
        ],
        [_vao("Q1", "Q2"), _vao("Q2", "Q3")],
        tipo="predicao",
    )
    relatorio = avaliar(referencia, predicao)
    assert relatorio["escopo"] == "regional"
    assert (relatorio["postes"]["tp"], relatorio["postes"]["fp"]) == (2, 0)
    assert (relatorio["vaos"]["tp"], relatorio["vaos"]["fp"]) == (1, 0)
    assert relatorio["simbolos"]["fp"] == 0
    assert relatorio["nao_casados"]["predicao"] == []
    assert relatorio["simbolos_nao_casados"]["predicao"] == []


def test_referencia_completa_conta_predicao_extra_como_fp() -> None:
    referencia = _ficha([_poste("P1", 0.1), _poste("P2", 0.3)], [_vao("P1", "P2")])
    predicao = _ficha(
        [
            _poste("Q1", 0.1),
            _poste("Q2", 0.3),
            _poste("Q3", 0.5, simbolos=[_simbolo("QS3", [0.5, 0.2, 0.54, 0.24])]),
        ],
        [_vao("Q1", "Q2"), _vao("Q2", "Q3")],
        tipo="predicao",
    )
    relatorio = avaliar(referencia, predicao)
    assert relatorio["postes"]["fp"] == 1
    assert relatorio["vaos"]["fp"] == 1
    assert relatorio["simbolos"]["fp"] == 1
    assert relatorio["nao_casados"]["predicao"] == ["Q3"]


def test_regiao_de_outra_pagina_nao_cobre_poste_predito() -> None:
    referencia = _ficha(
        [_poste("P1", 0.1)], [], regioes=[{"pagina": 1, "bbox": [0.0, 0.0, 0.4, 0.4]}]
    )
    fora = _poste("Q2", 0.3)
    fora["pagina"] = 2
    predicao = _ficha([_poste("Q1", 0.1), fora], [], tipo="predicao")
    relatorio = avaliar(referencia, predicao)
    assert relatorio["postes"]["fp"] == 0
    assert relatorio["nao_casados"]["predicao"] == []


def test_identificador_igual_casa_ate_distancia_maior() -> None:
    referencia = _ficha([_poste("P1", 0.10, nome="123")], [])
    mesmo = _ficha([_poste("Q1", 0.14, nome=" 123 ")], [], tipo="predicao")
    relatorio = avaliar(referencia, mesmo)
    assert relatorio["postes"]["tp"] == 1
    assert relatorio["pares"][0]["distancia"] == pytest.approx(0.04)
    outro = _ficha([_poste("Q1", 0.14, nome="999")], [], tipo="predicao")
    relatorio = avaliar(referencia, outro)
    assert (relatorio["postes"]["tp"], relatorio["postes"]["fp"], relatorio["postes"]["fn"]) == (
        0,
        1,
        1,
    )


def test_distancia_acima_do_maximo_para_mesmo_identificador_nao_casa() -> None:
    referencia = _ficha([_poste("P1", 0.10, nome="123")], [])
    longe = _ficha([_poste("Q1", 0.16, nome="123")], [], tipo="predicao")
    assert avaliar(referencia, longe)["postes"]["tp"] == 0


def test_casar_postes_prefere_identificador_igual_e_depois_distancia() -> None:
    referencia = [_poste("P1", 0.10, nome="7")]
    predicao = [_poste("Q1", 0.105, nome="8"), _poste("Q2", 0.14, nome="7")]
    pares = casar_postes(referencia, predicao)
    assert [(r, p) for r, p, _ in pares] == [("P1", "Q2")]
    assert pares[0][2] == pytest.approx(0.04)


def test_casar_postes_empate_resolve_por_ids() -> None:
    referencia = [_poste("P2", 0.10, nome=None), _poste("P1", 0.10, nome=None)]
    predicao = [_poste("Q2", 0.10, nome=None), _poste("Q1", 0.10, nome=None)]
    assert [(r, p) for r, p, _ in casar_postes(referencia, predicao)] == [
        ("P1", "Q1"),
        ("P2", "Q2"),
    ]


def test_casar_postes_so_na_mesma_pagina() -> None:
    outra = _poste("Q1", 0.10)
    outra["pagina"] = 2
    assert casar_postes([_poste("P1", 0.10)], [outra]) == []


def test_erro_de_campo_conta_so_no_campo() -> None:
    referencia = _ficha([_poste("P1", 0.1)], [])
    errado = _poste(
        "Q1",
        0.1,
        nome="999",
        estruturas=["X9"],
        poste="OUTRO",
        coordenada={"leste": 700001.0, "norte": 7800000.0, "zona": "23K"},
    )
    relatorio = avaliar(referencia, _ficha([errado], [], tipo="predicao"))
    assert relatorio["postes"]["tp"] == 1
    for campo in ("identificador", "estruturas", "poste", "coordenada"):
        bloco = relatorio["campos"][campo]
        assert (bloco["acertos"], bloco["total"], bloco["taxa"]) == (0, 1, 0.0)
        assert (bloco["erros_com_pendencia"], bloco["erros_sem_pendencia"]) == (0, 1)
    assert relatorio["pares"][0]["campos"] == {
        "identificador": False,
        "estruturas": False,
        "poste": False,
        "coordenada": False,
    }


def test_normalizacao_de_texto_e_ordem_das_estruturas() -> None:
    assert normalizar_texto("  dt   11/300 ") == "DT 11/300"
    assert normalizar_texto("   ") is None
    assert normalizar_texto(None) is None
    referencia = _ficha([_poste("P1", 0.1, estruturas=["N1", "M1"], poste="DT 11/300")], [])
    predicao = _ficha(
        [_poste("Q1", 0.1, estruturas=["m1", " n1"], poste="dt  11/300")], [], tipo="predicao"
    )
    campos = avaliar(referencia, predicao)["pares"][0]["campos"]
    assert campos["estruturas"] is True
    assert campos["poste"] is True


def test_coordenada_na_tolerancia_acerta_e_zona_nao_entra() -> None:
    referencia = _ficha(
        [_poste("P1", 0.1, coordenada={"leste": 10.0, "norte": 20.0, "zona": "23K"})], []
    )
    predicao = _ficha(
        [_poste("Q1", 0.1, coordenada={"leste": 10.01, "norte": 19.99, "zona": "24K"})],
        [],
        tipo="predicao",
    )
    assert avaliar(referencia, predicao)["campos"]["coordenada"]["acertos"] == 1
    predicao["postes"][0]["coordenada"]["norte"] = 19.98
    assert avaliar(referencia, predicao)["campos"]["coordenada"]["acertos"] == 0


def test_coordenada_nula_nos_dois_lados_acerta_e_so_um_lado_erra() -> None:
    referencia = _ficha([_poste("P1", 0.1)], [])
    referencia["postes"][0]["coordenada"] = None
    predicao = _ficha([_poste("Q1", 0.1)], [], tipo="predicao")
    predicao["postes"][0]["coordenada"] = None
    assert avaliar(referencia, predicao)["campos"]["coordenada"]["acertos"] == 1
    predicao["postes"][0]["coordenada"] = {"leste": 1.0, "norte": 2.0}
    assert avaliar(referencia, predicao)["campos"]["coordenada"]["acertos"] == 0


def test_campo_pendente_na_referencia_sai_do_denominador() -> None:
    referencia = _ficha(
        [
            _poste(
                "P1",
                0.1,
                pendentes=["identificador", "simbolos"],
                simbolos=[_simbolo("S1", [0.1, 0.2, 0.14, 0.24])],
            )
        ],
        [],
    )
    predicao = _ficha(
        [_poste("Q1", 0.1, nome="999", simbolos=[_simbolo("QS1", [0.1, 0.2, 0.14, 0.24])])],
        [],
        tipo="predicao",
    )
    relatorio = avaliar(referencia, predicao)
    assert relatorio["campos"]["identificador"]["total"] == 0
    assert relatorio["campos"]["identificador"]["taxa"] is None
    assert relatorio["campos"]["poste"]["total"] == 1
    assert relatorio["pares"][0]["campos"]["identificador"] is None
    simbolos = relatorio["simbolos"]
    assert (simbolos["tp"], simbolos["fp"], simbolos["fn"]) == (0, 0, 0)
    assert relatorio["simbolos_nao_casados"] == {"referencia": [], "predicao": []}


def test_simbolos_pendentes_de_poste_nao_casado_ficam_fora_so_na_referencia() -> None:
    referencia = _ficha(
        [
            _poste(
                "P1",
                0.1,
                pendentes=["simbolos"],
                simbolos=[_simbolo("S1", [0.1, 0.2, 0.14, 0.24])],
            )
        ],
        [],
    )
    predicao = _ficha(
        [_poste("Q1", 0.8, simbolos=[_simbolo("QS1", [0.8, 0.2, 0.84, 0.24])])],
        [],
        tipo="predicao",
    )
    relatorio = avaliar(referencia, predicao)
    assert (relatorio["simbolos"]["fn"], relatorio["simbolos"]["fp"]) == (0, 1)


def test_nulo_na_referencia_conta_e_predicao_inventada_e_erro() -> None:
    referencia = _ficha([_poste("P1", 0.1, nome=None)], [])
    inventada = _ficha([_poste("Q1", 0.1, nome="P9")], [], tipo="predicao")
    bloco = avaliar(referencia, inventada)["campos"]["identificador"]
    assert (bloco["acertos"], bloco["total"], bloco["erros_sem_pendencia"]) == (0, 1, 1)
    nula = _ficha([_poste("Q1", 0.1, nome=None)], [], tipo="predicao")
    bloco = avaliar(referencia, nula)["campos"]["identificador"]
    assert (bloco["acertos"], bloco["total"], bloco["taxa"]) == (1, 1, 1.0)


def test_erro_em_campo_pendente_da_predicao_conta_a_parte() -> None:
    referencia = _ficha([_poste("P1", 0.1)], [])
    predicao = _ficha(
        [_poste("Q1", 0.1, nome="999", pendentes=["identificador"])], [], tipo="predicao"
    )
    bloco = avaliar(referencia, predicao)["campos"]["identificador"]
    assert (bloco["erros_com_pendencia"], bloco["erros_sem_pendencia"]) == (1, 0)
    assert bloco["acertos"] == 0
    assert bloco["total"] == 1


def test_pendencia_do_vao_na_referencia_e_na_predicao() -> None:
    referencia = _ficha(
        [_poste("P1", 0.1), _poste("P2", 0.3)],
        [_vao("P1", "P2", 40.0, "MT", pendentes=["cabo"])],
    )
    predicao = _ficha(
        [_poste("Q1", 0.1), _poste("Q2", 0.3)],
        [_vao("Q1", "Q2", 10.0, "BT", pendentes=["comprimento_m"])],
        tipo="predicao",
    )
    vaos = avaliar(referencia, predicao)["vaos"]
    assert vaos["cabo"]["total"] == 0
    assert vaos["comprimento"]["total"] == 1
    assert (
        vaos["comprimento"]["erros_com_pendencia"],
        vaos["comprimento"]["erros_sem_pendencia"],
    ) == (1, 0)


def test_atributos_extras_nao_afetam_metricas() -> None:
    referencia, predicao = _acerto_total()
    base = avaliar(referencia, predicao)
    referencia["atributos_extras"] = {"a": 1}
    referencia["postes"][0]["atributos_extras"] = {"nome": "outro", "identificador": "zzz"}
    predicao["atributos_extras"] = {"b": [1, 2]}
    predicao["postes"][0]["atributos_extras"] = {"identificador": "yyy"}
    predicao["vaos"][0]["atributos_extras"] = {"cabo": "BT"}
    predicao["postes"][0]["simbolos"][0]["atributos_extras"] = {"classe": "OUTRA"}
    assert avaliar(referencia, predicao) == base


def test_gerador_da_predicao_vai_ao_relatorio() -> None:
    referencia, predicao = _acerto_total()
    predicao["gerador"] = {"versao_extracao": "v7", "modelo": "x"}
    assert avaliar(referencia, predicao)["gerador_predicao"] == {
        "versao_extracao": "v7",
        "modelo": "x",
    }


def test_denominador_zero_da_none() -> None:
    referencia = _ficha([], [])
    predicao = _ficha([], [], tipo="predicao")
    relatorio = avaliar(referencia, predicao)
    for bloco in (relatorio["postes"], relatorio["vaos"], relatorio["simbolos"]):
        assert bloco["precisao"] is None
        assert bloco["recall"] is None
    for campo in relatorio["campos"].values():
        assert campo["taxa"] is None
    assert relatorio["vaos"]["comprimento"]["taxa"] is None
    assert relatorio["vaos"]["cabo"]["taxa"] is None
    assert relatorio["pares"] == []


def test_so_predicao_ou_so_referencia_da_none_na_taxa_sem_denominador() -> None:
    referencia = _ficha([], [])
    predicao = _ficha([_poste("Q1", 0.1)], [], tipo="predicao")
    postes = avaliar(referencia, predicao)["postes"]
    assert postes["precisao"] == 0.0
    assert postes["recall"] is None
    postes = avaliar(_ficha([_poste("P1", 0.1)], []), _ficha([], [], tipo="predicao"))["postes"]
    assert postes["precisao"] is None
    assert postes["recall"] == 0.0


def _ficha_invalida() -> dict[str, Any]:
    ficha = _referencia()
    ficha["postes"][0]["id"] = ficha["postes"][1]["id"]
    return ficha


@pytest.mark.parametrize(
    "caso", ["sha", "referencia_como_predicao", "predicao_como_referencia", "invalida"]
)
def test_pdf_ou_tipo_errado_e_recusado(caso: str) -> None:
    referencia, predicao = _acerto_total()
    if caso == "sha":
        predicao["pdf_sha256"] = OUTRO_SHA
    elif caso == "referencia_como_predicao":
        referencia["tipo"] = "predicao"
        referencia["gerador"] = {"versao_extracao": "v1"}
    elif caso == "predicao_como_referencia":
        predicao["tipo"] = "referencia"
        del predicao["gerador"]
    else:
        referencia = _ficha_invalida()
    with pytest.raises(ValueError):
        avaliar(referencia, predicao)


def test_ficha_invalida_traz_as_mensagens_do_validador() -> None:
    _, predicao = _acerto_total()
    with pytest.raises(ValueError, match="id de poste repetido"):
        avaliar(_ficha_invalida(), predicao)


def _poste_com_empate(ids_pred: tuple[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    a = _simbolo("A", [8 * U, 8 * U, 16 * U, 16 * U])
    b = _simbolo("B", [10 * U, 8 * U, 18 * U, 16 * U])
    x = _simbolo(ids_pred[0], [9 * U, 8 * U, 17 * U, 16 * U])
    y = _simbolo(ids_pred[1], [7 * U, 8 * U, 15 * U, 16 * U])
    return (
        _ficha([_poste("P1", 0.1, simbolos=[a, b])], []),
        _ficha([_poste("Q1", 0.1, simbolos=[x, y])], [], tipo="predicao"),
    )


@pytest.mark.parametrize("ids_pred", [("X", "Y"), ("Y", "X")])
@pytest.mark.parametrize("inverter", [False, True])
def test_simbolos_com_empate_casam_em_cardinalidade_maxima(
    ids_pred: tuple[str, str], inverter: bool
) -> None:
    referencia, predicao = _poste_com_empate(ids_pred)
    if inverter:
        referencia["postes"][0]["simbolos"].reverse()
        predicao["postes"][0]["simbolos"].reverse()
    simbolos = avaliar(referencia, predicao)["simbolos"]
    assert (simbolos["tp"], simbolos["fp"], simbolos["fn"]) == (2, 0, 0)


def test_simbolo_de_classe_diferente_ou_sem_sobreposicao_nao_casa() -> None:
    caixa = [0.1, 0.2, 0.14, 0.24]
    referencia = _ficha([_poste("P1", 0.1, simbolos=[_simbolo("S1", caixa)])], [])
    outra_classe = _ficha(
        [_poste("Q1", 0.1, simbolos=[_simbolo("QS1", caixa, "TRANSFORMADOR")])],
        [],
        tipo="predicao",
    )
    assert avaliar(referencia, outra_classe)["simbolos"]["tp"] == 0
    deslocado = _ficha(
        [_poste("Q1", 0.1, simbolos=[_simbolo("QS1", [0.5, 0.5, 0.54, 0.54])])],
        [],
        tipo="predicao",
    )
    assert avaliar(referencia, deslocado)["simbolos"]["tp"] == 0


def _ficha_embaralhavel() -> tuple[dict[str, Any], dict[str, Any]]:
    referencia, predicao = _poste_com_empate(("X", "Y"))
    extras_ref = [
        _poste("P2", 0.30, nome="2", simbolos=[_simbolo("S2", [0.30, 0.2, 0.34, 0.24])]),
        _poste("P3", 0.50, nome="3", simbolos=[_simbolo("S3", [0.50, 0.2, 0.54, 0.24])]),
        _poste("P4", 0.70, nome="4"),
    ]
    extras_pred = [
        _poste("Q2", 0.30, nome="2", simbolos=[_simbolo("QS2", [0.30, 0.2, 0.34, 0.24])]),
        _poste("Q3", 0.505, nome="9", simbolos=[_simbolo("QS3", [0.50, 0.2, 0.54, 0.24])]),
        _poste("Q5", 0.90, nome="5"),
    ]
    referencia["postes"].extend(extras_ref)
    predicao["postes"].extend(extras_pred)
    referencia["vaos"] = [
        _vao("P1", "P2", 40.0, "MT"),
        _vao("P1", "P2", 60.0, "BT"),
        _vao("P2", "P3", 30.0, "MT"),
        _vao("P3", "P4", 20.0, None),
    ]
    predicao["vaos"] = [
        _vao("Q2", "Q1", 60.0, "MT"),
        _vao("Q1", "Q2", 40.0, "BT"),
        _vao("Q2", "Q3", 30.5, "MT"),
        _vao("Q3", "Q5", 20.0, None),
    ]
    return referencia, predicao


def _embaralhar(ficha: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    copia = copy.deepcopy(ficha)
    rng.shuffle(copia["postes"])
    rng.shuffle(copia["vaos"])
    for poste in copia["postes"]:
        rng.shuffle(poste["simbolos"])
        rng.shuffle(poste["estruturas"])
    return copia


def test_resultado_deterministico_independe_da_ordem() -> None:
    referencia, predicao = _ficha_embaralhavel()
    esperado = avaliar(referencia, predicao)
    assert esperado["simbolos"]["tp"] >= 3  # inclui o caso de empate
    rng = random.Random(7)
    for _ in range(25):
        assert avaliar(_embaralhar(referencia, rng), _embaralhar(predicao, rng)) == esperado


def test_avaliar_nao_altera_as_fichas() -> None:
    referencia, predicao = _ficha_embaralhavel()
    copia_ref, copia_pred = copy.deepcopy(referencia), copy.deepcopy(predicao)
    avaliar(referencia, predicao)
    assert (referencia, predicao) == (copia_ref, copia_pred)


def test_distancia_no_limite_casa_apesar_do_ruido_de_float() -> None:
    referencia = [_poste("P1", 0.50, nome=None)]
    pares = casar_postes(referencia, [_poste("Q1", 0.52, nome=None)])
    assert [(r, p) for r, p, _ in pares] == [("P1", "Q1")]
    assert pares[0][2] == 0.52 - 0.50  # a distância informada não é arredondada
    mesmo = casar_postes([_poste("P1", 0.50, nome="7")], [_poste("Q1", 0.55, nome="7")])
    assert [(r, p) for r, p, _ in mesmo] == [("P1", "Q1")]
    acima = casar_postes(referencia, [_poste("Q1", 0.5201, nome=None)])
    assert acima == []


def _ficha_vaos_empatados(vaos: list[dict[str, Any]], prefixo: str, tipo: str) -> dict[str, Any]:
    return _ficha([_poste(prefixo + "1", 0.1), _poste(prefixo + "2", 0.3)], vaos, tipo=tipo)


def test_vaos_empatados_com_pendentes_diferentes_independem_da_ordem() -> None:
    def ref(cabo: str | None, pendentes: list[str]) -> dict[str, Any]:
        return _vao("P1", "P2", 40.0, cabo, pendentes)

    def pred(cabo: str | None, pendentes: list[str]) -> dict[str, Any]:
        return _vao("Q1", "Q2", 40.0, cabo, pendentes)

    # Pendência na referência: o vão pendente não pode "roubar" o par do vão sem pendência.
    refs = [ref(None, ["cabo"]), ref(None, [])]
    preds = [pred("MT", []), pred(None, [])]
    # Pendência na predição: o erro do vão pendente é contado à parte, em qualquer ordem.
    refs2 = [ref(None, []), ref("X", [])]
    preds2 = [pred(None, ["cabo"]), pred(None, [])]
    for r, p, esperado in ((refs, preds, (1, 1, 0, 0)), (refs2, preds2, (1, 2, 1, 0))):
        relatorios = []
        for ordem_ref in (r, r[::-1]):
            for ordem_pred in (p, p[::-1]):
                relatorios.append(
                    avaliar(
                        _ficha_vaos_empatados(copy.deepcopy(ordem_ref), "P", "referencia"),
                        _ficha_vaos_empatados(copy.deepcopy(ordem_pred), "Q", "predicao"),
                    )
                )
        assert all(relatorio == relatorios[0] for relatorio in relatorios)
        cabo = relatorios[0]["vaos"]["cabo"]
        assert (cabo["acertos"], cabo["total"], cabo["erros_com_pendencia"]) == esperado[:3]
        assert cabo["erros_sem_pendencia"] == esperado[3]


def test_tolerancia_de_coordenada_exata_em_northing_utm() -> None:
    def acertos(norte_ref: float, norte_pred: float) -> int:
        referencia = _ficha(
            [_poste("P1", 0.1, coordenada={"leste": 700000.0, "norte": norte_ref})], []
        )
        predicao = _ficha(
            [_poste("Q1", 0.1, coordenada={"leste": 700000.0, "norte": norte_pred})],
            [],
            tipo="predicao",
        )
        return int(avaliar(referencia, predicao)["campos"]["coordenada"]["acertos"])

    assert acertos(7800000.48, 7800000.47) == 1
    assert acertos(7800000.47, 7800000.48) == 1
    assert acertos(7800000.48, 7800000.46) == 0


def test_tolerancia_de_comprimento_exata_em_valores_grandes() -> None:
    def acertos(comprimento_ref: float, comprimento_pred: float) -> int:
        referencia = _ficha(
            [_poste("P1", 0.1), _poste("P2", 0.3)], [_vao("P1", "P2", comprimento_ref)]
        )
        predicao = _ficha(
            [_poste("Q1", 0.1), _poste("Q2", 0.3)],
            [_vao("Q1", "Q2", comprimento_pred)],
            tipo="predicao",
        )
        return int(avaliar(referencia, predicao)["vaos"]["comprimento"]["acertos"])

    assert acertos(1234.5, 1234.4) == 1
    assert acertos(1234.4, 1234.5) == 1
    assert acertos(1234.5, 1234.3) == 0
