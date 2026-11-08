"""Ataque ao vão composto da ``propostas-v2``: ordem, determinismo, bordas e entradas hostis."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from scripts.benchmark_ficha_poste import VERSAO_EXTRACAO_PROPOSTAS_V2
from scripts.ficha_predita_propostas import ficha_predita_propostas
from tests.unit.test_ficha_predita_propostas import SHA_QUALQUER, _Cena, _decimal
from tests.unit.test_ficha_predita_propostas_v2 import (
    CABO,
    V1,
    _cabo,
    _ficha,
    _poste,
    _rotulos,
)

from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    OrigemComprimentoVao,
)
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

_SEM_SITUACAO: dict[str, Any] = {"situacao_projeto": None}


def _postes_com_coordenadas(cena: _Cena) -> tuple[Any, Any]:
    p1 = cena.elemento(
        CategoriaElemento.POSTE,
        codigo="POSTE",
        atributos={"coordenada_leste": 0, "coordenada_norte": 0},
    )
    p2 = cena.elemento(
        CategoriaElemento.POSTE,
        codigo="POSTE",
        x=0.6,
        atributos={"coordenada_leste": 30, "coordenada_norte": 40},
    )
    return p1, p2


def _ficha_com_extracao(cena: _Cena, extracao: object) -> dict[str, Any]:
    variante = cena.variante()
    variante["extraction"] = extracao
    return ficha_predita_propostas(
        variante, SHA_QUALQUER, native_only=True, versao=VERSAO_EXTRACAO_PROPOSTAS_V2
    )


def _evidencia(cena: _Cena, evidencia_id: UUID, x: float, y: float) -> SimpleNamespace:
    return SimpleNamespace(
        id=evidencia_id,
        geometria=GeometriaDocumento.caixa(
            cena.pagina_id,
            PontoNormalizado(_decimal(x), _decimal(y)),
            PontoNormalizado(_decimal(x + 0.05), _decimal(y + 0.05)),
        ),
    )


# --- ordem pelo rótulo -------------------------------------------------------------------------


def test_v2_ordena_por_y_antes_de_x(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    acima_a_direita, abaixo_a_esquerda = (uuid4(), 0.9, 0.1), (uuid4(), 0.1, 0.2)
    _cabo(cena, "B", p1, p2, abaixo_a_esquerda)
    _cabo(cena, "A", p1, p2, acima_a_direita)

    ficha = _ficha(cena, rotulos=_rotulos(acima_a_direita, abaixo_a_esquerda))

    assert [vao["cabo"] for vao in ficha["vaos"]] == ["A / B"]


@pytest.mark.parametrize("inverter", [False, True], ids=["ordem-direta", "ordem-invertida"])
def test_v2_empate_total_de_posicao_desempata_pelo_codigo(
    catalogo_inicial: CatalogoTecnico, inverter: bool
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    mesmo = (uuid4(), 0.3, 0.3)
    codigos = ["B", "A", "C"]
    for codigo in codigos[:: -1 if inverter else 1]:
        _cabo(cena, codigo, p1, p2, mesmo)

    ficha = _ficha(cena, rotulos=_rotulos(mesmo))

    assert [vao["cabo"] for vao in ficha["vaos"]] == ["A / B / C"]


@pytest.mark.parametrize("inverter", [False, True], ids=["ordem-direta", "ordem-invertida"])
def test_v2_rotulos_distintos_de_mesma_caixa_desempatam_pelo_codigo(
    catalogo_inicial: CatalogoTecnico, inverter: bool
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    um, outro = (uuid4(), 0.3, 0.3), (uuid4(), 0.3, 0.3)
    pares = [("B", um), ("A", outro)]
    for codigo, rotulo in pares[:: -1 if inverter else 1]:
        _cabo(cena, codigo, p1, p2, rotulo)

    ficha = _ficha(cena, rotulos=_rotulos(um, outro))

    assert [vao["cabo"] for vao in ficha["vaos"]] == ["A / B"]


def test_v2_cabos_sem_rotulo_ordenam_por_codigo_nao_pela_entrada(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    for codigo in ("C", "A", "B"):
        _cabo(cena, codigo, p1, p2)

    assert [vao["cabo"] for vao in _ficha(cena)["vaos"]] == ["A / B / C"]


def test_v2_ordem_do_cabo_usa_codigo_normalizado_no_desempate(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    _cabo(cena, "N-   (1N2)", p1, p2)
    _cabo(cena, "N-(1N1)", p1, p2)

    assert [vao["cabo"] for vao in _ficha(cena)["vaos"]] == ["N-(1N1) / N-(1N2)"]


# --- determinismo de de/para e dos demais campos ----------------------------------------------


def _cena_a_b_e_b_a(catalogo: CatalogoTecnico, ids_relacoes: list[UUID]) -> tuple[_Cena, Any, Any]:
    cena = _Cena(catalogo)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    primeiro, segundo = (uuid4(), 0.3, 0.1), (uuid4(), 0.3, 0.5)
    _cabo(cena, "A", p1, p2, primeiro)  # relações: p1, p2
    _cabo(cena, "B", p2, p1, segundo)  # relações: p2, p1
    cena.relacoes = [
        replace(relacao, id=novo_id)
        for relacao, novo_id in zip(cena.relacoes, ids_relacoes, strict=True)
    ]
    return cena, p1, _rotulos(primeiro, segundo)


def test_v2_de_para_do_vao_composto_nao_depende_dos_ids_das_relacoes(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    """Os mesmos cabos, rótulos e postes com ids de relação trocados não podem inverter o vão."""
    ids = sorted(uuid4() for _ in range(4))
    cena, _, rotulos = _cena_a_b_e_b_a(catalogo_inicial, ids)
    crescente = _ficha(cena, rotulos=rotulos)["vaos"][0]
    # Mesma cena (mesmos postes e cabos); só os ids das relações ficam em ordem inversa.
    cena.relacoes = [
        replace(relacao, id=novo_id)
        for relacao, novo_id in zip(cena.relacoes, reversed(ids), strict=True)
    ]
    decrescente = _ficha(cena, rotulos=rotulos)["vaos"][0]

    assert (crescente["de"], crescente["para"]) == (decrescente["de"], decrescente["para"])


@pytest.mark.parametrize("inverter", [False, True], ids=["ordem-direta", "ordem-invertida"])
def test_v2_vao_composto_nao_depende_da_ordem_dos_elementos(
    catalogo_inicial: CatalogoTecnico, inverter: bool
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _postes_com_coordenadas(cena)
    a, b = (uuid4(), 0.3, 0.1), (uuid4(), 0.3, 0.5)
    _cabo(cena, "A", p1, p2, a, atributos={"revisao_tecnica_pendente": True})
    _cabo(cena, "B", p1, p2, b, atributos={"comprimento_m": "12.5"})
    if inverter:
        cena.elementos.reverse()

    vao = _ficha(cena, rotulos=_rotulos(a, b))["vaos"][0]

    assert vao["cabo"] == "A / B"
    assert vao["comprimento_m"] == 12.5
    assert vao["pendentes"] == ["cabo", "comprimento_m"]


@pytest.mark.parametrize("inverter", [False, True], ids=["ordem-direta", "ordem-invertida"])
def test_v2_cabos_totalmente_empatados_com_comprimentos_distintos_sao_deterministicos(
    catalogo_inicial: CatalogoTecnico, inverter: bool
) -> None:
    """Mesmo código e mesmo rótulo: o resultado não pode depender da ordem de chegada."""
    cena = _Cena(catalogo_inicial)
    p1, p2 = _postes_com_coordenadas(cena)
    mesmo = (uuid4(), 0.3, 0.3)
    _cabo(cena, "A", p1, p2, mesmo, atributos={"comprimento_m": "10"})
    _cabo(cena, "A", p1, p2, mesmo, atributos={"comprimento_m": "20"})
    if inverter:
        cena.elementos.reverse()

    vao = _ficha(cena, rotulos=_rotulos(mesmo))["vaos"][0]

    assert vao["comprimento_m"] == 10.0


# --- evidencia_rotulo_id inválido, ausente ou de evidência sem geometria -----------------------


@pytest.mark.parametrize(
    "rotulo_id",
    [None, 7, "", "   ", "nao-e-uuid", "00000000-0000-0000-0000-000000000000"],
    ids=["none", "inteiro", "vazio", "branco", "nao-uuid", "uuid-inexistente"],
)
def test_v2_evidencia_de_rotulo_invalida_vai_depois_dos_rotulados(
    catalogo_inicial: CatalogoTecnico, rotulo_id: object
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    rotulado = (uuid4(), 0.9, 0.9)
    _cabo(cena, "A", p1, p2, atributos={"evidencia_rotulo_id": rotulo_id})
    _cabo(cena, "B", p1, p2, rotulado)

    ficha = _ficha(cena, rotulos=_rotulos(rotulado))

    assert [vao["cabo"] for vao in ficha["vaos"]] == ["B / A"]


def test_v2_sem_chave_de_rotulo_no_atributo_vai_depois(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    rotulado = (uuid4(), 0.9, 0.9)
    _cabo(cena, "A", p1, p2)
    _cabo(cena, "B", p1, p2, rotulado)

    assert [v["cabo"] for v in _ficha(cena, rotulos=_rotulos(rotulado))["vaos"]] == ["B / A"]


@pytest.mark.parametrize(
    "extracao", ["ausente", None, SimpleNamespace(), SimpleNamespace(evidencias=())]
)
def test_v2_sem_evidencias_na_variante_ordena_so_por_codigo(
    catalogo_inicial: CatalogoTecnico, extracao: object
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    _cabo(cena, "B", p1, p2, (uuid4(), 0.1, 0.1))
    _cabo(cena, "A", p1, p2, (uuid4(), 0.9, 0.9))
    variante = cena.variante()
    if extracao != "ausente":
        variante["extraction"] = extracao

    ficha = ficha_predita_propostas(
        variante, SHA_QUALQUER, native_only=True, versao=VERSAO_EXTRACAO_PROPOSTAS_V2
    )

    assert [vao["cabo"] for vao in ficha["vaos"]] == ["A / B"]


@pytest.mark.parametrize(
    "geometria",
    [None, SimpleNamespace(pontos=())],
    ids=["geometria-none", "geometria-sem-pontos"],
)
def test_v2_evidencia_de_rotulo_sem_geometria_nao_derruba_a_ficha(
    catalogo_inicial: CatalogoTecnico, geometria: object
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    sem_caixa, com_caixa = uuid4(), uuid4()
    _cabo(cena, "A", p1, p2, (sem_caixa, 0, 0))
    _cabo(cena, "B", p1, p2, (com_caixa, 0, 0))
    extracao = SimpleNamespace(
        evidencias=(
            SimpleNamespace(id=sem_caixa, geometria=geometria),
            _evidencia(cena, com_caixa, 0.5, 0.5),
        )
    )

    ficha = _ficha_com_extracao(cena, extracao)

    assert [vao["cabo"] for vao in ficha["vaos"]] == ["B / A"]


# --- pendentes, comprimento e origem -----------------------------------------------------------


def test_v2_pendentes_do_vao_composto_sao_a_uniao_ordenada_sem_repeticao(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _postes_com_coordenadas(cena)
    _cabo(cena, "A", p1, p2, atributos={"revisao_tecnica_pendente": True})
    _cabo(cena, "B", p1, p2, atributos={"revisao_tecnica_pendente": True})
    _cabo(cena, "C", p1, p2)

    assert _ficha(cena)["vaos"][0]["pendentes"] == ["cabo", "comprimento_m"]


def test_v2_pendentes_vazios_quando_nenhum_cabo_e_pendente(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _postes_com_coordenadas(cena)
    _cabo(cena, "A", p1, p2)
    _cabo(cena, "B", p1, p2)

    assert _ficha(cena)["vaos"][0]["pendentes"] == []


def test_v2_pendente_por_poste_pendente_entra_na_uniao(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _postes_com_coordenadas(cena)
    cena.elementos[0] = replace(p1, estado_revisao=EstadoRevisao.CONFLITANTE)
    _cabo(cena, "A", cena.elementos[0], p2)
    _cabo(cena, "B", cena.elementos[0], p2, atributos={"comprimento_m": "5"})

    vao = _ficha(cena)["vaos"][0]

    assert "comprimento_m" in vao["pendentes"]


def test_v2_primeiro_anotado_na_ordem_do_rotulo_vence_outro_anotado(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _postes_com_coordenadas(cena)
    alto, baixo = (uuid4(), 0.3, 0.1), (uuid4(), 0.3, 0.5)
    _cabo(cena, "A", p1, p2, baixo, atributos={"comprimento_m": "99"})
    _cabo(cena, "B", p1, p2, alto, atributos={"comprimento_m": "7"})

    vao = _ficha(cena, rotulos=_rotulos(alto, baixo))["vaos"][0]

    assert vao["cabo"] == "B / A"
    assert vao["comprimento_m"] == 7.0


def test_v2_anotado_sem_rotulo_vence_coordenadas_de_cabo_rotulado(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _postes_com_coordenadas(cena)
    rotulado = (uuid4(), 0.1, 0.1)
    _cabo(cena, "A", p1, p2, rotulado)
    _cabo(cena, "B", p1, p2, atributos={"comprimento_m": "3"})

    vao = _ficha(cena, rotulos=_rotulos(rotulado))["vaos"][0]

    assert vao["comprimento_m"] == 3.0
    assert vao["atributos_extras"]["origem_comprimento"] == (
        OrigemComprimentoVao.ANOTACAO_DESENHO.value
    )


@pytest.mark.parametrize("invalido", ["0", "-3", "abc", "nan", "inf", "", None])
def test_v2_anotado_invalido_cai_para_coordenadas(
    catalogo_inicial: CatalogoTecnico, invalido: object
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _postes_com_coordenadas(cena)
    _cabo(cena, "A", p1, p2, atributos={"comprimento_m": invalido})
    _cabo(cena, "B", p1, p2, atributos={"comprimento_m": invalido})

    vao = _ficha(cena)["vaos"][0]

    assert vao["comprimento_m"] == 50.0
    assert vao["atributos_extras"]["origem_comprimento"] == OrigemComprimentoVao.COORDENADAS.value


def test_v2_sem_nenhum_comprimento_vao_fica_sem_comprimento_e_sem_origem(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    _cabo(cena, "A", p1, p2)
    _cabo(cena, "B", p1, p2)

    vao = _ficha(cena)["vaos"][0]

    assert vao["comprimento_m"] is None
    assert vao["atributos_extras"]["origem_comprimento"] is None


# --- fronteiras do agrupamento -----------------------------------------------------------------


def test_v2_situacao_nula_nao_funde_com_situacao_definida(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    _cabo(cena, "A", p1, p2)
    sem_situacao = _cabo(cena, "B", p1, p2)
    cena.elementos[-1] = replace(sem_situacao, **_SEM_SITUACAO)

    assert sorted(vao["cabo"] for vao in _ficha(cena)["vaos"]) == ["A", "B"]


def test_v2_dois_cabos_sem_situacao_no_mesmo_par_se_fundem(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    for codigo in ("A", "B"):
        cabo = _cabo(cena, codigo, p1, p2)
        cena.elementos[-1] = replace(cabo, **_SEM_SITUACAO)

    assert [vao["cabo"] for vao in _ficha(cena)["vaos"]] == ["A / B"]


def test_v2_pares_diferentes_nao_se_fundem(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2, p3 = _poste(cena), _poste(cena, 0.5), _poste(cena, 0.8)
    _cabo(cena, "A", p1, p2)
    _cabo(cena, "B", p1, p3)
    _cabo(cena, "C", p2, p3)

    assert sorted(vao["cabo"] for vao in _ficha(cena)["vaos"]) == ["A", "B", "C"]


def test_v2_cabo_com_tres_postes_nao_vira_vao_nem_funde(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2, p3 = _poste(cena), _poste(cena, 0.5), _poste(cena, 0.8)
    triplo = cena.elemento(CABO, codigo="T")
    for poste in (p1, p2, p3):
        cena.relacao(triplo, poste, "CONECTA")
    _cabo(cena, "A", p1, p2)

    ficha = _ficha(cena)

    assert [vao["cabo"] for vao in ficha["vaos"]] == ["A"]
    assert ficha["atributos_extras"]["cabos_sem_vao"] == 1


def test_v2_cabo_rejeitado_fica_fora_da_uniao(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    _cabo(cena, "A", p1, p2)
    rejeitado = _cabo(cena, "Z", p1, p2)
    cena.elementos[-1] = replace(rejeitado, estado_revisao=EstadoRevisao.REJEITADA)

    ficha = _ficha(cena)

    assert [vao["cabo"] for vao in ficha["vaos"]] == ["A"]
    assert ficha["atributos_extras"].get("cabos_sem_vao", 0) == 0


def test_v2_cabo_so_rejeitado_nao_gera_vao(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    cabo = _cabo(cena, "Z", p1, p2)
    cena.elementos[-1] = replace(cabo, estado_revisao=EstadoRevisao.REJEITADA)

    assert _ficha(cena)["vaos"] == []


def test_v2_relacao_rejeitada_nao_liga_cabo_ao_par(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2, p3 = _poste(cena), _poste(cena, 0.5), _poste(cena, 0.8)
    _cabo(cena, "A", p1, p2)
    b = cena.elemento(CABO, codigo="B")
    cena.relacao(b, p1, "CONECTA")
    cena.relacao(b, p2, "CONECTA")
    cena.relacao(b, p3, "CONECTA", estado=EstadoRevisao.REJEITADA)

    assert [vao["cabo"] for vao in _ficha(cena)["vaos"]] == ["A / B"]


def test_v2_par_a_b_e_b_a_funde_mesmo_com_relacao_repetida(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    a = _cabo(cena, "A", p1, p2)
    cena.relacao(a, p1, "CONECTA")  # relação duplicada para o mesmo poste
    _cabo(cena, "B", p2, p1)

    assert [vao["cabo"] for vao in _ficha(cena)["vaos"]] == ["A / B"]


def test_v2_vao_composto_valida_contra_o_esquema_da_ficha(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    from scripts.ficha_poste import validar_ficha

    cena = _Cena(catalogo_inicial)
    p1, p2 = _postes_com_coordenadas(cena)
    _cabo(cena, "A", p1, p2, atributos={"revisao_tecnica_pendente": True})
    _cabo(cena, "B", p2, p1, atributos={"comprimento_m": "4"})
    _cabo(cena, None, p1, p2)

    assert validar_ficha(_ficha(cena)) == []


# --- v1 intocada -------------------------------------------------------------------------------


class _ExtracaoQueNaoPodeSerLida:
    @property
    def evidencias(self) -> object:
        raise AssertionError("a v1 não pode ler as evidências da extração")


def test_v1_nao_le_evidencias_nem_reordena_cabos(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    alto, baixo = (uuid4(), 0.3, 0.1), (uuid4(), 0.3, 0.5)
    _cabo(cena, "B", p1, p2, baixo)
    _cabo(cena, "A", p1, p2, alto)

    ficha = ficha_predita_propostas(
        {**cena.variante(), "extraction": _ExtracaoQueNaoPodeSerLida()},
        SHA_QUALQUER,
        native_only=True,
        versao=V1,
    )

    assert [vao["cabo"] for vao in ficha["vaos"]] == ["B", "A"]


def test_v1_nao_funde_a_b_e_b_a_nem_normaliza(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    _cabo(cena, "N- (1N2)", p1, p2)
    _cabo(cena, "N- (1N2)", p2, p1)

    assert [vao["cabo"] for vao in _ficha(cena, versao=V1)["vaos"]] == ["N- (1N2)", "N- (1N2)"]
