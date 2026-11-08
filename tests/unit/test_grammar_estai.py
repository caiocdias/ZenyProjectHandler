"""Gramática `forked_stem` (ESTAI): positivos e negativos do Review Focus da E06.3.4."""

from __future__ import annotations

from itertools import pairwise
from typing import Any

import pytest
from tests.fixtures.symbol_grammars.estai import (
    BASE,
    BRANCO,
    CINZA,
    DENTE,
    GASTO_DE_TRES_ESTAIS,
    GRAMATICAS_ESTAI,
    PRETO,
    ROXO,
    VERDE,
    VERMELHO,
    centro_do_garfo,
    circulo,
    estai_com_circulo,
    fino,
    garfo,
    pagina_estai,
    polar,
    vertice_de,
    x_sobre,
)
from tests.fixtures.symbol_grammars.paginas import poligono, texto

from zeny_project_handler.adapters.analysis.declarative_symbols import carregar_pacotes
from zeny_project_handler.adapters.analysis.drawing_model import grammar_estai
from zeny_project_handler.adapters.analysis.drawing_model.grammar_estai import (
    casa_estai,
    estai_candidatos,
)
from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import MarcasDaPagina
from zeny_project_handler.adapters.analysis.drawing_model.model import Caminho, Estilo
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    TetoGramaticasExcedido,
    contexto_gramaticas,
)


def _grupos(caminhos: list[Caminho], textos: tuple[Any, ...] = ()) -> dict[str, int]:
    contexto = contexto_gramaticas(pagina_estai(caminhos, textos=textos))
    candidatos = estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))
    return {
        nome: len(casa_estai(contexto, gramatica, candidatos=candidatos))
        for nome, gramatica in GRAMATICAS_ESTAI.items()
    }


NENHUM = {"existente": 0, "instalar": 0, "retirar": 0}


@pytest.mark.parametrize("cor", [PRETO, CINZA], ids=["preto", "cinza"])
def test_garfo_preto_ou_cinza_sem_marca_casa_so_existente(cor: Any) -> None:
    assert _grupos(garfo(cor=cor)) == {"existente": 1, "instalar": 0, "retirar": 0}


def test_verde_com_circulo_casa_so_instalar() -> None:
    assert _grupos(estai_com_circulo()) == {"existente": 0, "instalar": 1, "retirar": 0}


def test_x_sobre_circulo_casa_so_retirar() -> None:
    caminhos = [*estai_com_circulo(), *x_sobre(centro_do_garfo())]
    assert _grupos(caminhos) == {"existente": 0, "instalar": 0, "retirar": 1}


@pytest.mark.parametrize("cor", [PRETO, VERMELHO], ids=["preto", "vermelho"])
def test_x_sobre_garfo_sem_circulo_casa_so_retirar(cor: Any) -> None:
    caminhos = [*garfo(cor=cor), *x_sobre(centro_do_garfo())]
    assert _grupos(caminhos) == {"existente": 0, "instalar": 0, "retirar": 1}


@pytest.mark.parametrize("graus", [0, 37, 90, 145, 222, 300])
def test_rotacoes_casam(graus: float) -> None:
    assert _grupos(garfo(graus))["existente"] == 1


def test_dois_estais_opostos_sao_dois_casamentos() -> None:
    assert _grupos([*garfo(20.0), *garfo(200.0)])["existente"] == 2


def test_caixas_vizinhas_nao_trocam_componentes() -> None:
    caminhos = [*estai_com_circulo(0.0), *estai_com_circulo(180.0)]
    contexto = contexto_gramaticas(pagina_estai(caminhos))
    candidatos = estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))
    achados = casa_estai(contexto, GRAMATICAS_ESTAI["instalar"], candidatos=candidatos)
    assert len(achados) == 2
    conjuntos = [{ancora, *comp} for _, ancora, comp in achados]
    assert conjuntos[0].isdisjoint(conjuntos[1])
    assert all(len(c) == 4 for c in conjuntos)


