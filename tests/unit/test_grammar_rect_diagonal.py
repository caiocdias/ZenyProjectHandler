"""Gramática `rect_diagonal` (retângulo atravessado por diagonal): positivos, negativos e caixa."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.paginas import linha, pagina_gramatica, poligono, texto
from tests.fixtures.symbol_grammars.rect_diagonal import (
    CASOS_RECT_DIAGONAL,
    CENTRO,
    NEGATIVOS,
    VIZINHOS_POSITIVOS,
    DesenhoRetangulo,
    desenhar_bt_classico,
    desenhar_positivo,
    pagina_desenhada,
)

from zeny_project_handler.adapters.analysis.drawing_model import grammar_rect_diagonal
from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import tem_x
from zeny_project_handler.adapters.analysis.drawing_model.grammar_rect_diagonal import (
    casa_retangulos_diagonal,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa, Ponto
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    PaginaGramatica,
    Segmento,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import (
    CasamentoGramatica,
    casar_variantes,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_para_gramaticas
from zeny_project_handler.adapters.analysis.pymupdf_symbols import _extract_symbolic_equipment

_VARIANTES: Final = [variante for variante, _ in CASOS_RECT_DIAGONAL]
_V001, _V002, _V003, _V004 = _VARIANTES
_EPSILON: Final = 1e-3  # PyMuPDF devolve coordenadas em float32


def _pares() -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    return [
        (
            {"family_id": "autoral"},
            {"id": variante, "recognition": {"status": "enabled", "grammar": gramatica}},
        )
        for variante, gramatica in CASOS_RECT_DIAGONAL
    ]


def _casamentos(pagina: PaginaGramatica) -> tuple[CasamentoGramatica, ...]:
    return casar_variantes(pagina, _pares())


def _variantes(pagina: PaginaGramatica) -> list[str]:
    return [str(c.variante["id"]) for c in _casamentos(pagina)]


def _contem(caixa: Caixa, ponto: Ponto) -> bool:
    return (
        caixa[0] - _EPSILON <= ponto[0] <= caixa[2] + _EPSILON
        and caixa[1] - _EPSILON <= ponto[1] <= caixa[3] + _EPSILON
    )


def _desenhada(
    variante: str, graus: float = 0.0, **opcoes: Any
) -> tuple[PaginaGramatica, DesenhoRetangulo]:
    desenhos: list[DesenhoRetangulo] = []

    def desenhar(pagina: pymupdf.Page) -> None:
        desenhos.append(desenhar_positivo(pagina, variante, graus=graus, **opcoes))

    return pagina_desenhada(desenhar), desenhos[0]


@pytest.mark.parametrize("graus", [0.0, 30.0, 90.0], ids=["0", "30", "90"])
@pytest.mark.parametrize("ganchos", [False, True], ids=["liso", "ganchos"])
@pytest.mark.parametrize("variante", _VARIANTES)
def test_positivo_casa_so_a_variante_certa(variante: str, ganchos: bool, graus: float) -> None:
    pagina, _ = _desenhada(variante, graus, ganchos=ganchos)

    assert _variantes(pagina) == [variante]


@pytest.mark.parametrize("variante", _VARIANTES)
def test_ligado_por_haste_a_uma_linha_longa_casa_a_mesma_variante(variante: str) -> None:
    pagina, _ = _desenhada(variante, ganchos=True, haste=True, haste_longa=120.0)

    assert _variantes(pagina) == [variante]


@pytest.mark.parametrize("graus", [0.0, 30.0], ids=["0", "30"])
def test_diagonal_com_ganchos_e_haste_em_elipse_nao_forma_x_falso(graus: float) -> None:
    pagina, _ = _desenhada(_V002, graus, ganchos=True, haste=True)

    assert _variantes(pagina) == [_V002]


def _exibido(ponto: Ponto, matriz: Any) -> Ponto:
    """O ponto desenhado na página exibida, pela `rotation_matrix` da página."""
    return (
        matriz.a * ponto[0] + matriz.c * ponto[1] + matriz.e,
        matriz.b * ponto[0] + matriz.d * ponto[1] + matriz.f,
    )


@pytest.mark.parametrize("variante", _VARIANTES)
def test_pagina_com_rotate_90_casa_a_mesma_variante_na_pagina_exibida(variante: str) -> None:
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=300, height=200)
        desenho = desenhar_positivo(pagina, variante, centro=(100.0, 80.0), ganchos=True)
        pagina.set_rotation(90)
        matriz = pagina.rotation_matrix
        exibida = pagina_para_gramaticas(pagina, 0)

    [casamento] = _casamentos(exibida)
    assert casamento.variante["id"] == variante
    for ponto in (*desenho.cantos, *desenho.diagonal):
        assert _contem(casamento.caixa, _exibido(ponto, matriz))


@pytest.mark.parametrize("variante", _VARIANTES)
def test_caixa_e_o_pictograma(variante: str) -> None:
    pagina, desenho = _desenhada(variante, ganchos=True, haste=True)

    [casamento] = _casamentos(pagina)
    caixa = casamento.caixa
    for ponto in (*desenho.cantos, *desenho.diagonal, *desenho.ganchos):
        assert _contem(caixa, ponto)
    assert desenho.haste is not None
    assert not _contem(caixa, desenho.haste[1])
    if variante in (_V001, _V004):
        # Sem envolvente, a caixa é o retângulo unido à diagonal: o X não entra.
        pontos = (*desenho.cantos, *desenho.diagonal, *desenho.ganchos)
        assert caixa == pytest.approx(
            (
                min(p[0] for p in pontos),
                min(p[1] for p in pontos),
                max(p[0] for p in pontos),
                max(p[1] for p in pontos),
            ),
            abs=_EPSILON,
        )
        assert not any(_contem(caixa, p) for braco in desenho.bracos_x for p in braco)
    else:
        # Com envolvente, a caixa é a da elipse de raio 7 em torno do centro.
        cx, cy = CENTRO
        assert caixa == pytest.approx((cx - 7, cy - 7, cx + 7, cy + 7), abs=0.05)


@pytest.mark.parametrize(
    ("variante", "esperados"),
    [(_V001, (1, 2)), (_V002, (1, 2, 3)), (_V003, (1, 2, 3, 4, 5)), (_V004, (1, 2, 3, 4))],
)
def test_componentes(variante: str, esperados: tuple[int, ...]) -> None:
    """Ordem do desenho: retângulo (0, a âncora), diagonal com ganchos, haste, envolvente, X."""
    pagina, _ = _desenhada(variante, ganchos=True, haste=True)

    [casamento] = _casamentos(pagina)
    assert casamento.caminho == 0
    assert casamento.componentes == esperados


@pytest.mark.parametrize(
    ("variante", "esperados"),
    [(_V001, (1, 2, 3, 4)), (_V002, (1, 2, 3, 4, 5)), (_V004, (1, 2, 3, 4, 5, 6))],
)
def test_retangulo_de_quatro_caminhos_poe_os_lados_nos_componentes(
    variante: str, esperados: tuple[int, ...]
) -> None:
    """Um caminho por lado: a âncora é o primeiro lado e os outros três entram nos componentes."""
    pagina, _ = _desenhada(variante, lados_separados=True)

    [casamento] = _casamentos(pagina)
    assert casamento.caminho == 0
    assert casamento.componentes == esperados


@pytest.mark.parametrize("graus", [0.0, 30.0], ids=["0", "30"])
@pytest.mark.parametrize(("variante", "esperados"), [(_V002, (1, 2, 3)), (_V003, (1, 2, 3, 4, 5))])
def test_haste_que_sai_da_envolvente_entra_nos_componentes(
    variante: str, esperados: tuple[int, ...], graus: float
) -> None:
    """Com envolvente, a haste visível sai da borda dela, alinhada ao corpo, e não do corpo."""
    pagina, desenho = _desenhada(variante, graus, ganchos=True, haste_da_envolvente=True)

    [casamento] = _casamentos(pagina)
    assert casamento.variante["id"] == variante
    assert casamento.componentes == esperados
    assert desenho.haste is not None
    assert not _contem(casamento.caixa, desenho.haste[1])


@pytest.mark.parametrize("variante", [_V002, _V003])
def test_haste_que_sai_da_envolvente_entra_nos_proprios_do_x(
    variante: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    proprios_vistos: list[frozenset[Segmento]] = []

    def espiao(
        contexto: Any, pictograma: Caixa, escala: float, eixo: float, proprios: frozenset[Segmento]
    ) -> Any:
        proprios_vistos.append(proprios)
        return tem_x(contexto, pictograma, escala, eixo, proprios)

    monkeypatch.setattr(grammar_rect_diagonal, "tem_x", espiao)
    pagina, _ = _desenhada(variante, haste_da_envolvente=True)

    _casamentos(pagina)
    [proprios] = proprios_vistos
    assert any(segmento.caminho == 2 for segmento in proprios)


def test_traco_tangente_a_envolvente_nao_e_haste_de_ligacao() -> None:
    pagina, _ = _desenhada(_V002, traco_tangente=True)

    [casamento] = _casamentos(pagina)
    assert casamento.componentes == (1, 3)


def test_traco_perpendicular_na_ponta_nao_e_haste_de_ligacao() -> None:
    pagina, _ = _desenhada(_V001, traco_de_lado=True)

    [casamento] = _casamentos(pagina)
    assert casamento.componentes == (1,)


def test_cauda_longa_no_caminho_da_diagonal_nao_e_gancho() -> None:
    pagina, desenho = _desenhada(_V001, cauda=6.0)

    [casamento] = _casamentos(pagina)
    assert not _contem(casamento.caixa, desenho.ganchos[0])


@pytest.mark.parametrize("nome", sorted(NEGATIVOS))
def test_negativo_nao_casa(nome: str) -> None:
    assert _variantes(pagina_desenhada(NEGATIVOS[nome])) == []


@pytest.mark.parametrize("nome", sorted(VIZINHOS_POSITIVOS))
def test_vizinho_do_limiar_casa(nome: str) -> None:
    assert _variantes(pagina_desenhada(VIZINHOS_POSITIVOS[nome])) == [_V001]


def test_pagina_sem_desenho_nao_casa() -> None:
    assert _variantes(pagina_desenhada(lambda p: None)) == []


def test_dois_desenhos_na_mesma_pagina_casam_cada_um_a_sua_variante() -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        desenhar_positivo(pagina, _V001, centro=(60.0, 60.0), ganchos=True)
        desenhar_positivo(pagina, _V003, centro=(200.0, 200.0), graus=30.0)

    assert sorted(_variantes(pagina_desenhada(desenhar))) == [_V001, _V003]


def test_pictograma_maior_que_max_span_nao_casa() -> None:
    pagina, _ = _desenhada(_V002)
    estreita = {**dict(CASOS_RECT_DIAGONAL)[_V002], "max_span": 13.0}
    larga = {**dict(CASOS_RECT_DIAGONAL)[_V002], "max_span": 15.0}

    assert casa_retangulos_diagonal(contexto_gramaticas(pagina), estreita) == []
    assert len(casa_retangulos_diagonal(contexto_gramaticas(pagina), larga)) == 1


def test_casa_retangulos_diagonal_devolve_caixa_ancora_componentes_e_paga() -> None:
    pagina, desenho = _desenhada(_V001, ganchos=True)
    contexto = contexto_gramaticas(pagina)
    antes = contexto.orcamento.gasto

    [(caixa, ancora, componentes)] = casa_retangulos_diagonal(
        contexto, dict(CASOS_RECT_DIAGONAL)[_V001]
    )

    assert ancora == 0
    assert componentes == (1,)
    assert all(_contem(caixa, p) for p in (*desenho.cantos, *desenho.diagonal))
    assert contexto.orcamento.gasto > antes


def _pequena(origem: Any) -> PaginaGramatica:
    """Corpo de 2,4 por 0,8 pt, abaixo do lado maior mínimo absoluto de 3 pt."""
    cx, cy, meio_h, meio_l = 100.0, 100.0, 1.2, 0.4
    caminhos = [
        poligono(
            [
                (cx - meio_l, cy - meio_h),
                (cx + meio_l, cy - meio_h),
                (cx + meio_l, cy + meio_h),
                (cx - meio_l, cy + meio_h),
            ]
        ),
        linha((cx - 2 * meio_l, cy + meio_h / 2), (cx + 2 * meio_l, cy - meio_h / 2)),
    ]
    textos = () if origem is None else (texto("LIVRE", (5.0, 5.0, 30.0, 12.0), origem),)
    return pagina_gramatica(caminhos, textos)


def test_simbolo_pequeno_so_casa_na_pagina_de_texto_em_glifo() -> None:
    assert _variantes(_pequena("glifo")) == [_V001]
    assert _variantes(_pequena("nativo")) == []
    assert _variantes(_pequena("shx")) == []
    assert _variantes(_pequena(None)) == []


def _classica(situacao: str) -> tuple[PaginaGramatica, DesenhoRetangulo]:
    desenhos: list[DesenhoRetangulo] = []

    def desenhar(pagina: pymupdf.Page) -> None:
        desenhos.append(desenhar_bt_classico(pagina, situacao))

    return pagina_desenhada(desenhar), desenhos[0]


@pytest.mark.parametrize("situacao", _VARIANTES)
def test_bt_classico_satisfaz_o_legado(situacao: str) -> None:
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=300, height=300)
        desenhar_bt_classico(pagina, situacao)
        simbolos = _extract_symbolic_equipment(pagina, 1)

    assert [s.conteudo_bruto for s in simbolos] == ["PARA RAIOS BT"]


@pytest.mark.parametrize("situacao", _VARIANTES)
def test_bt_classico_casa_a_gramatica_nova(situacao: str) -> None:
    pagina, desenho = _classica(situacao)

    [casamento] = _casamentos(pagina)
    assert casamento.variante["id"] == situacao
    assert all(_contem(casamento.caixa, p) for p in (*desenho.cantos, *desenho.diagonal))
    assert desenho.haste is not None
    assert not _contem(casamento.caixa, desenho.haste[1])
    # A haste do legado é a haste de ligação da gramática nova: entra nos componentes.
    assert 0 in casamento.componentes
