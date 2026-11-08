"""Ataque a leitura errada afirmada: coerência com FP, critérios, bordas e relatório."""

from __future__ import annotations

from typing import Any

import scripts.simbolos_ficha_metricas as metricas
import scripts.simbolos_ficha_relatorio as relatorio

Dados = dict[str, Any]
TOL = metricas.TOLERANCIA_CENTRO
CLASSES = frozenset({"ATERRAMENTO", "PARA_RAIOS_BT"})


def _ref(classe: str, bbox: list[float], pagina: int = 1) -> Dados:
    return {"pagina": pagina, "classe": classe, "bbox": bbox}


def _pred(classe: str, bbox: list[float], pagina: int = 1) -> Dados:
    return {"pagina": pagina, "classe": classe, "bbox": bbox, "contexto": "drawing"}


def _em(x: float, y: float, meia: float = 0.01) -> list[float]:
    return [x - meia, y - meia, x + meia, y + meia]


def _ficha(
    simbolos: list[Dados],
    pendentes: list[list[float]] | None = None,
    regioes: list[Dados] | None = None,
) -> Dados:
    postes: list[Dados] = [
        {
            "pagina": s["pagina"],
            "bbox": s["bbox"],
            "pendentes": [],
            "simbolos": [{"classe": s["classe"], "bbox": s["bbox"]}],
        }
        for s in simbolos
    ]
    postes += [
        {"pagina": 1, "bbox": caixa, "pendentes": ["simbolos"], "simbolos": []}
        for caixa in pendentes or []
    ]
    escopo: Dados = (
        {"tipo": "completo"} if regioes is None else {"tipo": "regional", "regioes": regioes}
    )
    return {"escopo_anotacao": escopo, "postes": postes}


def test_predicao_perto_de_poste_pendente_nao_e_fp_nem_leitura_errada() -> None:
    # Pendente a 0.03 do centro (dentro do raio): o benchmark não a conta como FP (R-4: "FP").
    ficha = _ficha([_ref("PARA_RAIOS_BT", _em(0.5, 0.5))], pendentes=[_em(0.53, 0.5, 0.001)])
    bloco = metricas.avaliar_predicoes(ficha, [_pred("ATERRAMENTO", _em(0.5, 0.5))], CLASSES)

    assert bloco["centro"]["perto_de_poste_pendente"] == 1
    assert bloco["centro"]["geral"]["fp"] == 0
    assert bloco["centro"]["leituras_erradas"]["total"] == 0


def test_predicao_fora_das_regioes_nao_e_fp_nem_leitura_errada() -> None:
    regioes = [{"pagina": 1, "bbox": [0.0, 0.0, 0.45, 1.0]}]
    ficha = _ficha([_ref("PARA_RAIOS_BT", [0.4, 0.4, 0.6, 0.6])], regioes=regioes)
    bloco = metricas.avaliar_predicoes(ficha, [_pred("ATERRAMENTO", _em(0.55, 0.5))], CLASSES)

    assert bloco["centro"]["fora_das_regioes"] == 1
    assert bloco["centro"]["geral"]["fp"] == 0
    assert bloco["centro"]["leituras_erradas"]["total"] == 0


def test_leitura_errada_e_calculada_com_as_casadas_de_cada_criterio() -> None:
    # Predição ATERRAMENTO casa a referência ATERRAMENTO no centro, mas não no IoU;
    # seu centro também está numa referência PARA_RAIOS_BT.
    referencias = [
        _ref("ATERRAMENTO", [0.50, 0.50, 0.60, 0.60]),
        _ref("PARA_RAIOS_BT", [0.40, 0.40, 0.56, 0.56]),
    ]
    predicao = _pred("ATERRAMENTO", [0.50, 0.50, 0.60, 0.60])
    predicao["bbox"] = [0.55, 0.55, 0.57, 0.57]
    ficha = _ficha(referencias)

    bloco = metricas.avaliar_predicoes(ficha, [predicao], CLASSES)

    assert bloco["centro"]["geral"]["tp"] == 1
    assert bloco["iou"]["geral"]["tp"] == 0
    assert bloco["centro"]["leituras_erradas"]["total"] == 0
    assert bloco["iou"]["leituras_erradas"]["total"] == 1