def test_caixa_e_envolvente_e_haste_inteira_e_o_x_fica_de_fora() -> None:
    """R-E06.3.4-3: mediu melhor IoU com a haste inteira; o X não entra na caixa."""
    centro = centro_do_garfo()
    raio = DENTE * 0.8
    caminhos = [*estai_com_circulo(), *x_sobre(centro, meio=raio * 1.5)]
    contexto = contexto_gramaticas(pagina_estai(caminhos))
    candidatos = estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))
    assert len(candidatos) == 1
    assert candidatos[0].caixa == pytest.approx(
        (BASE[0], BASE[1] - raio, centro[0] + raio, BASE[1] + raio), abs=0.5
    )


def test_caixa_sem_envolvente_cobre_garfo_e_haste() -> None:
    contexto = contexto_gramaticas(pagina_estai(garfo()))
    candidatos = estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))
    pontas_x = vertice_de()[0] + DENTE * 0.8988
    assert candidatos[0].caixa[0] == pytest.approx(BASE[0], abs=0.01)
    assert candidatos[0].caixa[2] == pytest.approx(pontas_x, abs=0.2)


def test_desenho_sobreposto_em_duas_cores_e_um_estai() -> None:
    caminhos = [
        *garfo(cor=VERDE),
        circulo(centro_do_garfo(), DENTE * 0.8, VERDE),
        *garfo(cor=VERMELHO),
    ]
    caminhos += x_sobre(centro_do_garfo())
    assert _grupos(caminhos) == {"existente": 0, "instalar": 0, "retirar": 1}


def test_garfo_redesenhado_igual_e_um_estai() -> None:
    assert _grupos([*garfo(), *garfo()])["existente"] == 1


def test_seta_nao_casa() -> None:
    """Farpas voltadas para a linha: fechada para a haste, não aberta para longe dela."""
    vertice = vertice_de()
    caminhos = [
        fino(BASE, vertice),
        fino(vertice, polar(vertice, 180 - 26, DENTE)),
        fino(vertice, polar(vertice, 180 + 26, DENTE)),
    ]
    assert _grupos(caminhos) == NENHUM


def test_extensao_de_cota_nao_casa() -> None:
    vertice = vertice_de()
    caminhos = [
        fino(BASE, vertice),
        fino(vertice, polar(vertice, 90, DENTE)),
        fino(vertice, polar(vertice, -90, DENTE)),
    ]
    assert _grupos(caminhos) == NENHUM


def test_pe_de_galinha_de_cerca_nao_casa() -> None:
    """A linha da cerca segue além do vértice: quatro raios, não um garfo."""
    vertice = vertice_de()
    caminhos = [*garfo(), fino(vertice, polar(vertice, 0, 16.0))]
    assert _grupos(caminhos) == NENHUM


def test_ramal_de_condutor_nao_casa() -> None:
    """Os dentes seguem além das pontas: é derivação de condutor."""
    vertice = vertice_de()
    ponta = polar(vertice, 26, DENTE)
    caminhos = [*garfo(), fino(ponta, polar(ponta, 0, 16.0))]
    assert _grupos(caminhos) == NENHUM


def test_ramal_com_haste_longa_nao_casa() -> None:
    assert _grupos(garfo(haste=120.0)) == NENHUM


def test_chevron_sem_haste_nao_casa() -> None:
    vertice = vertice_de()
    caminhos = [
        fino(vertice, polar(vertice, 26, DENTE)),
        fino(vertice, polar(vertice, -26, DENTE)),
    ]
    assert _grupos(caminhos) == NENHUM


def test_v_de_aterramento_aberto_para_a_haste_nao_casa() -> None:
    vertice = vertice_de()
    caminhos = [
        fino(BASE, vertice),
        fino(BASE, polar(BASE, 26, DENTE)),
        fino(BASE, polar(BASE, -26, DENTE)),
    ]
    assert _grupos(caminhos) == NENHUM


def test_dentes_muito_abertos_ou_fechados_nao_casam() -> None:
    assert _grupos(garfo(abertura=55.0)) == NENHUM
    assert _grupos(garfo(abertura=8.0)) == NENHUM


def test_tracejado_nao_casa() -> None:
    assert _grupos(garfo(tracejado="[1 1] 0")) == NENHUM


def test_roxo_nao_casa() -> None:
    assert _grupos(garfo(cor=ROXO)) == NENHUM
    assert _grupos([*garfo(cor=ROXO), *x_sobre(centro_do_garfo())]) == NENHUM


