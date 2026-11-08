"""Concordância de situação entre ficha e predição no benchmark de símbolos (R-E06.3.3.2.1-4)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from scripts import benchmark_simbolos_ficha as bench
from scripts import simbolos_ficha_metricas as metricas
from scripts.simbolos_ficha_relatorio import _linhas_criterio

# Variante do inventário com `situation` vazia (estado não declarado).
VARIANTE_VAZIA = "cemig-eo-r3-s01-v001"
BALDES = (
    "concordantes",
    "discordantes",
    "sem_situacao_ficha",
    "situacao_nao_declarada",
    "sem_situacao_predita",
)


def _variante(situacao: str) -> str:
    """Id de uma variante do inventário cuja única situação normalizada é `situacao`."""
    inventario = metricas._situacoes_do_inventario()
    for variante, situacoes in inventario.items():
        if situacoes == frozenset({situacao}):
            return variante
    raise AssertionError(situacao)


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
    x: float = 0.1,
    *,
    variante: str | None = None,
    situacoes: Sequence[str] = (),
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


def _concordancia(
    referencias: Sequence[Mapping[str, Any]], predicoes: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    bloco = metricas.avaliar_predicoes(_ficha(referencias), predicoes, {"ATERRAMENTO"})
    resultado: dict[str, Any] = bloco["centro"]["concordancia_situacao"]
    return resultado


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("proposto instalar (verde, círculo…)", "proposto instalar"),
        ("existente (barras pretas…)", "existente"),
        ("proposto_instalar", "proposto instalar"),
        ("Proposto Instalar", "proposto instalar"),
        ("  Âncora   Existente ", "ancora existente"),
        (None, None),
        ("", None),
        ("(só parêntese)", None),
    ],
)
def test_normalizar_situacao(texto: str | None, esperado: str | None) -> None:
    assert metricas.normalizar_situacao(texto) == esperado


def test_situacoes_da_variante_do_inventario() -> None:
    existente = _variante("existente")
    assert metricas.situacoes_da_variante(existente) == frozenset({"existente"})
    assert metricas.situacoes_da_variante(VARIANTE_VAZIA) is None
    assert metricas.situacoes_da_variante("variante-que-nao-existe") is None


def test_inventario_com_na_nao_tem_situacao_declarada() -> None:
    nao_declaradas = [v for v, s in metricas._situacoes_do_inventario().items() if s is None]
    # `[]` (168) e "N/A" (23) no inventário congelado.
    assert len(nao_declaradas) >= 191


def test_concorda_com_a_variante_do_modelo() -> None:
    variante = _variante("proposto instalar")
    predicao = _pred(variante=variante, situacoes=["proposto instalar"])
    bloco = _concordancia([_ref("proposto instalar (verde, círculo…)")], [predicao])
    assert bloco["geral"]["concordantes"] == 1
    assert bloco["geral"]["discordantes"] == 0
    assert bloco["geral"]["taxa"] == 1.0
    assert bloco["por_classe"]["ATERRAMENTO"]["concordantes"] == 1


def test_concorda_com_a_situacao_do_legado_sem_variante() -> None:
    predicao = _pred(situacoes=["existente"])
    bloco = _concordancia([_ref("existente (barras pretas…)")], [predicao])
    assert bloco["geral"]["concordantes"] == 1


def test_concorda_com_a_variante_dos_pacotes_quando_ha_varias_situacoes() -> None:
    variante = next(
        v
        for v, s in metricas._situacoes_do_inventario().items()
        if s and {"proposto retirar", "proposto abandonar"} <= s
    )
    predicao = _pred(
        variante=variante, situacoes=sorted(metricas.situacoes_da_variante(variante) or ())
    )
    bloco = _concordancia([_ref("proposto_abandonar")], [predicao])
    assert bloco["geral"]["concordantes"] == 1


def test_discorda_quando_a_situacao_nao_esta_no_conjunto() -> None:
    predicao = _pred(situacoes=["existente"])
    bloco = _concordancia([_ref("proposto_instalar")], [predicao])
    assert bloco["geral"]["concordantes"] == 0
    assert bloco["geral"]["discordantes"] == 1
    assert bloco["geral"]["taxa"] == 0.0


def test_tres_baldes_a_parte() -> None:
    referencias = [
        _ref(None, 0.1),
        _ref("existente", 0.3),
        _ref("existente", 0.5),
        _ref("existente", 0.7),
    ]
    predicoes = [
        _pred(0.1, situacoes=["existente"]),
        _pred(0.3, variante=VARIANTE_VAZIA),
        _pred(0.5),
        _pred(0.7, situacoes=["existente"]),
    ]
    geral = _concordancia(referencias, predicoes)["geral"]
    assert {b: geral[b] for b in BALDES} == {
        "concordantes": 1,
        "discordantes": 0,
        "sem_situacao_ficha": 1,
        "situacao_nao_declarada": 1,
        "sem_situacao_predita": 1,
    }
    assert geral["taxa"] == 1.0


def test_sem_tp_com_situacao_a_taxa_e_nula() -> None:
    bloco = _concordancia([_ref(None)], [_pred(situacoes=["existente"])])
    assert bloco["geral"]["taxa"] is None


def test_agregacao_de_duas_folhas() -> None:
    folha_a = metricas.avaliar_predicoes(
        _ficha([_ref("existente")]), [_pred(situacoes=["existente"])], {"ATERRAMENTO"}
    )
    folha_b = metricas.avaliar_predicoes(
        _ficha([_ref("existente"), _ref(None, 0.5)]),
        [_pred(situacoes=["proposto instalar"]), _pred(0.5)],
        {"ATERRAMENTO"},
    )
    soma = metricas._somar_criterio([folha_a["centro"], folha_b["centro"]])
    geral = soma["concordancia_situacao"]["geral"]
    assert geral["concordantes"] == 1
    assert geral["discordantes"] == 1
    assert geral["sem_situacao_ficha"] == 1
    assert geral["taxa"] == 0.5
    assert soma["concordancia_situacao"]["por_classe"]["ATERRAMENTO"]["discordantes"] == 1


def test_chave_nova_nao_muda_as_existentes() -> None:
    comum = metricas.avaliar_predicoes(
        _ficha([_ref("existente")]), [_pred(situacoes=["existente"])], {"ATERRAMENTO"}
    )["centro"]
    outra = metricas.avaliar_predicoes(
        _ficha([_ref("existente")]), [_pred(situacoes=["proposto instalar"])], {"ATERRAMENTO"}
    )["centro"]
    sem_chave = {k: v for k, v in comum.items() if k != "concordancia_situacao"}
    assert set(sem_chave) == {
        "por_classe",
        "geral",
        "fora_do_escopo",
        "fora_das_regioes",
        "perto_de_poste_pendente",
        "leituras_erradas",
    }
    assert sem_chave == {k: v for k, v in outra.items() if k != "concordancia_situacao"}


def test_predicao_do_runner_leva_variante_e_situacoes() -> None:
    variante = _variante("existente")
    item_pacote = {
        "page": 1,
        "class_id": "ATERRAMENTO",
        "bbox": [0, 0, 1, 1],
        "method_id": "m",
        "context": "operational",
        "situation": None,
        "provenance": {"variant_id": variante},
    }
    pacote = bench._predicao_do_runner(item_pacote)
    assert pacote["variante"] == variante
    assert pacote["situacoes_preditas"] == frozenset({"existente"})
    legado = bench._predicao_do_runner(
        {**item_pacote, "situation": "Proposto_Instalar", "provenance": {}}
    )
    assert legado["variante"] is None
    assert legado["situacoes_preditas"] == frozenset({"proposto instalar"})
    sem_nada = bench._predicao_do_runner({**item_pacote, "provenance": {}})
    assert sem_nada["variante"] is None
    assert sem_nada["situacoes_preditas"] == frozenset()


def test_relatorio_markdown_tem_a_linha_de_concordancia() -> None:
    bloco = metricas.avaliar_predicoes(
        _ficha([_ref("existente")]), [_pred(situacoes=["existente"])], {"ATERRAMENTO"}
    )["centro"]
    texto = "\n".join(_linhas_criterio("centro", bloco))
    assert "Concordância de situação" in texto
    assert "100.0%" in texto
