"""Costuras da E07.2.2.1 (testador de etapa): raio novo, fusão do ESTAI, poste pendente, versões.

Cada caso passa pela cadeia inteira (`reconcile_symbols`, `InterpretadorFichaPoste`, opção de
símbolos ligada) sobre a cena autoral de `symbol_grammars/dois_postes.py`: P1 em (0,30; 0,30) e
P2 em (0,34; 0,30). O raio de suporte é 0,020 medido até a caixa do símbolo (ou até a caixa de
suporte, a haste), a margem de empate é 0,004.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine
from tests.fixtures.symbol_grammars import dois_postes as cena
from tests.integration.test_ficha_poste_cadeia import _atributos, _elementos
from tests.integration.test_ficha_poste_cadeia_simbolos import (
    _FOLHA,
    _INTERRUPCAO,
    _candidatos,
    _dois_postes,
    _executar,
    _folha_disputada,
    _postes_por_nome,
    _reconciliar,
    _simbolos,
    _suportes,
    _transformador_do_catalogo,
)
from tests.integration.test_model_symbols_runner import _settings
from tests.unit.test_symbol_reconciliation import _policy

from zeny_project_handler.adapters.persistence import create_sqlite_engine, upgrade_database
from zeny_project_handler.application import symbol_reconciliation
from zeny_project_handler.application.interpretation_pipeline import SYMBOL_SEMANTICS_VERSION
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, EstadoRevisao, SituacaoProjeto
from zeny_project_handler.domain.symbols import ObservacaoSimbolo
from zeny_project_handler_server import symbol_execution
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

pytestmark = pytest.mark.integration


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    motor = create_sqlite_engine(tmp_path / "costuras-etapa.sqlite3")
    upgrade_database(motor)
    try:
        yield motor
    finally:
        motor.dispose()


# Caixa grande que contém os dois postes (x de 0,29 a 0,345, y de 0,2725 a 0,3275): a distância
# até a caixa é zero para os dois. Pela métrica antiga (centro 0,3175) o P1 venceria por 0,005.
_CAIXA_GRANDE = ("0.29", "0.2725")
_LADO_GRANDE = "0.055"
# Caixa de 0,042 que contém só o P1 (x de 0,28 a 0,322): o P2 fica a 0,018, acima da margem.
_CAIXA_SO_P1 = ("0.28", "0.279")
_LADO_SO_P1 = "0.042"
# Legado do estai com o centro (0,314; 0,300) dentro das duas caixas acima.
_CAIXA_LEGADO_NO_MEIO = ("0.310", "0.296")
# Estai do modelo (0,020) em x de 0,305 a 0,325: o P1 a 0,005 e o P2 a 0,015 da caixa.
_CAIXA_ESTAI_P1 = ("0.305", "0.290")
_LADO_ESTAI = "0.020"
_HASTE_AO_P2 = (("simbolo_limites_suporte", "[325.0, 299.0, 340.0, 301.0]"),)


def _estai_modelo(canto: tuple[str, str], lado: str) -> ObservacaoSimbolo:
    return cena.observacao(cena.PERFIL_MODELO, "ESTAI", canto, _FOLHA, lado=lado)


def _estai_legado(
    canto: tuple[str, str] = _CAIXA_LEGADO_NO_MEIO, atributos: Any = ()
) -> ObservacaoSimbolo:
    return cena.observacao(
        cena.PERFIL_LEGADO, "ESTAI", canto, _FOLHA, subtipo="ancora", atributos=atributos
    )


def _um_simbolo(resultado: Any, classe: str) -> Any:
    (simbolo,) = _simbolos(resultado, classe)
    return simbolo


# --- ESTAI fundido: a caixa do modelo e a haste do legado definem o poste --------------------


def test_estai_fundido_sem_haste_aponta_o_poste_pela_caixa_do_modelo(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    modelo = _estai_modelo(_CAIXA_ESTAI_P1, _LADO_ESTAI)
    simbolos = _reconciliar(
        (cena.PERFIL_MODELO, (modelo,)), (cena.PERFIL_LEGADO, (_estai_legado(),))
    )

    resultado = _executar(engine, catalogo_inicial, _dois_postes(catalogo_inicial), simbolos)

    postes = _postes_por_nome(resultado)
    estai = _um_simbolo(resultado, "ESTAI")
    assert len(simbolos.occurrences) == 1
    assert _atributos(estai)["suporte_proposta_id"] == str(postes["P1"])


def test_estai_fundido_com_haste_ate_o_p2_aponta_o_p2_e_nao_o_da_caixa(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    # A caixa do modelo está mais perto do P1 (0,005 contra 0,015), mas a haste do legado vai
    # até o P2: a medida é pela `support_geometry` da ocorrência fundida.
    modelo = _estai_modelo(_CAIXA_ESTAI_P1, _LADO_ESTAI)
    simbolos = _reconciliar(
        (cena.PERFIL_MODELO, (modelo,)),
        (cena.PERFIL_LEGADO, (_estai_legado(atributos=_HASTE_AO_P2),)),
    )

    resultado = _executar(engine, catalogo_inicial, _dois_postes(catalogo_inicial), simbolos)

    postes = _postes_por_nome(resultado)
    estai = _um_simbolo(resultado, "ESTAI")
    (ocorrencia,) = simbolos.occurrences
    assert ocorrencia.support_geometry is not None
    assert _atributos(estai)["suporte_proposta_id"] == str(postes["P2"])
    # a caixa reportada continua sendo a do modelo; a haste só mede o suporte
    assert float(estai.geometria.pontos[0].x) == pytest.approx(0.305, abs=1e-6)
    assert float(estai.geometria.pontos[1].x) == pytest.approx(0.325, abs=1e-6)
    assert _atributos(estai)["simbolo_geometria_suporte"] is not None


def test_estai_so_do_legado_longe_dos_postes_chega_ao_poste_pela_haste(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    # Símbolo cuja caixa está a mais de 0,020 de qualquer poste: só a haste alcança o P2.
    legado = _estai_legado(
        canto=("0.40", "0.296"),
        atributos=(("simbolo_limites_suporte", "[344.0, 299.0, 400.0, 301.0]"),),
    )
    # haste de 0,344 a 0,400: o P2 (0,34) fica a 0,004 da haste; o P1 a 0,044.
    simbolos = _reconciliar((cena.PERFIL_LEGADO, (legado,)))

    resultado = _executar(engine, catalogo_inicial, _dois_postes(catalogo_inicial), simbolos)

    postes = _postes_por_nome(resultado)
    estai = _um_simbolo(resultado, "ESTAI")
    assert _atributos(estai)["suporte_proposta_id"] == str(postes["P2"])


def test_estai_com_haste_que_encosta_nos_dois_postes_fica_pendente(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    haste = (("simbolo_limites_suporte", "[295.0, 299.0, 345.0, 301.0]"),)
    modelo = _estai_modelo(_CAIXA_ESTAI_P1, _LADO_ESTAI)
    simbolos = _reconciliar(
        (cena.PERFIL_MODELO, (modelo,)),
        (cena.PERFIL_LEGADO, (_estai_legado(atributos=haste),)),
    )

    resultado = _executar(engine, catalogo_inicial, _dois_postes(catalogo_inicial), simbolos)

    postes = _postes_por_nome(resultado)
    estai = _um_simbolo(resultado, "ESTAI")
    assert _atributos(estai)["suporte_proposta_id"] is None
    assert _atributos(estai)["associacao_pendente"] is True
    assert _candidatos(estai) == {str(postes["P1"]), str(postes["P2"])}


# --- métrica por caixa: símbolo grande entre dois postes ------------------------------------


def test_estai_fundido_de_caixa_grande_sobre_os_dois_postes_fica_pendente(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    simbolos = _reconciliar(
        (cena.PERFIL_MODELO, (_estai_modelo(_CAIXA_GRANDE, _LADO_GRANDE),)),
        (cena.PERFIL_LEGADO, (_estai_legado(),)),
    )

    resultado = _executar(engine, catalogo_inicial, _dois_postes(catalogo_inicial), simbolos)

    postes = _postes_por_nome(resultado)
    estai = _um_simbolo(resultado, "ESTAI")
    assert len(simbolos.occurrences) == 1
    assert _atributos(estai)["suporte_proposta_id"] is None
    assert _candidatos(estai) == {str(postes["P1"]), str(postes["P2"])}


def test_transformador_de_caixa_grande_sobre_os_dois_postes_fica_pendente(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    equipamento = _transformador_do_catalogo(catalogo_inicial)
    observacao = cena.observacao(
        cena.PERFIL_MODELO,
        "TRANSFORMADOR",
        _CAIXA_GRANDE,
        _FOLHA,
        lado=_LADO_GRANDE,
        situacao=SituacaoProjeto.INSTALAR,
        atributos=(
            ("tipo_catalogo_id", str(equipamento.id)),
            ("situacao_validada", True),
            ("quantidade_ativos", 1),
        ),
    )
    simbolos = _reconciliar(
        (cena.PERFIL_MODELO, (observacao,)),
        politica=_policy((cena.PERFIL_MODELO, "TRANSFORMADOR", "0.995", 90)),
    )

    resultado = _executar(engine, catalogo_inicial, _dois_postes(catalogo_inicial), simbolos)

    trafo = _um_simbolo(resultado, "TRANSFORMADOR")
    assert _atributos(trafo)["suporte_proposta_id"] is None
    assert _atributos(trafo)["associacao_pendente"] is True
    assert trafo.estado_revisao is not EstadoRevisao.CONFIRMADA
    assert _suportes(resultado, trafo) == []


def test_caixa_grande_que_contem_so_um_poste_vence_o_outro_acima_da_margem(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    simbolos = _reconciliar(
        (cena.PERFIL_MODELO, (_estai_modelo(_CAIXA_SO_P1, _LADO_SO_P1),)),
        (cena.PERFIL_LEGADO, (_estai_legado(),)),
    )

    resultado = _executar(engine, catalogo_inicial, _dois_postes(catalogo_inicial), simbolos)

    postes = _postes_por_nome(resultado)
    estai = _um_simbolo(resultado, "ESTAI")
    assert _atributos(estai)["suporte_proposta_id"] == str(postes["P1"])


# --- EQUIPAMENTO_INTERRUPCAO (disco de 14 pt) perto de dois postes ---------------------------


def test_interrupcao_de_disco_pequeno_entre_dois_postes_fica_pendente_com_os_dois_candidatos(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    # O disco de 14 pt (cerca de 0,006 de lado) a meio caminho dos dois: empate, sem suporte.
    observacao = cena.observacao(
        cena.PERFIL_MODELO, _INTERRUPCAO, ("0.317", "0.297"), _FOLHA, lado="0.006"
    )
    simbolos = _reconciliar((cena.PERFIL_MODELO, (observacao,)))

    resultado = _executar(engine, catalogo_inicial, _dois_postes(catalogo_inicial), simbolos)

    postes = _postes_por_nome(resultado)
    simbolo = _um_simbolo(resultado, _INTERRUPCAO)
    assert _atributos(simbolo)["suporte_proposta_id"] is None
    assert _atributos(simbolo)["associacao_pendente"] is True
    assert _candidatos(simbolo) == {str(postes["P1"]), str(postes["P2"])}


def _interrupcao_fundida_com_legado_de_outra_classe(canto: tuple[str, str]) -> Any:
    modelo = cena.observacao(cena.PERFIL_MODELO, _INTERRUPCAO, canto, _FOLHA, lado="0.006")
    legado = cena.observacao(cena.PERFIL_LEGADO, "ATERRAMENTO", canto, _FOLHA, lado="0.006")
    # mesma primitiva e mesma caixa: `_same_occurrence` não olha a classe e funde
    legado = replace(legado, primitivas=modelo.primitivas)
    return _reconciliar((cena.PERFIL_MODELO, (modelo,)), (cena.PERFIL_LEGADO, (legado,)))


def test_interrupcao_fundida_com_legado_de_outra_classe_fica_sem_classe_sem_relacao_e_sem_ativo(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    # R-E06.3.5-6 na cadeia: junto do P1 (o disco a 0,004), a fusão com o ATERRAMENTO do legado
    # deixa a ocorrência sem classe única; ela não pode sair com suporte nem virar ativo.
    simbolos = _interrupcao_fundida_com_legado_de_outra_classe(("0.304", "0.297"))
    assert len(simbolos.occurrences) == 1
    assert len(simbolos.occurrences[0].observations) == 2

    resultado = _executar(engine, catalogo_inicial, _dois_postes(catalogo_inicial), simbolos)

    (proposta,) = [
        item for item in resultado.elementos if "origem_simbolo_ocorrencia_id" in _atributos(item)
    ]
    atributos = _atributos(proposta)
    postes = _postes_por_nome(resultado)
    # o disco está a 0,004 do P1: o suporte geométrico é o P1, nunca o P2; sem classe única a
    # ocorrência não é candidata a ativo e não gera a relação INSTALADO_EM
    assert atributos["suporte_proposta_id"] == str(postes["P1"])
    assert _suportes(resultado, proposta) == []
    assert proposta.estado_revisao is not EstadoRevisao.CONFIRMADA
    assert atributos.get("simbolo_classe") is None


def test_interrupcao_fundida_com_legado_nao_pareia_como_estai(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    simbolos = _interrupcao_fundida_com_legado_de_outra_classe(("0.304", "0.297"))

    (ocorrencia,) = simbolos.occurrences

    assert {a.classe for a in ocorrencia.alternatives} == {_INTERRUPCAO, "ATERRAMENTO"}
    assert ocorrencia.decision == "review"


# --- poste pendente: estrutura ligada e símbolo sem suporte no mesmo poste --------------------


def test_raio_novo_poste_pendente_e_fusao_do_estai_na_mesma_pagina(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    # Folha com disco disputado entre P1 e P2, estrutura U1 ligada ao P1 e um estai fundido sobre
    # o disco: sem suporte, os dois postes pendentes como candidatos, estrutura ainda ligada.
    modelo = _estai_modelo(("0.310", "0.290"), "0.020")
    legado = _estai_legado(canto=("0.316", "0.296"))
    simbolos = _reconciliar((cena.PERFIL_MODELO, (modelo,)), (cena.PERFIL_LEGADO, (legado,)))

    resultado = _executar(engine, catalogo_inicial, _folha_disputada(catalogo_inicial), simbolos)

    postes = _postes_por_nome(resultado)
    estai = _um_simbolo(resultado, "ESTAI")
    (estrutura,) = _elementos(resultado, CategoriaElemento.ESTRUTURA_MT)
    assert len(simbolos.occurrences) == 1
    assert _atributos(estai)["suporte_proposta_id"] is None
    assert _atributos(estai)["associacao_pendente"] is True
    assert {str(postes["P1"]), str(postes["P2"])} <= _candidatos(estai)
    ligacoes = [
        (item.tipo_relacao, item.destino_referencia_id)
        for item in resultado.relacoes
        if item.origem_referencia_id == estrutura.id
    ]
    assert ligacoes == [("INSTALADA_EM", postes["P1"])]


# --- versões na identidade da execução --------------------------------------------------------


def test_identidade_da_execucao_leva_a_versao_do_interpretador_e_a_semantica_de_simbolos(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    observacao = cena.observacao(
        cena.PERFIL_MODELO, _INTERRUPCAO, cena.CAIXA_PERTO_ESQUERDO, _FOLHA
    )
    simbolos = _reconciliar((cena.PERFIL_MODELO, (observacao,)))

    resultado = _executar(engine, catalogo_inicial, _dois_postes(catalogo_inicial), simbolos)

    parametros = dict(resultado.execucao.parametros)
    assert SYMBOL_SEMANTICS_VERSION == "e07-2-2-symbol-support-3"
    assert parametros["semantica_simbolos_versao"] == "e07-2-2-symbol-support-3"
    assert resultado.execucao.versao_metodo == "27.0"


def test_assinatura_do_runner_muda_com_o_digest_de_symbol_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuracao = _settings(tmp_path / "dados")
    original = SymbolCompositionRunner(configuracao).signature
    digest_original = symbol_execution._module_digest
    visto: list[str] = []

    def digest(alvo: Any) -> str:
        if alvo is symbol_reconciliation:
            visto.append(alvo.__name__)
            return "alterado"
        return str(digest_original(alvo))

    monkeypatch.setattr(symbol_execution, "_module_digest", digest)

    assert SymbolCompositionRunner(configuracao).signature != original
    assert visto == [symbol_reconciliation.__name__]


# --- opção desligada --------------------------------------------------------------------------


def _impressao(resultado: Any) -> list[str]:
    """Elementos sem o marcador de reanálise (que só a opção ligada grava), em ordem estável."""
    return sorted(
        repr(
            (
                e.categoria,
                e.geometria,
                sorted(
                    (k, v)
                    for k, v in e.atributos_sugeridos
                    if k != "reconciliacao_reanalise_pendente"
                ),
            )
        )
        for e in resultado.elementos
    )


def test_sem_simbolos_equivale_a_reconciliacao_vazia_exceto_pela_identidade_de_simbolos(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    folha = _folha_disputada(catalogo_inicial)

    sem = _executar(engine, catalogo_inicial, folha, None)
    com_vazia = _executar(engine, catalogo_inicial, folha, _reconciliar())

    assert _simbolos(sem) == _simbolos(com_vazia) == []
    assert _impressao(sem) == _impressao(com_vazia)
    assert sorted(r.tipo_relacao for r in sem.relacoes) == sorted(
        r.tipo_relacao for r in com_vazia.relacoes
    )
    assert not {chave for chave, _ in sem.execucao.parametros if "simbolo" in chave}
