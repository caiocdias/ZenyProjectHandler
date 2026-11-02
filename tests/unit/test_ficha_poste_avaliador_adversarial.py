"""Ataques ao avaliador por poste: números calculados à mão e mutantes que a suíte base não pega."""

from __future__ import annotations

import copy
import itertools
from typing import Any

import pytest
from scripts.ficha_poste_avaliador import avaliar, casar_postes

SHA = "a" * 64
U = 1 / 32  # unidade binária exata: IoU sem ruído de ponto flutuante


def _simbolo(identificador: str, bbox: list[float], classe: str = "ESTAI") -> dict[str, Any]:
    return {"id": identificador, "classe": classe, "bbox": bbox}


def _caixa(x0: float, y0: float, x1: float, y1: float) -> list[float]:
    """Caixa em unidades de 1/32 (coordenadas exatas em ponto flutuante)."""
    return [x0 * U, y0 * U, x1 * U, y1 * U]


def _poste(
    identificador: str,
    x: float,
    *,
    nome: str | None = "1",
    estruturas: list[str] | None = None,
    poste: str | None = "DT 11/300",
    coordenada: dict[str, Any] | None = None,
    simbolos: list[dict[str, Any]] | None = None,
    pendentes: list[str] | None = None,
    pagina: int = 1,
    y: float = 0.1,
) -> dict[str, Any]:
    return {
        "id": identificador,
        "pagina": pagina,
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
    vaos: list[dict[str, Any]] | None = None,
    *,
    tipo: str = "referencia",
    regioes: list[dict[str, Any]] | None = None,
    gerador: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ficha: dict[str, Any] = {
        "schema_version": 1,
        "tipo": tipo,
        "pdf_sha256": SHA,
        "escopo_anotacao": {"tipo": "completo"}
        if regioes is None
        else {"tipo": "regional", "regioes": regioes},
        "postes": postes,
        "vaos": [] if vaos is None else vaos,
    }
    if tipo == "predicao":
        ficha["gerador"] = {"versao_extracao": "v1"} if gerador is None else gerador
    return ficha


def _pred(postes: list[dict[str, Any]], vaos: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return _ficha(postes, vaos, tipo="predicao")


def _p(identificador: str, x: float, nome: str | None = None, pagina: int = 1) -> dict[str, Any]:
    """Poste mínimo para ``casar_postes`` (que só lê id, pagina, bbox e identificador)."""
    return {
        "id": identificador,
        "pagina": pagina,
        "bbox": [x, 0.5, x, 0.5],
        "identificador": nome,
    }


def _ids(pares: list[tuple[str, str, float]]) -> list[tuple[str, str]]:
    return [(ref, pred) for ref, pred, _ in pares]


# --- elegibilidade por distância -----------------------------------------------------------------


def test_distancia_exatamente_no_limite_casa() -> None:
    assert _ids(casar_postes([_p("R", 0.0)], [_p("Q", 0.02)])) == [("R", "Q")]


def test_distancia_um_pouco_acima_do_limite_nao_casa() -> None:
    assert casar_postes([_p("R", 0.0)], [_p("Q", 0.0200001)]) == []


def test_par_0_50_e_0_52_casa_apesar_do_ruido_de_ponto_flutuante() -> None:
    pares = casar_postes([_p("R", 0.5)], [_p("Q", 0.52)])
    assert _ids(pares) == [("R", "Q")]
    assert pares[0][2] == 0.52 - 0.5  # a distância reportada não é arredondada


@pytest.mark.parametrize(
    ("limite", "nome", "casa"),
    [
        (0.02, None, True),
        (0.02 + 4e-10, None, True),
        (0.02 + 2e-9, None, False),
        (0.05, "P1", True),
        (0.05 + 4e-10, "P1", True),
        (0.05 + 2e-9, "P1", False),
    ],
)
def test_limite_arredondado_a_nove_casas(limite: float, nome: str | None, casa: bool) -> None:
    pares = casar_postes([_p("R", 0.0, nome)], [_p("Q", limite, nome)])
    assert (_ids(pares) == [("R", "Q")]) is casa


def test_distancia_e_euclidiana_nos_dois_eixos() -> None:
    # dx = dy = 0.015: Chebyshev daria 0.015 (casa); a euclidiana dá ~0.0212 (não casa).
    ref = {"id": "R", "pagina": 1, "bbox": [0.1, 0.1, 0.1, 0.1], "identificador": None}
    pred = {"id": "Q", "pagina": 1, "bbox": [0.115, 0.115, 0.115, 0.115], "identificador": None}
    assert casar_postes([ref], [pred]) == []


def test_distancia_usa_o_centro_da_bbox_e_nao_o_canto() -> None:
    ref = {"id": "R", "pagina": 1, "bbox": [0.0, 0.0, 0.2, 0.2], "identificador": None}
    pred = {"id": "Q", "pagina": 1, "bbox": [0.1, 0.1, 0.1, 0.1], "identificador": None}
    pares = casar_postes([ref], [pred])
    assert _ids(pares) == [("R", "Q")]
    assert pares[0][2] == pytest.approx(0.0, abs=1e-12)


def test_distancia_devolvida_e_a_medida() -> None:
    pares = casar_postes([_p("R", 0.0)], [_p("Q", 0.0125)])
    assert pares[0][2] == pytest.approx(0.0125)


def test_mesmo_identificador_casa_exatamente_ate_0_05() -> None:
    assert _ids(casar_postes([_p("R", 0.0, "p1")], [_p("Q", 0.05, " P1 ")])) == [("R", "Q")]


def test_mesmo_identificador_acima_de_0_05_nao_casa() -> None:
    assert casar_postes([_p("R", 0.0, "P1")], [_p("Q", 0.0500001, "P1")]) == []


def test_identificador_diferente_a_0_03_nao_casa() -> None:
    assert casar_postes([_p("R", 0.0, "P1")], [_p("Q", 0.03, "P2")]) == []


def test_identificador_nulo_nos_dois_nao_conta_como_igual() -> None:
    assert casar_postes([_p("R", 0.0, None)], [_p("Q", 0.03, None)]) == []


def test_identificador_igual_na_caixa_e_espacos_internos_normaliza() -> None:
    pares = casar_postes([_p("R", 0.0, "p  1")], [_p("Q", 0.04, "P 1")])
    assert _ids(pares) == [("R", "Q")]


def test_paginas_diferentes_nunca_casam_nem_com_mesmo_identificador() -> None:
    assert casar_postes([_p("R", 0.1, "P1", pagina=1)], [_p("Q", 0.1, "P1", pagina=2)]) == []


def test_avaliar_poste_em_outra_pagina_e_fp_e_fn() -> None:
    referencia = _ficha([_poste("P1", 0.1)])
    predicao = _pred([_poste("Q1", 0.1, pagina=2)])
    relatorio = avaliar(referencia, predicao)
    assert (relatorio["postes"]["tp"], relatorio["postes"]["fp"], relatorio["postes"]["fn"]) == (
        0,
        1,
        1,
    )
    assert relatorio["pares"] == []
    assert relatorio["nao_casados"] == {"referencia": ["P1"], "predicao": ["Q1"]}


# --- ordem gulosa --------------------------------------------------------------------------------


def test_guloso_fica_com_o_par_mais_proximo() -> None:
    # R1 a 0.015 de Q, R2 a 0.005: R2 leva o predito, R1 fica sem par.
    pares = casar_postes([_p("R1", 0.0), _p("R2", 0.02)], [_p("Q", 0.015)])
    assert _ids(pares) == [("R2", "Q")]


def test_guloso_identificador_igual_vence_a_distancia_menor() -> None:
    # R1 (mesmo identificador) está mais longe que R2; o grupo 0 vem antes da distância.
    pares = casar_postes([_p("R1", 0.0, "A"), _p("R2", 0.02, "B")], [_p("Q", 0.015, "A")])
    assert _ids(pares) == [("R1", "Q")]


def test_guloso_empate_de_distancia_desempata_por_id_da_referencia() -> None:
    pares = casar_postes([_p("B", 0.0), _p("A", 0.02)], [_p("Q", 0.01)])
    assert _ids(pares) == [("A", "Q")]


def test_guloso_empate_de_distancia_desempata_por_id_da_predicao() -> None:
    pares = casar_postes([_p("R", 0.01)], [_p("Z", 0.0), _p("Y", 0.02)])
    assert _ids(pares) == [("R", "Y")]


def test_guloso_e_um_para_um_e_ordenado_por_id_de_referencia() -> None:
    pares = casar_postes(
        [_p("R2", 0.5), _p("R1", 0.1)],
        [_p("Q1", 0.1), _p("Q2", 0.5), _p("Q3", 0.505)],
    )
    assert _ids(pares) == [("R1", "Q1"), ("R2", "Q2")]


def test_guloso_nao_e_otimo_documentado_r4() -> None:
    # R1 (x=0) e R2 (x=0.02); Q1 em 0.015 e Q2 em -: só Q1 existe. O guloso dá Q1 a R2 (0.005).
    # Se houvesse otimização global por soma de distâncias o resultado seria o mesmo; o objetivo é
    # travar que a escolha é por menor distância individual, não por ordem de entrada.
    entrada = casar_postes([_p("R1", 0.0), _p("R2", 0.02)], [_p("Q1", 0.015)])
    invertida = casar_postes([_p("R2", 0.02), _p("R1", 0.0)], [_p("Q1", 0.015)])
    assert _ids(entrada) == _ids(invertida) == [("R2", "Q1")]


# --- campos: R5, normalização, coordenada --------------------------------------------------------


def _par_unico(ref: dict[str, Any], pred: dict[str, Any]) -> dict[str, Any]:
    return avaliar(_ficha([ref]), _pred([pred]))


def test_campos_numeros_exatos_em_tres_pares() -> None:
    ref_ok = _poste("P1", 0.1, nome="1")
    ref_errado = _poste("P2", 0.3, nome="2")
    ref_nulo = _poste("P3", 0.5, nome="7")
    pred_ok = copy.deepcopy(ref_ok) | {"id": "Q1"}
    pred_errado = _poste(
        "Q2",
        0.3,
        nome="9",
        estruturas=["X1"],
        poste="OUTRO",
        coordenada={"leste": 1.0, "norte": 2.0, "zona": "23K"},
    )
    pred_nulo = _poste("Q3", 0.5, nome=None)
    relatorio = avaliar(
        _ficha([ref_ok, ref_errado, ref_nulo]), _pred([pred_ok, pred_errado, pred_nulo])
    )
    campos = relatorio["campos"]
    assert campos["identificador"] == {
        "acertos": 1,
        "total": 3,
        "taxa": 1 / 3,
        "erros_com_pendencia": 0,
        "erros_sem_pendencia": 2,
    }
    for campo in ("estruturas", "poste", "coordenada"):
        assert campos[campo] == {
            "acertos": 2,
            "total": 3,
            "taxa": 2 / 3,
            "erros_com_pendencia": 0,
            "erros_sem_pendencia": 1,
        }
    assert [par["campos"]["identificador"] for par in relatorio["pares"]] == [True, False, False]


def test_textos_normalizados_acertam_com_caixa_e_espacos_diferentes() -> None:
    ref = _poste("P1", 0.1, nome="  p  1 ", poste=" dt   11/300", estruturas=["n1", "M1 "])
    pred = _poste("Q1", 0.1, nome="P 1", poste="DT 11/300", estruturas=["m1", "N1"])
    campos = _par_unico(ref, pred)["campos"]
    for campo in ("identificador", "estruturas", "poste"):
        assert (campos[campo]["acertos"], campos[campo]["total"]) == (1, 1), campo


def test_estruturas_em_ordem_diferente_acertam() -> None:
    ref = _poste("P1", 0.1, estruturas=["A", "B", "C"])
    pred = _poste("Q1", 0.1, estruturas=["C", "A", "B"])
    assert _par_unico(ref, pred)["campos"]["estruturas"]["acertos"] == 1


@pytest.mark.parametrize(
    ("ref_estruturas", "pred_estruturas"),
    [(["A", "B"], ["A"]), (["A"], ["A", "B"]), ([], ["A"]), (["A"], []), (["A", "B"], ["A", "C"])],
)
def test_estruturas_com_conteudo_diferente_erram(
    ref_estruturas: list[str], pred_estruturas: list[str]
) -> None:
    campo = _par_unico(
        _poste("P1", 0.1, estruturas=ref_estruturas), _poste("Q1", 0.1, estruturas=pred_estruturas)
    )["campos"]["estruturas"]
    assert (campo["acertos"], campo["total"], campo["erros_sem_pendencia"]) == (0, 1, 1)


def test_estruturas_vazias_nos_dois_lados_acertam() -> None:
    campo = _par_unico(_poste("P1", 0.1, estruturas=[]), _poste("Q1", 0.1, estruturas=[]))
    assert (campo["campos"]["estruturas"]["acertos"], campo["campos"]["estruturas"]["total"]) == (
        1,
        1,
    )


def _texto(chave: str, valor: str | None) -> dict[str, Any]:
    return {chave: valor}


@pytest.mark.parametrize("campo", ["identificador", "poste"])
def test_nulo_na_referencia_e_predicao_inventada_conta_erro(campo: str) -> None:
    chave = "nome" if campo == "identificador" else "poste"
    ref = _poste("P1", 0.1, **_texto(chave, None))
    pred = _poste("Q1", 0.1, **_texto(chave, "P9"))
    bloco = _par_unico(ref, pred)["campos"][campo]
    assert (bloco["acertos"], bloco["total"], bloco["erros_sem_pendencia"]) == (0, 1, 1)


@pytest.mark.parametrize("campo", ["identificador", "poste"])
def test_nulo_nos_dois_lados_acerta_e_texto_na_ref_com_nulo_na_predicao_erra(campo: str) -> None:
    chave = "nome" if campo == "identificador" else "poste"
    nulo = _par_unico(
        _poste("P1", 0.1, **_texto(chave, None)), _poste("Q1", 0.1, **_texto(chave, None))
    )
    assert (nulo["campos"][campo]["acertos"], nulo["campos"][campo]["total"]) == (1, 1)
    omitido = _par_unico(
        _poste("P1", 0.1, **_texto(chave, "P9")), _poste("Q1", 0.1, **_texto(chave, None))
    )
    bloco = omitido["campos"][campo]
    assert (bloco["acertos"], bloco["total"], bloco["erros_sem_pendencia"]) == (0, 1, 1)


def _coordenada(leste: float, norte: float, zona: str | None = "23K") -> dict[str, Any]:
    return {"leste": leste, "norte": norte, "zona": zona}


L0, N0 = 700000.0, 7800000.0


@pytest.mark.parametrize(
    ("pred_coordenada", "acerta"),
    [
        (_coordenada(L0 + 0.01, N0), True),
        (_coordenada(L0 - 0.01, N0), True),
        (_coordenada(L0, N0 + 0.01), True),
        (_coordenada(L0, N0 - 0.01), True),
        (_coordenada(L0 + 0.01, N0 + 0.01), True),
        (_coordenada(L0, N0, "22J"), True),
        (_coordenada(L0, N0, None), True),
        (_coordenada(L0 + 0.0100001, N0), False),
        (_coordenada(L0 - 0.0100001, N0), False),
        (_coordenada(L0, N0 + 0.0100001), False),
        (_coordenada(L0, N0 - 0.0100001), False),
        (_coordenada(L0 + 0.02, N0 + 0.02), False),
        (_coordenada(L0 + 0.5, N0), False),
    ],
)
def test_coordenada_na_tolerancia_de_um_centimetro(
    pred_coordenada: dict[str, Any], acerta: bool
) -> None:
    ref = _poste("P1", 0.1, coordenada=_coordenada(L0, N0))
    bloco = _par_unico(ref, _poste("Q1", 0.1, coordenada=pred_coordenada))["campos"]["coordenada"]
    assert (bloco["acertos"], bloco["total"]) == (int(acerta), 1)
    assert bloco["erros_sem_pendencia"] == int(not acerta)


def test_coordenada_nula_nos_dois_lados_acerta() -> None:
    ref, pred = _poste("P1", 0.1), _poste("Q1", 0.1)
    ref["coordenada"] = None
    pred["coordenada"] = None
    bloco = _par_unico(ref, pred)["campos"]["coordenada"]
    assert (bloco["acertos"], bloco["total"], bloco["erros_sem_pendencia"]) == (1, 1, 0)


def test_coordenada_nula_so_na_referencia_ou_so_na_predicao_erra() -> None:
    ref, pred = _poste("P1", 0.1), _poste("Q1", 0.1)
    ref["coordenada"] = None
    inventada = _par_unico(ref, pred)["campos"]["coordenada"]
    assert (inventada["acertos"], inventada["total"], inventada["erros_sem_pendencia"]) == (0, 1, 1)
    ref2, pred2 = _poste("P1", 0.1), _poste("Q1", 0.1)
    pred2["coordenada"] = None
    omitida = _par_unico(ref2, pred2)["campos"]["coordenada"]
    assert (omitida["acertos"], omitida["total"], omitida["erros_sem_pendencia"]) == (0, 1, 1)


_ERRADO: dict[str, dict[str, Any]] = {
    "identificador": {"nome": "ZZ"},
    "estruturas": {"estruturas": ["ZZ"]},
    "poste": {"poste": "ZZ"},
    "coordenada": {"coordenada": _coordenada(1.0, 2.0)},
}
_CAMPOS = ["identificador", "estruturas", "poste", "coordenada"]


def _todos_errados(**extra: Any) -> dict[str, Any]:
    atributos: dict[str, Any] = {}
    for valores in _ERRADO.values():
        atributos |= valores
    return _poste("Q1", 0.1, **atributos, **extra)


@pytest.mark.parametrize("pendente", _CAMPOS)
def test_campo_pendente_na_referencia_sai_so_do_proprio_denominador(pendente: str) -> None:
    ref = _poste("P1", 0.1, pendentes=[pendente])
    relatorio = _par_unico(ref, _todos_errados())
    for campo in _CAMPOS:
        bloco = relatorio["campos"][campo]
        if campo == pendente:
            assert bloco == {
                "acertos": 0,
                "total": 0,
                "taxa": None,
                "erros_com_pendencia": 0,
                "erros_sem_pendencia": 0,
            }
            assert relatorio["pares"][0]["campos"][campo] is None
        else:
            assert (bloco["acertos"], bloco["total"], bloco["erros_sem_pendencia"]) == (0, 1, 1)
            assert relatorio["pares"][0]["campos"][campo] is False


@pytest.mark.parametrize("pendente", _CAMPOS)
def test_campo_pendente_na_predicao_classifica_o_erro_e_continua_no_denominador(
    pendente: str,
) -> None:
    relatorio = _par_unico(_poste("P1", 0.1), _todos_errados(pendentes=[pendente]))
    for campo in _CAMPOS:
        bloco = relatorio["campos"][campo]
        assert (bloco["acertos"], bloco["total"]) == (0, 1)
        assert bloco["erros_com_pendencia"] == int(campo == pendente), campo
        assert bloco["erros_sem_pendencia"] == int(campo != pendente), campo


@pytest.mark.parametrize("pendente", _CAMPOS)
def test_campo_pendente_na_predicao_mas_certo_nao_gera_erro(pendente: str) -> None:
    relatorio = _par_unico(_poste("P1", 0.1), _poste("Q1", 0.1, pendentes=[pendente]))
    bloco = relatorio["campos"][pendente]
    assert (bloco["acertos"], bloco["total"]) == (1, 1)
    assert (bloco["erros_com_pendencia"], bloco["erros_sem_pendencia"]) == (0, 0)


@pytest.mark.parametrize("pendente", _CAMPOS)
def test_pendente_nos_dois_lados_nao_conta_em_lugar_nenhum(pendente: str) -> None:
    ref = _poste("P1", 0.1, pendentes=[pendente])
    bloco = _par_unico(ref, _todos_errados(pendentes=[pendente]))["campos"][pendente]
    assert (bloco["total"], bloco["erros_com_pendencia"], bloco["erros_sem_pendencia"]) == (0, 0, 0)


# --- vãos ----------------------------------------------------------------------------------------


def _dois_postes() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return (
        [_poste("P1", 0.1), _poste("P2", 0.3)],
        [_poste("Q1", 0.1), _poste("Q2", 0.3)],
    )


def test_vao_com_de_e_para_trocados_casa() -> None:
    ref, pred = _dois_postes()
    vaos = avaliar(_ficha(ref, [_vao("P1", "P2")]), _pred(pred, [_vao("Q2", "Q1")]))["vaos"]
    assert (vaos["tp"], vaos["fp"], vaos["fn"]) == (1, 0, 0)
    assert vaos["comprimento"]["acertos"] == 1
    assert vaos["cabo"]["acertos"] == 1


def test_tres_vaos_no_mesmo_par_casam_um_a_um_por_cabo() -> None:
    ref, pred = _dois_postes()
    vaos_ref = [
        _vao("P1", "P2", 10.0, "MT"),
        _vao("P1", "P2", 20.0, "BT"),
        _vao("P2", "P1", 30.0, None),
    ]
    vaos_pred = [
        _vao("Q2", "Q1", 30.0, None),
        _vao("Q1", "Q2", 20.0, "MT"),
        _vao("Q2", "Q1", 10.0, "BT"),
    ]
    vaos = avaliar(_ficha(ref, vaos_ref), _pred(pred, vaos_pred))["vaos"]
    assert (vaos["tp"], vaos["fp"], vaos["fn"]) == (3, 0, 0)
    assert vaos["cabo"] == {
        "acertos": 3,
        "total": 3,
        "taxa": 1.0,
        "erros_com_pendencia": 0,
        "erros_sem_pendencia": 0,
    }
    assert (vaos["comprimento"]["acertos"], vaos["comprimento"]["total"]) == (1, 3)
    assert vaos["comprimento"]["erros_sem_pendencia"] == 2


def test_tres_vaos_na_referencia_e_dois_na_predicao_deixam_um_fn() -> None:
    ref, pred = _dois_postes()
    vaos_ref = [
        _vao("P1", "P2", 10.0, "MT"),
        _vao("P1", "P2", 20.0, "BT"),
        _vao("P1", "P2", 5.0, "AT"),
    ]
    vaos_pred = [_vao("Q1", "Q2", 10.0, "MT"), _vao("Q1", "Q2", 20.0, "BT")]
    vaos = avaliar(_ficha(ref, vaos_ref), _pred(pred, vaos_pred))["vaos"]
    assert (vaos["tp"], vaos["fp"], vaos["fn"]) == (2, 0, 1)
    assert vaos["cabo"]["total"] == 2
    assert vaos["cabo"]["acertos"] == 2
    assert vaos["precisao"] == 1.0
    assert vaos["recall"] == pytest.approx(2 / 3)


def test_comprimento_nulo_ordena_por_ultimo_quando_so_um_lado_tem_nulo() -> None:
    ref, pred = _dois_postes()
    # Predição com [None, 30]: o 30 da referência tem de pegar o 30 (None é o último, sobra FP).
    sobra_pred = avaliar(
        _ficha(ref, [_vao("P1", "P2", 30.0, None)]),
        _pred(pred, [_vao("Q1", "Q2", None, None), _vao("Q1", "Q2", 30.0, None)]),
    )["vaos"]
    assert (sobra_pred["tp"], sobra_pred["fp"], sobra_pred["fn"]) == (1, 1, 0)
    assert (sobra_pred["comprimento"]["acertos"], sobra_pred["comprimento"]["total"]) == (1, 1)
    # Referência com [None, 30]: o 30 pega o 30 da predição, e o None da referência é FN.
    sobra_ref = avaliar(
        _ficha(ref, [_vao("P1", "P2", None, None), _vao("P1", "P2", 30.0, None)]),
        _pred(pred, [_vao("Q1", "Q2", 30.0, None)]),
    )["vaos"]
    assert (sobra_ref["tp"], sobra_ref["fp"], sobra_ref["fn"]) == (1, 0, 1)
    assert (sobra_ref["comprimento"]["acertos"], sobra_ref["comprimento"]["total"]) == (1, 1)


def test_vaos_restantes_casam_em_ordem_de_comprimento_e_nulo_por_ultimo() -> None:
    ref, pred = _dois_postes()
    # Sem cabo em nenhum: o par é por ordem de comprimento (None por último), não de entrada.
    vaos_ref = [
        _vao("P1", "P2", None, None),
        _vao("P1", "P2", 50.0, None),
        _vao("P1", "P2", 30.0, None),
    ]
    vaos_pred = [
        _vao("Q1", "Q2", 50.05, None),
        _vao("Q1", "Q2", None, None),
        _vao("Q1", "Q2", 29.95, None),
    ]
    vaos = avaliar(_ficha(ref, vaos_ref), _pred(pred, vaos_pred))["vaos"]
    assert vaos["tp"] == 3
    assert vaos["comprimento"]["acertos"] == 3
    assert vaos["comprimento"]["erros_sem_pendencia"] == 0


def test_cabo_da_referencia_nulo_com_cabo_na_predicao_casa_no_resto_e_erra_o_cabo() -> None:
    ref, pred = _dois_postes()
    vaos = avaliar(
        _ficha(ref, [_vao("P1", "P2", 40.0, None)]), _pred(pred, [_vao("Q1", "Q2", 40.0, "MT")])
    )["vaos"]
    assert vaos["tp"] == 1
    assert vaos["cabo"] == {
        "acertos": 0,
        "total": 1,
        "taxa": 0.0,
        "erros_com_pendencia": 0,
        "erros_sem_pendencia": 1,
    }


def test_cabo_normalizado_casa_com_caixa_e_espacos_diferentes() -> None:
    ref, pred = _dois_postes()
    vaos = avaliar(
        _ficha(ref, [_vao("P1", "P2", 40.0, " cabo  mt ")]),
        _pred(pred, [_vao("Q1", "Q2", 40.0, "CABO MT")]),
    )["vaos"]
    assert vaos["cabo"]["acertos"] == 1


def test_vao_cujo_par_de_postes_nao_casou_e_fn_e_o_da_predicao_e_fp() -> None:
    ref = [_poste("P1", 0.1), _poste("P2", 0.3)]
    pred = [_poste("Q1", 0.1), _poste("Q2", 0.9)]  # Q2 está longe de P2
    relatorio = avaliar(_ficha(ref, [_vao("P1", "P2")]), _pred(pred, [_vao("Q1", "Q2")]))
    postes, vaos = relatorio["postes"], relatorio["vaos"]
    assert (postes["tp"], postes["fp"], postes["fn"]) == (1, 1, 1)
    assert (vaos["tp"], vaos["fp"], vaos["fn"]) == (0, 1, 1)
    assert vaos["comprimento"]["total"] == 0
    assert vaos["cabo"]["total"] == 0
    assert vaos["precisao"] == 0.0
    assert vaos["recall"] == 0.0


@pytest.mark.parametrize(
    ("ref_c", "pred_c", "acerta"),
    [
        (40.0, 40.1, True),
        (40.0, 39.9, True),
        (40.0, 40.1000001, False),
        (40.0, 39.8999999, False),
        (None, None, True),
        (None, 40.0, False),
        (40.0, None, False),
    ],
)
def test_comprimento_na_tolerancia_de_um_decimetro(
    ref_c: float | None, pred_c: float | None, acerta: bool
) -> None:
    ref, pred = _dois_postes()
    bloco = avaliar(
        _ficha(ref, [_vao("P1", "P2", ref_c)]), _pred(pred, [_vao("Q1", "Q2", pred_c)])
    )["vaos"]["comprimento"]
    assert (bloco["acertos"], bloco["total"]) == (int(acerta), 1)
    assert bloco["erros_sem_pendencia"] == int(not acerta)


def test_comprimento_e_cabo_pendentes_na_referencia_saem_do_denominador() -> None:
    ref, pred = _dois_postes()
    vaos = avaliar(
        _ficha(ref, [_vao("P1", "P2", 40.0, "MT", pendentes=["comprimento_m"])]),
        _pred(pred, [_vao("Q1", "Q2", 99.0, "MT")]),
    )["vaos"]
    assert vaos["tp"] == 1
    assert (vaos["comprimento"]["total"], vaos["comprimento"]["taxa"]) == (0, None)
    assert (vaos["cabo"]["acertos"], vaos["cabo"]["total"]) == (1, 1)
    vaos = avaliar(
        _ficha(ref, [_vao("P1", "P2", 40.0, "MT", pendentes=["cabo"])]),
        _pred(pred, [_vao("Q1", "Q2", 99.0, "BT")]),
    )["vaos"]
    assert (vaos["cabo"]["total"], vaos["cabo"]["taxa"]) == (0, None)
    assert (vaos["comprimento"]["acertos"], vaos["comprimento"]["total"]) == (0, 1)


def test_erro_em_vao_pendente_na_predicao_conta_a_parte() -> None:
    ref, pred = _dois_postes()
    vaos = avaliar(
        _ficha(ref, [_vao("P1", "P2", 40.0, "MT")]),
        _pred(pred, [_vao("Q1", "Q2", 99.0, "BT", pendentes=["comprimento_m"])]),
    )["vaos"]
    assert (
        vaos["comprimento"]["erros_com_pendencia"],
        vaos["comprimento"]["erros_sem_pendencia"],
    ) == (1, 0)
    assert (vaos["cabo"]["erros_com_pendencia"], vaos["cabo"]["erros_sem_pendencia"]) == (0, 1)
    vaos = avaliar(
        _ficha(ref, [_vao("P1", "P2", 40.0, "MT")]),
        _pred(pred, [_vao("Q1", "Q2", 99.0, "BT", pendentes=["cabo"])]),
    )["vaos"]
    assert (vaos["cabo"]["erros_com_pendencia"], vaos["cabo"]["erros_sem_pendencia"]) == (1, 0)
    assert (
        vaos["comprimento"]["erros_com_pendencia"],
        vaos["comprimento"]["erros_sem_pendencia"],
    ) == (0, 1)


# --- taxas: fp e fn não podem se confundir -------------------------------------------------------


def _com_extra(extra_na_predicao: bool) -> dict[str, Any]:
    base_ref = [
        _poste("P1", 0.1, simbolos=[_simbolo("S1", _caixa(2, 2, 6, 6))]),
        _poste("P2", 0.3, simbolos=[_simbolo("S2", _caixa(10, 2, 14, 6))]),
    ]
    base_pred = [
        _poste("Q1", 0.1, simbolos=[_simbolo("QS1", _caixa(2, 2, 6, 6))]),
        _poste("Q2", 0.3, simbolos=[_simbolo("QS2", _caixa(10, 2, 14, 6))]),
    ]
    extra = [_poste("X3", 0.7, simbolos=[_simbolo("XS3", _caixa(20, 2, 24, 6))])]
    vao_extra = [_vao("X3", "Q2" if extra_na_predicao else "P2")]
    vao_base_ref, vao_base_pred = [_vao("P1", "P2")], [_vao("Q1", "Q2")]
    if extra_na_predicao:
        return avaliar(
            _ficha(base_ref, vao_base_ref), _pred(base_pred + extra, vao_base_pred + vao_extra)
        )
    return avaliar(
        _ficha(base_ref + extra, vao_base_ref + vao_extra), _pred(base_pred, vao_base_pred)
    )


def test_extra_na_predicao_derruba_precisao_e_nao_o_recall() -> None:
    r = _com_extra(extra_na_predicao=True)
    assert (r["postes"]["tp"], r["postes"]["fp"], r["postes"]["fn"]) == (2, 1, 0)
    assert r["postes"]["precisao"] == pytest.approx(2 / 3)
    assert r["postes"]["recall"] == 1.0
    assert (r["vaos"]["tp"], r["vaos"]["fp"], r["vaos"]["fn"]) == (1, 1, 0)
    assert r["vaos"]["precisao"] == 0.5
    assert r["vaos"]["recall"] == 1.0
    assert (r["simbolos"]["tp"], r["simbolos"]["fp"], r["simbolos"]["fn"]) == (2, 1, 0)
    assert r["simbolos"]["precisao"] == pytest.approx(2 / 3)
    assert r["simbolos"]["recall"] == 1.0
    assert r["nao_casados"] == {"referencia": [], "predicao": ["X3"]}
    assert r["simbolos_nao_casados"] == {"referencia": [], "predicao": ["XS3"]}


def test_extra_na_referencia_derruba_recall_e_nao_a_precisao() -> None:
    r = _com_extra(extra_na_predicao=False)
    assert (r["postes"]["tp"], r["postes"]["fp"], r["postes"]["fn"]) == (2, 0, 1)
    assert r["postes"]["precisao"] == 1.0
    assert r["postes"]["recall"] == pytest.approx(2 / 3)
    assert (r["vaos"]["tp"], r["vaos"]["fp"], r["vaos"]["fn"]) == (1, 0, 1)
    assert r["vaos"]["precisao"] == 1.0
    assert r["vaos"]["recall"] == 0.5
    assert (r["simbolos"]["tp"], r["simbolos"]["fp"], r["simbolos"]["fn"]) == (2, 0, 1)
    assert r["simbolos"]["precisao"] == 1.0
    assert r["simbolos"]["recall"] == pytest.approx(2 / 3)
    assert r["nao_casados"] == {"referencia": ["X3"], "predicao": []}
    assert r["simbolos_nao_casados"] == {"referencia": ["XS3"], "predicao": []}


# --- símbolos ------------------------------------------------------------------------------------


def _simbolos(ref: list[dict[str, Any]], pred: list[dict[str, Any]]) -> dict[str, Any]:
    relatorio = avaliar(
        _ficha([_poste("P1", 0.1, simbolos=ref)]), _pred([_poste("Q1", 0.1, simbolos=pred)])
    )
    return relatorio


def test_simbolo_de_mesma_classe_sem_geometria_elegivel_e_fp_e_fn() -> None:
    r = _simbolos([_simbolo("S1", _caixa(2, 2, 6, 6))], [_simbolo("QS1", _caixa(20, 20, 24, 24))])
    assert (r["simbolos"]["tp"], r["simbolos"]["fp"], r["simbolos"]["fn"]) == (0, 1, 1)
    assert r["simbolos"]["precisao"] == 0.0
    assert r["simbolos"]["recall"] == 0.0
    assert r["simbolos_nao_casados"] == {"referencia": ["S1"], "predicao": ["QS1"]}


def test_simbolo_com_mesma_geometria_e_classe_diferente_nao_casa() -> None:
    r = _simbolos(
        [_simbolo("S1", _caixa(2, 2, 6, 6), "ESTAI")],
        [_simbolo("QS1", _caixa(2, 2, 6, 6), "ATERRAMENTO")],
    )
    assert (r["simbolos"]["tp"], r["simbolos"]["fp"], r["simbolos"]["fn"]) == (0, 1, 1)


def test_simbolo_de_classes_diferentes_casam_cada_um_com_a_sua() -> None:
    r = _simbolos(
        [
            _simbolo("S1", _caixa(2, 2, 6, 6), "ESTAI"),
            _simbolo("S2", _caixa(2, 2, 6, 6), "ATERRAMENTO"),
        ],
        [
            _simbolo("QS1", _caixa(2, 2, 6, 6), "ATERRAMENTO"),
            _simbolo("QS2", _caixa(2, 2, 6, 6), "ESTAI"),
        ],
    )
    assert (r["simbolos"]["tp"], r["simbolos"]["fp"], r["simbolos"]["fn"]) == (2, 0, 0)


def test_simbolo_com_iou_exatamente_meio_e_elegivel_e_abaixo_nao() -> None:
    # 3x1 contra 3x1 deslocado de 1: interseção 2, união 4 -> IoU 0,5 exato.
    meio = _simbolos([_simbolo("S1", _caixa(4, 4, 7, 5))], [_simbolo("QS1", _caixa(5, 4, 8, 5))])
    assert meio["simbolos"]["tp"] == 1
    # deslocado de 1,25: interseção 1,75, união 4,25 -> IoU ~0,41.
    abaixo = _simbolos(
        [_simbolo("S1", _caixa(4, 4, 7, 5))], [_simbolo("QS1", _caixa(5.25, 4, 8.25, 5))]
    )
    assert (abaixo["simbolos"]["tp"], abaixo["simbolos"]["fp"], abaixo["simbolos"]["fn"]) == (
        0,
        1,
        1,
    )


def test_simbolos_de_poste_nao_casado_contam_fp_e_fn_com_ids() -> None:
    ref = _ficha(
        [
            _poste("P1", 0.1, simbolos=[_simbolo("S1", _caixa(2, 2, 6, 6))]),
            _poste(
                "P2",
                0.5,
                simbolos=[_simbolo("S2", _caixa(2, 2, 6, 6)), _simbolo("S3", _caixa(8, 2, 12, 6))],
            ),
        ]
    )
    pred = _pred(
        [
            _poste("Q1", 0.1, simbolos=[_simbolo("QS1", _caixa(2, 2, 6, 6))]),
            _poste("Q9", 0.9, simbolos=[_simbolo("QS9", _caixa(2, 2, 6, 6))]),
        ]
    )
    r = avaliar(ref, pred)
    assert (r["simbolos"]["tp"], r["simbolos"]["fp"], r["simbolos"]["fn"]) == (1, 1, 2)
    assert r["simbolos_nao_casados"] == {"referencia": ["S2", "S3"], "predicao": ["QS9"]}
    assert r["nao_casados"] == {"referencia": ["P2"], "predicao": ["Q9"]}


def test_simbolos_pendentes_na_referencia_ficam_fora_do_par_dos_dois_lados() -> None:
    ref = _ficha(
        [_poste("P1", 0.1, simbolos=[_simbolo("S1", _caixa(2, 2, 6, 6))], pendentes=["simbolos"])]
    )
    pred = _pred(
        [
            _poste(
                "Q1",
                0.1,
                simbolos=[
                    _simbolo("QS1", _caixa(2, 2, 6, 6)),
                    _simbolo("QS2", _caixa(20, 2, 24, 6)),
                ],
            )
        ]
    )
    r = avaliar(ref, pred)
    assert (r["simbolos"]["tp"], r["simbolos"]["fp"], r["simbolos"]["fn"]) == (0, 0, 0)
    assert r["simbolos"]["precisao"] is None
    assert r["simbolos"]["recall"] is None
    assert r["simbolos_nao_casados"] == {"referencia": [], "predicao": []}


def test_simbolos_pendentes_na_referencia_nao_afetam_outros_pares() -> None:
    ref = _ficha(
        [
            _poste(
                "P1", 0.1, simbolos=[_simbolo("S1", _caixa(2, 2, 6, 6))], pendentes=["simbolos"]
            ),
            _poste("P2", 0.3, simbolos=[_simbolo("S2", _caixa(2, 2, 6, 6))]),
        ]
    )
    pred = _pred(
        [
            _poste("Q1", 0.1, simbolos=[_simbolo("QS1", _caixa(2, 2, 6, 6))]),
            _poste("Q2", 0.3, simbolos=[]),
        ]
    )
    r = avaliar(ref, pred)
    assert (r["simbolos"]["tp"], r["simbolos"]["fp"], r["simbolos"]["fn"]) == (0, 0, 1)
    assert r["simbolos_nao_casados"] == {"referencia": ["S2"], "predicao": []}


# --- cardinalidade máxima ------------------------------------------------------------------------

# A=[6,2,14,10], X igual a A (IoU 1,0). B=[7,2,15,10] só é elegível com X (0,78).
# Y=[4,2,12,10] é elegível com A (0,6) mas não com B (0,45). C=[2,2,10,10] só com Y (0,6).
A = _caixa(6, 2, 14, 10)
X = _caixa(6, 2, 14, 10)
B = _caixa(7, 2, 15, 10)
Y = _caixa(4, 2, 12, 10)
C = _caixa(2, 2, 10, 10)
Z = _caixa(20, 20, 24, 24)


@pytest.mark.parametrize("nomes", [("S1", "S2"), ("S2", "S1")])
def test_guloso_por_iou_erra_e_cardinalidade_maxima_acerta(nomes: tuple[str, str]) -> None:
    # Guloso por IoU: A-X (1,0) e B fica sem par (tp 1). O máximo é A-Y e B-X (tp 2).
    nome_a, nome_b = nomes
    r = _simbolos(
        [_simbolo(nome_a, A), _simbolo(nome_b, B)], [_simbolo("QX", X), _simbolo("QY", Y)]
    )
    assert (r["simbolos"]["tp"], r["simbolos"]["fp"], r["simbolos"]["fn"]) == (2, 0, 0)
    assert r["simbolos"]["precisao"] == 1.0
    assert r["simbolos"]["recall"] == 1.0
    assert r["simbolos_nao_casados"] == {"referencia": [], "predicao": []}


def _simbolos_do_caso_maximo() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return (
        [_simbolo("A", A), _simbolo("B", B), _simbolo("C", C)],
        [_simbolo("X", X), _simbolo("Y", Y), _simbolo("Z", Z)],
    )


def test_cardinalidade_maxima_com_tres_referencias_e_dois_candidatos() -> None:
    ref, pred = _simbolos_do_caso_maximo()
    r = _simbolos(ref, pred)
    # Candidatos: A{X,Y}, B{X}, C{Y}; Z sem candidato. O máximo é 2. Pelo brief (referências por id,
    # candidatos por -iou): A->X; B desloca A para Y; C não acha lugar.
    assert (r["simbolos"]["tp"], r["simbolos"]["fp"], r["simbolos"]["fn"]) == (2, 1, 1)
    assert r["simbolos_nao_casados"] == {"referencia": ["C"], "predicao": ["Z"]}


def test_resultado_dos_simbolos_nao_muda_com_permutacoes_das_listas() -> None:
    ref, pred = _simbolos_do_caso_maximo()
    base = _simbolos(ref, pred)
    for ordem_ref in itertools.permutations(ref):
        for ordem_pred in itertools.permutations(pred):
            assert _simbolos(list(ordem_ref), list(ordem_pred)) == base


def test_resultado_geral_nao_muda_com_permutacoes_de_postes_e_vaos() -> None:
    ref_postes = [
        _poste("P1", 0.1, simbolos=[_simbolo("S1", A)]),
        _poste("P2", 0.3, simbolos=[_simbolo("S2", B)]),
        _poste("P3", 0.5),
    ]
    ref_vaos = [
        _vao("P1", "P2", 40.0, "MT"),
        _vao("P1", "P2", 30.0, "BT"),
        _vao("P2", "P3", 20.0, None),
    ]
    pred_postes = [
        _poste("Q1", 0.1, simbolos=[_simbolo("QS1", X), _simbolo("QS2", Y)]),
        _poste("Q2", 0.3),
        _poste("Q3", 0.5),
    ]
    pred_vaos = [
        _vao("Q2", "Q1", 30.0, "BT"),
        _vao("Q1", "Q2", 41.0, "MT"),
        _vao("Q2", "Q3", 20.0, None),
    ]
    base = avaliar(_ficha(ref_postes, ref_vaos), _pred(pred_postes, pred_vaos))
    assert base["postes"]["tp"] == 3
    assert base["vaos"]["tp"] == 3
    for postes in itertools.permutations(ref_postes):
        for vaos in itertools.permutations(ref_vaos):
            assert avaliar(_ficha(list(postes), list(vaos)), _pred(pred_postes, pred_vaos)) == base
    for postes in itertools.permutations(pred_postes):
        for vaos in itertools.permutations(pred_vaos):
            assert avaliar(_ficha(ref_postes, ref_vaos), _pred(list(postes), list(vaos))) == base


# --- escopo regional -----------------------------------------------------------------------------

REGIAO = [{"pagina": 1, "bbox": [0.0, 0.0, 0.4, 0.4]}]


def test_regional_descarta_poste_fora_simbolos_e_vaos_que_o_tocam() -> None:
    ref = _ficha([_poste("P1", 0.1), _poste("P2", 0.3)], [_vao("P1", "P2")], regioes=REGIAO)
    pred = _pred(
        [
            _poste("Q1", 0.1),
            _poste("Q2", 0.3),
            _poste("Q3", 0.5, simbolos=[_simbolo("QS3", _caixa(2, 2, 6, 6))]),
        ],
        [_vao("Q1", "Q2"), _vao("Q2", "Q3")],
    )
    r = avaliar(ref, pred)
    assert r["escopo"] == "regional"
    assert (r["postes"]["tp"], r["postes"]["fp"], r["postes"]["fn"]) == (2, 0, 0)
    assert (r["vaos"]["tp"], r["vaos"]["fp"], r["vaos"]["fn"]) == (1, 0, 0)
    assert (r["simbolos"]["tp"], r["simbolos"]["fp"], r["simbolos"]["fn"]) == (0, 0, 0)
    assert r["nao_casados"] == {"referencia": [], "predicao": []}
    assert r["simbolos_nao_casados"] == {"referencia": [], "predicao": []}


def test_regional_poste_dentro_sem_par_continua_fp() -> None:
    ref = _ficha([_poste("P1", 0.1)], regioes=REGIAO)
    pred = _pred([_poste("Q1", 0.1), _poste("Q2", 0.3)])
    r = avaliar(ref, pred)
    assert (r["postes"]["tp"], r["postes"]["fp"], r["postes"]["fn"]) == (1, 1, 0)
    assert r["nao_casados"] == {"referencia": [], "predicao": ["Q2"]}


def test_regional_centro_na_borda_da_regiao_fica() -> None:
    ref = _ficha([_poste("P1", 0.4)], regioes=REGIAO)
    r = avaliar(ref, _pred([_poste("Q1", 0.4)]))
    assert r["postes"]["tp"] == 1


def test_regional_regiao_de_outra_pagina_nao_protege_poste_predito() -> None:
    ref = _ficha([_poste("P1", 0.1)], regioes=REGIAO)
    # Mesmas coordenadas da região, mas na página 2: fora do escopo, descartado (nem FP).
    pred = _pred([_poste("Q1", 0.1), _poste("Q2", 0.2, pagina=2)])
    r = avaliar(ref, pred)
    assert (r["postes"]["tp"], r["postes"]["fp"], r["postes"]["fn"]) == (1, 0, 0)
    assert r["nao_casados"]["predicao"] == []


def test_regional_poste_fora_da_regiao_em_y_e_descartado() -> None:
    ref = _ficha([_poste("P1", 0.1)], regioes=REGIAO)
    pred = _pred([_poste("Q1", 0.1), _poste("Q2", 0.1, y=0.6)])
    r = avaliar(ref, pred)
    assert (r["postes"]["tp"], r["postes"]["fp"]) == (1, 0)


def test_completo_nao_descarta_nada() -> None:
    ref = _ficha([_poste("P1", 0.1)])
    r = avaliar(ref, _pred([_poste("Q1", 0.1), _poste("Q2", 0.9)]))
    assert (r["postes"]["tp"], r["postes"]["fp"]) == (1, 1)
    assert r["escopo"] == "completo"


# --- relatório -----------------------------------------------------------------------------------


def test_gerador_da_predicao_e_copiado_integralmente() -> None:
    gerador = {"versao_extracao": "v7", "modelo": {"nome": "m", "pesos": [1, 2]}, "nota": None}
    ref = _ficha([_poste("P1", 0.1)])
    pred = _ficha([_poste("Q1", 0.1)], tipo="predicao", gerador=gerador)
    assert avaliar(ref, pred)["gerador_predicao"] == gerador


def test_atributos_extras_de_poste_ficha_nao_mudam_nada() -> None:
    ref = _ficha([_poste("P1", 0.1)])
    pred = _pred([_poste("Q1", 0.1)])
    base = avaliar(ref, pred)
    ref["atributos_extras"] = {"qualquer": [1, 2, 3]}
    pred["atributos_extras"] = {"outro": "x"}
    assert avaliar(ref, pred) == base


def test_pdf_diferente_e_recusado_com_mensagem_sobre_o_hash() -> None:
    ref = _ficha([_poste("P1", 0.1)])
    pred = _pred([_poste("Q1", 0.1)])
    pred["pdf_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="pdf_sha256"):
        avaliar(ref, pred)


def test_predicao_invalida_e_recusada_com_prefixo() -> None:
    ref = _ficha([_poste("P1", 0.1)])
    pred = _pred([_poste("Q1", 0.1)])
    del pred["gerador"]
    with pytest.raises(ValueError, match="predicao:"):
        avaliar(ref, pred)


def test_referencia_com_tipo_predicao_e_predicao_com_tipo_referencia_sao_recusadas() -> None:
    with pytest.raises(ValueError, match="referencia"):
        avaliar(_pred([_poste("P1", 0.1)]), _pred([_poste("Q1", 0.1)]))
    with pytest.raises(ValueError, match="predicao"):
        avaliar(_ficha([_poste("P1", 0.1)]), _ficha([_poste("Q1", 0.1)]))


def test_denominadores_zero_dao_none_em_todo_o_relatorio() -> None:
    r = avaliar(_ficha([]), _pred([]))
    for bloco in (r["postes"], r["vaos"], r["simbolos"]):
        assert (bloco["tp"], bloco["fp"], bloco["fn"]) == (0, 0, 0)
        assert bloco["precisao"] is None
        assert bloco["recall"] is None
    for campo in r["campos"].values():
        assert (campo["acertos"], campo["total"], campo["taxa"]) == (0, 0, None)
    assert r["vaos"]["comprimento"]["taxa"] is None
    assert r["vaos"]["cabo"]["taxa"] is None
    assert r["pares"] == []


def test_so_predicao_vazia_da_recall_zero_e_precisao_none() -> None:
    r = avaliar(_ficha([_poste("P1", 0.1)]), _pred([]))
    assert r["postes"]["precisao"] is None
    assert r["postes"]["recall"] == 0.0


# --- rodada 2: vãos empatados com pendências distintas e tolerância sem ruído de float -----------


def _relatorios_em_todas_as_ordens(
    vaos_ref: list[dict[str, Any]], vaos_pred: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    ref, pred = _dois_postes()
    relatorios = []
    for ordem_ref in itertools.permutations(vaos_ref):
        for ordem_pred in itertools.permutations(vaos_pred):
            relatorios.append(
                avaliar(
                    _ficha(ref, copy.deepcopy(list(ordem_ref))),
                    _pred(pred, copy.deepcopy(list(ordem_pred))),
                )
            )
    return relatorios


def test_tres_vaos_empatados_com_pendencias_distintas_em_toda_ordem_dao_o_mesmo_relatorio() -> None:
    # Os três vãos de cada lado só diferem em `pendentes`; ordem canônica (pendentes ordenadas):
    # (), (cabo, comp), (comp). Pareamento por posto: R0-Q0 (comprimento errado, sem pendência),
    # R1-Q1 e R2-Q2 (comprimento pendente na referência).
    refs = [
        _vao("P1", "P2", 40.0, "MT", pendentes=[]),
        _vao("P1", "P2", 40.0, "MT", pendentes=["comprimento_m"]),
        _vao("P1", "P2", 40.0, "MT", pendentes=["comprimento_m", "cabo"]),
    ]
    preds = [
        _vao("Q1", "Q2", 50.0, "MT", pendentes=[]),
        _vao("Q1", "Q2", 50.0, "MT", pendentes=["comprimento_m"]),
        _vao("Q1", "Q2", 50.0, "MT", pendentes=["cabo", "comprimento_m"]),
    ]
    relatorios = _relatorios_em_todas_as_ordens(refs, preds)
    assert len(relatorios) == 36
    assert all(relatorio == relatorios[0] for relatorio in relatorios)
    vaos = relatorios[0]["vaos"]
    assert (vaos["tp"], vaos["fp"], vaos["fn"]) == (3, 0, 0)
    comp = vaos["comprimento"]
    assert (comp["acertos"], comp["total"]) == (0, 1)
    assert (comp["erros_com_pendencia"], comp["erros_sem_pendencia"]) == (0, 1)
    cabo = vaos["cabo"]
    assert (cabo["acertos"], cabo["total"]) == (2, 2)


def test_vaos_empatados_pendencia_so_na_predicao_em_toda_ordem_dao_o_mesmo_relatorio() -> None:
    # Ordem canônica: refs [], [cabo]; preds [], [comp]. Pares: ref [] com pred [] (erro de
    # comprimento sem pendência) e ref [cabo] com pred [comp] (erro de comprimento com pendência).
    refs = [_vao("P1", "P2", 40.0, "MT"), _vao("P1", "P2", 40.0, "MT", pendentes=["cabo"])]
    preds = [
        _vao("Q1", "Q2", 99.0, "MT", pendentes=["comprimento_m"]),
        _vao("Q1", "Q2", 99.0, "MT", pendentes=[]),
    ]
    relatorios = _relatorios_em_todas_as_ordens(refs, preds)
    assert all(relatorio == relatorios[0] for relatorio in relatorios)
    comp = relatorios[0]["vaos"]["comprimento"]
    assert (comp["acertos"], comp["total"]) == (0, 2)
    assert (comp["erros_com_pendencia"], comp["erros_sem_pendencia"]) == (1, 1)
    cabo = relatorios[0]["vaos"]["cabo"]
    assert (cabo["acertos"], cabo["total"]) == (1, 1)


def test_vaos_empatados_pendencia_so_na_referencia_em_toda_ordem_dao_o_mesmo_relatorio() -> None:
    # Canônico: ref [] com pred [] e ref [comp] com pred [cabo]. Comprimento: só o primeiro conta
    # (40 = 40, acerto); cabo: os dois contam e acertam (o ref [comp] não anula o cabo).
    refs = [
        _vao("P1", "P2", 40.0, "MT", pendentes=["comprimento_m"]),
        _vao("P1", "P2", 40.0, "MT", pendentes=[]),
    ]
    preds = [_vao("Q1", "Q2", 40.0, "MT"), _vao("Q1", "Q2", 40.0, "MT", pendentes=["cabo"])]
    relatorios = _relatorios_em_todas_as_ordens(refs, preds)
    assert all(relatorio == relatorios[0] for relatorio in relatorios)
    vaos = relatorios[0]["vaos"]
    assert (vaos["comprimento"]["acertos"], vaos["comprimento"]["total"]) == (1, 1)
    assert (vaos["cabo"]["acertos"], vaos["cabo"]["total"]) == (2, 2)


def test_vaos_empatados_com_cabo_nulo_e_pendencias_distintas_independem_da_ordem() -> None:
    # Cabo nulo cai no pareamento por posto (sobras): a chave com `pendentes` fixa o posto.
    refs = [
        _vao("P1", "P2", 40.0, None, pendentes=["comprimento_m"]),
        _vao("P1", "P2", 40.0, None, pendentes=[]),
    ]
    preds = [
        _vao("Q1", "Q2", 41.0, None, pendentes=[]),
        _vao("Q1", "Q2", 41.0, None, pendentes=["comprimento_m"]),
    ]
    relatorios = _relatorios_em_todas_as_ordens(refs, preds)
    assert all(relatorio == relatorios[0] for relatorio in relatorios)
    comp = relatorios[0]["vaos"]["comprimento"]
    # canônico: ref [] com pred [] (41 contra 40, fora de 0,1: um erro sem pendência);
    # ref [comp] com pred [comp] fica fora da métrica.
    assert (comp["acertos"], comp["total"]) == (0, 1)
    assert (comp["erros_com_pendencia"], comp["erros_sem_pendencia"]) == (0, 1)


def test_pendentes_do_vao_entram_na_chave_como_conjunto_ordenado() -> None:
    # A mesma pendência escrita em ordens diferentes entre os lados não pode mudar o posto:
    # canônico (sorted): refs (cabo, comp), (comp); preds (cabo, comp), (comp).
    # Pares: R(cabo,comp)-Q(cabo,comp) fora da métrica; R(comp)-Q(comp): cabo errado, a predição
    # não marcou `cabo` como pendente, logo um erro sem pendência. Sem ordenar, o R(comp) casaria
    # com Q(cabo,comp) e o erro viraria "com pendência".
    refs = [
        _vao("P1", "P2", 40.0, "MT", pendentes=["comprimento_m", "cabo"]),
        _vao("P1", "P2", 40.0, "MT", pendentes=["comprimento_m"]),
    ]
    preds = [
        _vao("Q1", "Q2", 40.0, "BT", pendentes=["cabo", "comprimento_m"]),
        _vao("Q1", "Q2", 40.0, "BT", pendentes=["comprimento_m"]),
    ]
    relatorios = _relatorios_em_todas_as_ordens(refs, preds)
    assert all(relatorio == relatorios[0] for relatorio in relatorios)
    cabo = relatorios[0]["vaos"]["cabo"]
    assert (cabo["acertos"], cabo["total"]) == (0, 1)
    assert (cabo["erros_com_pendencia"], cabo["erros_sem_pendencia"]) == (0, 1)


def _acertos_coordenada(
    leste_ref: float, norte_ref: float, leste_pred: float, norte_pred: float
) -> int:
    referencia = _ficha(
        [_poste("P1", 0.1, coordenada={"leste": leste_ref, "norte": norte_ref, "zona": "23K"})]
    )
    predicao = _pred(
        [_poste("Q1", 0.1, coordenada={"leste": leste_pred, "norte": norte_pred, "zona": "23K"})]
    )
    return int(avaliar(referencia, predicao)["campos"]["coordenada"]["acertos"])


@pytest.mark.parametrize(
    ("ref", "pred", "esperado"),
    [
        (7800000.48, 7800000.47, 1),  # no limite: o float dá 0,01000000070...
        (7800000.47, 7800000.48, 1),
        (7800000.03, 7800000.02, 1),
        (7800000.07, 7800000.06, 1),
        (7800000.11, 7800000.10, 1),
        (7800000.48, 7800000.46, 0),  # 0,02 acima do limite
        (7800000.46, 7800000.48, 0),
        (7800000.49, 7800000.47, 0),
    ],
)
def test_tolerancia_de_coordenada_norte_utm_nos_dois_lados_do_limite(
    ref: float, pred: float, esperado: int
) -> None:
    assert _acertos_coordenada(700000.0, ref, 700000.0, pred) == esperado


@pytest.mark.parametrize(
    ("ref", "pred", "esperado"),
    [
        (700000.01, 700000.0, 1),
        (700000.0, 700000.01, 1),
        (700000.02, 700000.01, 1),
        (700000.02, 700000.0, 0),
        (700000.0, 700000.02, 0),
        # 1e-10 acima do limite: round(.., 9) engoliria; o valor escrito não.
        (700000.0100000001, 700000.0, 0),
        (700000.0, 700000.0100000001, 0),
    ],
)
def test_tolerancia_de_coordenada_leste_utm_nos_dois_lados_do_limite(
    ref: float, pred: float, esperado: int
) -> None:
    assert _acertos_coordenada(ref, 7800000.0, pred, 7800000.0) == esperado


def test_tolerancia_de_coordenada_exige_leste_e_norte_dentro_do_limite() -> None:
    assert _acertos_coordenada(700000.01, 7800000.48, 700000.0, 7800000.47) == 1
    assert _acertos_coordenada(700000.02, 7800000.48, 700000.0, 7800000.47) == 0
    assert _acertos_coordenada(700000.01, 7800000.48, 700000.0, 7800000.46) == 0


def test_tolerancia_de_coordenada_compara_o_valor_escrito_nao_o_ruido_de_float() -> None:
    # 0.1 + 0.2 escreve 0.30000000000000004: acima de 0.29 por 0,01000000000000004 (> 0,01).
    assert _acertos_coordenada(0.1 + 0.2, 7800000.0, 0.29, 7800000.0) == 0
    assert _acertos_coordenada(0.3, 7800000.0, 0.29, 7800000.0) == 1
    assert _acertos_coordenada(0.1 + 0.2, 7800000.0, 0.3, 7800000.0) == 1


def _acertos_comprimento(ref: float, pred: float) -> int:
    ref_postes, pred_postes = _dois_postes()
    relatorio = avaliar(
        _ficha(ref_postes, [_vao("P1", "P2", ref)]), _pred(pred_postes, [_vao("Q1", "Q2", pred)])
    )
    return int(relatorio["vaos"]["comprimento"]["acertos"])


@pytest.mark.parametrize(
    ("ref", "pred", "esperado"),
    [
        (7800000.2, 7800000.1, 1),  # discrimina Decimal de round(abs(a-b), 9): float dá 0,099999999
        (7800000.4, 7800000.3, 1),
        (7800000.7, 7800000.6, 1),
        (7800000.2, 7800000.09, 0),
        (7800000.09, 7800000.2, 0),
        (40.1, 40.0, 1),
        (40.0, 40.1, 1),
        (40.2, 40.0, 0),
        (40.0, 40.1000000001, 0),  # 1e-10 acima do limite
        (0.1 + 0.2, 0.2, 0),  # 0.30000000000000004 - 0.2 > 0,1 no valor escrito
        (0.3, 0.2, 1),
    ],
)
def test_tolerancia_de_comprimento_nos_dois_lados_do_limite(
    ref: float, pred: float, esperado: int
) -> None:
    assert _acertos_comprimento(ref, pred) == esperado


# ---------------------------------------------------------------------------------------------
# Onda final E02: o relatório não compartilha estado com o protocolo nem com a predição
# ---------------------------------------------------------------------------------------------


def _par_com_gerador_aninhado() -> tuple[dict[str, Any], dict[str, Any]]:
    from tests.unit.test_ficha_poste_avaliador import _acerto_total

    referencia, predicao = _acerto_total()
    predicao["gerador"] = {"versao_extracao": "v1", "aninhado": {"lista": [1, 2], "x": {"y": 1}}}
    return referencia, predicao


def test_mutar_dicionarios_aninhados_do_relatorio_nao_altera_protocolo_nem_entradas() -> None:
    from scripts.ficha_poste_avaliador import PROTOCOLO_FICHA

    referencia, predicao = _par_com_gerador_aninhado()
    protocolo_antes = copy.deepcopy(dict(PROTOCOLO_FICHA))
    referencia_antes = copy.deepcopy(referencia)
    predicao_antes = copy.deepcopy(predicao)

    relatorio = avaliar(referencia, predicao)
    relatorio["protocolo"]["inventario"] = "mutado"
    relatorio["protocolo"].clear()
    relatorio["gerador_predicao"]["aninhado"]["lista"].append(3)
    relatorio["gerador_predicao"]["aninhado"]["x"]["y"] = 99

    assert dict(PROTOCOLO_FICHA) == protocolo_antes
    assert referencia == referencia_antes
    assert predicao == predicao_antes


def test_duas_avaliacoes_seguidas_dao_o_mesmo_relatorio_mesmo_apos_mutar_a_primeira() -> None:
    referencia, predicao = _par_com_gerador_aninhado()
    primeiro = avaliar(referencia, predicao)
    esperado = copy.deepcopy(primeiro)
    primeiro["protocolo"]["distancia_max"] = 99.0
    primeiro["gerador_predicao"]["aninhado"]["x"]["y"] = 99
    segundo = avaliar(referencia, predicao)
    assert segundo == esperado
    assert segundo["protocolo"] is not primeiro["protocolo"]
    assert segundo["gerador_predicao"] is not primeiro["gerador_predicao"]


def test_mutar_o_protocolo_importado_nao_e_necessario_para_limiar_do_proximo_lote() -> None:
    from tests.unit.test_ficha_poste_avaliador import _acerto_total

    referencia, predicao = _acerto_total()
    for _ in range(3):
        relatorio = avaliar(referencia, predicao)
        assert relatorio["protocolo"]["distancia_max"] == 0.02
        relatorio["protocolo"]["distancia_max"] = 0.0
