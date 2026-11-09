"""E07.2.2.1, Task 4: emparelhamento do ESTAI do legado e do modelo (R-E07.2.2.1-2)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from tests.unit.test_symbol_reconciliation import _observation, _profile, _result

from zeny_project_handler.adapters.analysis.declarative_symbols import carregar_pacotes
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import carregar_tabela_glifos
from zeny_project_handler.adapters.analysis.model_symbols import perfil_pacotes_modelo
from zeny_project_handler.application import symbol_reconciliation
from zeny_project_handler.application.symbol_reconciliation import (
    CalibrationPolicy,
    SymbolReconciliation,
    reconcile_symbols,
)
from zeny_project_handler.domain.catalog import ExtraAttributes
from zeny_project_handler.domain.symbols import (
    AlternativaClasseSimbolo,
    ObservacaoSimbolo,
    PerfilMetodoSimbolos,
)
from zeny_project_handler.domain.values import PontoNormalizado


def _perfil(nome: str) -> PerfilMetodoSimbolos:
    perfil = _profile(nome)
    return replace(perfil, classes_suportadas=(*perfil.classes_suportadas, "PARA_RAIOS_MT"))


_MODELO = _perfil("declarative-drawing-model")
_LEGADO = _perfil("pymupdf-guys")
_OUTRO_LEGADO = _perfil("pymupdf-symbols")
_HASTE: ExtraAttributes = (("simbolo_limites_suporte", "[100.0, 100.0, 140.0, 160.0]"),)

_Entrada = tuple[PerfilMetodoSimbolos, tuple[ObservacaoSimbolo, ...]]


def _modelo(
    x: str = "0.100",
    y: str = "0.100",
    *,
    classe: str = "ESTAI",
    subtipo: str | None = None,
    primitive: str | None = None,
    attributes: ExtraAttributes = (),
    page: int = 1,
) -> ObservacaoSimbolo:
    """Caixa do pictograma, de lado 0,020: o centro fica a 0,010 do canto (x, y)."""
    observacao = _observation(
        _MODELO,
        classe,
        x=x,
        y=y,
        width="0.020",
        height="0.020",
        primitive=primitive,
        attributes=attributes,
        page=page,
    )
    alternativa = AlternativaClasseSimbolo(classe=classe, subtipo=subtipo, score_bruto=Decimal(0))
    return replace(observacao, alternativas=(alternativa,))


def _legado(
    x: str = "0.105",
    y: str = "0.105",
    *,
    perfil: PerfilMetodoSimbolos = _LEGADO,
    classe: str = "ESTAI",
    subtipo: str | None = "ancora",
    alternativas_extras: tuple[str, ...] = (),
    primitive: str | None = None,
    attributes: ExtraAttributes = (),
    page: int = 1,
) -> ObservacaoSimbolo:
    """Caixa do eixo da haste, de lado 0,010: o centro fica a 0,005 do canto (x, y)."""
    observacao = _observation(
        perfil,
        classe,
        x=x,
        y=y,
        width="0.010",
        height="0.010",
        primitive=primitive,
        attributes=attributes,
        page=page,
    )
    alternativas = tuple(
        AlternativaClasseSimbolo(classe=codigo, subtipo=subtipo, score_bruto=Decimal(0))
        for codigo in (classe, *alternativas_extras)
    )
    return replace(observacao, alternativas=alternativas)


def _reconciliar(*entradas: _Entrada) -> SymbolReconciliation:
    return reconcile_symbols(
        tuple(_result(perfil, *observacoes) for perfil, observacoes in entradas),
        CalibrationPolicy(),
    )


def _grupos(reconciliacao: SymbolReconciliation) -> set[frozenset[str]]:
    return {
        frozenset(observacao.id for observacao in ocorrencia.observations)
        for ocorrencia in reconciliacao.occurrences
    }


def _ids(*observacoes: ObservacaoSimbolo) -> frozenset[str]:
    return frozenset(observacao.id for observacao in observacoes)


# --- fusão, geometria e subtipo ---------------------------------------------------------------


def test_legado_com_centro_na_caixa_do_modelo_funde_em_uma_ocorrencia() -> None:
    modelo, legado = _modelo(), _legado()

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(modelo, legado)}


def test_centro_na_borda_da_caixa_do_modelo_funde() -> None:
    # Centro do legado em 0,120, exatamente a borda direita da caixa do modelo.
    modelo, legado = _modelo(), _legado(x="0.115")

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(modelo, legado)}


def test_centro_fora_da_caixa_do_modelo_nao_funde() -> None:
    # Centro do legado em 0,1201, logo além da borda direita.
    modelo, legado = _modelo(), _legado(x="0.1151")

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(modelo), _ids(legado)}


def test_fusao_usa_a_geometria_do_modelo_mesmo_com_legado_de_mais_primitivas() -> None:
    modelo, legado = _modelo(), _legado(primitive="drawing:9")

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    assert [ocorrencia.geometry for ocorrencia in reconciliacao.occurrences] == [modelo.geometria]


def test_subtipo_do_legado_e_preservado_sem_ambiguidade_de_classe() -> None:
    modelo, legado = _modelo(), _legado(subtipo="ancora")

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    ocorrencia = reconciliacao.occurrences[0]
    assert "ambiguous_class_or_id" not in ocorrencia.reasons
    assert {alternativa.subtipo for alternativa in ocorrencia.alternatives} == {None, "ancora"}


@pytest.mark.parametrize("lado", ["legado", "modelo"])
def test_support_geometry_da_haste_e_preservada_com_a_geometria_do_modelo(lado: str) -> None:
    modelo = _modelo(attributes=_HASTE if lado == "modelo" else ())
    legado = _legado(attributes=_HASTE if lado == "legado" else ())

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(modelo, legado)}
    ocorrencia = reconciliacao.occurrences[0]
    assert ocorrencia.geometry == modelo.geometria
    assert ocorrencia.support_geometry is not None
    assert ocorrencia.support_geometry.pontos_normalizados == (
        PontoNormalizado(Decimal("0.1"), Decimal("0.1")),
        PontoNormalizado(Decimal("0.14"), Decimal("0.16")),
    )


# --- emparelhamento 1 para 1 ------------------------------------------------------------------


def _dois_estais_sobrepostos() -> tuple[
    ObservacaoSimbolo, ObservacaoSimbolo, ObservacaoSimbolo, ObservacaoSimbolo
]:
    """Modelos com centros em 0,110 e 0,112; legados com centros em 0,1095 e 0,1125."""
    return (
        _modelo(x="0.100"),
        _modelo(x="0.102"),
        _legado(x="0.1045"),
        _legado(x="0.1075", perfil=_OUTRO_LEGADO),
    )


def test_dois_estais_no_mesmo_poste_pareiam_um_a_um() -> None:
    m1, m2, l1, l2 = _dois_estais_sobrepostos()

    reconciliacao = _reconciliar((_MODELO, (m1, m2)), (_LEGADO, (l1,)), (_OUTRO_LEGADO, (l2,)))

    assert _grupos(reconciliacao) == {_ids(m1, l1), _ids(m2, l2)}


def test_ordem_das_observacoes_nao_altera_o_resultado() -> None:
    m1, m2, l1, l2 = _dois_estais_sobrepostos()

    direta = _reconciliar((_MODELO, (m1, m2)), (_LEGADO, (l1,)), (_OUTRO_LEGADO, (l2,)))
    invertida = _reconciliar((_OUTRO_LEGADO, (l2,)), (_LEGADO, (l1,)), (_MODELO, (m2, m1)))

    assert [o.id for o in direta.occurrences] == [o.id for o in invertida.occurrences]
    assert _grupos(direta) == {_ids(m1, l1), _ids(m2, l2)}


def test_dois_legados_nao_fundem_o_mesmo_modelo_e_a_sobra_nao_some() -> None:
    modelo = _modelo()
    perto = _legado(x="0.105")  # centro 0,110: sobre o centro do modelo
    longe = _legado(x="0.100", perfil=_OUTRO_LEGADO)  # centro 0,105

    reconciliacao = _reconciliar(
        (_MODELO, (modelo,)), (_LEGADO, (perto,)), (_OUTRO_LEGADO, (longe,))
    )

    assert _grupos(reconciliacao) == {_ids(modelo, perto), _ids(longe)}


def test_empate_exato_entre_legados_decide_pelo_menor_id() -> None:
    modelo = _modelo()
    a = _legado(x="0.104")  # centro 0,109: a 0,001 do centro do modelo
    b = _legado(x="0.106", perfil=_OUTRO_LEGADO)  # centro 0,111: a 0,001 do centro do modelo
    menor, maior = sorted((a, b), key=lambda observacao: observacao.id)

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (a,)), (_OUTRO_LEGADO, (b,)))

    assert _grupos(reconciliacao) == {_ids(modelo, menor), _ids(maior)}


def test_empate_exato_entre_modelos_decide_pelo_menor_id() -> None:
    m1, m2 = _modelo(x="0.100"), _modelo(x="0.102")  # centros 0,110 e 0,112
    legado = _legado(x="0.106")  # centro 0,111: a 0,001 dos dois
    menor, maior = sorted((m1, m2), key=lambda observacao: observacao.id)

    reconciliacao = _reconciliar((_MODELO, (m1, m2)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(menor, legado), _ids(maior)}


def test_quase_empate_nao_tem_margem_e_funde_o_mais_perto() -> None:
    m1, m2 = _modelo(x="0.100"), _modelo(x="0.102")  # centros 0,110 e 0,112
    legado = _legado(x="0.1059")  # centro 0,1109: 0,0009 de m1 e 0,0011 de m2

    reconciliacao = _reconciliar((_MODELO, (m1, m2)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(m1, legado), _ids(m2)}


def test_passada_repetida_pareia_a_sobra_com_o_modelo_livre() -> None:
    m1, m2 = _modelo(x="0.100"), _modelo(x="0.102")  # centros 0,110 e 0,112
    perto = _legado(x="0.105")  # centro 0,110: 0 de m1
    sobra = _legado(x="0.1041", perfil=_OUTRO_LEGADO)  # centro 0,1091: 0,0009 de m1, sem mútuo

    reconciliacao = _reconciliar(
        (_MODELO, (m1, m2)), (_LEGADO, (perto,)), (_OUTRO_LEGADO, (sobra,))
    )

    assert _grupos(reconciliacao) == {_ids(m1, perto), _ids(m2, sobra)}


# --- o que não é par compatível ---------------------------------------------------------------


def test_dois_modelos_sobrepostos_nao_se_fundem() -> None:
    m1, m2 = _modelo(x="0.100"), _modelo(x="0.102")
    legado = _legado(x="0.105")

    reconciliacao = _reconciliar((_MODELO, (m1, m2)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(m1, legado), _ids(m2)}


def test_dois_legados_contidos_um_no_outro_nao_fundem_sem_o_modelo() -> None:
    grande = replace(_modelo(), metodo_assinatura=_OUTRO_LEGADO.assinatura())
    pequeno = _legado()

    reconciliacao = _reconciliar((_OUTRO_LEGADO, (grande,)), (_LEGADO, (pequeno,)))

    assert _grupos(reconciliacao) == {_ids(grande), _ids(pequeno)}


@pytest.mark.parametrize(
    ("classe_modelo", "classe_legado"),
    [
        ("ESTAI", "ATERRAMENTO"),
        ("PARA_RAIOS_MT", "ESTAI"),
    ],
    ids=["aterramento-no-legado", "para-raios-no-modelo"],
)
def test_leitura_de_outra_classe_sobre_o_estai_nao_funde(
    classe_modelo: str, classe_legado: str
) -> None:
    modelo, legado = _modelo(classe=classe_modelo), _legado(classe=classe_legado, subtipo=None)

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(modelo), _ids(legado)}


@pytest.mark.parametrize("classe", ["ATERRAMENTO", "PARA_RAIOS_MT"])
def test_mesma_contencao_em_outra_classe_nao_funde(classe: str) -> None:
    modelo, legado = _modelo(classe=classe), _legado(classe=classe, subtipo=None)

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(modelo), _ids(legado)}


def test_legado_com_alternativa_de_outra_classe_nao_funde() -> None:
    modelo, legado = _modelo(), _legado(alternativas_extras=("ATERRAMENTO",))

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(modelo), _ids(legado)}


def test_outra_pagina_nao_funde() -> None:
    modelo, legado = _modelo(), _legado(page=2)

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(modelo), _ids(legado)}


def test_contexto_de_legenda_nao_funde_com_desenho() -> None:
    modelo, legado = _modelo(), _legado(attributes=(("contexto", "legenda"),))

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(modelo), _ids(legado)}


# --- guarda: a escolha entre rivais muda o resultado ------------------------------------------


def test_rivais_legados_com_subtipo_divergente_nao_fundem() -> None:
    modelo = _modelo()
    a = _legado(x="0.104", subtipo="ancora")
    b = _legado(x="0.1065", perfil=_OUTRO_LEGADO, subtipo="poste_poste")

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (a,)), (_OUTRO_LEGADO, (b,)))

    assert _grupos(reconciliacao) == {_ids(modelo), _ids(a), _ids(b)}


def test_rival_legado_com_limites_de_suporte_nao_funde() -> None:
    modelo = _modelo()
    a = _legado(x="0.104")
    b = _legado(x="0.1065", perfil=_OUTRO_LEGADO, attributes=_HASTE)

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (a,)), (_OUTRO_LEGADO, (b,)))

    assert _grupos(reconciliacao) == {_ids(modelo), _ids(a), _ids(b)}


def test_rivais_modelos_com_subtipo_divergente_nao_fundem() -> None:
    m1 = _modelo(x="0.100", subtipo="um")
    m2 = _modelo(x="0.102", subtipo="dois")
    legado = _legado(x="0.1055")

    reconciliacao = _reconciliar((_MODELO, (m1, m2)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(m1), _ids(m2), _ids(legado)}


def test_rival_modelo_com_limites_de_suporte_nao_funde() -> None:
    m1 = _modelo(x="0.100", attributes=_HASTE)
    m2 = _modelo(x="0.102")
    legado = _legado(x="0.1055")

    reconciliacao = _reconciliar((_MODELO, (m1, m2)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(m1), _ids(m2), _ids(legado)}


def test_legado_com_limites_de_suporte_disputando_dois_modelos_nao_funde() -> None:
    m1, m2 = _modelo(x="0.100"), _modelo(x="0.102")
    legado = _legado(x="0.1055", attributes=_HASTE)

    reconciliacao = _reconciliar((_MODELO, (m1, m2)), (_LEGADO, (legado,)))

    assert _grupos(reconciliacao) == {_ids(m1), _ids(m2), _ids(legado)}


def test_guarda_nao_alcanca_par_independente_na_mesma_pagina() -> None:
    disputado = _modelo()
    a = _legado(x="0.104", subtipo="ancora")
    b = _legado(x="0.1065", perfil=_OUTRO_LEGADO, subtipo="poste_poste")
    modelo_distante = _modelo(x="0.500")
    legado_distante = _legado(x="0.505")

    reconciliacao = _reconciliar(
        (_MODELO, (disputado, modelo_distante)),
        (_LEGADO, (a, legado_distante)),
        (_OUTRO_LEGADO, (b,)),
    )

    assert _grupos(reconciliacao) == {
        _ids(disputado),
        _ids(a),
        _ids(b),
        _ids(modelo_distante, legado_distante),
    }


# --- ablação e caminhos que não mudam ---------------------------------------------------------


def test_ablacao_sem_o_legado_nao_perde_a_ocorrencia() -> None:
    modelo, legado = _modelo(), _legado()

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    ablacao = next(
        item for item in reconciliacao.ablations if item.method_signature == _LEGADO.assinatura()
    )
    assert ablacao.lost_occurrence_ids == ()
    assert [ocorrencia.observations for ocorrencia in ablacao.occurrences] == [(modelo,)]


def test_so_legado_nao_dispara_a_fusao_e_a_ocorrencia_fica_igual() -> None:
    legado = _legado(subtipo="ancora")

    reconciliacao = _reconciliar((_LEGADO, (legado,)))

    assert len(reconciliacao.occurrences) == 1
    ocorrencia = reconciliacao.occurrences[0]
    assert ocorrencia.observations == (legado,)
    assert ocorrencia.geometry == legado.geometria
    assert ocorrencia.alternatives == legado.alternativas
    assert ocorrencia.reasons == ("insufficient_calibration",)


def test_ablacao_do_modelo_devolve_o_legado_como_ocorrencia_propria() -> None:
    modelo, legado = _modelo(), _legado(subtipo="ancora")

    reconciliacao = _reconciliar((_MODELO, (modelo,)), (_LEGADO, (legado,)))

    ablacao = next(
        item for item in reconciliacao.ablations if item.method_signature == _MODELO.assinatura()
    )
    assert [ocorrencia.observations for ocorrencia in ablacao.occurrences] == [(legado,)]
    assert ablacao.occurrences[0].geometry == legado.geometria


@pytest.mark.parametrize("classe", ["ESTAI", "TRANSFORMADOR"])
def test_grupo_pela_regra_antiga_segue_ambiguo_com_subtipos_diferentes(classe: str) -> None:
    # Mesma caixa: é o caminho de `_same_occurrence`, que não é "fundido por este caminho".
    base = _legado(x="0.100", classe=classe, subtipo="um")
    igual = _legado(x="0.100", perfil=_MODELO, classe=classe, subtipo="dois")

    reconciliacao = _reconciliar((_LEGADO, (base,)), (_MODELO, (igual,)))

    assert _grupos(reconciliacao) == {_ids(base, igual)}
    assert "ambiguous_class_or_id" in reconciliacao.occurrences[0].reasons


# --- paridade com o perfil real ---------------------------------------------------------------


def test_constante_do_metodo_do_modelo_bate_com_o_perfil_real() -> None:
    perfil = perfil_pacotes_modelo(carregar_pacotes(), carregar_tabela_glifos())

    assert perfil.metodo_id == symbol_reconciliation._MODEL_METHOD_ID