def test_wipeout_branco_nao_casa_nem_garfo_coberto() -> None:
    assert _grupos(garfo(cor=BRANCO)) == NENHUM
    cobertura = poligono(
        ((140.0, 130.0), (190.0, 130.0), (190.0, 170.0), (140.0, 170.0)),
        ordem=5,
        preenchimento=BRANCO,
        cor=None,
    )
    assert _grupos([*garfo(), cobertura]) == NENHUM


def test_texto_dentro_do_garfo_nao_casa() -> None:
    vertice = vertice_de()
    meio = (vertice[0] + 8.0, vertice[1])
    caixa = (meio[0] - 1.0, meio[1] - 1.0, meio[0] + 1.0, meio[1] + 1.0)
    assert _grupos(garfo(), (texto("A", caixa),)) == NENHUM


def test_so_preenchimento_nao_casa() -> None:
    caminhos = [
        Caminho(c.subcaminhos, Estilo("", None, PRETO, 0.0, ""), "preenchimento", c.ordem)
        for c in garfo()
    ]
    assert _grupos(caminhos) == NENHUM


def test_garfo_colorido_sem_marca_nao_casa() -> None:
    assert _grupos(garfo(cor=VERDE)) == NENHUM
    assert _grupos(garfo(cor=VERMELHO)) == NENHUM


def test_circulo_de_outro_desenho_nao_conta() -> None:
    """Círculo vizinho que não contém o garfo, ou de outra cor: o garfo segue sem envolvente."""
    longe = polar(centro_do_garfo(), 90, 14.0)
    assert _grupos([*garfo(), circulo(longe, DENTE * 0.8, PRETO)])["existente"] == 1
    assert _grupos([*garfo(), circulo(centro_do_garfo(), DENTE * 0.8, VERDE)]) == {
        "existente": 1,
        "instalar": 0,
        "retirar": 0,
    }


def test_candidato_de_outro_contexto_e_recusado() -> None:
    a = contexto_gramaticas(pagina_estai(garfo()))
    b = contexto_gramaticas(pagina_estai(garfo()))
    candidatos = estai_candidatos(a, marcas=MarcasDaPagina(a))
    with pytest.raises(ValueError, match="outro contexto"):
        casa_estai(b, GRAMATICAS_ESTAI["existente"], candidatos=candidatos)


def test_max_span_filtra() -> None:
    contexto = contexto_gramaticas(pagina_estai(garfo()))
    candidatos = estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))
    gramatica = {**GRAMATICAS_ESTAI["existente"], "max_span": 1}
    assert casa_estai(contexto, gramatica, candidatos=candidatos) == []


def test_pagina_hostil_estoura_o_orcamento() -> None:
    caminhos: list[Caminho] = []
    for i in range(40):
        for j in range(40):
            caminhos.extend(garfo(base=(10.0 + i * 7.0, 10.0 + j * 7.0)))
    contexto = contexto_gramaticas(pagina_estai(caminhos), limite=len(caminhos) * 6)
    with pytest.raises(TetoGramaticasExcedido):
        estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))


def test_despacho_casa_uma_variante_por_forma() -> None:
    from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import casar_variantes

    variantes = [
        ({"family_id": "f"}, {"id": nome, "recognition": {"grammar": gramatica}})
        for nome, gramatica in GRAMATICAS_ESTAI.items()
    ]
    caminhos = [*garfo(), *estai_com_circulo(base=(60.0, 60.0))]
    achados = casar_variantes(pagina_estai(caminhos), variantes)
    assert sorted(str(a.variante["id"]) for a in achados) == ["existente", "instalar"]
    assert all(a.componentes for a in achados)


def test_vertice_sobre_o_circulo_nao_e_continuacao() -> None:
    """O círculo de retas passa pelo vértice: é traço de outro caminho, não continuação."""
    centro = centro_do_garfo()
    raio = DENTE * 0.75
    caminhos = [*garfo(cor=VERDE), circulo(centro, raio, VERDE)]
    assert _grupos(caminhos) == {"existente": 0, "instalar": 1, "retirar": 0}


