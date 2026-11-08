"""Ataques a `rect_diagonal` (Task 3, E06.3.3.1): exclusividade, geometria, X falso, vizinhança."""

from __future__ import annotations

import ast
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import pymupdf
import pytest
from tests.fixtures.symbol_grammars import stem_bars
from tests.fixtures.symbol_grammars.paginas import linha, pagina_gramatica, poligono, texto
from tests.fixtures.symbol_grammars.rect_diagonal import (
    CASOS_RECT_DIAGONAL,
    CENTRO,
    CORPO,
    PRETO,
    desenhar_positivo,
    desenhar_retangulo,
    diagonal_inclinada,
    pagina_desenhada,
)

from zeny_project_handler.adapters.analysis.drawing_model import grammar_rect_diagonal
from zeny_project_handler.adapters.analysis.drawing_model.grammar_rect_diagonal import (
    retangulos_candidatos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Ponto
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    PaginaGramatica,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import (
    CasamentoGramatica,
    casar_variantes,
)

_VARIANTES: Final = [variante for variante, _ in CASOS_RECT_DIAGONAL]
_V001, _V002, _V003, _V004 = _VARIANTES
_MEIO_H: Final = CORPO[0] / 2
_MEIO_L: Final = CORPO[1] / 2


def _pares(
    casos: tuple[tuple[str, Mapping[str, Any]], ...] = CASOS_RECT_DIAGONAL,
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    return [
        (
            {"family_id": "autoral"},
            {"id": variante, "recognition": {"status": "enabled", "grammar": gramatica}},
        )
        for variante, gramatica in casos
    ]


def _casamentos(pagina: PaginaGramatica) -> tuple[CasamentoGramatica, ...]:
    return casar_variantes(pagina, _pares())


def _variantes(pagina: PaginaGramatica) -> list[str]:
    return [str(c.variante["id"]) for c in _casamentos(pagina)]


def _retangulo_liso(pagina: pymupdf.Page) -> None:
    cx, cy = CENTRO
    pagina.draw_rect(
        pymupdf.Rect(cx - _MEIO_L, cy - _MEIO_H, cx + _MEIO_L, cy + _MEIO_H),  # type: ignore[no-untyped-call]
        color=PRETO,
        width=0.5,
    )


def _diagonal_padrao() -> tuple[Ponto, Ponto]:
    cx, cy = CENTRO
    return (cx - _MEIO_L * 2, cy + _MEIO_H * 0.5), (cx + _MEIO_L * 2, cy - _MEIO_H * 0.5)


def _diagonal_espelhada() -> tuple[Ponto, Ponto]:
    cx, cy = CENTRO
    return (cx - _MEIO_L * 2, cy - _MEIO_H * 0.5), (cx + _MEIO_L * 2, cy + _MEIO_H * 0.5)


# --- exclusividade e geometria -------------------------------------------------------------


@pytest.mark.parametrize(
    "graus", [15.0, 45.0, 60.0, 75.0, 120.0, 135.0, 180.0, 225.0, 270.0, 315.0]
)
@pytest.mark.parametrize("variante", _VARIANTES)
def test_retangulo_girado_em_qualquer_angulo_casa_so_a_variante_certa(
    variante: str, graus: float
) -> None:
    pagina = pagina_desenhada(lambda p: desenhar_positivo(p, variante, graus=graus, ganchos=True))

    assert _variantes(pagina) == [variante]


@pytest.mark.parametrize("rotacao", [90, 180, 270])
@pytest.mark.parametrize("variante", _VARIANTES)
def test_pagina_com_rotate_e_desenho_girado_casa_so_a_variante_certa(
    variante: str, rotacao: int
) -> None:
    pagina = pagina_desenhada(
        lambda p: desenhar_positivo(p, variante, graus=30.0, ganchos=True), rotacao=rotacao
    )

    assert _variantes(pagina) == [variante]


@pytest.mark.parametrize("graus", [0.0, 30.0], ids=["0", "30"])
@pytest.mark.parametrize("variante", _VARIANTES)
def test_diagonal_espelhada_casa_a_mesma_variante(variante: str, graus: float) -> None:
    espelhada = _diagonal_espelhada()
    pagina = pagina_desenhada(
        lambda p: desenhar_positivo(p, variante, graus=graus, diagonal=espelhada, ganchos=True)
    )

    assert _variantes(pagina) == [variante]


@pytest.mark.parametrize("variante", _VARIANTES)
def test_ordem_das_variantes_nao_muda_o_resultado(variante: str) -> None:
    pagina = pagina_desenhada(lambda p: desenhar_positivo(p, variante, graus=30.0))

    direta = casar_variantes(pagina, _pares())
    inversa = casar_variantes(pagina, list(reversed(_pares())))
    assert [(c.variante["id"], c.caixa, c.caminho, c.componentes) for c in direta] == [
        (c.variante["id"], c.caixa, c.caminho, c.componentes) for c in inversa
    ]


def test_casar_duas_vezes_a_mesma_pagina_da_o_mesmo() -> None:
    pagina = pagina_desenhada(lambda p: desenhar_positivo(p, _V003, graus=30.0, ganchos=True))

    primeira = [(c.caixa, c.caminho, c.componentes) for c in _casamentos(pagina)]
    segunda = [(c.caixa, c.caminho, c.componentes) for c in _casamentos(pagina)]
    assert primeira == segunda != []


def test_o_mesmo_desenho_duas_vezes_gera_um_casamento_so() -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        desenhar_positivo(pagina, _V001)
        desenhar_positivo(pagina, _V001)

    assert _variantes(pagina_desenhada(desenhar)) == [_V001]


# --- diagonal em traços soltos, ganchos de um lado, retângulo e diagonal no mesmo caminho ----


@pytest.mark.parametrize(
    ("gancho_a", "gancho_b"), [(True, True), (True, False), (False, True)], ids=["ab", "a", "b"]
)
def test_ganchos_em_tracos_soltos_nao_mudam_a_variante(gancho_a: bool, gancho_b: bool) -> None:
    a, b = _diagonal_padrao()

    def desenhar(pagina: pymupdf.Page) -> None:
        desenhar_retangulo(pagina)
        if gancho_a:
            pagina.draw_line(a, (a[0] + 1.2, a[1]), color=PRETO, width=0.5)
        if gancho_b:
            pagina.draw_line(b, (b[0] - 1.2, b[1]), color=PRETO, width=0.5)

    assert _variantes(pagina_desenhada(desenhar)) == [_V001]


@pytest.mark.parametrize("lado", ["a", "b"])
def test_gancho_em_uma_so_ponta_do_caminho_da_diagonal_casa_sem_x(lado: str) -> None:
    a, b = _diagonal_padrao()
    pontos = [(a[0] + 1.2, a[1]), a, b] if lado == "a" else [a, b, (b[0] - 1.2, b[1])]

    def desenhar(pagina: pymupdf.Page) -> None:
        _retangulo_liso(pagina)
        pagina.draw_polyline(pontos, color=PRETO, width=0.5)

    assert _variantes(pagina_desenhada(desenhar)) == [_V001]


def test_retangulo_e_diagonal_no_mesmo_caminho_nao_repete_a_ancora_nos_componentes() -> None:
    cx, cy = CENTRO
    a, b = _diagonal_padrao()

    def desenhar(pagina: pymupdf.Page) -> None:
        forma = pagina.new_shape()  # type: ignore[no-untyped-call]
        forma.draw_polyline(
            [
                (cx - _MEIO_L, cy - _MEIO_H),
                (cx + _MEIO_L, cy - _MEIO_H),
                (cx + _MEIO_L, cy + _MEIO_H),
                (cx - _MEIO_L, cy + _MEIO_H),
                (cx - _MEIO_L, cy - _MEIO_H),
            ]
        )
        forma.draw_line(a, b)
        forma.finish(color=PRETO, width=0.5)
        forma.commit()

    [casamento] = _casamentos(pagina_desenhada(desenhar))
    assert casamento.variante["id"] == _V001
    assert casamento.caminho not in casamento.componentes
    assert list(casamento.componentes) == sorted(set(casamento.componentes))


# --- X falso -----------------------------------------------------------------------------------


@pytest.mark.parametrize("graus", [0.0, 30.0, 90.0, 135.0], ids=["0", "30", "90", "135"])
@pytest.mark.parametrize("variante", [_V001, _V002])
def test_ganchos_e_haste_nao_formam_x_em_nenhum_angulo(variante: str, graus: float) -> None:
    pagina = pagina_desenhada(
        lambda p: desenhar_positivo(p, variante, graus=graus, ganchos=True, haste=True)
    )

    assert _variantes(pagina) == [variante]


def test_haste_nas_duas_pontas_com_ganchos_nao_forma_x() -> None:
    cx, cy = CENTRO

    def desenhar(pagina: pymupdf.Page) -> None:
        desenhar_retangulo(pagina, ganchos=True, haste=True)
        pagina.draw_line((cx, cy + _MEIO_H), (cx, cy + _MEIO_H + 10), color=PRETO, width=0.5)

    assert _variantes(pagina_desenhada(desenhar)) == [_V001]


def test_um_unico_traco_curto_cruzando_a_diagonal_fora_do_corpo_nao_e_x() -> None:
    cx, cy = CENTRO

    def desenhar(pagina: pymupdf.Page) -> None:
        desenhar_retangulo(pagina)
        pagina.draw_line((cx - 4, cy + 0.5), (cx - 2.5, cy + 3.5), color=PRETO, width=0.5)

    assert _variantes(pagina_desenhada(desenhar)) == [_V001]


# --- negativos novos ------------------------------------------------------------------------


def test_retangulo_sem_diagonal_nao_casa() -> None:
    assert _variantes(pagina_desenhada(_retangulo_liso)) == []


def test_retangulo_com_haste_e_sem_diagonal_nao_casa() -> None:
    cx, cy = CENTRO

    def desenhar(pagina: pymupdf.Page) -> None:
        _retangulo_liso(pagina)
        pagina.draw_line((cx, cy - _MEIO_H), (cx, cy - _MEIO_H - 10), color=PRETO, width=0.5)

    assert _variantes(pagina_desenhada(desenhar)) == []


def _diagonal_de_comprimento(fator: float) -> tuple[Ponto, Ponto]:
    cx, cy = CENTRO
    meio = fator * CORPO[0] / 2
    dx, dy = meio * math.sin(0.8), meio * math.cos(0.8)
    return (cx - dx, cy + dy), (cx + dx, cy - dy)


@pytest.mark.parametrize("fator", [1.6, 2.0], ids=["1_6", "2_0"])
def test_diagonal_longa_demais_nao_casa(fator: float) -> None:
    diagonal = _diagonal_de_comprimento(fator)

    assert _variantes(pagina_desenhada(lambda p: desenhar_retangulo(p, diagonal=diagonal))) == []


def test_diagonal_no_limite_de_comprimento_ainda_casa() -> None:
    diagonal = _diagonal_de_comprimento(1.4)

    pagina = pagina_desenhada(lambda p: desenhar_retangulo(p, diagonal=diagonal))

    assert _variantes(pagina) == [_V001]


def test_paralelogramo_inclinado_nao_casa() -> None:
    cx, cy = CENTRO
    a, b = _diagonal_padrao()
    d = 2.0

    def desenhar(pagina: pymupdf.Page) -> None:
        pagina.draw_polyline(
            [
                (cx - _MEIO_L + d, cy - _MEIO_H),
                (cx + _MEIO_L + d, cy - _MEIO_H),
                (cx + _MEIO_L - d, cy + _MEIO_H),
                (cx - _MEIO_L - d, cy + _MEIO_H),
                (cx - _MEIO_L + d, cy - _MEIO_H),
            ],
            color=PRETO,
            width=0.5,
        )
        pagina.draw_line(a, b, color=PRETO, width=0.5)

    assert _variantes(pagina_desenhada(desenhar)) == []


def test_trapezio_nao_casa() -> None:
    cx, cy = CENTRO

    def desenhar(pagina: pymupdf.Page) -> None:
        pagina.draw_polyline(
            [
                (cx - 1.5, cy - _MEIO_H),
                (cx + 1.5, cy - _MEIO_H),
                (cx + 2.5, cy + _MEIO_H),
                (cx - 2.5, cy + _MEIO_H),
                (cx - 1.5, cy - _MEIO_H),
            ],
            color=PRETO,
            width=0.5,
        )
        pagina.draw_line((cx - 3.0, cy + 2.0), (cx + 3.0, cy - 2.0), color=PRETO, width=0.5)

    assert _variantes(pagina_desenhada(desenhar)) == []


def test_duas_diagonais_de_inclinacoes_diferentes_no_retangulo_nao_casam() -> None:
    primeira = _diagonal_espelhada()
    segunda = diagonal_inclinada(CORPO, 0.75)

    def desenhar(pagina: pymupdf.Page) -> None:
        desenhar_retangulo(pagina, diagonal=primeira)
        pagina.draw_line(segunda[0], segunda[1], color=PRETO, width=0.5)

    assert _variantes(pagina_desenhada(desenhar)) == []


def test_palavra_fora_do_retangulo_nao_impede_o_casamento() -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        desenhar_retangulo(pagina)
        pagina.insert_text((200, 40), "AB", fontsize=6)

    assert _variantes(pagina_desenhada(desenhar)) == [_V001]


def test_retangulo_com_texto_em_glifo_no_miolo_nao_casa() -> None:
    cx, cy, meio_h, meio_l = 100.0, 100.0, 4.0, 1.5
    caminhos = [
        poligono(
            [
                (cx - meio_l, cy - meio_h),
                (cx + meio_l, cy - meio_h),
                (cx + meio_l, cy + meio_h),
                (cx - meio_l, cy + meio_h),
            ]
        ),
        linha((cx - 3.0, cy + 2.0), (cx + 3.0, cy - 2.0)),
    ]
    textos = (texto("A", (cx - 0.5, cy - 0.5, cx + 0.5, cy + 0.5), "glifo"),)

    assert _variantes(pagina_gramatica(caminhos, textos)) == []


# --- cor da diagonal (R-E06.3.3.2.1-5): a cor canonica do retangulo -------------------------

_AZUL: Final = (0.0, 0.0, 1.0)
_VERMELHO: Final = (1.0, 0.0, 0.0)
_VERDE: Final = (0.0, 0.5, 0.0)


def _retangulo_e_diagonal(cor_retangulo: Any, cor_diagonal: Any) -> PaginaGramatica:
    a, b = _diagonal_padrao()
    cx, cy = CENTRO

    def desenhar(pagina: pymupdf.Page) -> None:
        pagina.draw_rect(
            pymupdf.Rect(cx - _MEIO_L, cy - _MEIO_H, cx + _MEIO_L, cy + _MEIO_H),  # type: ignore[no-untyped-call]
            color=cor_retangulo,
            width=0.5,
        )
        pagina.draw_line(a, b, color=cor_diagonal, width=0.5)

    return pagina_desenhada(desenhar)


@pytest.mark.parametrize(
    ("cor_retangulo", "cor_diagonal"),
    [(PRETO, _AZUL), (PRETO, _VERMELHO), (_VERDE, PRETO), (_VERMELHO, _VERDE)],
    ids=["preto-azul", "preto-vermelho", "verde-preto", "vermelho-verde"],
)
def test_diagonal_de_cor_canonica_diferente_da_do_retangulo_nao_casa(
    cor_retangulo: Any, cor_diagonal: Any
) -> None:
    """Nas 16 folhas, os 23 BT candidatos tem a mesma cor canonica na diagonal e no retangulo
    (ruling da Task 4): diagonal de outra cor canonica nao e a do para-raios."""
    assert _variantes(_retangulo_e_diagonal(cor_retangulo, cor_diagonal)) == []


@pytest.mark.parametrize(
    ("cor_retangulo", "cor_diagonal"),
    [
        (PRETO, PRETO),
        (_VERDE, _VERDE),
        (_VERMELHO, _VERMELHO),
        (PRETO, (0.1, 0.1, 0.1)),
        (_VERDE, (0.1, 0.6, 0.1)),
    ],
    ids=["preto", "verde", "vermelho", "preto-e-cinza-escuro", "verde-e-verde-claro"],
)
def test_diagonal_da_mesma_cor_canonica_do_retangulo_casa(
    cor_retangulo: Any, cor_diagonal: Any
) -> None:
    """Controle positivo: a cor canonica e a mesma, ainda que o RGB cru mude."""
    assert _variantes(_retangulo_e_diagonal(cor_retangulo, cor_diagonal)) == [_V001]


_LEDGER: Final = "ledger E06.3.3.1 Task 3, para a E06.3.3.2"


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=f"diagonal quase duplicada recusa o simbolo ({_LEDGER})",
)
def test_diagonal_tracada_duas_vezes_com_deslocamento_ainda_reconhece_o_simbolo() -> None:
    """Dois tracos quase coincidentes (entidade duplicada de CAD) sao um simbolo so."""
    a, b = _diagonal_padrao()

    def desenhar(pagina: pymupdf.Page) -> None:
        desenhar_retangulo(pagina)
        pagina.draw_line((a[0] + 0.3, a[1]), (b[0] + 0.3, b[1]), color=PRETO, width=0.5)

    assert _variantes(pagina_desenhada(desenhar)) == [_V001]


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=f"contorno quase duplicado gera dois casamentos ({_LEDGER})",
)
def test_contorno_duplicado_com_deslocamento_gera_um_casamento_so() -> None:
    """Dois retangulos quase coincidentes sao um simbolo so."""
    cx, cy = CENTRO

    def desenhar(pagina: pymupdf.Page) -> None:
        desenhar_retangulo(pagina)
        contorno = pymupdf.Rect(cx - 1.8, cy - 4.3, cx + 1.8, cy + 4.3)  # type: ignore[no-untyped-call]
        pagina.draw_rect(contorno, color=PRETO, width=0.5)

    assert _variantes(pagina_desenhada(desenhar)) == [_V001]


