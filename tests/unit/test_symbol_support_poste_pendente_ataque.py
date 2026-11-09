"""Ataque à associação símbolo → poste: caixa, margem, sítios e entradas hostis (E07.2.2.1)."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest
from tests.unit.test_ancoragem_poste import (
    OUTRA_PAGINA,
    PAGINA,
    _atributos,
    _disco,
    _ponto,
    _poste,
)

from zeny_project_handler.adapters.interpretation.ancoragem_poste import (
    ancorar_postes_no_desenho,
)
from zeny_project_handler.application.interpretation_pipeline import (
    _symbol_support,
    _symbol_support_candidates_json,
)
from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.enums import EstadoRevisao
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado


def _caixa(x0: float, y0: float, x1: float, y1: float) -> GeometriaDocumento:
    return GeometriaDocumento.caixa(PAGINA, _ponto(x0, y0), _ponto(x1, y1))


def _poste_em(
    chave: str, x: str, y: str, *extras: tuple[str, Any], pagina: Any = PAGINA
) -> PropostaElemento:
    base = _poste(chave, chave.upper(), 0.5, 0.5, extras=tuple(extras), pagina=pagina)
    return replace(
        base,
        geometria=GeometriaDocumento.ponto(pagina, PontoNormalizado(Decimal(x), Decimal(y))),
    )


def _pendente(chave: str, sitios: Any, x: str = "0.9", y: str = "0.9") -> PropostaElemento:
    return _poste_em(
        chave,
        x,
        y,
        ("associacao_pendente", "poste_disco"),
        ("poste_disco_sitios", sitios),
    )


# --- caixa grande: distância zero dentro da caixa ---------------------------------------


def test_dois_postes_dentro_de_caixa_grande_empatam_em_zero_e_ficam_pendentes() -> None:
    a = _poste_em("a", "0.30", "0.30")
    b = _poste_em("b", "0.40", "0.30")

    suporte, candidatos = _symbol_support(_caixa(0.2, 0.2, 0.5, 0.4), "base", (a, b))

    assert suporte is None
    assert [round(d, 9) for d, _ in candidatos] == [0.0, 0.0]


def test_poste_dentro_da_caixa_grande_vence_o_que_esta_fora_acima_da_margem() -> None:
    dentro = _poste_em("a", "0.30", "0.30")
    fora = _poste_em("b", "0.51", "0.30")  # 0,01 da borda direita

    suporte, _ = _symbol_support(_caixa(0.2, 0.2, 0.5, 0.4), "base", (dentro, fora))

    assert suporte == dentro


def test_poste_dentro_da_caixa_e_outro_colado_na_borda_ficam_ambiguos() -> None:
    dentro = _poste_em("a", "0.30", "0.30")
    colado = _poste_em("b", "0.503", "0.30")  # 0,003 < margem 0,004

    suporte, candidatos = _symbol_support(_caixa(0.2, 0.2, 0.5, 0.4), "base", (dentro, colado))

    assert suporte is None
    assert len(candidatos) == 2


def test_estai_com_haste_longa_prefere_o_poste_sob_a_haste_ao_da_ponta() -> None:
    haste = _caixa(0.30, 0.299, 0.40, 0.301)
    sob_a_haste = _poste_em("a", "0.35", "0.30")
    na_ponta = _poste_em("b", "0.415", "0.30")

    suporte, candidatos = _symbol_support(haste, "base", (sob_a_haste, na_ponta))

    assert suporte == sob_a_haste
    assert [item.id for _, item in candidatos] == [sob_a_haste.id, na_ponta.id]


# --- caixa pequena e raio ----------------------------------------------------------------


def test_raio_e_euclidiano_e_nao_por_eixo() -> None:
    poste = _poste_em("a", "0.2850", "0.2850")  # 0,015 em cada eixo: 0,0212 da quina

    suporte, candidatos = _symbol_support(_caixa(0.30, 0.30, 0.31, 0.31), "base", (poste,))

    assert suporte is None
    assert candidatos == ()


def test_distancia_na_diagonal_dentro_do_raio_e_suporte() -> None:
    poste = _poste_em("a", "0.2880", "0.2880")  # 0,012 por eixo: 0,0170

    suporte, candidatos = _symbol_support(_caixa(0.30, 0.30, 0.31, 0.31), "base", (poste,))

    assert suporte == poste
    assert candidatos[0][0] == pytest.approx(0.012 * 2**0.5)


@pytest.mark.parametrize(
    ("segundo_x", "decide"),
    [
        pytest.param("0.3739", False, id="dentro-da-margem"),
        pytest.param("0.3741", True, id="acima-da-margem"),
    ],
)
def test_margem_de_0_004_entre_o_primeiro_e_o_segundo(segundo_x: str, decide: bool) -> None:
    # Caixa [0.29, 0.36]: o primeiro está a 0,010 da borda; o segundo, a 0,0139/0,0141.
    primeiro = _poste_em("a", "0.28", "0.30")
    segundo = _poste_em("b", segundo_x, "0.30")

    suporte, candidatos = _symbol_support(
        _caixa(0.29, 0.29, 0.36, 0.31), "base", (primeiro, segundo)
    )

    assert suporte == (primeiro if decide else None)
    assert len(candidatos) == 2


def test_resultado_nao_depende_da_ordem_das_propostas() -> None:
    a = _poste_em("a", "0.28", "0.30")
    b = _poste_em("b", "0.373", "0.30")
    c = _poste_em("c", "0.31", "0.42")
    caixa = _caixa(0.29, 0.29, 0.36, 0.31)

    assert _symbol_support(caixa, "base", (a, b, c)) == _symbol_support(caixa, "base", (c, b, a))


def test_empate_exato_de_distancia_lista_pelo_menor_id_e_nao_decide() -> None:
    # Valores diádicos: as duas distâncias são exatamente 0,0078125.
    a = _poste_em("a", "0.4921875", "0.5")
    b = _poste_em("b", "0.5703125", "0.5")

    suporte, candidatos = _symbol_support(_caixa(0.5, 0.49, 0.5625, 0.51), "base", (b, a))

    assert suporte is None
    assert candidatos[0][0] == candidatos[1][0]
    assert [item.id for _, item in candidatos] == sorted([a.id, b.id], key=str)


def test_simbolo_degenerado_em_ponto_mede_do_ponto() -> None:
    poste = _poste_em("a", "0.31", "0.30")
    ponto = GeometriaDocumento.ponto(PAGINA, _ponto(0.30, 0.30))

    suporte, candidatos = _symbol_support(ponto, "base", (poste,))

    assert suporte == poste
    assert candidatos[0][0] == pytest.approx(0.01)


def test_simbolo_em_ponto_no_limite_do_raio() -> None:
    poste = _poste_em("a", "0.02", "0.30")
    no_limite = GeometriaDocumento.ponto(PAGINA, _ponto(0.04, 0.30))
    acima = GeometriaDocumento.ponto(PAGINA, _ponto(0.0401, 0.30))

    assert _symbol_support(no_limite, "base", (poste,))[0] == poste
    assert _symbol_support(acima, "base", (poste,)) == (None, ())


# --- filtros do poste --------------------------------------------------------------------


def test_poste_de_outra_pagina_nao_e_candidato_mesmo_mais_perto() -> None:
    longe = _poste_em("a", "0.31", "0.30")
    de_outra_pagina = _poste_em("b", "0.30", "0.30", pagina=OUTRA_PAGINA)

    suporte, candidatos = _symbol_support(
        _caixa(0.29, 0.29, 0.31, 0.31), "base", (de_outra_pagina, longe)
    )

    assert suporte == longe
    assert [item.id for _, item in candidatos] == [longe.id]


def test_poste_rejeitado_nao_e_candidato() -> None:
    rejeitado = replace(_poste_em("a", "0.30", "0.30"), estado_revisao=EstadoRevisao.REJEITADA)

    assert _symbol_support(_caixa(0.29, 0.29, 0.31, 0.31), "base", (rejeitado,)) == (None, ())


@pytest.mark.parametrize("chave", ["simbolo_camada", "camada"])
def test_poste_de_outra_camada_nao_e_candidato(chave: str) -> None:
    poste = _poste_em("a", "0.30", "0.30", (chave, "legenda"))

    assert _symbol_support(_caixa(0.29, 0.29, 0.31, 0.31), "base", (poste,)) == (None, ())


def test_camada_que_nao_e_base_nunca_tem_suporte() -> None:
    poste = _poste_em("a", "0.30", "0.30")

    assert _symbol_support(_caixa(0.29, 0.29, 0.31, 0.31), "legenda", (poste,)) == (None, ())


def test_poste_pendente_de_outra_pagina_ou_rejeitado_nao_entra_pelos_sitios() -> None:
    outra = _poste_em(
        "a",
        "0.9",
        "0.9",
        ("associacao_pendente", "poste_disco"),
        ("poste_disco_sitios", "0.30,0.30"),
        pagina=OUTRA_PAGINA,
    )
    rejeitado = replace(_pendente("b", "0.30,0.30"), estado_revisao=EstadoRevisao.REJEITADA)

    assert _symbol_support(_caixa(0.29, 0.29, 0.31, 0.31), "base", (outra, rejeitado)) == (
        None,
        (),
    )


# --- pendente: quem manda é o sítio ------------------------------------------------------


def test_pendente_mais_proximo_impede_suporte_do_nao_pendente_mais_longe() -> None:
    pendente = _pendente("a", "0.300,0.300")
    firme = _poste_em("b", "0.30", "0.315")  # 0,014 > margem

    suporte, candidatos = _symbol_support(
        _caixa(0.299, 0.299, 0.301, 0.301), "base", (firme, pendente)
    )

    assert suporte is None
    assert [item.id for _, item in candidatos] == [pendente.id, firme.id]


def test_nao_pendente_bem_mais_proximo_vence_o_pendente_mais_longe() -> None:
    pendente = _pendente("a", "0.300,0.315")
    firme = _poste_em("b", "0.30", "0.30")

    suporte, candidatos = _symbol_support(
        _caixa(0.299, 0.299, 0.301, 0.301), "base", (pendente, firme)
    )

    assert suporte == firme
    assert len(candidatos) == 2


def test_dois_pendentes_empatados_nao_dao_suporte() -> None:
    a = _pendente("a", "0.30,0.30")
    b = _pendente("b", "0.30,0.30")

    suporte, candidatos = _symbol_support(_caixa(0.299, 0.299, 0.301, 0.301), "base", (a, b))

    assert suporte is None
    assert len(candidatos) == 2


def test_pendente_com_dois_sitios_usa_o_mais_proximo_da_caixa() -> None:
    pendente = _pendente("a", "0.10,0.10;0.305,0.30")

    suporte, candidatos = _symbol_support(_caixa(0.299, 0.299, 0.301, 0.301), "base", (pendente,))

    assert suporte is None
    assert candidatos[0][0] == pytest.approx(0.004)


def test_pendente_com_sitio_no_limite_exato_do_raio() -> None:
    no_limite = _pendente("a", "0.02,0.30")
    acima = _pendente("b", "0.0199,0.30")  # 0,0201 da caixa que começa em 0,04

    caixa = _caixa(0.04, 0.29, 0.05, 0.31)

    assert _symbol_support(caixa, "base", (no_limite,))[1][0][1] == no_limite
    assert _symbol_support(caixa, "base", (acima,)) == (None, ())


def test_pendente_ao_alcance_pela_posicao_do_texto_mas_com_sitio_longe_fica_fora() -> None:
    pendente = _pendente("a", "0.80,0.80", x="0.30", y="0.30")

    assert _symbol_support(_caixa(0.299, 0.299, 0.301, 0.301), "base", (pendente,)) == (None, ())


@pytest.mark.parametrize(
    "sitios",
    [
        pytest.param("abc", id="texto-solto"),
        pytest.param("0.30", id="uma-coordenada"),
        pytest.param("0.30,0.30,0.30", id="tres-coordenadas"),
        pytest.param("0.30,0.30;", id="separador-sobrando"),
        pytest.param(";0.30,0.30", id="separador-no-inicio"),
        pytest.param("0.30,0.30;;0.31,0.31", id="sitio-vazio-no-meio"),
        pytest.param("a,b", id="coordenadas-nao-numericas"),
        pytest.param("0.30,", id="coordenada-vazia"),
        pytest.param(" ; ", id="so-espacos"),
    ],
)
def test_sitios_malformados_nao_explodem_e_nao_dao_suporte(sitios: str) -> None:
    pendente = _pendente("a", sitios)

    suporte, _ = _symbol_support(_caixa(0.299, 0.299, 0.301, 0.301), "base", (pendente,))

    assert suporte is None


@pytest.mark.parametrize(
    "sitios",
    [
        pytest.param("nan,nan", id="nan"),
        pytest.param("inf,0.30", id="infinito"),
        pytest.param("-inf,-inf", id="menos-infinito"),
        pytest.param("", id="vazio"),
        pytest.param(None, id="nulo"),
        pytest.param(0.3, id="numero"),
        pytest.param(("0.30", "0.30"), id="tupla"),
    ],
)
def test_sitios_invalidos_ou_de_tipo_errado_deixam_o_pendente_fora(sitios: Any) -> None:
    pendente = _pendente("a", sitios)

    assert _symbol_support(_caixa(0.299, 0.299, 0.301, 0.301), "base", (pendente,)) == (None, ())


def test_sitio_malformado_nao_derruba_o_simbolo_com_poste_bom_ao_lado() -> None:
    ruim = _pendente("a", "lixo")
    bom = _poste_em("b", "0.30", "0.30")

    suporte, _ = _symbol_support(_caixa(0.299, 0.299, 0.301, 0.301), "base", (ruim, bom))

    assert suporte == bom


# --- candidatos serializados -------------------------------------------------------------


def test_json_dos_candidatos_leva_ids_pagina_e_distancia_arredondada_na_ordem() -> None:
    pendente = _pendente("a", "0.30,0.30")
    firme = _poste_em("b", "0.3123456789", "0.30")

    _, candidatos = _symbol_support(_caixa(0.299, 0.299, 0.301, 0.301), "base", (firme, pendente))
    carregado = json.loads(_symbol_support_candidates_json(candidatos))

    assert [item["proposta_id"] for item in carregado] == [str(pendente.id), str(firme.id)]
    assert {item["pagina_id"] for item in carregado} == {str(PAGINA)}
    assert carregado[0]["distancia_normalizada"] == 0.0
    assert carregado[1]["distancia_normalizada"] == round(0.3123456789 - 0.301, 6)


def test_json_sem_candidatos_e_lista_vazia() -> None:
    assert json.loads(_symbol_support_candidates_json(())) == []


# --- ancoragem: o atributo só nasce na disputa -------------------------------------------


def test_sem_discos_as_propostas_saem_identicas_e_sem_o_atributo() -> None:
    postes = (_poste("a", "P1", 0.30, 0.30), _poste("b", "P2", 0.34, 0.30))

    resultado = ancorar_postes_no_desenho(postes, ())

    assert resultado == postes
    assert all("poste_disco_sitios" not in _atributos(item) for item in resultado)


def test_disco_de_outra_pagina_nao_cria_o_atributo() -> None:
    postes = (_poste("a", "P1", 0.30, 0.30), _poste("b", "P2", 0.34, 0.30))

    resultado = ancorar_postes_no_desenho(postes, (_disco("d", 0.32, 0.30, pagina=OUTRA_PAGINA),))

    assert resultado == postes


def test_vencedor_da_disputa_resolvida_nao_grava_sitios() -> None:
    vencedor = _poste("a", "P1", 0.335, 0.30)
    perdedor = _poste("b", "P2", 0.365, 0.30)
    discos = (_disco("d1", 0.30, 0.30), _disco("d2", 0.345, 0.30))

    resultado = {item.id: item for item in ancorar_postes_no_desenho((vencedor, perdedor), discos)}

    assert _atributos(resultado[vencedor.id])["poste_ancorado_disco"] is True
    assert "poste_disco_sitios" not in _atributos(resultado[vencedor.id])
    assert "poste_disco_sitios" not in _atributos(resultado[perdedor.id])


def test_sitios_gravados_sao_lidos_de_volta_pelo_simbolo() -> None:
    primeiro = _poste("a", "P1", 0.30, 0.30)
    segundo = _poste("b", "P2", 0.34, 0.30)
    ancorados = ancorar_postes_no_desenho((primeiro, segundo), (_disco("d", 0.32, 0.30),))

    suporte, candidatos = _symbol_support(_caixa(0.319, 0.299, 0.321, 0.301), "base", ancorados)

    assert suporte is None
    assert {item.id for _, item in candidatos} == {primeiro.id, segundo.id}
    assert all(distancia == pytest.approx(0.0, abs=1e-6) for distancia, _ in candidatos)