def test_envolvente_da_cor_do_garfo_vence_contorno_menor_de_outra_cor() -> None:
    centro = centro_do_garfo()
    caminhos = [
        *garfo(cor=VERDE),
        circulo(centro, DENTE * 0.8, VERDE),
        circulo(centro, DENTE * 0.77, VERMELHO),
    ]
    assert _grupos(caminhos) == {"existente": 0, "instalar": 1, "retirar": 0}


def test_garfo_redesenhado_quase_igual_e_um_estai() -> None:
    """Dois desenhos do mesmo estai que diferem em décimos de ponto são um estai só."""
    caminhos = [*garfo(cor=PRETO), *garfo(cor=PRETO, abertura=27.0, dente=11.8)]
    assert _grupos(caminhos)["existente"] == 1


def test_caminho_lido_como_glifo_nao_e_garfo() -> None:
    from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import PaginaGramatica

    pag = pagina_estai(garfo())
    pag = PaginaGramatica(pag.modelo, pag.indices_crus, pag.translucidos, frozenset({0, 1, 2}))
    contexto = contexto_gramaticas(pag)
    assert estai_candidatos(contexto, marcas=MarcasDaPagina(contexto)) == ()


def test_condutor_que_passa_sobre_a_haste_nao_e_continuacao() -> None:
    """O condutor da mesma cor passa pelo vértice sem terminar nele: o garfo segue valendo."""
    vertice = vertice_de()
    caminhos = [
        *garfo(cor=PRETO),
        fino(polar(BASE, 180, 30.0), polar(vertice, 0, 60.0), espessura=0.48),
    ]
    assert _grupos(caminhos)["existente"] == 1


def test_dentes_de_estais_vizinhos_que_se_tocam_na_ponta_nao_sao_continuacao() -> None:
    """Pontas de dentes de dois estais vizinhos no mesmo ponto: dois estais, não um ramal."""
    vertice = vertice_de(0.0)
    ponta = polar(vertice, 26, DENTE)
    caminhos = [*garfo(), fino(ponta, polar(ponta, 26 + 150, DENTE))]
    assert _grupos(caminhos)["existente"] == 1


def _gasto_de(caminhos: list[Caminho]) -> int:
    contexto = contexto_gramaticas(pagina_estai(caminhos))
    marcas = MarcasDaPagina(contexto)
    antes = contexto.orcamento.gasto
    estai_candidatos(contexto, marcas=marcas)
    return contexto.orcamento.gasto - antes


def test_cada_cor_do_garfo_paga_a_varredura_dos_contornos() -> None:
    """A grade por cor filtra todos os contornos da página: o filtro gasta do orçamento."""
    outros = [circulo((20.0 + 9.0 * i, 280.0), 3.0, ROXO) for i in range(30)]
    bases = [(60.0, 60.0), (120.0, 60.0), (180.0, 60.0)]
    mesma_cor = [c for b in bases for c in garfo(cor=PRETO, base=b)]
    tres_cores = [
        c
        for b, cor in zip(bases, (PRETO, CINZA, VERMELHO), strict=True)
        for c in garfo(cor=cor, base=b)
    ]
    extra = _gasto_de([*outros, *tres_cores]) - _gasto_de([*outros, *mesma_cor])
    assert extra >= 3 * len(outros) // 2  # duas cores a mais, uma varredura cada


def test_pilha_de_raios_no_mesmo_vertice_nao_casa_e_paga() -> None:
    vertice = vertice_de()
    pilha = [fino(vertice, polar(vertice, 20.0 + 5.0 * i, DENTE)) for i in range(40)]
    caminhos = [fino(BASE, vertice), *pilha]
    assert _grupos(caminhos) == NENHUM
    assert _gasto_de(caminhos) >= len(pilha)


@pytest.mark.parametrize(
    ("cor", "casa"),
    [
        ((0.0, 0.0, 0.05), True),
        ((0.0, 0.0, 0.06), False),
        ((0.39, 0.39, 0.39), True),
        ((0.41, 0.41, 0.41), False),
    ],
    ids=["diferenca_no_limite", "diferenca_acima", "cinza_abaixo_de_0_4", "cinza_claro"],
)
def test_limite_de_preto_ou_cinza(cor: Any, casa: bool) -> None:
    assert (_grupos(garfo(cor=cor))["existente"] == 1) is casa


