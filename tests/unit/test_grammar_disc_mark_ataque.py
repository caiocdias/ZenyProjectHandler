"""Ataque à gramática `disc_mark` (E06.3.5, Task 3): bordas fora da suíte do desenvolvedor."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from tests.fixtures.symbol_grammars.disc_mark import (
    CAIXA_DUPLA,
    CENTRO,
    FUSIVEL,
    VAO,
    VERMELHO,
    conteudo_caixa_dupla,
    conteudo_fusivel,
    curvas_do_fusivel,
    disco,
    disco_em_dois_caminhos,
    ponto_terminal,
    pontos_dos_terminais,
    repintado,
    reta_paralela,
    retangulo_girado,
)
from tests.fixtures.symbol_grammars.paginas import pagina_gramatica, poligono, texto

from zeny_project_handler.adapters.analysis.drawing_model.grammar_disc_mark import (
    casa_disc_mark,
    disc_mark_candidatos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caminho,
    ItemCaminho,
    Ponto,
    TextoModelo,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    ContextoGramatica,
    contexto_gramaticas,
)

_CELULA = 0.15 * 72.0
_BRANCO = (1.0, 1.0, 1.0)


def _contexto(
    caminhos: list[Caminho],
    textos: tuple[TextoModelo, ...] = (),
    largura: float = 300.0,
    altura: float = 300.0,
) -> ContextoGramatica:
    return contexto_gramaticas(
        pagina_gramatica(caminhos, textos=textos, largura=largura, altura=altura)
    )


def _conteudos(caminhos: list[Caminho]) -> list[str]:
    return [c.content for c in disc_mark_candidatos(_contexto(caminhos))]


def _caixa_com(*retas: Caminho) -> list[Caminho]:
    return [
        disco(),
        retangulo_girado(ordem=1),
        *retas,
        *pontos_dos_terminais(VAO, 2 + len(retas)),
    ]


def _deslocado(caminho: Caminho, dx: float, *, so_inicio: bool = False) -> Caminho:
    subcaminhos = []
    for sub in caminho.subcaminhos:
        inicio = sub[0].pontos[0]
        subcaminhos.append(
            tuple(
                ItemCaminho(
                    i.tipo,
                    tuple((x + dx, y) for x, y in i.pontos)
                    if not so_inicio
                    else tuple((x + dx, y) if (x, y) == inicio else (x, y) for x, y in i.pontos),
                )
                for i in sub
            )
        )
    return replace(caminho, subcaminhos=tuple(subcaminhos))


# --- disco com curvas e caixa dupla ---------------------------------------------------------


def test_disco_com_curvas_e_caixa_dupla_sai_como_fuse_curve_sem_o_retangulo() -> None:
    """Decisão fixada: com 2 curvas o disco é `fuse_curve`; retângulo e reta ficam de fora."""
    caminhos = [
        disco(),
        *curvas_do_fusivel(VAO, 1),
        retangulo_girado(ordem=3),
        reta_paralela(ordem=4),
        *pontos_dos_terminais(VAO, 5),
    ]
    contexto = _contexto(caminhos)
    candidatos = disc_mark_candidatos(contexto)

    assert [(c.content, c.componentes) for c in candidatos] == [("fuse_curve", (1, 2, 5, 6))]
    assert casa_disc_mark(contexto, CAIXA_DUPLA, candidatos=candidatos) == []
    assert len(casa_disc_mark(contexto, FUSIVEL, candidatos=candidatos)) == 1


def test_disco_com_uma_curva_e_caixa_dupla_nao_casa() -> None:
    caminhos = [
        disco(),
        curvas_do_fusivel(VAO, 1)[0],
        retangulo_girado(ordem=2),
        reta_paralela(ordem=3),
        *pontos_dos_terminais(VAO, 4),
    ]
    assert _conteudos(caminhos) == []


def test_disco_com_tres_curvas_distintas_nao_casa() -> None:
    terceira = _deslocado(curvas_do_fusivel(VAO, 3)[0], 0.25 * VAO)
    caminhos = [disco(), *curvas_do_fusivel(VAO, 1), terceira, *pontos_dos_terminais(VAO, 4)]
    assert _conteudos(caminhos) == []


# --- retas no mesmo meio, perto de 0,1 do vão -----------------------------------------------


@pytest.mark.parametrize(
    ("fracao", "esperado"),
    [(1.2, ["double_box"]), (1.26, [])],
    ids=["diferenca-0.08-do-vao-e-a-mesma-reta", "diferenca-0.104-do-vao-sao-duas"],
)
def test_retas_no_mesmo_meio_viram_uma_ate_um_decimo_do_vao(
    fracao: float, esperado: list[str]
) -> None:
    retas = (reta_paralela(ordem=2), reta_paralela(ordem=3, fracao_do_lado=fracao))
    assert _conteudos(_caixa_com(*retas)) == esperado


# --- deduplicação perto de borda de célula e na tolerância ----------------------------------


@pytest.mark.parametrize("separacao", [0.14, 0.16], ids=["dentro", "fora"])
@pytest.mark.parametrize("celula", [1, 10, 100], ids=lambda c: f"celula-{c}")
def test_dedup_atravessa_a_borda_da_celula_so_dentro_da_tolerancia(
    celula: int, separacao: float
) -> None:
    borda = celula * _CELULA
    a: Ponto = (borda - separacao * VAO / 2, 150.0)
    b: Ponto = (borda + separacao * VAO / 2, 150.0)
    caminhos = [
        disco(centro=a),
        disco(ordem=1, centro=b),
        *conteudo_fusivel(ordem=2, centro=a),
    ]
    candidatos = disc_mark_candidatos(_contexto(caminhos, largura=2000.0, altura=400.0))
    esperado = [0] if separacao < 0.15 else [0, 1]
    assert [c.caminho_ancora for c in candidatos] == esperado


def test_dedup_vertical_atravessa_a_borda_da_celula() -> None:
    borda = 10 * _CELULA
    a: Ponto = (150.0, borda - 0.05 * VAO)
    b: Ponto = (150.0, borda + 0.05 * VAO)
    caminhos = [
        disco(centro=a),
        disco(ordem=1, centro=b),
        *conteudo_fusivel(ordem=2, centro=a),
    ]
    candidatos = disc_mark_candidatos(_contexto(caminhos))
    assert [c.caminho_ancora for c in candidatos] == [0]


def test_redesenho_maior_cobre_o_disco_antigo_e_so_o_novo_sai() -> None:
    caminhos = [
        disco(14.0),
        disco(14.8, ordem=1),
        *conteudo_fusivel(14.0, ordem=2),
    ]
    candidatos = disc_mark_candidatos(_contexto(caminhos))
    assert [c.caminho_ancora for c in candidatos] == [1]


def test_redesenho_menor_nao_cobre_e_o_mais_antigo_fica() -> None:
    caminhos = [
        disco(14.8),
        disco(14.0, ordem=1),
        *conteudo_fusivel(14.0, ordem=2),
    ]
    candidatos = disc_mark_candidatos(_contexto(caminhos))
    assert [c.caminho_ancora for c in candidatos] == [0]


# --- elipse: conteúdo fora do disco ---------------------------------------------------------


@pytest.mark.parametrize(("raio", "esperado"), [(1.04, ["fuse_curve"]), (1.07, [])])
def test_ponto_na_borda_da_elipse_respeita_a_tolerancia_de_5_por_cento(
    raio: float, esperado: list[str]
) -> None:
    x = 0.5 * raio - 0.045
    caminhos = [
        disco(),
        *curvas_do_fusivel(VAO, 1),
        ponto_terminal(VAO, -0.13, 0.27, 3),
        ponto_terminal(VAO, x, 0.0, 4),
    ]
    assert _conteudos(caminhos) == esperado


def test_curva_com_uma_ponta_fora_da_elipse_nao_conta() -> None:
    curvas = curvas_do_fusivel(VAO, 1)
    saindo = _deslocado(curvas[0], 0.9 * VAO, so_inicio=True)
    assert _conteudos([disco(), saindo, curvas[1], *pontos_dos_terminais(VAO, 3)]) == []


# --- palavra e cobertura com conteúdo completo ----------------------------------------------


def test_palavra_com_centro_na_borda_do_disco_recusa() -> None:
    x1 = CENTRO[0] + VAO / 2
    palavra = texto("A-4", (x1 - 1.0, CENTRO[1] - 1.0, x1 + 1.0, CENTRO[1] + 1.0))
    assert disc_mark_candidatos(_contexto([disco(), *conteudo_fusivel()], (palavra,))) == ()


def _capa(meia: float, ordem: int) -> Caminho:
    x, y = CENTRO
    cantos = (
        (x - meia, y - meia),
        (x + meia, y - meia),
        (x + meia, y + meia),
        (x - meia, y + meia),
    )
    return poligono(cantos, ordem, _BRANCO, cor=None)


def test_cobertura_anterior_ao_disco_nao_esconde_nada() -> None:
    assert _conteudos([_capa(VAO, 0), disco(ordem=1), *conteudo_fusivel(ordem=2)]) == ["fuse_curve"]


def test_cobertura_menor_que_o_disco_nao_o_esconde() -> None:
    assert _conteudos([disco(), *conteudo_fusivel(), _capa(0.1 * VAO, 6)]) == ["fuse_curve"]


# --- Ghostscript e contexto -----------------------------------------------------------------


def test_ghostscript_com_conteudo_entre_o_preenchimento_e_o_traco_casa_uma_vez() -> None:
    preenchimento, traco = disco_em_dois_caminhos()
    conteudo = conteudo_fusivel(ordem=1)
    candidatos = disc_mark_candidatos(_contexto([preenchimento, *conteudo, repintado(traco, 6)]))
    assert [(c.content, c.caminho_ancora) for c in candidatos] == [("fuse_curve", 0)]


def test_ghostscript_casa_uma_vez_na_variante() -> None:
    conteudo = conteudo_fusivel(ordem=2)
    duplicados = [repintado(c, 7 + i) for i, c in enumerate(conteudo[1:])]
    contexto = _contexto([*disco_em_dois_caminhos(), *conteudo, *duplicados])
    candidatos = disc_mark_candidatos(contexto)
    assert len(casa_disc_mark(contexto, FUSIVEL, candidatos=candidatos)) == 1


def test_value_error_com_um_candidato_estranho_no_meio_do_lote() -> None:
    caminhos = [disco(), *conteudo_fusivel()]
    contexto = _contexto(caminhos)
    proprio = disc_mark_candidatos(contexto)
    estranho = disc_mark_candidatos(_contexto(caminhos))
    with pytest.raises(ValueError, match="outro contexto"):
        casa_disc_mark(contexto, FUSIVEL, candidatos=(*proprio, *estranho))


def test_sem_candidatos_nao_e_erro() -> None:
    assert casa_disc_mark(_contexto([]), FUSIVEL, candidatos=()) == []


def test_candidatos_sao_uma_tupla_e_a_caixa_e_a_do_disco() -> None:
    contexto = _contexto([disco(), *conteudo_fusivel()])
    candidatos = disc_mark_candidatos(contexto)
    assert isinstance(candidatos, tuple)
    assert candidatos[0].caixa == contexto.caixas_caminhos[0]


@pytest.mark.parametrize("gramatica", [FUSIVEL, CAIXA_DUPLA], ids=["fuse", "box"])
def test_variante_do_outro_content_nao_casa_nada(gramatica: dict[str, Any]) -> None:
    conteudo = conteudo_caixa_dupla() if gramatica is FUSIVEL else conteudo_fusivel()
    contexto = _contexto([disco(), *conteudo])
    assert casa_disc_mark(contexto, gramatica, candidatos=disc_mark_candidatos(contexto)) == []


def test_ponto_vermelho_nao_conta_como_ponto_preto() -> None:
    preto = ponto_terminal(VAO, 0.13, -0.27, 4)
    vermelho = replace(preto, estilo=replace(preto.estilo, cor=VERMELHO, preenchimento=VERMELHO))
    caminhos = [
        disco(),
        *curvas_do_fusivel(VAO, 1),
        ponto_terminal(VAO, -0.13, 0.27, 3),
        vermelho,
    ]
    assert _conteudos(caminhos) == []
