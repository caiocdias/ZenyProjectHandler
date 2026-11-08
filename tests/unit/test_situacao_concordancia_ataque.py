"""Ataque à concordância de situação do benchmark de símbolos (R-E06.3.3.2.1-4)."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from scripts import benchmark_simbolos_ficha as bench
from scripts import simbolos_ficha_metricas as metricas

BALDES = metricas.BALDES_SITUACAO


def _variante_com(situacoes: Sequence[str]) -> str:
    alvo = frozenset(situacoes)
    for variante, conjunto in metricas._situacoes_do_inventario().items():
        if conjunto == alvo:
            return variante
    raise AssertionError(situacoes)


def _ficha(simbolos: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "escopo_anotacao": {"tipo": "completo"},
        "postes": [
            {
                "pagina": 1,
                "bbox": [0.0, 0.0, 1.0, 1.0],
                "pendentes": [],
                "simbolos": [dict(s) for s in simbolos],
            }
        ],
    }


def _ref(situacao: str | None, x: float = 0.1) -> dict[str, Any]:
    simbolo: dict[str, Any] = {"classe": "ATERRAMENTO", "bbox": [x, 0.1, x + 0.02, 0.12]}
    if situacao is not None:
        simbolo["atributos_extras"] = {"situacao": situacao}
    return simbolo


def _pred(
    x: float = 0.1, *, variante: str | None = None, situacoes: Sequence[str] = ()
) -> dict[str, Any]:
    return {
        "pagina": 1,
        "classe": "ATERRAMENTO",
        "bbox": [x, 0.1, x + 0.02, 0.12],
        "metodo": "teste",
        "contexto": "operational",
        "variante": variante,
        "situacoes_preditas": frozenset(situacoes),
    }


def _bloco(
    referencias: Sequence[Mapping[str, Any]], predicoes: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    resultado: dict[str, Any] = metricas.avaliar_predicoes(
        _ficha(referencias), predicoes, {"ATERRAMENTO"}
    )["centro"]
    return resultado


def _geral(
    referencias: Sequence[Mapping[str, Any]], predicoes: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    geral: dict[str, Any] = _bloco(referencias, predicoes)["concordancia_situacao"]["geral"]
    return geral


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Proposto Retirar (traço vermelho com X, …)", "proposto retirar"),
        ("PROPOSTO_RETIRAR", "proposto retirar"),
        ("proposto_retirar", "proposto retirar"),
        ("Proposto_Retirar (traço)", "proposto retirar"),
        ("Existente  (a) (b)", "existente"),
        ("ÂNCORA Existência", "ancora existencia"),
        ("Propósto\tRetirar", "proposto retirar"),
        ("   ", None),
        ("_", None),
        ("-", "-"),
    ],
)
def test_normalizacao_de_textos_reais_variados(texto: str, esperado: str | None) -> None:
    assert metricas.normalizar_situacao(texto) == esperado


def test_normalizacao_e_idempotente() -> None:
    for texto in ["Proposto_Retirar (x)", "Existente", "ÃO é"]:
        uma = metricas.normalizar_situacao(texto)
        assert metricas.normalizar_situacao(uma) == uma


def test_texto_com_ponto_e_virgula_concorda_com_o_prefixo() -> None:
    """Texto real "existente; sem comprimento escrito" deveria casar com "Existente".

    A normalização só corta no parêntese: o resto depois do ";" permanece e a concordância
    vira discordância falsa. Defeito candidato (ver relatório).
    """
    predicao = _pred(situacoes=["existente"])
    geral = _geral([_ref("existente; sem comprimento escrito")], [predicao])
    assert geral["concordantes"] == 1
    assert geral["discordantes"] == 0


def test_variante_com_varias_situacoes_aceita_cada_uma_e_rejeita_outra() -> None:
    variante = _variante_com(["existente", "abandonado"])
    conjunto = sorted(metricas.situacoes_da_variante(variante) or ())
    assert conjunto == ["abandonado", "existente"]
    referencias = [
        _ref("Existente (barras)", 0.1),
        _ref("ABANDONADO", 0.3),
        _ref("proposto_instalar", 0.5),
    ]
    predicoes = [_pred(x, variante=variante, situacoes=conjunto) for x in (0.1, 0.3, 0.5)]
    geral = _geral(referencias, predicoes)
    assert geral["concordantes"] == 2
    assert geral["discordantes"] == 1
    assert geral["taxa"] == pytest.approx(2 / 3)


def test_inventario_real_na_e_lista_vazia_viram_none() -> None:
    inventario = json.loads(metricas.INVENTARIO.read_text(encoding="utf-8"))
    for variante in inventario["variants"]:
        bruto = variante.get("situation") or []
        resultado = metricas.situacoes_da_variante(variante["id"])
        if not bruto or all(str(t).strip().lower() == "n/a" for t in bruto):
            assert resultado is None, variante["id"]
        else:
            assert resultado, variante["id"]


def test_variante_nao_declarada_do_inventario_vai_para_o_balde_proprio() -> None:
    vazia = next(v for v, s in metricas._situacoes_do_inventario().items() if s is None)
    geral = _geral([_ref("existente")], [_pred(variante=vazia, situacoes=["existente"])])
    assert geral["situacao_nao_declarada"] == 1
    assert geral["concordantes"] == 0


def test_variante_desconhecida_vira_nao_declarada() -> None:
    assert metricas.situacoes_da_variante("nao-existe-xyz") is None
    geral = _geral([_ref("existente")], [_pred(variante="nao-existe-xyz", situacoes=["existente"])])
    assert geral["situacao_nao_declarada"] == 1


def test_traco_conta_como_declarada_caracterizacao() -> None:
    """O desenvolvedor reporta que "-" é situação declarada (1 variante no inventário)."""
    traco = _variante_com(["-"])
    assert metricas.situacoes_da_variante(traco) == frozenset({"-"})
    geral = _geral([_ref("existente")], [_pred(variante=traco, situacoes=["-"])])
    assert geral["discordantes"] == 1
    assert geral["situacao_nao_declarada"] == 0


def test_ficha_sem_situacao_tem_precedencia_sobre_variante_nao_declarada() -> None:
    geral = _geral([_ref(None)], [_pred(variante="nao-existe-xyz")])
    assert geral["sem_situacao_ficha"] == 1
    assert geral["situacao_nao_declarada"] == 0


def test_ficha_com_situacao_so_parentese_conta_como_sem_situacao() -> None:
    geral = _geral([_ref("(texto solto)")], [_pred(situacoes=["existente"])])
    assert geral["sem_situacao_ficha"] == 1
    assert geral["discordantes"] == 0


def test_baldes_fecham_o_total_de_tp() -> None:
    variante = _variante_com(["existente"])
    vazia = next(v for v, s in metricas._situacoes_do_inventario().items() if s is None)
    referencias = [
        _ref(None, 0.1),
        _ref("existente", 0.2),
        _ref("proposto_instalar", 0.3),
        _ref("existente", 0.4),
        _ref("existente", 0.5),
        _ref("existente", 0.6),
    ]
    predicoes = [
        _pred(0.1, variante=variante, situacoes=["existente"]),
        _pred(0.2, variante=variante, situacoes=["existente"]),
        _pred(0.3, variante=variante, situacoes=["existente"]),
        _pred(0.4, variante=vazia),
        _pred(0.5),
        _pred(0.6, situacoes=["existente"]),
        _pred(0.8, situacoes=["existente"]),  # FP: fora dos baldes
    ]
    bloco = _bloco(referencias, predicoes)
    geral = bloco["concordancia_situacao"]["geral"]
    assert bloco["geral"]["tp"] == 6
    assert sum(geral[b] for b in BALDES) == 6
    por_classe = bloco["concordancia_situacao"]["por_classe"]["ATERRAMENTO"]
    assert sum(por_classe[b] for b in BALDES) == bloco["por_classe"]["ATERRAMENTO"]["tp"]


def test_fn_e_fp_nao_entram_na_concordancia() -> None:
    bloco = _bloco([_ref("existente", 0.1)], [_pred(0.7, situacoes=["existente"])])
    geral = bloco["concordancia_situacao"]["geral"]
    assert sum(geral[b] for b in BALDES) == 0
    assert geral["taxa"] is None


def test_somar_duas_folhas_preserva_os_totais_por_balde() -> None:
    a = _bloco(
        [_ref("existente", 0.1), _ref(None, 0.3)],
        [_pred(0.1, situacoes=["existente"]), _pred(0.3)],
    )
    b = _bloco(
        [_ref("existente", 0.1), _ref("existente", 0.3)],
        [_pred(0.1), _pred(0.3, situacoes=["x"])],
    )
    soma = metricas._somar_criterio([a, b])
    geral_a = a["concordancia_situacao"]["geral"]
    geral_b = b["concordancia_situacao"]["geral"]
    for balde in BALDES:
        assert soma["concordancia_situacao"]["geral"][balde] == geral_a[balde] + geral_b[balde]
    assert sum(soma["concordancia_situacao"]["geral"][k] for k in BALDES) == soma["geral"]["tp"]
    assert geral_a["concordantes"] == 1


def test_somar_uma_folha_preserva_as_chaves_existentes() -> None:
    a = _bloco([_ref("existente")], [_pred(situacoes=["existente"])])
    antes = copy.deepcopy(a)
    soma = metricas._somar_criterio([a])
    assert a == antes
    assert soma["concordancia_situacao"] == a["concordancia_situacao"]
    for chave in ("por_classe", "geral", "fora_do_escopo", "fora_das_regioes"):
        assert soma[chave] == a[chave]


def test_metricas_antigas_nao_dependem_das_chaves_de_situacao() -> None:
    referencias = [_ref("existente", 0.1), _ref(None, 0.3)]
    com = _bloco(referencias, [_pred(0.1, situacoes=["existente"]), _pred(0.3)])
    sem = _bloco(
        referencias,
        [
            {k: v for k, v in _pred(x).items() if k not in ("variante", "situacoes_preditas")}
            for x in (0.1, 0.3)
        ],
    )
    assert {k: v for k, v in com.items() if k != "concordancia_situacao"} == {
        k: v for k, v in sem.items() if k != "concordancia_situacao"
    }
    assert sem["concordancia_situacao"]["geral"]["sem_situacao_predita"] == 1


def test_inventario_carrega_independente_do_cwd(tmp_path: Path, monkeypatch: Any) -> None:
    metricas._situacoes_do_inventario.cache_clear()
    monkeypatch.chdir(tmp_path)
    try:
        assert metricas.INVENTARIO.is_absolute()
        assert metricas.INVENTARIO.is_file()
        variante = _variante_com(["existente"])
        assert metricas.situacoes_da_variante(variante) == frozenset({"existente"})
    finally:
        metricas._situacoes_do_inventario.cache_clear()


def test_predicao_do_runner_com_provenance_none_e_variante_desconhecida() -> None:
    base: dict[str, Any] = {
        "page": 1,
        "class_id": "ATERRAMENTO",
        "bbox": [0, 0, 1, 1],
        "method_id": "m",
        "context": "operational",
        "situation": "Existente (x)",
        "provenance": None,
    }
    legado = bench._predicao_do_runner(base)
    assert legado["variante"] is None
    assert legado["situacoes_preditas"] == frozenset({"existente"})
    desconhecida = bench._predicao_do_runner({**base, "provenance": {"variant_id": "zzz"}})
    assert desconhecida["variante"] == "zzz"
    assert desconhecida["situacoes_preditas"] == frozenset()