def test_haste_por_origem_do_texto_da_pagina_estai() -> None:
    """Haste de 5 pt: lida nas folhas de glifo (4 a 20 pt), não nas de texto nativo (10 a 24 pt)."""
    pequeno = garfo(haste=5.0, dente=3.0)
    assert _grupos(pequeno) == NENHUM
    glifo = texto("A", (10.0, 10.0, 12.0, 12.0), "glifo")
    assert _grupos(pequeno, (glifo,))["existente"] == 1
    assert _grupos(garfo(haste=22.0, dente=14.0), (glifo,)) == NENHUM


def test_gasto_de_tres_estais_fica_no_registrado() -> None:
    caminhos = [*estai_com_circulo(), *garfo(base=(60.0, 60.0)), *garfo(200.0, base=(200.0, 200.0))]
    assert _gasto_de(caminhos) == GASTO_DE_TRES_ESTAIS


@pytest.mark.parametrize("cor", [PRETO, VERMELHO], ids=["preto", "vermelho"])
def test_garfo_preto_ou_vermelho_com_circulo_da_mesma_cor_e_recusado(cor: Any) -> None:
    """R-E06.3.4-2: só o garfo verde com círculo verde é "instalar"."""
    caminhos = [*garfo(cor=cor), circulo(centro_do_garfo(), DENTE * 0.8, cor)]
    assert _grupos(caminhos) == NENHUM


@pytest.mark.parametrize("cor", [PRETO, VERMELHO], ids=["preto", "vermelho"])
def test_x_vale_sobre_garfo_com_circulo_de_qualquer_cor(cor: Any) -> None:
    caminhos = [
        *garfo(cor=cor),
        circulo(centro_do_garfo(), DENTE * 0.8, cor),
        *x_sobre(centro_do_garfo()),
    ]
    assert _grupos(caminhos) == {"existente": 0, "instalar": 0, "retirar": 1}


def test_disputa_de_marcas_em_cascata_paga_cada_rodada(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cada garfo que perde um X passa ao seguinte e o toma do vizinho: uma rodada por garfo.

    Cada rodada percorre todas as leituras; o orçamento tem de ver esse percurso, e não só a
    releitura do perdedor.
    """
    caminhos: list[Caminho] = []
    for i in range(300):
        base = (150.0, 10.0 + i * 8.0)
        caminhos += [*garfo(base=base), *x_sobre(centro_do_garfo(base=base), meio=9.0)]
    contexto = contexto_gramaticas(pagina_estai(caminhos, altura=2600.0))
    marcas = MarcasDaPagina(contexto)
    original = grammar_estai._disputar
    gastos: list[int] = []
    leituras: list[int] = []

    def medir(lidos: Any, perdas: Any) -> bool:
        gastos.append(contexto.orcamento.gasto)
        leituras.append(len(lidos))
        return original(lidos, perdas)

    monkeypatch.setattr(grammar_estai, "_disputar", medir)
    estai_candidatos(contexto, marcas=marcas)
    assert len(gastos) > 100
    assert all(depois - antes >= leituras[0] for antes, depois in pairwise(gastos))


def test_casa_estai_nao_gasta_do_orcamento() -> None:
    contexto = contexto_gramaticas(pagina_estai(estai_com_circulo()))
    candidatos = estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))
    antes = contexto.orcamento.gasto
    for gramatica in GRAMATICAS_ESTAI.values():
        casa_estai(contexto, gramatica, candidatos=candidatos)
    assert contexto.orcamento.gasto == antes


def test_variantes_habilitadas_do_pacote_usam_exatamente_as_gramaticas_da_fixture() -> None:
    """Task 3: as 3 variantes de f02-14 habilitadas levam `GRAMATICAS_ESTAI`, nem mais nem menos."""
    habilitadas = {
        variante["id"]: variante["recognition"]["grammar"]
        for pacote in carregar_pacotes()
        for variante in pacote["variants"]
        if variante["recognition"]["status"] == "enabled"
        and variante["recognition"]["grammar"]["kind"] == "forked_stem"
    }
    assert habilitadas == {
        "cemig-eo-r3-s14-v001": GRAMATICAS_ESTAI["existente"],
        "cemig-eo-r3-s14-v002": GRAMATICAS_ESTAI["instalar"],
        "cemig-eo-r3-s14-v003": GRAMATICAS_ESTAI["retirar"],
    }