def test_tolerancia_vale_nos_quatro_lados() -> None:
    caixa = [0.4, 0.4, 0.5, 0.5]
    referencias = [_ref("PARA_RAIOS_BT", caixa)]
    dentro = [(0.4 - 0.004, 0.45), (0.5 + 0.004, 0.45), (0.45, 0.4 - 0.004), (0.45, 0.5 + 0.004)]
    fora = [(0.4 - 0.006, 0.45), (0.5 + 0.006, 0.45), (0.45, 0.4 - 0.006), (0.45, 0.5 + 0.006)]

    for x, y in dentro:
        assert (
            len(
                metricas.leituras_erradas(
                    referencias, [_pred("ATERRAMENTO", _em(x, y, 0))], set(), TOL
                )
            )
            == 1
        )
    for x, y in fora:
        assert (
            metricas.leituras_erradas(referencias, [_pred("ATERRAMENTO", _em(x, y, 0))], set(), TOL)
            == []
        )


def test_predicao_sobre_duas_referencias_de_outras_classes_gera_um_item_por_referencia() -> None:
    referencias = [_ref("PARA_RAIOS_BT", _em(0.5, 0.5)), _ref("PARA_RAIOS_MT", _em(0.5, 0.5))]

    itens = metricas.leituras_erradas(
        referencias, [_pred("ATERRAMENTO", _em(0.5, 0.5))], set(), TOL
    )

    assert [(i["classe_referencia"], i["referencia_id"]) for i in itens] == [
        ("PARA_RAIOS_BT", 0),
        ("PARA_RAIOS_MT", 1),
    ]


def test_segunda_predicao_da_mesma_classe_nao_casada_nao_e_leitura_errada() -> None:
    referencias = [_ref("ATERRAMENTO", _em(0.5, 0.5))]
    predicoes = [_pred("ATERRAMENTO", _em(0.5, 0.5)), _pred("ATERRAMENTO", _em(0.5, 0.5))]

    bloco = metricas.avaliar_predicoes(_ficha(referencias), predicoes, CLASSES)

    assert bloco["centro"]["leituras_erradas"] == {"total": 0, "por_classe": {}, "itens": []}


def test_folha_sem_referencia_nao_tem_leitura_errada() -> None:
    bloco = metricas.avaliar_predicoes(_ficha([]), [_pred("ATERRAMENTO", _em(0.5, 0.5))], CLASSES)

    assert bloco["centro"]["leituras_erradas"] == {"total": 0, "por_classe": {}, "itens": []}
    assert bloco["iou"]["leituras_erradas"]["total"] == 0


def test_predicao_de_contexto_legenda_ou_fora_do_escopo_nao_e_leitura_errada() -> None:
    ficha = _ficha([_ref("PARA_RAIOS_BT", _em(0.5, 0.5))])
    legenda = {**_pred("ATERRAMENTO", _em(0.5, 0.5)), "contexto": "legend"}
    fora = _pred("OUTRA_CLASSE", _em(0.5, 0.5))

    bloco = metricas.avaliar_predicoes(ficha, [legenda, fora], CLASSES)

    assert bloco["centro"]["leituras_erradas"]["total"] == 0


def test_soma_de_folhas_diferentes_soma_por_classe_predita() -> None:
    a = metricas.avaliar_predicoes(
        _ficha([_ref("PARA_RAIOS_BT", _em(0.5, 0.5))]),
        [_pred("ATERRAMENTO", _em(0.5, 0.5))],
        CLASSES,
    )
    b = metricas.avaliar_predicoes(
        _ficha([_ref("ATERRAMENTO", _em(0.5, 0.5))]),
        [_pred("PARA_RAIOS_BT", _em(0.5, 0.5))],
        CLASSES,
    )
    folhas = [{"situacao": "ok", "metodos": {"m": {"situacao": "ok", **bloco}}} for bloco in (a, b)]

    soma = metricas._agregar_folhas(folhas, ["m"])["m"]["centro"]["leituras_erradas"]

    assert soma["total"] == 2
    assert soma["por_classe"] == {"ATERRAMENTO": 1, "PARA_RAIOS_BT": 1}


def test_markdown_traz_total_de_leituras_erradas_no_criterio_centro() -> None:
    bloco = metricas.avaliar_predicoes(
        _ficha([_ref("PARA_RAIOS_BT", _em(0.5, 0.5))]),
        [_pred("ATERRAMENTO", _em(0.5, 0.5))],
        CLASSES,
    )
    folha = {"situacao": "ok", "metodos": {"m": {"situacao": "ok", **bloco}}}
    agregado = metricas._agregar_folhas([folha, folha, folha], ["m"])["m"]

    texto = "\n".join(relatorio._linhas_metodo("m", agregado))

    assert "leituras erradas (centro): 3." in texto