def test_x_curto_de_cor_diferente_da_do_retangulo_nao_e_lido_como_diagonal() -> None:
    """Bracos vermelhos de 1,2 vezes o lado maior cruzam o retangulo preto como diagonais, mas
    a cor canonica difere da do retangulo (R-E06.3.3.2.1-5): nao sao diagonais, sao o X da
    v004. O X curto da mesma cor do retangulo continua sem cobertura (ledger)."""
    cx, cy = CENTRO
    meio = 1.2 * CORPO[0] / 2 / math.sqrt(2)

    def desenhar(pagina: pymupdf.Page) -> None:
        desenhar_retangulo(pagina)
        for sinal in (1, -1):
            pagina.draw_line(
                (cx - meio, cy - sinal * meio),
                (cx + meio, cy + sinal * meio),
                color=(1.0, 0.0, 0.0),
                width=0.5,
            )

    assert _variantes(pagina_desenhada(desenhar)) == [_V004]


# --- desconhecidos, orcamento, pureza e convivencia com a haste ------------------------------


def test_kind_desconhecido_e_recusado_com_erro_claro() -> None:
    pagina = pagina_desenhada(lambda p: desenhar_positivo(p, _V001))
    gramatica = {**dict(CASOS_RECT_DIAGONAL)[_V001], "kind": "rect_diagonal_v2"}
    pares = [
        (
            {"family_id": "autoral"},
            {"id": "x", "recognition": {"status": "enabled", "grammar": gramatica}},
        )
    ]

    with pytest.raises(ValueError, match="rect_diagonal_v2"):
        casar_variantes(pagina, pares)


