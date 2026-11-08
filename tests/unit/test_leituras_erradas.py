"""Leitura errada afirmada: predição não casada sobre a referência de outra classe (R-E06.3.2-4)."""

from __future__ import annotations

from typing import Any

import scripts.simbolos_ficha_metricas as metricas

Dados = dict[str, Any]
TOL = metricas.TOLERANCIA_CENTRO


def _ref(classe: str, bbox: list[float], pagina: int = 1) -> Dados:
    return {"pagina": pagina, "classe": classe, "bbox": bbox}


def _pred(classe: str, bbox: list[float], pagina: int = 1) -> Dados:
    return {"pagina": pagina, "classe": classe, "bbox": bbox, "contexto": "drawing"}


def _em(x: float, y: float, meia: float = 0.01) -> list[float]:
    return [x - meia, y - meia, x + meia, y + meia]


def test_predicao_nao_casada_sobre_outra_classe_conta() -> None:
    referencias = [_ref("PARA_RAIOS_BT", _em(0.5, 0.5))]
    predicoes = [_pred("ATERRAMENTO", _em(0.5, 0.5))]

    itens = metricas.leituras_erradas(referencias, predicoes, set(), TOL)

    assert itens == [
        {
            "classe_predita": "ATERRAMENTO",
            "classe_referencia": "PARA_RAIOS_BT",
            "referencia_id": 0,
        }
    ]


def test_predicao_casada_nao_conta_mesmo_com_outra_referencia_encostada() -> None:
    referencias = [_ref("ATERRAMENTO", _em(0.5, 0.5)), _ref("PARA_RAIOS_MT", _em(0.51, 0.5))]
    predicoes = [_pred("ATERRAMENTO", _em(0.5, 0.5))]

    assert metricas.leituras_erradas(referencias, predicoes, {0}, TOL) == []


def test_predicao_longe_de_toda_referencia_nao_conta() -> None:
    referencias = [_ref("PARA_RAIOS_BT", _em(0.2, 0.2))]

    assert (
        metricas.leituras_erradas(referencias, [_pred("ATERRAMENTO", _em(0.8, 0.8))], set(), TOL)
        == []
    )


def test_referencia_da_mesma_classe_ou_de_outra_pagina_nao_conta() -> None:
    referencias = [_ref("ATERRAMENTO", _em(0.5, 0.5)), _ref("PARA_RAIOS_BT", _em(0.5, 0.5), 2)]

    assert (
        metricas.leituras_erradas(referencias, [_pred("ATERRAMENTO", _em(0.5, 0.5))], set(), TOL)
        == []
    )


def test_limite_da_tolerancia() -> None:
    referencias = [_ref("PARA_RAIOS_BT", [0.4, 0.4, 0.5, 0.5])]
    no_limite = _pred("ATERRAMENTO", _em(0.5 + 0.004, 0.45, 0.0))
    fora = _pred("ATERRAMENTO", _em(0.5 + 0.006, 0.45, 0.0))

    assert len(metricas.leituras_erradas(referencias, [no_limite], set(), TOL)) == 1
    assert metricas.leituras_erradas(referencias, [fora], set(), TOL) == []


def _ficha(simbolos: list[Dados]) -> Dados:
    return {
        "escopo_anotacao": {"tipo": "completo"},
        "postes": [
            {
                "pagina": s["pagina"],
                "bbox": s["bbox"],
                "pendentes": [],
                "simbolos": [{"classe": s["classe"], "bbox": s["bbox"]}],
            }
            for s in simbolos
        ],
    }


def test_avaliar_predicoes_grava_leituras_erradas() -> None:
    ficha = _ficha([_ref("PARA_RAIOS_BT", _em(0.5, 0.5))])
    classes = frozenset({"ATERRAMENTO", "PARA_RAIOS_BT"})

    bloco = metricas.avaliar_predicoes(ficha, [_pred("ATERRAMENTO", _em(0.5, 0.5))], classes)

    erradas = bloco["centro"]["leituras_erradas"]
    assert erradas["total"] == 1
    assert erradas["por_classe"] == {"ATERRAMENTO": 1}
    assert erradas["itens"][0]["classe_referencia"] == "PARA_RAIOS_BT"
    assert bloco["iou"]["leituras_erradas"]["total"] == 1


def test_chave_nova_nao_muda_contagens_existentes() -> None:
    ficha = _ficha([_ref("PARA_RAIOS_BT", _em(0.5, 0.5))])
    classes = frozenset({"ATERRAMENTO", "PARA_RAIOS_BT"})

    geral = metricas.avaliar_predicoes(ficha, [_pred("ATERRAMENTO", _em(0.5, 0.5))], classes)[
        "centro"
    ]["geral"]

    assert {k: geral[k] for k in ("tp", "fp", "fn")} == {"tp": 0, "fp": 1, "fn": 1}


def test_agregacao_soma_duas_folhas() -> None:
    classes = frozenset({"ATERRAMENTO", "PARA_RAIOS_BT"})
    ficha = _ficha([_ref("PARA_RAIOS_BT", _em(0.5, 0.5))])
    bloco = metricas.avaliar_predicoes(ficha, [_pred("ATERRAMENTO", _em(0.5, 0.5))], classes)
    folha = {"situacao": "ok", "metodos": {"m": {"situacao": "ok", **bloco}}}

    soma = metricas._agregar_folhas([folha, folha], ["m"])["m"]["centro"]["leituras_erradas"]

    assert soma["total"] == 2
    assert soma["por_classe"] == {"ATERRAMENTO": 2}
    assert len(soma["itens"]) == 2
