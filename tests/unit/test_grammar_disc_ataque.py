# mypy: disable-error-code="no-untyped-call"
"""Ataque à gramática do disco terminal: paridade com o motor em PDFs sintéticos, custo contado
em orçamento e coordenada ou cor degeneradas."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Final

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.paginas import estilo, pagina_gramatica, texto

from zeny_project_handler.adapters.analysis import declarative_symbols as motor_atual
from zeny_project_handler.adapters.analysis.drawing_model.grammar_disc import (
    casa_disco,
    discos_candidatos,
    pontas_terminais,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caixa,
    Caminho,
    Cor,
    ItemCaminho,
    Polilinha,
    TextoModelo,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    PaginaGramatica,
    TetoGramaticasExcedido,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import (
    pagina_modelo_com_indices,
)

GRAMATICA: Final[dict[str, Any]] = {
    "kind": "terminal_disc",
    "fill": "purple",
    "min_span": 1.0,
    "max_span": 4.0,
    "terminal_line": True,
}
ROXO: Final[Cor] = (0.31, 0.10, 0.30)
CINZA: Final[Cor] = (0.5, 0.5, 0.5)
BRANCO: Final[Cor] = (1.0, 1.0, 1.0)
CENTRO: Final = (150.0, 150.0)
KAPPA: Final = 0.5522847498307936

Desenho = Callable[[pymupdf.Page], None]


# --- leitores: o motor atual e o modelo, sobre o mesmo PDF ---------------------------------


@contextmanager
def _pagina_lida(desenho: Desenho) -> Iterator[pymupdf.Page]:
    with pymupdf.open() as escrito:
        desenho(escrito.new_page(width=300, height=300))
        with pymupdf.open("pdf", escrito.tobytes()) as lido:
            yield lido.load_page(0)


def _casados_pelo_motor(pagina: pymupdf.Page) -> int:
    desenhos = tuple(pagina.get_drawings())
    discos = motor_atual._disc_candidates(desenhos)
    campos: dict[str, Any] = {
        "page": pagina,
        "source": None,
        "profile": None,
        "drawings": desenhos,
        "frames": (),
        "discs": discos,
        "segments": motor_atual._visible_segments(desenhos),
        "word_boxes": tuple(pymupdf.Rect(palavra[:4]) for palavra in pagina.get_text("words")),
    }
    contexto = motor_atual._ObservationContext(**campos)
    return sum(motor_atual._terminal_disc_matches(contexto, GRAMATICA, d) for d in discos)


def _casados_pelo_modelo(pagina: pymupdf.Page) -> int:
    modelo, indices = pagina_modelo_com_indices(pagina, 0)
    desenhos = pagina.get_drawings()
    translucidos = frozenset(
        posicao
        for posicao, cru in enumerate(indices)
        if float(desenhos[cru].get("fill_opacity") or 1.0) < 0.99
    )
    contexto = contexto_gramaticas(PaginaGramatica(modelo, indices, translucidos))
    pontas = pontas_terminais(contexto)
    return sum(casa_disco(contexto, GRAMATICA, d, pontas) for d in discos_candidatos(contexto))


def _leituras(desenho: Desenho) -> tuple[bool, bool]:
    """(motor casa, modelo casa) sobre o mesmo PDF gerado."""
    with _pagina_lida(desenho) as pagina:
        return _casados_pelo_motor(pagina) > 0, _casados_pelo_modelo(pagina) > 0


# --- desenhos (cada um recebe a página) ---------------------------------------------------


def _linha(
    pagina: pymupdf.Page,
    a: tuple[float, float] = (60.0, 150.0),
    b: tuple[float, float] = CENTRO,
    cor: Cor = CINZA,
    tracejado: str | None = None,
) -> None:
    pagina.draw_line(a, b, color=cor, width=0.7, dashes=tracejado)


def _disco(
    pagina: pymupdf.Page,
    cor: Cor = ROXO,
    raio: float = 1.4,
    centro: tuple[float, float] = CENTRO,
) -> None:
    pagina.draw_circle(centro, raio, color=cor, fill=cor, width=0.2)


def _elipse(pagina: pymupdf.Page, caixa: pymupdf.Rect) -> None:
    pagina.draw_oval(caixa, color=ROXO, fill=ROXO)


def _corda(indice: int, quantidade: int, raio: float) -> pymupdf.Rect:
    altura = 2 * raio / quantidade
    topo = CENTRO[1] - raio + indice * altura
    desvio = topo + altura / 2 - CENTRO[1]
    meia = math.sqrt(max(0.0, raio * raio - desvio * desvio))
    return pymupdf.Rect(CENTRO[0] - meia, topo, CENTRO[0] + meia, topo + altura)


def _faixas(
    pagina: pymupdf.Page, quantidade: int = 12, raio: float = 1.4, *, com_triangulos: bool = False
) -> None:
    for indice in range(quantidade):
        caixa = _corda(indice, quantidade, raio)
        if com_triangulos and indice % 2:
            forma = pagina.new_shape()
            forma.draw_polyline(
                [caixa.tl, caixa.tr, caixa.br, caixa.tl, caixa.br, caixa.bl, caixa.tl]
            )
            forma.finish(color=ROXO, fill=ROXO, width=0.1)
            forma.commit()
        else:
            pagina.draw_rect(caixa, color=ROXO if com_triangulos else None, fill=ROXO, width=0.1)


def _faixas_num_so_caminho(pagina: pymupdf.Page, de_baixo_para_cima: bool = False) -> None:
    indices = range(12)
    forma = pagina.new_shape()
    for indice in reversed(indices) if de_baixo_para_cima else indices:
        forma.draw_rect(_corda(indice, 12, 1.4))
    forma.finish(color=None, fill=ROXO)
    forma.commit()


def _faixas_com_triangulos_no_mesmo_caminho(pagina: pymupdf.Page) -> None:
    forma = pagina.new_shape()
    for indice in range(12):
        caixa = _corda(indice, 12, 1.4)
        if indice % 2:
            forma.draw_polyline([caixa.tl, caixa.tr, caixa.br, caixa.tl])
        else:
            forma.draw_rect(caixa)
    forma.finish(color=None, fill=ROXO)
    forma.commit()


def _polilinha(
    pagina: pymupdf.Page, pontos: list[tuple[float, float]], preenchimento: Cor | None = None
) -> None:
    forma = pagina.new_shape()
    forma.draw_polyline(pontos)
    forma.finish(color=CINZA, fill=preenchimento, width=0.7, closePath=False)
    forma.commit()


def _cobertura(pagina: pymupdf.Page, caixa: pymupdf.Rect, opacidade: float = 1.0) -> None:
    pagina.draw_rect(caixa, color=None, fill=BRANCO, fill_opacity=opacidade)


def _texto(
    pagina: pymupdf.Page, posicao: tuple[float, float], conteudo: str, tamanho: float = 2.0
) -> None:
    pagina.insert_text(posicao, conteudo, fontsize=tamanho)


def _cena(*passos: Desenho) -> Desenho:
    def desenhar(pagina: pymupdf.Page) -> None:
        for passo in passos:
            passo(pagina)

    return desenhar


def _com_linha_e(*passos: Desenho) -> Desenho:
    return _cena(_linha, *passos)


def _quadro_com_quina_no_centro(pagina: pymupdf.Page) -> None:
    pagina.draw_rect(pymupdf.Rect(60, 60, 150, 150), color=CINZA, width=0.7)


def _circulo_branco_maior(pagina: pymupdf.Page) -> None:
    pagina.draw_circle(CENTRO, 3, color=None, fill=BRANCO)


def _traco_branco_largo(pagina: pymupdf.Page) -> None:
    pagina.draw_line((100, 150), (200, 150), color=BRANCO, width=6)


def _split_com_contorno_duplicado(pagina: pymupdf.Page) -> None:
    pagina.draw_circle(CENTRO, 1.4, color=None, fill=ROXO)
    pagina.draw_circle(CENTRO, 1.4, color=ROXO, width=0.3)
    pagina.draw_circle(CENTRO, 1.4, color=ROXO, width=0.3)


def _p(funcao: Callable[..., None], *args: Any, **kwargs: Any) -> Desenho:
    """Fixa os argumentos depois da página: `funcao(pagina, *args, **kwargs)`."""

    def desenhar(pagina: pymupdf.Page) -> None:
        funcao(pagina, *args, **kwargs)

    return desenhar


def _linha_ate(ponta: tuple[float, float]) -> Desenho:
    return _p(_linha, b=ponta)


def _linha_de(origem: tuple[float, float]) -> Desenho:
    return _p(_linha, a=origem)


# --- paridade: o motor e o modelo concordam -----------------------------------------------

# nome -> (desenho, casa). O motor e o modelo precisam dar o mesmo `casa`: o teste confere os
# dois contra o valor da tabela, e não um contra o outro, para um empate em "não casa" não passar.
PARES: Final[dict[str, tuple[Desenho, bool]]] = {
    # onde termina a ponta: perto = max(0,6; 0,35 * vão) = 0,98 para o disco de vão 2,8
    "ponta_no_centro": (_com_linha_e(_disco), True),
    "ponta_a_0_5_do_centro": (_cena(_linha_ate((150.5, 150.0)), _disco), True),
    "ponta_a_0_9_do_centro": (_cena(_linha_ate((150.9, 150.0)), _disco), True),
    "ponta_a_1_0_do_centro": (_cena(_linha_ate((151.0, 150.0)), _disco), False),
    "ponta_a_1_1_do_centro": (_cena(_linha_ate((151.1, 150.0)), _disco), False),
    # onde está a outra ponta: longe = 2 * vão = 5,6
    "outra_ponta_a_5_5": (_cena(_linha_de((144.5, 150.0)), _disco), False),
    "outra_ponta_a_5_61": (_cena(_linha_de((144.39, 150.0)), _disco), True),
    "outra_ponta_a_6": (_cena(_linha_de((144.0, 150.0)), _disco), True),
    "linha_curta": (_cena(_linha_de((148.0, 150.0)), _disco), False),
    "linha_diagonal": (_cena(_linha_de((100.0, 100.0)), _disco), True),
    "linha_branca": (_cena(_p(_linha, cor=BRANCO), _disco), False),
    "linha_quase_branca_visivel": (_cena(_p(_linha, cor=(0.89, 0.95, 0.95)), _disco), True),
    "linha_tracejada": (_cena(_p(_linha, tracejado="[2 1] 0"), _disco), True),
    "linha_pintada_duas_vezes": (_cena(_linha, _linha, _disco), True),
    "linha_e_outra_na_outra_ponta": (
        _cena(_linha, _p(_linha, (60.0, 150.0), (60.0, 10.0)), _disco),
        True,
    ),
    "tres_linhas_convergindo": (
        _cena(
            _linha,
            _p(_linha, (150.0, 60.0), CENTRO),
            _p(_linha, (240.0, 150.0), CENTRO),
            _disco,
        ),
        True,
    ),
    "linha_de_traco_e_preenchimento": (
        _cena(_disco, _p(_polilinha, [(60.0, 150.0), (150.0, 150.0)], (0.7, 0.7, 0.9))),
        True,
    ),
    "dois_tracos_de_estilos_diferentes_em_canto": (
        _cena(_linha, _p(_linha, CENTRO, (150.0, 240.0), (0.4, 0.5, 0.5)), _disco),
        True,
    ),
    "quadro_com_quina_no_centro_e_so_re": (_cena(_quadro_com_quina_no_centro, _disco), False),
    "sem_linha": (_cena(_disco), False),
    "disco_longe_da_linha": (_com_linha_e(_p(_disco, centro=(290.0, 150.0))), False),
    "disco_que_vaza_da_pagina": (
        _cena(_p(_linha, (200.0, 150.0), (299.5, 150.0)), _p(_disco, centro=(299.5, 150.0))),
        True,
    ),
    # forma do disco
    "disco_solido": (_com_linha_e(_disco), True),
    "disco_dividido_com_contorno_duplicado": (_com_linha_e(_split_com_contorno_duplicado), True),
    "faixas_12": (_com_linha_e(_faixas), True),
    "faixas_12_com_traco_e_triangulos": (_com_linha_e(_p(_faixas, com_triangulos=True)), True),
    "faixas_5": (_com_linha_e(_p(_faixas, 5)), True),
    "faixas_4": (_com_linha_e(_p(_faixas, 4)), False),
    "faixas_30_de_raio_1_9": (_com_linha_e(_p(_faixas, 30, 1.9)), True),
    "faixas_num_so_caminho_de_re": (_com_linha_e(_faixas_num_so_caminho), True),
    "faixas_num_so_caminho_de_baixo_para_cima": (
        _com_linha_e(_p(_faixas_num_so_caminho, True)),
        True,
    ),
    "faixas_num_so_caminho_com_triangulos": (
        _com_linha_e(_faixas_com_triangulos_no_mesmo_caminho),
        False,
    ),
    "elipse_2_8_por_3_4": (
        _com_linha_e(_p(_elipse, pymupdf.Rect(148.6, 148.0, 151.4, 151.4))),
        True,
    ),
    "elipse_4_por_2_8": (
        _com_linha_e(_p(_elipse, pymupdf.Rect(148.0, 148.6, 152.0, 151.4))),
        False,
    ),
    "raio_0_45": (_com_linha_e(_p(_disco, raio=0.45)), False),
    "raio_0_55": (_com_linha_e(_p(_disco, raio=0.55)), True),
    "raio_2": (_com_linha_e(_p(_disco, raio=2.0)), True),
    "raio_2_02": (_com_linha_e(_p(_disco, raio=2.02)), False),
    # cor
    "cor_roxa_escura": (_com_linha_e(_p(_disco, (0.2, 0.0, 0.3))), True),
    "cor_com_verde_alto": (_com_linha_e(_p(_disco, (0.3, 0.25, 0.3))), False),
    "cor_clara": (_com_linha_e(_p(_disco, (0.9, 0.2, 0.9))), False),
    "cor_acima_de_0_6": (_com_linha_e(_p(_disco, (0.61, 0.1, 0.6))), False),
    # texto
    "rotulo_sobre_o_disco": (_com_linha_e(_disco, _p(_texto, (149.2, 150.7), "1")), False),
    "rotulo_ao_lado": (_com_linha_e(_disco, _p(_texto, (152.0, 150.7), "1")), True),
    "rotulo_de_varias_palavras_no_disco": (
        _com_linha_e(_disco, _p(_texto, (146.0, 150.7), "A B C")),
        False,
    ),
    "texto_longo_que_so_atravessa_o_disco": (
        _com_linha_e(_disco, _p(_texto, (100.0, 150.7), "ABC DEF", 8.0)),
        True,
    ),
    # cobertura
    "coberto_por_retangulo_maior": (
        _com_linha_e(_disco, _p(_cobertura, pymupdf.Rect(140, 140, 160, 160))),
        False,
    ),
    "coberto_por_retangulo_igual": (
        _com_linha_e(_disco, _p(_cobertura, pymupdf.Rect(148.6, 148.6, 151.4, 151.4))),
        False,
    ),
    "coberto_por_retangulo_recuado_0_005": (
        _com_linha_e(_disco, _p(_cobertura, pymupdf.Rect(148.605, 148.605, 151.395, 151.395))),
        False,
    ),
    "coberto_por_circulo_maior": (_com_linha_e(_disco, _circulo_branco_maior), False),
    "coberto_por_retangulo_gigante": (
        _com_linha_e(_disco, _p(_cobertura, pymupdf.Rect(-500, -500, 900, 900))),
        False,
    ),
    "coberto_por_translucido": (
        _com_linha_e(_disco, _p(_cobertura, pymupdf.Rect(140, 140, 160, 160), 0.5)),
        True,
    ),
    "coberto_antes": (_com_linha_e(_p(_cobertura, pymupdf.Rect(140, 140, 160, 160)), _disco), True),
    "coberto_so_em_parte": (
        _com_linha_e(_disco, _p(_cobertura, pymupdf.Rect(149, 140, 160, 160))),
        True,
    ),
    "traco_branco_largo_nao_e_preenchimento": (_com_linha_e(_disco, _traco_branco_largo), True),
}


@pytest.mark.parametrize("nome", sorted(PARES))
def test_o_modelo_casa_como_o_motor(nome: str) -> None:
    desenho, casa = PARES[nome]
    assert _leituras(desenho) == (casa, casa)


# --- divergências previstas pelo plano (R-E06.2.1-6) --------------------------------------

DIVERGENCIAS_PREVISTAS: Final[dict[str, tuple[Desenho, bool, bool]]] = {
    "dois_tracos_atravessando_o_disco": (
        _cena(_linha, _p(_linha, CENTRO, (240.0, 150.0)), _disco),
        True,
        False,
    ),
    "polilinha_de_um_traco_atravessando_o_disco": (
        _cena(_p(_polilinha, [(60.0, 150.0), CENTRO, (240.0, 150.0)]), _disco),
        True,
        False,
    ),
    # o último segmento é curto: o motor julga cada segmento e perde a ponta; o modelo, não
    "ziguezague_que_termina_no_disco": (
        _cena(_p(_polilinha, [(60.0, 150.0), (149.0, 150.0), (150.1, 150.1)]), _disco),
        False,
        True,
    ),
}


@pytest.mark.parametrize("nome", sorted(DIVERGENCIAS_PREVISTAS))
def test_divergencia_prevista_com_o_motor(nome: str) -> None:
    desenho, motor, modelo = DIVERGENCIAS_PREVISTAS[nome]
    assert _leituras(desenho) == (motor, modelo)


# --- a decidir: o plano não diz, e o modelo difere do motor ---------------------------------
# R-E06.2.1-6 fala da linha que "atravessa o disco em dois segmentos". Estes casos são da mesma
# família, mas o plano não os nomeia: a linha dobra no disco, duas linhas chegam dos dois lados,
# ou um traço solto de mesmo estilo começa a menos de 0,5 pt do centro (a fusão de polilinhas
# junta pontas a até 0,5 pt). Os testes só gravam o comportamento de hoje, para o caso ser
# reproduzível; nenhum deles afirma que ele é o certo.

A_DECIDIR: Final[dict[str, Desenho]] = {
    "linha_dobra_no_disco_em_dois_tracos": _cena(
        _linha, _p(_linha, CENTRO, (150.0, 240.0)), _disco
    ),
    "linha_dobra_no_disco_numa_polilinha": _cena(
        _p(_polilinha, [(60.0, 150.0), CENTRO, (150.0, 240.0)]), _disco
    ),
    "duas_linhas_chegam_de_lados_opostos": _cena(
        _linha, _p(_linha, (240.0, 150.0), CENTRO), _disco
    ),
    "linha_e_traco_solto_a_menos_de_meio_ponto": _cena(
        _linha, _p(_linha, (150.4, 150.0), (150.4, 100.0)), _disco
    ),
}


@pytest.mark.parametrize("nome", sorted(A_DECIDIR))
def test_a_decidir_o_motor_casa_e_o_modelo_nao(nome: str) -> None:
    assert _leituras(A_DECIDIR[nome]) == (True, False)


# --- degenerações: o modelo aceita qualquer float finito -----------------------------------


def _curvas_em(centro: tuple[float, float], raio: float) -> tuple[ItemCaminho, ...]:
    cx, cy = centro
    k = KAPPA * raio
    pontos = (
        ((cx + raio, cy), (cx + raio, cy + k), (cx + k, cy + raio), (cx, cy + raio)),
        ((cx, cy + raio), (cx - k, cy + raio), (cx - raio, cy + k), (cx - raio, cy)),
        ((cx - raio, cy), (cx - raio, cy - k), (cx - k, cy - raio), (cx, cy - raio)),
        ((cx, cy - raio), (cx + k, cy - raio), (cx + raio, cy - k), (cx + raio, cy)),
    )
    return tuple(ItemCaminho("c", quatro) for quatro in pontos)


def _disco_a_mao(centro: tuple[float, float], ordem: int, cor: Cor = ROXO) -> Caminho:
    return Caminho((_curvas_em(centro, 1.4),), estilo(None, cor), "preenchimento", ordem)


def _faixa_a_mao(caixa: Caixa, ordem: int, cor: Cor = ROXO) -> Caminho:
    x0, y0, x1, y1 = caixa
    cantos = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    itens = tuple(ItemCaminho("l", (p, cantos[(i + 1) % 4])) for i, p in enumerate(cantos))
    return Caminho((itens,), estilo(None, cor), "preenchimento", ordem)


def _vertical(x: float, ordem: int) -> Caminho:
    item = ItemCaminho("l", ((x, 50.0), (x, 150.0)))
    return Caminho(((item,),), estilo(CINZA), "traco", ordem)


def _casados_a_mao(caminhos: list[Caminho], primitivas: list[Polilinha] | None = None) -> int:
    contexto = contexto_gramaticas(pagina_gramatica(caminhos, primitivas=primitivas))
    pontas = pontas_terminais(contexto)
    return sum(casa_disco(contexto, GRAMATICA, d, pontas) for d in discos_candidatos(contexto))


def _faixas_de_disco_a_mao(cor: Cor) -> list[Caminho]:
    cordas = [_corda(indice, 12, 1.4) for indice in range(12)]
    return [
        _faixa_a_mao((c.x0, c.y0, c.x1, c.y1), indice + 1, cor) for indice, c in enumerate(cordas)
    ]


def test_faixas_de_altura_subnormal_nao_quebram() -> None:
    minimo = 5e-324
    caminhos = [_faixa_a_mao((0.0, 0.0, minimo, minimo), ordem) for ordem in range(6)]
    assert _casados_a_mao(caminhos) == 0


def test_disco_de_curva_de_largura_subnormal_nao_quebra() -> None:
    minimo = 5e-324
    pontos = ((0.0, 0.0), (minimo, 0.0), (minimo, minimo), (0.0, minimo))
    itens = tuple(ItemCaminho("c", pontos) for _ in range(4))
    caminho = Caminho((itens,), estilo(None, ROXO), "preenchimento", 0)
    assert _casados_a_mao([caminho]) == 0


@pytest.mark.parametrize(
    "cor",
    [
        (math.nan, math.nan, math.nan),
        (math.inf, math.inf, math.inf),
        (-math.inf, 0.0, -math.inf),
        (1e308, 1e308, 1e308),
        (-0.0, -0.0, -0.0),
        (0.31, 0.10, math.nan),
    ],
    ids=["nan", "inf", "menos_inf", "enorme", "zero_negativo", "azul_nan"],
)
def test_cor_degenerada_do_disco_nao_quebra_nem_casa(cor: Cor) -> None:
    assert _casados_a_mao([_vertical(150.0, 0), _disco_a_mao(CENTRO, 1, cor)]) == 0


@pytest.mark.parametrize(
    "cor",
    [(math.nan, math.nan, math.nan), (math.inf, math.inf, math.inf), (1e308, 1e308, 1e308)],
    ids=["nan", "inf", "enorme"],
)
def test_cor_degenerada_das_faixas_nao_quebra_nem_casa(cor: Cor) -> None:
    assert _casados_a_mao([_vertical(150.0, 0), *_faixas_de_disco_a_mao(cor)]) == 0


def test_faixas_de_disco_a_mao_casam_com_cor_roxa() -> None:
    """O controle dos testes de cor: as mesmas faixas, em roxo, casam."""
    assert _casados_a_mao([_vertical(150.0, 0), *_faixas_de_disco_a_mao(ROXO)]) == 1


@pytest.mark.parametrize("centro", [(1e308, 1e308), (-1e308, 1e308), (1.7e308, -1.7e308)])
def test_disco_em_coordenada_enorme_nao_quebra(centro: tuple[float, float]) -> None:
    assert _casados_a_mao([_disco_a_mao(centro, 0)]) == 0


def test_ponta_de_linha_em_coordenada_enorme_termina_no_disco_sem_quebrar() -> None:
    linha = Polilinha(((1.7e308, 1.7e308), CENTRO), False, estilo(CINZA), (1,))
    assert _casados_a_mao([_disco_a_mao(CENTRO, 0)], primitivas=[linha]) == 1


def test_linha_de_coordenada_enorme_dos_dois_lados_nao_quebra() -> None:
    linha = Polilinha(((-1.7e308, 150.0), (1.7e308, 150.0)), False, estilo(CINZA), (1,))
    assert _casados_a_mao([_disco_a_mao(CENTRO, 0)], primitivas=[linha]) == 0


# --- custo contado em orçamento, em página hostil ---------------------------------------------


def _fundo(quantidade: int, primeira_ordem: int, caixa: Caixa) -> list[Caminho]:
    """Preenchimentos cinza, altos demais para virar faixa, que não contêm nenhum disco."""
    return [_faixa_a_mao(caixa, primeira_ordem + i, (0.7, 0.7, 0.7)) for i in range(quantidade)]


def _gasto_de_casar_todos(
    caminhos: list[Caminho], textos: list[TextoModelo] | None = None, *, limite: int | None = None
) -> tuple[int, int]:
    """(gasto de casar todos os discos, casados), sem a montagem do contexto, das pontas e dos
    candidatos. Com `limite`, o teto é o gasto da montagem, medido numa página igual, mais ele."""
    pagina = pagina_gramatica(caminhos, textos or [])
    if limite is None:
        contexto = contexto_gramaticas(pagina)
    else:
        medicao = contexto_gramaticas(pagina)
        pontas_terminais(medicao)
        discos_candidatos(medicao)
        contexto = contexto_gramaticas(pagina, limite=medicao.orcamento.gasto + limite)
    pontas = pontas_terminais(contexto)
    candidatos = discos_candidatos(contexto)
    antes = contexto.orcamento.gasto
    casados = sum(casa_disco(contexto, GRAMATICA, d, pontas) for d in candidatos)
    return contexto.orcamento.gasto - antes, casados


def test_caminhos_sobre_o_disco_gastam_um_por_caminho_consultado() -> None:
    quantidade = 300
    caminhos = [_vertical(150.0, 0), _disco_a_mao(CENTRO, 1)]
    caminhos += _fundo(quantidade, 2, (140.0, 149.5, 160.0, 150.5))
    gasto, casados = _gasto_de_casar_todos(caminhos)
    assert casados == 1
    assert quantidade <= gasto <= quantidade + 10


def test_muitos_discos_sob_muitos_caminhos_gastam_o_produto_e_estouram_o_teto() -> None:
    discos, sobre = 30, 100
    caminhos = [_disco_a_mao((140.0 + 3 * i, 150.0), i) for i in range(discos)]
    caminhos += [_vertical(140.0 + 3 * i, discos + i) for i in range(discos)]
    caminhos += _fundo(sobre, 2 * discos, (130.0, 149.5, 250.0, 150.5))
    gasto, casados = _gasto_de_casar_todos(caminhos)
    assert casados == discos
    assert gasto >= discos * sobre
    with pytest.raises(TetoGramaticasExcedido):
        _gasto_de_casar_todos(caminhos, limite=gasto // 2)


def test_palavras_na_celula_do_disco_gastam_uma_por_palavra() -> None:
    """Duas fileiras de 100 spans de 1 pt, passo 0,01: nenhum cola (a fileira só chegaria ao
    vizinho a 100 passos, e as fileiras se sobrepõem 0,4 < 50%)."""
    quantidade = 200
    textos = [
        texto(
            "X",
            (
                155.0 + 0.01 * (i % 100),
                145.0 + 0.6 * (i // 100),
                156.0 + 0.01 * (i % 100),
                146.0 + 0.6 * (i // 100),
            ),
        )
        for i in range(quantidade)
    ]
    gasto, casados = _gasto_de_casar_todos([_vertical(150.0, 0), _disco_a_mao(CENTRO, 1)], textos)
    assert casados == 1
    assert quantidade <= gasto <= quantidade + 10


def test_palavras_coladas_na_celula_do_disco_gastam_uma_por_palavra_fundida() -> None:
    """Passo 0,01 numa fileira só: o span `i` encosta no `i - 100` e os 200 viram 100 palavras."""
    textos = [texto("X", (155.0 + 0.01 * i, 145.0, 156.0 + 0.01 * i, 146.0)) for i in range(200)]
    gasto, casados = _gasto_de_casar_todos([_vertical(150.0, 0), _disco_a_mao(CENTRO, 1)], textos)
    assert casados == 1
    assert 100 <= gasto <= 110


def test_disco_que_falha_na_cor_ou_no_vao_nao_gasta_consulta() -> None:
    verdes = [_disco_a_mao((10.0 + 3 * i, 150.0), i, (0.0, 0.8, 0.0)) for i in range(50)]
    grande = Caminho((_curvas_em((250.0, 150.0), 6.0),), estilo(None, ROXO), "preenchimento", 50)
    caminhos = [*verdes, grande, *_fundo(200, 51, (0.0, 149.5, 260.0, 150.5))]
    assert _gasto_de_casar_todos(caminhos) == (0, 0)


def test_cadeia_longa_de_faixas_gasta_linear() -> None:
    def gasto_de(quantidade: int) -> int:
        faixas = [_faixa_a_mao((10.0, 0.5 * i, 11.0, 0.5 * (i + 1)), i) for i in range(quantidade)]
        contexto = contexto_gramaticas(pagina_gramatica(faixas, altura=3000.0))
        antes = contexto.orcamento.gasto
        assert discos_candidatos(contexto) == ()
        return contexto.orcamento.gasto - antes

    assert gasto_de(200) == 199
    assert gasto_de(400) == 399