def test_pagina_sem_quadrilatero_nao_gasta_orcamento_nas_consultas_novas() -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        for i in range(40):
            pagina.draw_line((10 + i, 10), (20 + i, 40), color=PRETO, width=0.5)

    contexto = contexto_gramaticas(pagina_desenhada(desenhar))
    antes = contexto.orcamento.gasto

    assert retangulos_candidatos(contexto) == ()
    assert contexto.orcamento.gasto == antes


def test_pagina_com_retangulo_paga_pelas_consultas() -> None:
    contexto = contexto_gramaticas(pagina_desenhada(lambda p: desenhar_positivo(p, _V003)))
    antes = contexto.orcamento.gasto

    assert len(retangulos_candidatos(contexto)) == 1
    assert contexto.orcamento.gasto > antes


def test_gasto_de_retangulos_candidatos_cresce_com_as_sementes_nas_celulas_do_retangulo() -> None:
    """Sementes (tracos de comprimento plausivel) junto ao retangulo pagam consultas a grade.

    Mede so o gasto da chamada: orcamento antes e depois de `retangulos_candidatos`.
    """
    cx, cy = CENTRO

    def gasto_com(n: int) -> int:
        def desenhar(pagina: pymupdf.Page) -> None:
            desenhar_retangulo(pagina)
            for i in range(n):
                x = cx + 2.5 + 0.01 * i
                pagina.draw_line((x, cy - 2.5), (x, cy + 2.5), color=PRETO, width=0.5)

        contexto = contexto_gramaticas(pagina_desenhada(desenhar))
        antes = contexto.orcamento.gasto
        retangulos_candidatos(contexto)
        return contexto.orcamento.gasto - antes

    assert gasto_com(100) > gasto_com(0)


