"""Ataques à onda final da E02: contagens de postes sem geometria e símbolos órfãos."""

from __future__ import annotations

from typing import Any

import pytest
from scripts.benchmark_ficha_poste import ficha_predita
from scripts.ficha_poste import validar_ficha
from tests.unit.test_benchmark_ficha_poste_adversarial import SHA, _Cenario, _variante

from zeny_project_handler.domain.catalog import CatalogoTecnico

ESTAI = {"simbolo_classe": "ESTAI"}


def _ficha(cenario: _Cenario, atributos: dict[Any, dict[str, Any]]) -> dict[str, Any]:
    ficha = ficha_predita(_variante(cenario.montar(), atributos), SHA, native_only=True)
    assert validar_ficha(ficha) == []
    return ficha


def test_sem_ocorrencia_as_chaves_novas_ficam_ausentes(catalogo_inicial: CatalogoTecnico) -> None:
    cenario = _Cenario(catalogo_inicial)
    poste = cenario.poste(identificador_operacional="A")
    equipamento = cenario.equipamento(
        poste, geometria=cenario.caixa(cenario.p1, ("0.1", "0.1"), ("0.15", "0.15"))
    )
    extras = _ficha(cenario, {equipamento.id: ESTAI})["atributos_extras"]
    assert "postes_sem_geometria" not in extras
    assert "simbolos_de_poste_fora_da_ficha" not in extras
    assert extras == {
        "equipamentos_sem_simbolo": 0,
        "simbolos_fora_do_inventario": 0,
        "simbolos_sem_area": 0,
    }


def test_um_poste_sem_geometria_sem_equipamento_conta_so_o_poste(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    cenario.poste(identificador_operacional="COM")
    cenario.poste(identificador_operacional="SEM", geometria=None)
    ficha = _ficha(cenario, {})
    assert [p["identificador"] for p in ficha["postes"]] == ["COM"]
    assert ficha["atributos_extras"]["postes_sem_geometria"] == 1
    assert "simbolos_de_poste_fora_da_ficha" not in ficha["atributos_extras"]


def test_varios_postes_sem_geometria_e_varios_orfaos_somam_exato(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    cenario.poste(identificador_operacional="COM")
    sem1 = cenario.poste(identificador_operacional="S1", geometria=None)
    sem2 = cenario.poste(identificador_operacional="S2", geometria=None)
    sem3 = cenario.poste(identificador_operacional="S3", geometria=None)
    atributos: dict[Any, dict[str, Any]] = {}
    # 3 orfaos com classe (um fora do inventario: poste ausente vence), 2 orfaos sem classe
    for poste, valores in ((sem1, ESTAI), (sem2, ESTAI), (sem3, {"simbolo_classe": "INEXISTENTE"})):
        atributos[cenario.equipamento(poste).id] = valores
    for poste in (sem1, sem2):
        atributos[cenario.equipamento(poste).id] = {}
    extras = _ficha(cenario, atributos)["atributos_extras"]
    assert extras["postes_sem_geometria"] == 3
    assert extras["simbolos_de_poste_fora_da_ficha"] == 3
    assert extras["equipamentos_sem_simbolo"] == 2
    assert extras["simbolos_fora_do_inventario"] == 0
    assert extras["simbolos_sem_area"] == 0


def test_equipamento_sem_classe_em_poste_fora_da_ficha_nao_vira_simbolo_fora_da_ficha(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    sem = cenario.poste(identificador_operacional="SEM", geometria=None)
    equipamento = cenario.equipamento(sem)
    extras = _ficha(cenario, {equipamento.id: {}})["atributos_extras"]
    assert extras["equipamentos_sem_simbolo"] == 1
    assert "simbolos_de_poste_fora_da_ficha" not in extras
    assert extras["postes_sem_geometria"] == 1


def test_equipamento_sem_nenhuma_proposta_tambem_conta_como_sem_simbolo(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    sem = cenario.poste(identificador_operacional="SEM", geometria=None)
    cenario.equipamento(sem)
    extras = _ficha(cenario, {})["atributos_extras"]
    assert extras["equipamentos_sem_simbolo"] == 1
    assert "simbolos_de_poste_fora_da_ficha" not in extras


@pytest.mark.parametrize("com_geometria", [0, 1, 4])
def test_postes_com_geometria_nunca_entram_na_contagem_de_sem_geometria(
    catalogo_inicial: CatalogoTecnico, com_geometria: int
) -> None:
    cenario = _Cenario(catalogo_inicial)
    for indice in range(com_geometria):
        cenario.poste(identificador_operacional=f"P{indice}")
    ficha = _ficha(cenario, {})
    assert len(ficha["postes"]) == com_geometria
    assert "postes_sem_geometria" not in ficha["atributos_extras"]
