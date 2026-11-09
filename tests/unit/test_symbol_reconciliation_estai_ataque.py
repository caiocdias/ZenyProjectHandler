"""E07.2.2.1, Task 4: ataque ao emparelhamento do ESTAI (testador; complementa o do dev)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from itertools import permutations

import pytest
from tests.unit.test_symbol_reconciliation import _observation
from tests.unit.test_symbol_reconciliation_estai import (
    _HASTE,
    _LEGADO,
    _MODELO,
    _OUTRO_LEGADO,
    _Entrada,
    _grupos,
    _ids,
    _legado,
    _modelo,
    _reconciliar,
)

from zeny_project_handler.application import symbol_reconciliation
from zeny_project_handler.domain.symbols import AlternativaClasseSimbolo, ObservacaoSimbolo

_OUTRO_OUTRO_LEGADO = replace(_OUTRO_LEGADO, metodo_id="pymupdf-extra")
_MODELO_B = replace(_MODELO, parametros=(("variant", 2),))


# --- ordem: nenhuma permutacao de observacoes ou de resultados muda o desfecho ----------------


def _cenario_em_cadeia() -> tuple[list[_Entrada], set[frozenset[str]]]:
    """L1-M1-L2-M2: a primeira passada une L1-M1, a segunda une as sobras L2-M2."""
    m1, m2 = _modelo(x="0.100"), _modelo(x="0.102")  # centros 0,110 e 0,112
    l1 = _legado(x="0.1045")  # centro 0,1095: M1 a 0,0005
    l2 = _legado(x="0.1058", perfil=_OUTRO_LEGADO)  # centro 0,1108: M1 a 0,0008, M2 a 0,0012
    entradas: list[_Entrada] = [(_MODELO, (m1, m2)), (_LEGADO, (l1,)), (_OUTRO_LEGADO, (l2,))]
    return entradas, {_ids(m1, l1), _ids(m2, l2)}


def test_cadeia_de_sobras_pareia_na_segunda_passada() -> None:
    entradas, esperado = _cenario_em_cadeia()

    assert _grupos(_reconciliar(*entradas)) == esperado


def test_resultado_independe_da_ordem_de_resultados_e_observacoes() -> None:
    entradas, esperado = _cenario_em_cadeia()
    vistos = set()
    for ordem in permutations(entradas):
        for inverter in (False, True):
            ajustadas = [
                (perfil, tuple(reversed(obs)) if inverter else obs) for perfil, obs in ordem
            ]
            reconciliacao = _reconciliar(*ajustadas)
            assert _grupos(reconciliacao) == esperado
            vistos.add(tuple(o.id for o in reconciliacao.occurrences))
    assert len(vistos) == 1


# --- empate exato por valores diferentes de dx e dy --------------------------------------------


def test_empate_exato_entre_legados_por_offsets_1_7_e_5_5_decide_pelo_menor_id() -> None:
    modelo = _modelo()  # centro (0,110; 0,110)
    a = _legado(x="0.106", y="0.112")  # centro (0,111; 0,117): dx 0,001 dy 0,007
    b = _legado(x="0.110", y="0.110", perfil=_OUTRO_LEGADO)  # centro (0,115; 0,115)
    menor, maior = sorted((a, b), key=lambda o: o.id)

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (a,)), (_OUTRO_LEGADO, (b,)))

    assert _grupos(reconciliacao) == {_ids(modelo, menor), _ids(maior)}


def test_empate_exato_entre_modelos_por_offsets_1_7_e_5_5_decide_pelo_menor_id() -> None:
    legado = _legado(x="0.105", y="0.105")  # centro (0,110; 0,110)
    m1 = _modelo(x="0.101", y="0.107")  # centro (0,111; 0,117)
    m2 = _modelo(x="0.105", y="0.105")  # centro (0,115; 0,115)
    menor, maior = sorted((m1, m2), key=lambda o: o.id)

    reconciliacao = _reconciliar((_MODELO, (m1, m2)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(menor, legado), _ids(maior)}


# --- grupos com mais de uma observacao ------------------------------------------------------------


def test_dois_legados_na_mesma_caixa_fundem_juntos_ao_modelo() -> None:
    modelo = _modelo()
    a = _legado(x="0.105", y="0.105")
    b = _legado(x="0.105", y="0.105", perfil=_OUTRO_LEGADO)

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (a,)), (_OUTRO_LEGADO, (b,)))

    assert _grupos(reconciliacao) == {_ids(modelo, a, b)}


def test_dois_legados_no_mesmo_grupo_com_um_centro_fora_do_modelo_nao_fundem() -> None:
    modelo = _modelo()  # caixa x de 0,100 a 0,120
    dentro = _legado(x="0.1149")  # centro 0,1199, dentro
    fora = _legado(x="0.1151", perfil=_OUTRO_LEGADO)  # centro 0,1201, fora

    reconciliacao = _reconciliar(
        (_MODELO, (modelo,)), (_LEGADO, (dentro,)), (_OUTRO_LEGADO, (fora,))
    )

    assert _grupos(reconciliacao) == {_ids(modelo), _ids(dentro, fora)}


def test_duas_configuracoes_do_modelo_na_mesma_caixa_e_um_legado_ficam_numa_ocorrencia() -> None:
    a = _modelo()
    b = replace(a, metodo_assinatura=_MODELO_B.assinatura())
    legado = _legado()

    reconciliacao = _reconciliar((_MODELO, (a,)), (_MODELO_B, (b,)), (_LEGADO, (legado,)))

    assert _MODELO_B.metodo_id == symbol_reconciliation._MODEL_METHOD_ID
    assert _grupos(reconciliacao) == {_ids(a, b, legado)}


# --- guarda -------------------------------------------------------------------------------------


def test_modelo_com_limites_de_suporte_disputado_por_dois_legados_nao_funde() -> None:
    modelo = _modelo(attributes=_HASTE)
    a = _legado(x="0.104")
    b = _legado(x="0.1065", perfil=_OUTRO_LEGADO)

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (a,)), (_OUTRO_LEGADO, (b,)))

    assert _grupos(reconciliacao) == {_ids(modelo), _ids(a), _ids(b)}


def test_rivais_legados_com_o_mesmo_subtipo_nao_acionam_a_guarda() -> None:
    modelo = _modelo()
    a = _legado(x="0.104", subtipo="ancora")
    b = _legado(x="0.1065", perfil=_OUTRO_LEGADO, subtipo="ancora")

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (a,)), (_OUTRO_LEGADO, (b,)))

    assert _grupos(reconciliacao) == {_ids(modelo, a), _ids(b)}


def test_rivais_modelos_com_o_mesmo_subtipo_nao_acionam_a_guarda() -> None:
    m1, m2 = _modelo(x="0.100", subtipo="um"), _modelo(x="0.102", subtipo="um")
    legado = _legado(x="0.1059")

    reconciliacao = _reconciliar((_MODELO, (m1, m2)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(m1, legado), _ids(m2)}


def test_guarda_recusa_o_par_e_o_legado_funde_com_outro_modelo_compativel() -> None:
    """Fixa a leitura do desenvolvedor: a guarda recusa pares, nao a observacao.

    M1 e disputado por L1 e L2, que divergem no subtipo: (L1,M1) e (L2,M1) caem. L1 tambem
    cabe em M2, e esse par nao e recusado.
    """
    m1 = _modelo(x="0.100")  # caixa x de 0,100 a 0,120
    m2 = _modelo(x="0.110")  # caixa x de 0,110 a 0,130
    l1 = _legado(x="0.1095", subtipo="ancora")  # centro 0,1145: dentro de M1 e de M2
    l2 = _legado(x="0.1000", perfil=_OUTRO_LEGADO, subtipo="poste_poste")  # centro 0,105: so M1

    reconciliacao = _reconciliar((_MODELO, (m1, m2)), (_LEGADO, (l1,)), (_OUTRO_LEGADO, (l2,)))

    assert _grupos(reconciliacao) == {_ids(m2, l1), _ids(m1), _ids(l2)}


# --- classe ---------------------------------------------------------------------------------------


def test_modelo_com_alternativa_de_duas_classes_nao_funde() -> None:
    modelo = _modelo()
    modelo = replace(
        modelo,
        alternativas=(
            *modelo.alternativas,
            AlternativaClasseSimbolo(classe="PARA_RAIOS_MT", score_bruto=Decimal(0)),
        ),
    )
    legado = _legado()

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(modelo), _ids(legado)}


def test_legado_sem_subtipo_e_modelo_com_subtipo_fundem_sem_ambiguidade() -> None:
    modelo, legado = _modelo(subtipo="um"), _legado(subtipo=None)

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(modelo, legado)}
    assert "ambiguous_class_or_id" not in reconciliacao.occurrences[0].reasons


def test_estai_funde_e_outra_classe_vizinha_continua_propria() -> None:
    modelo, legado = _modelo(), _legado()
    aterramento = _modelo(x="0.300", classe="ATERRAMENTO")
    aterramento_legado = _legado(x="0.305", classe="ATERRAMENTO", subtipo=None)

    reconciliacao = _reconciliar(
        (_MODELO, (modelo, aterramento)), (_LEGADO, (legado, aterramento_legado))
    )

    assert _grupos(reconciliacao) == {
        _ids(modelo, legado),
        _ids(aterramento),
        _ids(aterramento_legado),
    }


# --- fonte ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mudanca",
    [{"documento_id": "outro"}, {"camada": "anotacao"}, {"documento_sha256": "b" * 64}],
    ids=["documento", "camada", "sha"],
)
def test_fonte_diferente_nao_funde(mudanca: dict[str, str]) -> None:
    modelo = _modelo()
    legado = replace(_legado(), fonte=replace(modelo.fonte, **mudanca))

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(modelo), _ids(legado)}


# --- ocorrencia fundida ---------------------------------------------------------------------------


def _com_atributo(observacao: ObservacaoSimbolo, chave: str, valor: str) -> ObservacaoSimbolo:
    return replace(observacao, atributos=(*observacao.atributos, (chave, valor)))


def test_referencias_do_legado_e_do_modelo_sao_somadas_e_ficam_ambiguas() -> None:
    modelo = _com_atributo(_modelo(), "referencias_possiveis", "ESTAI-A")
    legado = _com_atributo(_legado(), "variante_inventario", "ESTAI-B")

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    ocorrencia = reconciliacao.occurrences[0]
    assert ocorrencia.reference_ids == ("ESTAI-A", "ESTAI-B")
    assert "ambiguous_reference_id" in ocorrencia.reasons
    assert "ambiguous_class_or_id" not in ocorrencia.reasons


def test_referencia_igual_nos_dois_lados_nao_e_ambigua() -> None:
    modelo = _com_atributo(_modelo(), "referencias_possiveis", "ESTAI-A")
    legado = _com_atributo(_legado(), "variante_inventario", "ESTAI-A")

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    ocorrencia = reconciliacao.occurrences[0]
    assert ocorrencia.reference_ids == ("ESTAI-A",)
    assert "ambiguous_reference_id" not in ocorrencia.reasons


def test_ocorrencia_fundida_tem_suporte_dos_dois_metodos_e_matriz_de_suporte() -> None:
    modelo, legado = _modelo(), _legado()

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    ocorrencia = reconciliacao.occurrences[0]
    assert set(ocorrencia.support) == {_MODELO.assinatura(), _LEGADO.assinatura()}
    assert {linha.method_signature: linha.state for linha in reconciliacao.method_matrix} == {
        _MODELO.assinatura(): "support",
        _LEGADO.assinatura(): "support",
    }
    assert {a.classe for a in ocorrencia.alternatives} == {"ESTAI"}


def test_fusao_usa_a_geometria_do_modelo_sem_primitivas_dele() -> None:
    modelo = replace(_modelo(), primitivas=())
    legado = _legado(primitive="drawing:3")

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(modelo, legado)}
    assert reconciliacao.occurrences[0].geometry == modelo.geometria


# --- ablacao ------------------------------------------------------------------------------


def test_ablacao_do_legado_que_ganhou_o_par_reemparelha_o_outro_sem_perder_ocorrencia() -> None:
    modelo = _modelo()
    perto = _legado(x="0.105")
    longe = _legado(x="0.100", perfil=_OUTRO_LEGADO)

    reconciliacao = _reconciliar(
        (_MODELO, (modelo,)), (_LEGADO, (perto,)), (_OUTRO_LEGADO, (longe,))
    )

    ablacao = next(i for i in reconciliacao.ablations if i.method_signature == _LEGADO.assinatura())
    assert {_ids(*oc.observations) for oc in ablacao.occurrences} == {_ids(modelo, longe)}
    assert ablacao.lost_occurrence_ids == ()


def test_ablacao_do_modelo_entre_dois_estais_mantem_os_dois_legados() -> None:
    m1, m2 = _modelo(x="0.100"), _modelo(x="0.102")
    l1, l2 = _legado(x="0.1045"), _legado(x="0.1075", perfil=_OUTRO_LEGADO)

    reconciliacao = _reconciliar((_MODELO, (m1, m2)), (_LEGADO, (l1,)), (_OUTRO_LEGADO, (l2,)))

    ablacao = next(i for i in reconciliacao.ablations if i.method_signature == _MODELO.assinatura())
    assert {_ids(*oc.observations) for oc in ablacao.occurrences} == {_ids(l1), _ids(l2)}
    assert ablacao.lost_occurrence_ids == ()


# --- demais classes ------------------------------------------------------------------------------


@pytest.mark.parametrize("classe", ["ATERRAMENTO", "PARA_RAIOS_MT"])
def test_demais_classes_com_a_mesma_caixa_seguem_a_regra_antiga(classe: str) -> None:
    base = _observation(_LEGADO, classe, x="0.100", y="0.100", width="0.020", height="0.020")
    igual = _observation(_MODELO, classe, x="0.100", y="0.100", width="0.020", height="0.020")

    reconciliacao = _reconciliar((_LEGADO, (base,)), (_MODELO, (igual,)))

    assert _grupos(reconciliacao) == {_ids(base, igual)}