def test_modulo_da_gramatica_nao_importa_pymupdf() -> None:
    arvore = ast.parse(Path(grammar_rect_diagonal.__file__).read_text(encoding="utf-8"))
    importados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados.update(alias.name.split(".")[0] for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            importados.add(no.module.split(".")[0])

    assert not importados & {"pymupdf", "fitz", "sqlite3", "sqlalchemy"}


def _identidade(pagina: PaginaGramatica, variante: str) -> list[tuple[Any, ...]]:
    return [
        (c.variante["id"], c.caixa, c.caminho, c.componentes)
        for c in casar_variantes(pagina, _pares((*stem_bars.CASOS_HASTE, *CASOS_RECT_DIAGONAL)))
        if c.variante["id"] == variante
    ]


@pytest.mark.parametrize("variante", [v for v, _ in stem_bars.CASOS_HASTE])
def test_haste_tem_a_mesma_saida_com_a_gramatica_nova_na_mesma_pagina(variante: str) -> None:
    def so_haste(pagina: pymupdf.Page) -> None:
        stem_bars.desenhar_positivo(pagina, variante, centro=(60.0, 60.0))

    def os_dois(pagina: pymupdf.Page) -> None:
        so_haste(pagina)
        desenhar_positivo(pagina, _V004, centro=(220.0, 220.0), ganchos=True, haste=True)

    sozinha = _identidade(pagina_desenhada(so_haste), variante)
    junta = _identidade(pagina_desenhada(os_dois), variante)
    assert sozinha == junta != []


@pytest.mark.parametrize("variante", _VARIANTES)
def test_retangulo_tem_a_mesma_saida_com_a_haste_na_mesma_pagina(variante: str) -> None:
    def so_retangulo(pagina: pymupdf.Page) -> None:
        desenhar_positivo(pagina, variante, centro=(220.0, 220.0), ganchos=True)

    def os_dois(pagina: pymupdf.Page) -> None:
        so_retangulo(pagina)
        stem_bars.desenhar_positivo(pagina, "cemig-eo-r3-s19-v003", centro=(60.0, 60.0))

    sozinho = _identidade(pagina_desenhada(so_retangulo), variante)
    junto = _identidade(pagina_desenhada(os_dois), variante)
    assert sozinho == junto != []
