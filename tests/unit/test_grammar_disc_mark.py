"""Gramática `disc_mark` (E06.3.5, Task 3): disco vermelho com curva fusível ou caixa dupla."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any, Final

import pytest
from tests.fixtures.symbol_grammars.disc_mark import (
    BRANCO,
    CAIXA_DUPLA,
    CENTRO,
    FUSIVEL,
    PRETO,
    SEGMENTOS_DA_CURVA,
    VAO,
    VAOS,
    VERDE,
    VERMELHO,
    conteudo_caixa_dupla,
    conteudo_fusivel,
    curvas_do_fusivel,
    diagonal,
    disco,
    disco_em_dois_caminhos,
    elipse_vermelha,
    polilinha,
    ponto_terminal,
    pontos_dos_terminais,
    repintado,
    reta_paralela,
    retangulo_girado,
)
from tests.fixtures.symbol_grammars.paginas import (
    circulo_bezier,
    linha,
    pagina_gramatica,
    poligono,
    retangulo_traco,
    texto,
)
from tests.integration.test_model_symbols_runner import _settings

from zeny_project_handler.adapters.analysis.drawing_model import symbol_matcher
from zeny_project_handler.adapters.analysis.drawing_model.grammar_disc_mark import (
    CandidatoDiscMark,
    casa_disc_mark,
    disc_mark_candidatos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caminho,
    Cor,
    ItemCaminho,
    Ponto,
    TextoModelo,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    ContextoGramatica,
    PaginaGramatica,
    contexto_gramaticas,
)
from zeny_project_handler_server import symbol_execution
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

ROXO: Final[Cor] = (0.31, 0.10, 0.30)
CINZA: Final[Cor] = (0.5, 0.5, 0.5)
CENTRO_DO_TERMINAL: Final[Ponto] = (60.0, 60.0)
TERMINAL: Final[dict[str, Any]] = {
    "kind": "terminal_disc",
    "fill": "purple",
    "min_span": 1.0,
    "max_span": 4.0,
    "terminal_line": True,
}
_Variante = tuple[Mapping[str, Any], Mapping[str, Any]]


def _contexto(
    caminhos: Sequence[Caminho],
    textos: Sequence[TextoModelo] = (),
    *,
    translucidos: frozenset[int] = frozenset(),
    largura: float = 300.0,
    altura: float = 300.0,
) -> ContextoGramatica:
    return contexto_gramaticas(
        pagina_gramatica(
            caminhos, textos=textos, translucidos=translucidos, largura=largura, altura=altura
        )
    )


def _conteudos(caminhos: Sequence[Caminho]) -> list[str]:
    return [candidato.content for candidato in disc_mark_candidatos(_contexto(caminhos))]


def _variante(nome: str, gramatica: Mapping[str, Any]) -> _Variante:
    return ({"id": "pacote"}, {"id": nome, "recognition": {"grammar": gramatica}})


# --- positivos ----------------------------------------------------------------------------


@pytest.mark.parametrize("vao", VAOS, ids=str)
def test_fuse_curve_casa_com_a_caixa_do_disco(vao: float) -> None:
    contexto = _contexto([disco(vao), *conteudo_fusivel(vao)])
    candidatos = disc_mark_candidatos(contexto)
    assert [c.content for c in candidatos] == ["fuse_curve"]

    achados = casa_disc_mark(contexto, {**FUSIVEL, "min_span": 4.5}, candidatos=candidatos)

    assert len(achados) == 1
    caixa, ancora, componentes = achados[0]
    assert caixa == pytest.approx(contexto.caixas_caminhos[0])
    assert ancora == 0
    # A diagonal (1) não faz parte da confirmação; as polilinhas e os pontos, sim.
    assert componentes == (2, 3, 4, 5)
    assert casa_disc_mark(contexto, CAIXA_DUPLA, candidatos=candidatos) == []


@pytest.mark.parametrize("vao", VAOS, ids=str)
def test_double_box_casa_com_a_caixa_do_disco(vao: float) -> None:
    contexto = _contexto([disco(vao), *conteudo_caixa_dupla(vao)])
    candidatos = disc_mark_candidatos(contexto)
    assert [c.content for c in candidatos] == ["double_box"]

    achados = casa_disc_mark(contexto, CAIXA_DUPLA, candidatos=candidatos)

    assert len(achados) == 1
    caixa, ancora, componentes = achados[0]
    assert caixa == pytest.approx(contexto.caixas_caminhos[0])
    assert ancora == 0
    assert componentes == (2, 3, 4, 5)
    assert casa_disc_mark(contexto, FUSIVEL, candidatos=candidatos) == []


@pytest.mark.parametrize("graus", [0.0, 25.0, 90.0, 137.0], ids=str)
def test_double_box_vale_em_qualquer_giro(graus: float) -> None:
    assert _conteudos([disco(), *conteudo_caixa_dupla(graus=graus)]) == ["double_box"]


def test_curva_de_dez_segmentos_e_o_minimo() -> None:
    def pagina(segmentos: int) -> list[Caminho]:
        return [
            disco(),
            *curvas_do_fusivel(VAO, 1, segmentos=segmentos),
            *pontos_dos_terminais(VAO, 3),
        ]

    assert _conteudos(pagina(10)) == ["fuse_curve"]
    assert _conteudos(pagina(9)) == []


def test_teto_do_disco_e_o_limite_do_schema() -> None:
    assert _conteudos([disco(72.0), *conteudo_fusivel(72.0)]) == ["fuse_curve"]
    assert _conteudos([disco(72.5), *conteudo_fusivel(72.5)]) == []


def test_candidato_e_imutavel() -> None:
    candidato = disc_mark_candidatos(_contexto([disco(), *conteudo_fusivel()]))[0]
    assert isinstance(candidato, CandidatoDiscMark)
    with pytest.raises(FrozenInstanceError):
        candidato.content = "double_box"  # type: ignore[misc]


def test_vao_da_variante_filtra_nos_dois_limites() -> None:
    contexto = _contexto([disco(), *conteudo_fusivel()])
    candidatos = disc_mark_candidatos(contexto)
    caixa = candidatos[0].caixa
    vao = max(caixa[2] - caixa[0], caixa[3] - caixa[1])

    def achados(minimo: float, maximo: float) -> int:
        gramatica = {**FUSIVEL, "min_span": minimo, "max_span": maximo}
        return len(casa_disc_mark(contexto, gramatica, candidatos=candidatos))

    assert achados(vao, vao + 1) == 1
    assert achados(vao - 1, vao) == 1
    assert achados(vao + 0.01, vao + 1) == 0
    assert achados(vao - 1, vao - 0.01) == 0


def test_candidato_de_outro_contexto_e_value_error() -> None:
    caminhos = [disco(), *conteudo_fusivel()]
    candidatos = disc_mark_candidatos(_contexto(caminhos))
    with pytest.raises(ValueError, match="outro contexto"):
        casa_disc_mark(_contexto(caminhos), FUSIVEL, candidatos=candidatos)


def test_dois_discos_distantes_saem_os_dois() -> None:
    outro: Ponto = (CENTRO[0] + 40, CENTRO[1])
    caminhos = [
        disco(),
        *conteudo_fusivel(ordem=1),
        disco(ordem=6, centro=outro),
        *conteudo_fusivel(ordem=7, centro=outro),
    ]
    candidatos = disc_mark_candidatos(_contexto(caminhos))
    assert [c.caminho_ancora for c in candidatos] == [0, 6]


# --- Review Focus 1: disco sem a marca, marca fora do disco, guardas -----------------------


@pytest.mark.parametrize(
    "conteudo",
    [
        pytest.param(lambda: [], id="poste-sem-conteudo"),
        pytest.param(lambda: [diagonal(VAO, 1)], id="aterramento-so-a-diagonal"),
        pytest.param(lambda: pontos_dos_terminais(VAO, 1), id="so-os-pontos"),
        pytest.param(lambda: curvas_do_fusivel(VAO, 1), id="so-as-curvas"),
    ],
)
def test_disco_vermelho_sem_a_marca_nao_casa(conteudo: Any) -> None:
    assert _conteudos([disco(), *conteudo()]) == []


@pytest.mark.parametrize("cor", [VERDE, PRETO, ROXO], ids=["verde", "preto", "roxo"])
def test_disco_de_outra_cor_com_a_marca_nao_casa(cor: Cor) -> None:
    assert _conteudos([disco(cor=cor), *conteudo_fusivel()]) == []
    assert _conteudos([disco(cor=cor), *conteudo_caixa_dupla()]) == []


def _retangulo_vermelho() -> Caminho:
    x0, y0, x1, y1 = CENTRO[0] - VAO, CENTRO[1] - VAO, CENTRO[0] + VAO, CENTRO[1] + VAO
    return poligono(((x0, y0), (x1, y0), (x1, y1), (x0, y1)), 0, VERMELHO, cor=None)


@pytest.mark.parametrize(
    "envolvente",
    [
        pytest.param(_retangulo_vermelho, id="retangulo-vermelho"),
        pytest.param(
            lambda: circulo_bezier(CENTRO, VAO / 2, 0, cor=VERMELHO), id="aro-vermelho-sem-fundo"
        ),
        pytest.param(elipse_vermelha, id="elipse-esticada"),
    ],
)
def test_marca_dentro_de_outro_desenho_nao_casa(envolvente: Any) -> None:
    assert _conteudos([envolvente(), *conteudo_fusivel()]) == []
    assert _conteudos([envolvente(), *conteudo_caixa_dupla()]) == []


def test_conteudo_pintado_antes_do_disco_fica_escondido() -> None:
    conteudo = conteudo_fusivel(ordem=0)
    assert _conteudos([*conteudo, disco(ordem=len(conteudo))]) == []


def test_ponto_na_caixa_mas_fora_da_elipse_nao_conta() -> None:
    def pagina(x: float, y: float) -> list[Caminho]:
        return [
            disco(),
            *curvas_do_fusivel(VAO, 1),
            ponto_terminal(VAO, -0.13, 0.27, 3),
            ponto_terminal(VAO, x, y, 4),
        ]

    assert _conteudos(pagina(0.13, -0.27)) == ["fuse_curve"]
    assert _conteudos(pagina(0.44, -0.44)) == []


def test_contagem_exata_de_pontos() -> None:
    conteudo = conteudo_fusivel()
    assert _conteudos([disco(), *conteudo[:-1]]) == []
    terceiro = ponto_terminal(VAO, 0.0, 0.38, 6)
    assert _conteudos([disco(), *conteudo, terceiro]) == []


def test_contagem_exata_de_curvas() -> None:
    conteudo = conteudo_fusivel()
    uma_curva = [item for item in conteudo if item is not conteudo[2]]
    assert _conteudos([disco(), *uma_curva]) == []
    terceira = polilinha(VAO, (-0.3, -0.1), (-0.1, 0.1), 6)
    assert _conteudos([disco(), *conteudo, terceira]) == []


def test_curvas_coincidentes_contam_como_uma_so() -> None:
    curva = curvas_do_fusivel(VAO, 1)[0]
    caminhos = [disco(), curva, repintado(curva, 2), *pontos_dos_terminais(VAO, 3)]
    assert _conteudos(caminhos) == []


def test_pontos_coincidentes_contam_como_um_so() -> None:
    ponto = pontos_dos_terminais(VAO, 3)[0]
    caminhos = [disco(), *curvas_do_fusivel(VAO, 1), ponto, repintado(ponto, 4)]
    assert _conteudos(caminhos) == []


def test_ponto_sem_preenchimento_nao_conta() -> None:
    caminhos = [
        disco(),
        *curvas_do_fusivel(VAO, 1),
        ponto_terminal(VAO, -0.13, 0.27, 3, preenchido=False),
        ponto_terminal(VAO, 0.13, -0.27, 4, preenchido=False),
    ]
    assert _conteudos(caminhos) == []


def test_ponto_grande_demais_nao_conta() -> None:
    caminhos = [
        disco(),
        *curvas_do_fusivel(VAO, 1),
        ponto_terminal(VAO, -0.13, 0.27, 3, raio=0.11),
        ponto_terminal(VAO, 0.13, -0.27, 4, raio=0.11),
    ]
    assert _conteudos(caminhos) == []


def test_curva_de_outra_cor_nao_conta() -> None:
    caminhos = [
        disco(),
        polilinha(VAO, (-0.05, 0.3), (0.05, 0.02), 1, cor=VERDE),
        polilinha(VAO, (0.05, -0.3), (-0.05, -0.02), 2, cor=VERDE),
        *pontos_dos_terminais(VAO, 3),
    ]
    assert _conteudos(caminhos) == []


def test_conteudo_lido_como_glifo_nao_conta() -> None:
    caminhos = [disco(), *conteudo_fusivel()]
    pagina = pagina_gramatica(caminhos)
    assert disc_mark_candidatos(contexto_gramaticas(pagina)) != ()
    com_glifo = replace(pagina, glifos_lidos=frozenset({5}))
    assert disc_mark_candidatos(contexto_gramaticas(com_glifo)) == ()


def test_conteudo_translucido_nao_conta() -> None:
    caminhos = [disco(), *conteudo_fusivel()]
    assert disc_mark_candidatos(_contexto(caminhos, translucidos=frozenset({5}))) == ()


def _palavra_no_centro() -> TextoModelo:
    return texto("A-4", (CENTRO[0] - 2.0, CENTRO[1] - 2.0, CENTRO[0] + 2.0, CENTRO[1] + 2.0))


def test_palavra_sobre_o_disco_recusa() -> None:
    caminhos = [disco(), *conteudo_fusivel()]
    assert disc_mark_candidatos(_contexto(caminhos, [_palavra_no_centro()])) == ()


def test_palavra_longe_do_disco_nao_recusa() -> None:
    longe = texto("A-4", (20.0, 20.0, 24.0, 24.0))
    assert len(disc_mark_candidatos(_contexto([disco(), *conteudo_fusivel()], [longe]))) == 1


def _capa(ordem: int) -> Caminho:
    x0, y0, x1, y1 = CENTRO[0] - VAO, CENTRO[1] - VAO, CENTRO[0] + VAO, CENTRO[1] + VAO
    return poligono(((x0, y0), (x1, y0), (x1, y1), (x0, y1)), ordem, BRANCO, cor=None)


def test_preenchimento_opaco_posterior_cobre_o_disco() -> None:
    caminhos = [disco(), *conteudo_fusivel(), _capa(6)]
    assert disc_mark_candidatos(_contexto(caminhos)) == ()


def test_preenchimento_translucido_posterior_nao_cobre_o_disco() -> None:
    caminhos = [disco(), *conteudo_fusivel(), _capa(6)]
    assert len(disc_mark_candidatos(_contexto(caminhos, translucidos=frozenset({6})))) == 1


# --- caixa dupla: forma do retângulo e da reta ---------------------------------------------


def _caixa_com(retangulo: Caminho, *retas: Caminho) -> list[Caminho]:
    ordem = 2 + len(retas)
    return [disco(), retangulo, *retas, *pontos_dos_terminais(VAO, ordem)]


def test_double_box_sem_os_pontos_nao_casa() -> None:
    assert _conteudos([disco(), retangulo_girado(ordem=1), reta_paralela(ordem=2)]) == []


def test_double_box_sem_a_reta_nao_casa() -> None:
    assert _conteudos(_caixa_com(retangulo_girado())) == []


def test_double_box_sem_o_retangulo_nao_casa() -> None:
    caminhos = [disco(), reta_paralela(ordem=1), *pontos_dos_terminais(VAO, 2)]
    assert _conteudos(caminhos) == []


def test_double_box_com_duas_retas_paralelas_distintas_nao_casa() -> None:
    primeira = reta_paralela(ordem=2)
    segunda = reta_paralela(ordem=3, afastamento=-0.24)
    assert _conteudos(_caixa_com(retangulo_girado(), primeira, segunda)) == []


def test_double_box_com_dois_retangulos_distintos_nao_casa() -> None:
    primeiro = retangulo_girado()
    segundo = retangulo_traco(
        (CENTRO[0] + 2.0, CENTRO[1] + 2.0, CENTRO[0] + 4.0, CENTRO[1] + 3.0), 2
    )
    assert _conteudos(_caixa_com(primeiro, segundo, reta_paralela(ordem=3))) == []


def test_double_box_com_retangulos_concentricos_de_tamanhos_diferentes_nao_casa() -> None:
    menor = retangulo_girado(ordem=2, escala=0.6)
    assert _conteudos(_caixa_com(retangulo_girado(), menor, reta_paralela(ordem=3))) == []


def test_double_box_com_retas_no_mesmo_meio_e_comprimentos_diferentes_nao_casa() -> None:
    comprida = reta_paralela(ordem=3, fracao_do_lado=1.29)
    assert _conteudos(_caixa_com(retangulo_girado(), reta_paralela(ordem=2), comprida)) == []


def test_double_box_com_uma_curva_nao_casa() -> None:
    curva = curvas_do_fusivel(VAO, 3)[0]
    caminhos = [
        disco(),
        retangulo_girado(ordem=1),
        reta_paralela(ordem=2),
        curva,
        *pontos_dos_terminais(VAO, 4),
    ]
    assert _conteudos(caminhos) == []


@pytest.mark.parametrize(
    "reta",
    [
        pytest.param(lambda: reta_paralela(giro=90.0), id="perpendicular"),
        pytest.param(lambda: reta_paralela(giro=12.0), id="fora-do-paralelismo"),
        pytest.param(lambda: reta_paralela(fracao_do_lado=0.5), id="curta"),
        pytest.param(lambda: reta_paralela(afastamento=0.1), id="dentro-do-retangulo"),
        pytest.param(lambda: reta_paralela(afastamento=0.38), id="longe-do-retangulo"),
    ],
)
def test_reta_fora_da_forma_nao_e_caixa_dupla(reta: Any) -> None:
    assert _conteudos(_caixa_com(retangulo_girado(), reta())) == []


def test_reta_comprida_nao_e_caixa_dupla() -> None:
    longa = reta_paralela(fracao_do_lado=1.4, afastamento=0.15)
    assert _conteudos(_caixa_com(retangulo_girado(), longa)) == []


def test_quadrilatero_sem_angulos_retos_nao_e_caixa_dupla() -> None:
    torto = retangulo_girado(torcao=0.1)
    assert _conteudos(_caixa_com(torto, reta_paralela(ordem=2))) == []


# --- Review Focus 2: curva fusível fora de disco --------------------------------------------


def test_curva_fusivel_fora_de_disco_nao_vira_esta_classe() -> None:
    assert _conteudos(conteudo_fusivel(ordem=0)) == []


def test_curva_solta_ao_lado_de_disco_vazio_nao_casa() -> None:
    ao_lado: Ponto = (CENTRO[0] + 30, CENTRO[1])
    assert _conteudos([disco(), *conteudo_fusivel(ordem=1, centro=ao_lado)]) == []


def test_curva_solta_nao_entra_nos_componentes_do_disco() -> None:
    ao_lado: Ponto = (CENTRO[0] + 30, CENTRO[1])
    caminhos = [disco(), *conteudo_fusivel(), *conteudo_fusivel(ordem=6, centro=ao_lado)]
    candidatos = disc_mark_candidatos(_contexto(caminhos))
    assert [(c.caminho_ancora, c.componentes) for c in candidatos] == [(0, (2, 3, 4, 5))]


# --- Review Focus 3: Ghostscript e deduplicação ---------------------------------------------


def test_ghostscript_fuse_curve_casa_uma_vez() -> None:
    conteudo = conteudo_fusivel(ordem=2)
    duplicados = [repintado(caminho, 7 + i) for i, caminho in enumerate(conteudo[1:])]
    candidatos = disc_mark_candidatos(
        _contexto([*disco_em_dois_caminhos(), *conteudo, *duplicados])
    )
    assert [(c.content, c.caminho_ancora) for c in candidatos] == [("fuse_curve", 0)]
    assert candidatos[0].componentes == (3, 4, 5, 6, 7, 8, 9, 10)


def test_ghostscript_double_box_casa_uma_vez() -> None:
    conteudo = conteudo_caixa_dupla(ordem=2)
    duplicados = [repintado(caminho, 7 + i) for i, caminho in enumerate(conteudo[1:])]
    candidatos = disc_mark_candidatos(
        _contexto([*disco_em_dois_caminhos(), *conteudo, *duplicados])
    )
    assert [(c.content, c.caminho_ancora) for c in candidatos] == [("double_box", 0)]
    assert candidatos[0].componentes == (3, 4, 5, 6, 7, 8, 9, 10)


def test_disco_redesenhado_com_centro_proximo_sai_uma_vez() -> None:
    desvio: Ponto = (CENTRO[0] + 0.05 * VAO, CENTRO[1] - 0.05 * VAO)
    caminhos = [disco(), disco(ordem=1, centro=desvio), *conteudo_fusivel(ordem=2)]
    candidatos = disc_mark_candidatos(_contexto(caminhos))
    assert [c.caminho_ancora for c in candidatos] == [0]


def test_disco_redesenhado_com_vao_diferente_sai_uma_vez_em_coordenada_grande() -> None:
    """A célula da deduplicação não pode depender do vão de cada disco: longe da origem, vãos
    próximos cairiam em células distantes e o mesmo disco sairia em dobro."""
    centro: Ponto = (3000.0, 3000.0)
    caminhos = [
        disco(14.4, centro=centro),
        disco(14.3, ordem=1, centro=centro),
        *conteudo_fusivel(14.4, ordem=2, centro=centro),
    ]
    candidatos = disc_mark_candidatos(_contexto(caminhos, largura=4000.0, altura=4000.0))
    assert [c.caminho_ancora for c in candidatos] == [0]


# --- despacho, digest e `terminal_disc` -----------------------------------------------------


def _pagina_com_os_dois() -> PaginaGramatica:
    x, y = CENTRO_DO_TERMINAL
    return pagina_gramatica(
        [
            disco(),
            *conteudo_fusivel(),
            circulo_bezier((x, y), 1.4, 6, cor=ROXO, preenchimento=ROXO),
            linha((x - 90.0, y), (x, y), 7, cor=CINZA),
        ]
    )


def test_despacho_casa_a_variante_pelo_conteudo() -> None:
    variantes = [_variante("v-fusivel", FUSIVEL), _variante("v-caixa", CAIXA_DUPLA)]
    casamentos = symbol_matcher.casar_variantes(_pagina_com_os_dois(), variantes)
    assert [(c.variante["id"], c.caminho, c.componentes) for c in casamentos] == [
        ("v-fusivel", 0, (2, 3, 4, 5))
    ]


def test_variantes_filtram_a_mesma_classificacao() -> None:
    pagina = _pagina_com_os_dois()
    uma = symbol_matcher.gasto_por_fase(pagina, [_variante("a", FUSIVEL)])
    duas = symbol_matcher.gasto_por_fase(
        pagina, [_variante("a", FUSIVEL), _variante("b", CAIXA_DUPLA)]
    )
    assert uma == duas


def test_casa_disc_mark_nao_gasta() -> None:
    contexto = _contexto([disco(), *conteudo_fusivel()])
    candidatos = disc_mark_candidatos(contexto)
    antes = contexto.orcamento.gasto
    casa_disc_mark(contexto, FUSIVEL, candidatos=candidatos)
    assert contexto.orcamento.gasto == antes


def test_terminal_disc_sai_igual_com_disc_mark_na_pagina() -> None:
    pagina = _pagina_com_os_dois()
    terminal = _variante("v-terminal", TERMINAL)
    sozinho = symbol_matcher.casar_variantes(pagina, [terminal])
    junto = symbol_matcher.casar_variantes(pagina, [terminal, _variante("v-f", FUSIVEL)])

    assert len(sozinho) == 1
    assert [(c.caixa, c.caminho) for c in sozinho] == [
        (c.caixa, c.caminho) for c in junto if c.variante["id"] == "v-terminal"
    ]


def test_terminal_disc_nao_paga_pelo_disc_mark_e_vice_versa() -> None:
    pagina = _pagina_com_os_dois()
    terminal = _variante("v-terminal", TERMINAL)
    fusivel = _variante("v-f", FUSIVEL)
    gasto = symbol_matcher.gasto_por_fase

    assert (
        gasto(pagina, [terminal, fusivel]).gramaticas
        == gasto(pagina, [terminal]).gramaticas + gasto(pagina, [fusivel]).gramaticas
    )


def test_disco_vermelho_com_marca_nao_e_terminal_disc() -> None:
    gramatica = {**TERMINAL, "min_span": 1.0, "max_span": 72.0}
    pagina = pagina_gramatica(
        [disco(), *conteudo_fusivel(), linha((60.0, 150.0), CENTRO, 6, cor=CINZA)]
    )
    assert symbol_matcher.casar_variantes(pagina, [_variante("v", gramatica)]) == ()


def test_so_disc_mark_nao_calcula_os_discos_do_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def nao_chamar(*_: object, **__: object) -> tuple[()]:
        raise AssertionError("discos_candidatos não é da gramática de disco com marca")

    monkeypatch.setattr(symbol_matcher, "discos_candidatos", nao_chamar)
    casamentos = symbol_matcher.casar_variantes(_pagina_com_os_dois(), [_variante("v", FUSIVEL)])
    assert len(casamentos) == 1


def test_sem_variante_a_pagina_nao_paga_pelo_disc_mark() -> None:
    pagina = _pagina_com_os_dois()
    assert symbol_matcher.gasto_por_fase(pagina, []).gramaticas == 0


def test_mudanca_em_grammar_disc_mark_muda_a_assinatura_do_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def assinatura(sal: str) -> str:
        def digest(modulo: Any) -> str:
            nome = str(modulo.__name__)
            return nome + (sal if nome.endswith(".grammar_disc_mark") else "")

        monkeypatch.setattr(symbol_execution, "_module_digest", digest)
        return SymbolCompositionRunner(_settings(tmp_path / "dados")).signature

    assert assinatura("") == assinatura("")
    assert assinatura("") != assinatura("-mudou")


# --- orçamento: cada parcela é derivada do desenho da página --------------------------------


def _gasto(caminhos: Sequence[Caminho]) -> int:
    contexto = _contexto(caminhos)
    antes = contexto.orcamento.gasto
    disc_mark_candidatos(contexto)
    return contexto.orcamento.gasto - antes


# Numa lista de 2 peças distintas: a primeira examina 0 únicas e a segunda, 1.
_DUAS_PECAS_DISTINTAS: Final = (1 + 0) + (1 + 1)
_UMA_PECA: Final = 1
_ITENS_DO_PONTO: Final = 8


def test_cada_caminho_da_pagina_paga_uma_vez() -> None:
    caminhos = [linha((10.0 + i, 10.0), (10.0 + i, 20.0), i) for i in range(7)]
    assert _gasto(caminhos) == len(caminhos)


def test_caminho_vermelho_paga_por_subcaminho() -> None:
    subcaminhos = tuple((ItemCaminho("l", ((10.0 + i, 10.0), (10.0 + i, 20.0))),) for i in range(7))
    base = poligono(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)), 0, VERMELHO, cor=None)
    caminho = Caminho(subcaminhos, base.estilo, base.tipo, 0)
    assert _gasto([caminho]) == 1 + len(subcaminhos)


def test_caminho_de_outra_cor_nao_paga_por_subcaminho() -> None:
    subcaminhos = tuple((ItemCaminho("l", ((10.0 + i, 10.0), (10.0 + i, 20.0))),) for i in range(7))
    base = poligono(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)), 0, VERDE, cor=None)
    assert _gasto([Caminho(subcaminhos, base.estilo, base.tipo, 0)]) == 1


def test_disco_sem_conteudo_paga_o_disco_e_a_consulta() -> None:
    assert _gasto([disco()]) == 1 + 1 + 1 + 1  # página, subcaminho, disco, grade


def test_gasto_de_uma_curva_fusivel() -> None:
    caminhos = [disco(), *conteudo_fusivel()]
    pagina, subcaminho, por_disco, grade, cobertura = (
        len(caminhos),
        1,
        1,
        len(caminhos),
        len(caminhos),
    )
    itens = 1 + 2 * SEGMENTOS_DA_CURVA + 2 * _ITENS_DO_PONTO
    deduplicacao = 1

    assert _gasto(caminhos) == (
        pagina
        + subcaminho
        + por_disco
        + grade
        + itens
        + _DUAS_PECAS_DISTINTAS  # pontos
        + _DUAS_PECAS_DISTINTAS  # curvas
        + cobertura
        + deduplicacao
    )


def test_gasto_de_uma_caixa_dupla() -> None:
    caminhos = [disco(), *conteudo_caixa_dupla()]
    pagina, subcaminho, por_disco, grade, cobertura = (
        len(caminhos),
        1,
        1,
        len(caminhos),
        len(caminhos),
    )
    itens = 1 + 4 + 1 + 2 * _ITENS_DO_PONTO
    retas_examinadas = 2  # a diagonal e a paralela
    deduplicacao = 1

    assert _gasto(caminhos) == (
        pagina
        + subcaminho
        + por_disco
        + grade
        + itens
        + _DUAS_PECAS_DISTINTAS  # pontos
        + _UMA_PECA  # retângulos
        + retas_examinadas
        + _UMA_PECA  # reta paralela
        + cobertura
        + deduplicacao
    )


def test_gasto_de_disco_redesenhado_inclui_os_vizinhos_da_deduplicacao() -> None:
    desvio: Ponto = (CENTRO[0] + 0.02, CENTRO[1] - 0.02)
    caminhos = [disco(), disco(ordem=1, centro=desvio), *conteudo_fusivel(ordem=2)]
    pagina, subcaminhos, por_disco = len(caminhos), 2, 2
    grade, cobertura = 2 * len(caminhos), 2 * len(caminhos)
    itens = 2 * (1 + 2 * SEGMENTOS_DA_CURVA + 2 * _ITENS_DO_PONTO)
    pecas = 2 * (_DUAS_PECAS_DISTINTAS + _DUAS_PECAS_DISTINTAS)
    deduplicacao = 1 + (1 + 1)  # o segundo examina o primeiro

    assert _gasto(caminhos) == (
        pagina + subcaminhos + por_disco + grade + itens + pecas + cobertura + deduplicacao
    )
