# mypy: disable-error-code="no-untyped-call"
"""Ataque às gramáticas de moldura: paridade com o motor em PDF sintético e custo contado."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import pymupdf
import pytest
from tests.fixtures.declarative_symbols import corpus
from tests.fixtures.symbol_grammars.paginas import (
    circulo_bezier,
    linha,
    pagina_gramatica,
    poligono,
    retangulo_traco,
    texto,
)

from zeny_project_handler.adapters.analysis import declarative_symbols as motor_antigo
from zeny_project_handler.adapters.analysis.drawing_model import grammar_frames
from zeny_project_handler.adapters.analysis.drawing_model.grammar_frames import casa_moldura
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caixa,
    Caminho,
    Cor,
    Estilo,
    ItemCaminho,
    Ponto,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    ContextoGramatica,
    Moldura,
    PaginaGramatica,
    TetoGramaticasExcedido,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_modelo_com_indices

PRETO: Cor = (0.0, 0.0, 0.0)
CINZA: Cor = (0.86, 0.86, 0.88)
VERMELHO: Cor = (0.7, 0.0, 0.0)
FORMA_DO_MOTOR = {"retangulo": "rectangle", "elipse": "ellipse", "losango": "diamond"}
_Achado = tuple[str, tuple[float, ...], int]


def _gramaticas() -> dict[str, dict[str, Any]]:
    return {
        variante["id"]: dict(variante["recognition"]["grammar"])
        for pacote in motor_antigo.carregar_pacotes()
        for variante in pacote["variants"]
        if variante["recognition"]["status"] == "enabled"
        and variante["recognition"]["grammar"]["kind"] != "terminal_disc"
    }


GRAMATICAS = _gramaticas()
CT_VAZIO = GRAMATICAS["cemig-eo-r3-s06-v001"]
EH_CINZA = GRAMATICAS["cemig-eo-r3-s23-v002"]
QDP = GRAMATICAS["cemig-eo-r3-s07-v003"]
TRIANGULO_VAZIO = GRAMATICAS["cemig-eo-r3-s07-v001"]
TRIANGULO_SOLIDO = GRAMATICAS["cemig-eo-r3-s07-v002"]
DIAGONAIS = GRAMATICAS["cemig-eo-r3-s11-v001"]
BARRA = GRAMATICAS["cemig-eo-r3-s05-v004"]
LOSANGO = GRAMATICAS["cemig-eo-r3-s27-v005"]
SENSIVEIS_A_ORIENTACAO = {"triangle_in_frame", "nested_rectangles_bar"}


# --- harness: o motor antigo e o núcleo sobre o mesmo PDF ---------------------------------


def _arredondada(caixa: Sequence[float]) -> tuple[float, ...]:
    return tuple(round(float(v), 3) for v in caixa)


def _do_motor(pagina: pymupdf.Page, gramatica: dict[str, Any]) -> set[_Achado]:
    desenhos = tuple(pagina.get_drawings(extended=True))
    contexto = motor_antigo._page_context(pagina, cast(Any, None), cast(Any, None), desenhos, ())
    achados: set[_Achado] = set()
    for forma, retangulo, indice in contexto.frames:
        if motor_antigo._frame_ok(forma, retangulo, gramatica) and motor_antigo._grammar_matches(
            contexto, gramatica, retangulo, indice
        ):
            achados.add((forma, _arredondada(motor_antigo._rounded_box(retangulo)), indice))
    return achados


def _contexto_do_pdf(pagina: pymupdf.Page) -> tuple[ContextoGramatica, tuple[int, ...]]:
    modelo, indices = pagina_modelo_com_indices(pagina, 0)
    return contexto_gramaticas(PaginaGramatica(modelo, indices, frozenset())), indices


def _do_nucleo(
    contexto: ContextoGramatica, indices: tuple[int, ...], gramatica: dict[str, Any]
) -> set[_Achado]:
    return {
        (FORMA_DO_MOTOR[m.forma], _arredondada(m.caixa), indices[m.caminho])
        for m in contexto.molduras
        if casa_moldura(contexto, gramatica, m)
    }


def _para_o_visual(achados: set[_Achado], pagina: pymupdf.Page) -> set[_Achado]:
    matriz = pagina.rotation_matrix
    return {
        (forma, _arredondada((pymupdf.Rect(caixa) * matriz).normalize()), indice)
        for forma, caixa, indice in achados
    }


@contextmanager
def _pdf(
    desenhar: Callable[[pymupdf.Page], object], rotacao: int = 0, tamanho: float = 300.0
) -> Iterator[pymupdf.Page]:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=tamanho, height=tamanho)
        desenhar(pagina)
        if rotacao:
            pagina.set_rotation(rotacao)
        yield pagina


def _comparar(
    desenhar: Callable[[pymupdf.Page], object], gramatica: dict[str, Any]
) -> tuple[set[_Achado], set[_Achado]]:
    with _pdf(desenhar) as pagina:
        contexto, indices = _contexto_do_pdf(pagina)
        return _do_motor(pagina, gramatica), _do_nucleo(contexto, indices, gramatica)


def _acrescentar_conteudo(pagina: pymupdf.Page, bruto: str) -> None:
    """Operadores de conteúdo crus ao fim da página (clip, `re`/`qu`, fora da página)."""
    xref = pagina.get_contents()[0]
    pagina.parent.update_stream(xref, pagina.parent.xref_stream(xref) + b"\n" + bruto.encode())


def _poligono(pagina: pymupdf.Page, pontos: list[Ponto], **opcoes: Any) -> None:
    forma = pagina.new_shape()
    forma.draw_polyline(pontos)
    forma.finish(**opcoes)
    forma.commit()


QUADRADO = pymupdf.Rect(110, 110, 158, 158)


def _camara(pagina: pymupdf.Page, rotulo: str = "CT") -> None:
    pagina.draw_rect(pymupdf.Rect(101, 115, 169, 149), color=PRETO, width=1)
    pagina.insert_text((107, 140), rotulo, fontsize=11)


def _quadrado_com_rotulo(pagina: pymupdf.Page, rotulo: str = "QDP") -> None:
    pagina.draw_rect(QUADRADO, color=PRETO, width=1)
    pagina.insert_text((116, 139), rotulo, fontsize=11)


# --- paridade na página do corpus, com índice cru e /Rotate ---------------------------------


@pytest.fixture(scope="module")
def corpus_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    caminho = tmp_path_factory.mktemp("corpus") / "c.pdf"
    corpus.build_enabled_corpus(caminho)
    return caminho


CROPBOX = pymupdf.Rect(60, 40, 260, 230)


@pytest.mark.parametrize(
    ("rotacao", "recorte"),
    [(0, False), (90, False), (180, False), (270, False), (0, True), (90, True)],
    ids=["0", "90", "180", "270", "0-cropbox", "90-cropbox"],
)
def test_corpus_caixa_e_indice_cru_batem_com_o_motor_em_cada_gramatica(
    corpus_pdf: Path, rotacao: int, recorte: bool
) -> None:
    """Invariantes: igual ao motor (caixa visual, índice cru). Sensíveis: R-7 diz onde divergem."""
    divergencias: list[str] = []
    positivos = 0
    with pymupdf.open(corpus_pdf) as documento:
        for pagina in documento:
            if recorte:
                pagina.set_cropbox(CROPBOX)
            pagina.set_rotation(rotacao)
            contexto, indices = _contexto_do_pdf(pagina)
            for variante, gramatica in GRAMATICAS.items():
                esperado = _para_o_visual(_do_motor(pagina, gramatica), pagina)
                if gramatica["kind"] in SENSIVEIS_A_ORIENTACAO:
                    em_pe = rotacao == 0 or (
                        gramatica["kind"] == "nested_rectangles_bar" and rotacao == 180
                    )
                    if not em_pe:
                        esperado = set()
                obtido = _do_nucleo(contexto, indices, gramatica)
                positivos += len(obtido)
                if obtido != esperado:
                    divergencias.append(
                        f"pagina={pagina.number} {variante}: motor={sorted(esperado)} "
                        f"nucleo={sorted(obtido)}"
                    )
    assert divergencias == []
    assert positivos == {0: 24, 90: 19, 180: 20, 270: 19}[rotacao]


# --- paridade em PDF sintético, gramática por gramática ------------------------------------


def _com_marca(marca: Callable[[pymupdf.Page], object]) -> Callable[[pymupdf.Page], object]:
    def desenhar(pagina: pymupdf.Page) -> None:
        _camara(pagina)
        marca(pagina)

    return desenhar


def _retangulo_cheio(caixa: tuple[float, float, float, float]) -> Callable[[pymupdf.Page], object]:
    return lambda p: p.draw_rect(pymupdf.Rect(*caixa), color=None, fill=VERMELHO)


def _clip_com_marca(pagina: pymupdf.Page) -> None:
    _acrescentar_conteudo(pagina, "q 148 154 20 28 re W n 0.7 0 0 rg 150 154 16 28 re f Q")


def _clip_sem_pintar(pagina: pymupdf.Page) -> None:
    _acrescentar_conteudo(pagina, "q 103 153 60 30 re W n Q")


def _marca_em_duas_pinceladas(pagina: pymupdf.Page) -> None:
    """Preenchimento e contorno da mesma caixa, em dois desenhos, sobre a moldura."""
    pagina.draw_rect(pymupdf.Rect(101, 115, 169, 149), color=None, fill=CINZA)
    pagina.draw_rect(pymupdf.Rect(101, 115, 169, 149), color=PRETO, width=1)


def _dois_retangulos_num_caminho(pagina: pymupdf.Page) -> None:
    forma = pagina.new_shape()
    forma.draw_rect(pymupdf.Rect(108, 108, 168, 168))
    forma.draw_rect(pymupdf.Rect(114, 114, 162, 162))
    forma.finish(color=PRETO, fill=CINZA, width=1)
    forma.commit()
    pagina.insert_text((119, 144), "EH", fontsize=11)


def _aninhado(pagina: pymupdf.Page, interno: pymupdf.Rect, preenchimento: Cor | None) -> None:
    pagina.draw_rect(pymupdf.Rect(108, 108, 168, 168), color=PRETO, width=1)
    pagina.draw_rect(interno, color=PRETO, fill=preenchimento, width=1)
    pagina.insert_text((119, 144), "EH", fontsize=11)


def _triangulo(
    pontos: list[Ponto], preenchimento: Cor | None = None, **opcoes: Any
) -> Callable[[pymupdf.Page], object]:
    def desenhar(pagina: pymupdf.Page) -> None:
        pagina.draw_rect(QUADRADO, color=PRETO, width=1)
        _poligono(pagina, pontos, color=VERMELHO, fill=preenchimento, width=1, **opcoes)

    return desenhar


def _diagonais(
    pontas: list[tuple[Ponto, Ponto]], rotulo: str = ""
) -> Callable[[pymupdf.Page], object]:
    def desenhar(pagina: pymupdf.Page) -> None:
        pagina.draw_rect(QUADRADO, color=PRETO, width=1)
        for a, b in pontas:
            pagina.draw_line(a, b, color=PRETO, width=1)
        if rotulo:
            pagina.insert_text((116, 139), rotulo, fontsize=11)

    return desenhar


X = [((111.0, 111.0), (157.0, 157.0)), ((157.0, 111.0), (111.0, 157.0))]


def _barra(
    y: float, x0: float = 119.0, x1: float = 149.0, interno: bool = True
) -> Callable[[pymupdf.Page], object]:
    def desenhar(pagina: pymupdf.Page) -> None:
        pagina.draw_rect(QUADRADO, color=PRETO, width=1)
        if interno:
            pagina.draw_rect(pymupdf.Rect(118, 118, 150, 150), color=PRETO, width=1)
        pagina.draw_line((x0, y), (x1, y), color=PRETO, width=1)

    return desenhar


def _losango_com_pontos(
    centros: list[Ponto], raio: float = 3.0, preenchidos: bool = False
) -> Callable[[pymupdf.Page], object]:
    def desenhar(pagina: pymupdf.Page) -> None:
        _poligono(pagina, [(134, 110), (158, 134), (134, 158), (110, 134), (134, 110)], color=PRETO)
        for centro in centros:
            pagina.draw_circle(centro, raio, color=PRETO, fill=PRETO if preenchidos else None)

    return desenhar


TRES: list[Ponto] = [(126.0, 134.0), (134.0, 134.0), (142.0, 134.0)]
TRIANGULO_PONTOS: list[Ponto] = [(134, 112), (156, 156), (112, 156), (134, 112)]
INTERNO = pymupdf.Rect(114, 114, 162, 162)
CASOS: list[Any] = [
    # empty_interior
    pytest.param(_camara, CT_VAZIO, True, id="camara-vazia"),
    pytest.param(
        _com_marca(_retangulo_cheio((120, 118, 132, 130))), CT_VAZIO, False, id="marca-12x12"
    ),
    pytest.param(
        _com_marca(_retangulo_cheio((120, 118, 131, 129))), CT_VAZIO, True, id="marca-11x11"
    ),
    pytest.param(
        _com_marca(lambda p: p.draw_line((105, 117), (145, 147), color=PRETO)),
        CT_VAZIO,
        False,
        id="linha-diagonal-longa",
    ),
    pytest.param(
        _com_marca(lambda p: p.draw_line((105, 117), (125, 147), color=PRETO)),
        CT_VAZIO,
        True,
        id="linha-diagonal-curta",
    ),
    pytest.param(_com_marca(_clip_com_marca), CT_VAZIO, False, id="clip-com-marca-pintada"),
    pytest.param(_com_marca(_clip_sem_pintar), CT_VAZIO, True, id="clip-sem-marca"),
    pytest.param(
        _com_marca(_marca_em_duas_pinceladas), CT_VAZIO, True, id="externa-em-dois-caminhos"
    ),
    # moldura interna cinza
    pytest.param(lambda p: _aninhado(p, INTERNO, CINZA), EH_CINZA, True, id="cinza"),
    pytest.param(lambda p: _aninhado(p, INTERNO, None), EH_CINZA, False, id="sem-preenchimento"),
    pytest.param(lambda p: _aninhado(p, INTERNO, VERMELHO), EH_CINZA, False, id="colorida"),
    pytest.param(
        lambda p: _aninhado(p, pymupdf.Rect(120, 114, 168, 162), CINZA),
        EH_CINZA,
        False,
        id="descentrada",
    ),
    pytest.param(
        _dois_retangulos_num_caminho, EH_CINZA, False, id="dois-retangulos-no-mesmo-caminho"
    ),
    # triângulo
    pytest.param(_triangulo(TRIANGULO_PONTOS), TRIANGULO_VAZIO, True, id="triangulo-vazio"),
    pytest.param(
        _triangulo(TRIANGULO_PONTOS, VERMELHO), TRIANGULO_SOLIDO, True, id="triangulo-solido"
    ),
    pytest.param(
        _triangulo(TRIANGULO_PONTOS, VERMELHO),
        TRIANGULO_VAZIO,
        False,
        id="triangulo-solido-pede-vazio",
    ),
    pytest.param(
        _triangulo(TRIANGULO_PONTOS[:3], closePath=True),
        TRIANGULO_VAZIO,
        True,
        id="triangulo-aberto-com-closepath",
    ),
    pytest.param(
        _triangulo([(134, 110), (158, 158), (110, 158), (134, 110)]),
        TRIANGULO_VAZIO,
        True,
        id="triangulo-na-caixa-da-moldura",
    ),
    pytest.param(
        _triangulo([(134, 156), (156, 112), (112, 112), (134, 156)]),
        TRIANGULO_VAZIO,
        False,
        id="triangulo-invertido",
    ),
    # diagonais
    pytest.param(_diagonais(X), DIAGONAIS, True, id="x"),
    pytest.param(_diagonais(X[:1]), DIAGONAIS, False, id="uma-diagonal"),
    pytest.param(_diagonais(X, "CT"), DIAGONAIS, False, id="x-com-texto"),
    pytest.param(
        _diagonais([((106, 106), (162, 162)), ((162, 106), (106, 162))]),
        DIAGONAIS,
        True,
        id="diagonais-na-tolerancia",
    ),
    pytest.param(
        _diagonais([((103, 103), (165, 165)), ((165, 103), (103, 165))]),
        DIAGONAIS,
        False,
        id="diagonais-alem-da-tolerancia",
    ),
    # barra
    pytest.param(_barra(134.0), BARRA, True, id="barra"),
    pytest.param(_barra(134.0, interno=False), BARRA, False, id="barra-sem-interno"),
    pytest.param(_barra(137.5), BARRA, True, id="barra-quase-12-por-cento-abaixo"),
    pytest.param(_barra(138.5), BARRA, False, id="barra-alem-de-12-por-cento"),
    pytest.param(_barra(134.0, 119.0, 136.0), BARRA, False, id="barra-curta"),
    pytest.param(_barra(134.0, 109.0, 159.0), BARRA, True, id="barra-vai-ate-a-folga"),
    pytest.param(_barra(134.0, 108.0, 160.0), BARRA, False, id="barra-passa-da-folga"),
    # losango
    pytest.param(_losango_com_pontos(TRES), LOSANGO, True, id="tres-pontos"),
    pytest.param(_losango_com_pontos(TRES[:2]), LOSANGO, False, id="dois-pontos"),
    pytest.param(_losango_com_pontos([*TRES, (134.0, 126.0)]), LOSANGO, False, id="quatro-pontos"),
    pytest.param(_losango_com_pontos(TRES, preenchidos=True), LOSANGO, True, id="pontos-cheios"),
    pytest.param(
        _losango_com_pontos([(126.0, 134.0), (134.0, 134.0), (154.5, 134.0)]),
        LOSANGO,
        False,
        id="ponto-fora-do-losango",
    ),
]


@pytest.mark.parametrize(("desenhar", "gramatica", "casa"), CASOS)
def test_paridade_com_o_motor_em_pdf_sintetico(
    desenhar: Callable[[pymupdf.Page], object], gramatica: dict[str, Any], casa: bool
) -> None:
    motor, nucleo = _comparar(desenhar, gramatica)

    assert nucleo == motor
    assert bool(nucleo) is casa


def _barra_deslocada(dy: float, y_da_barra: float) -> Callable[[pymupdf.Page], object]:
    def desenhar(pagina: pymupdf.Page) -> None:
        pagina.draw_rect(pymupdf.Rect(110, 110 + dy, 158, 158 + dy), color=PRETO, width=1)
        pagina.draw_rect(pymupdf.Rect(118, 118 + dy, 150, 150 + dy), color=PRETO, width=1)
        pagina.draw_line((119, y_da_barra), (149, y_da_barra), color=PRETO, width=1)

    return desenhar


@pytest.mark.parametrize(
    ("y_da_barra", "casa"),
    [
        pytest.param(146.2, True, id="barra-em-outra-celula-da-grade-dentro-dos-12-por-cento"),
        pytest.param(138.8, True, id="barra-acima-dentro-dos-12-por-cento"),
        pytest.param(146.5, False, id="barra-em-outra-celula-alem-dos-12-por-cento"),
    ],
)
def test_barra_fora_da_celula_do_centro_mas_dentro_da_faixa_casa(
    y_da_barra: float, casa: bool
) -> None:
    """O meio da interna (142,5) e a barra (146,2) caem em células de 16 pt diferentes: a faixa da
    consulta precisa cobrir os 12% da altura, não só a linha do meio."""
    motor, nucleo = _comparar(_barra_deslocada(8.5, y_da_barra), BARRA)

    assert nucleo == motor
    assert bool(nucleo) is casa


# --- span de várias palavras em fonte proporcional (R-4 contra o motor) ---------------------


def _span(rotulo: str, x: float, y: float = 139.0) -> Callable[[pymupdf.Page], object]:
    def desenhar(pagina: pymupdf.Page) -> None:
        pagina.draw_rect(QUADRADO, color=PRETO, width=1)
        pagina.insert_text((x, y), rotulo, fontsize=11)

    return desenhar


@pytest.mark.parametrize(
    ("conteudo", "x"),
    [
        pytest.param("QDP iiii", 136.0, id="rotulo-na-frente-de-palavra-estreita"),
        pytest.param("iiii QDP", 96.0, id="rotulo-atras-de-palavra-estreita"),
        pytest.param("W QDP i", 122.0, id="rotulo-no-meio-1"),
        pytest.param("WW QDP ii", 116.0, id="rotulo-no-meio-2"),
        pytest.param("ii QDP WW", 100.0, id="rotulo-no-meio-3"),
    ],
)
def test_rotulo_de_span_de_varias_palavras_nao_casa_onde_o_motor_recusa(
    conteudo: str, x: float
) -> None:
    """A repartição por caracteres põe a palavra dentro da caixa interna onde os glifos reais
    (Helvetica, proporcional) saem dela: o motor recusa e o núcleo casa. Review Focus 3: o rótulo
    casa como no motor ou falha fechado."""
    motor, nucleo = _comparar(_span(conteudo, x), QDP)

    assert motor == set(), "premissa: a palavra real não cabe na caixa interna"
    assert nucleo - motor == set()


@pytest.mark.parametrize(
    ("conteudo", "x"),
    [
        pytest.param("iiii WW", 150.0, id="palavra-larga-depois-de-estreita"),
        pytest.param("i WWW i", 156.0, id="palavra-larga-no-meio"),
    ],
)
def test_guarda_de_texto_nao_abre_onde_o_motor_recusa(conteudo: str, x: float) -> None:
    """Mesma repartição, na guarda `_moldura_tem_texto`: o centro estimado cai fora da moldura e o
    real, dentro. O motor vê o texto e recusa o X; o núcleo casa."""

    def desenhar(pagina: pymupdf.Page) -> None:
        _diagonais(X)(pagina)
        pagina.insert_text((x, 139), conteudo, fontsize=11)

    motor, nucleo = _comparar(desenhar, DIAGONAIS)

    assert motor == set(), "premissa: o centro de uma palavra real está dentro da moldura"
    assert nucleo - motor == set()


def test_nucleo_nunca_casa_onde_o_motor_recusa_em_fonte_monoespacada() -> None:
    """Invariante unilateral (R-4 emendado): o núcleo pode perder recall, nunca ganhar casamento
    que o motor recusa. Perdas esperadas: rótulo nativo de várias palavras e span que a guarda
    não pode repartir."""
    ganhos = []
    perdas = 0
    for dx in range(-30, 60, 3):
        for gramatica, desenhar in (
            (QDP, _span_cour("QDP 12", 116.0 + dx)),
            (DIAGONAIS, _x_com_cour("CT 12", 116.0 + dx)),
        ):
            motor, nucleo = _comparar(desenhar, gramatica)
            if nucleo - motor:
                ganhos.append((gramatica["kind"], dx))
            perdas += len(motor - nucleo)
    assert ganhos == []
    assert perdas == PERDAS_DE_RECALL_ACEITAS


def _span_cour(rotulo: str, x: float) -> Callable[[pymupdf.Page], object]:
    def desenhar(pagina: pymupdf.Page) -> None:
        pagina.draw_rect(QUADRADO, color=PRETO, width=1)
        pagina.insert_text((x, 139), rotulo, fontname="cour", fontsize=11)

    return desenhar


def _x_com_cour(rotulo: str, x: float) -> Callable[[pymupdf.Page], object]:
    def desenhar(pagina: pymupdf.Page) -> None:
        _diagonais(X)(pagina)
        pagina.insert_text((x, 139), rotulo, fontname="cour", fontsize=11)

    return desenhar


# --- palavra `inteira` e itens de caminho pagos: as duas decisões do desenvolvedor ----------

PERDAS_DE_RECALL_ACEITAS = 9
MOLDURA_X: Caixa = (110.0, 110.0, 158.0, 158.0)
DIAGONAIS_DO_X = [
    linha((111.0, 111.0), (157.0, 157.0), 1),
    linha((157.0, 111.0), (111.0, 157.0), 2),
]


def _contexto(
    caminhos: Sequence[Caminho], textos: Sequence[Any] = (), **opcoes: Any
) -> ContextoGramatica:
    return contexto_gramaticas(pagina_gramatica(caminhos, textos, **opcoes))


def _moldura_em(contexto: ContextoGramatica, caixa: Caixa) -> Moldura:
    return next(m for m in contexto.molduras if m.caixa == caixa)


def _x_com_span_vertical(caixa_do_span: Caixa, conteudo: str = "CT 12") -> bool:
    """Span de várias palavras rotacionado: nunca é repartido, a palavra é `inteira`."""
    textos = [texto(conteudo, caixa_do_span, rotacao=90.0)]
    contexto = _contexto([retangulo_traco(MOLDURA_X), *DIAGONAIS_DO_X], textos)
    assert all(p.inteira for p in contexto.grade_palavras.consultar((-16.0, -16.0, 316.0, 316.0)))
    return casa_moldura(contexto, DIAGONAIS, _moldura_em(contexto, MOLDURA_X))


@pytest.mark.parametrize(
    ("caixa_do_span", "casa"),
    [
        pytest.param((100.0, 120.0, 112.0, 148.0), False, id="cruza-a-borda-esquerda"),
        pytest.param((156.0, 120.0, 170.0, 148.0), False, id="cruza-a-borda-direita"),
        pytest.param((120.0, 100.0, 148.0, 112.0), False, id="cruza-a-borda-de-cima"),
        pytest.param((120.0, 156.0, 148.0, 170.0), False, id="cruza-a-borda-de-baixo"),
        pytest.param((100.0, 100.0, 200.0, 200.0), False, id="engole-a-moldura"),
        pytest.param((120.0, 120.0, 148.0, 148.0), False, id="dentro-da-moldura"),
        pytest.param((158.0, 120.0, 170.0, 148.0), True, id="so-encosta-por-fora"),
        pytest.param((160.0, 120.0, 172.0, 148.0), True, id="inteiramente-fora"),
    ],
)
def test_guarda_com_palavra_inteira_recusa_por_interseccao(
    caixa_do_span: Caixa, casa: bool
) -> None:
    assert _x_com_span_vertical(caixa_do_span) is casa


def test_span_nativo_que_cruza_a_moldura_recusa_a_guarda_mesmo_com_centro_fora() -> None:
    """Nativo fica com a caixa do span: de várias palavras é `inteira` e recusa por interseção."""
    textos = [texto("AB CD", (154.0, 120.0, 194.0, 130.0), origem="nativo")]
    contexto = _contexto([retangulo_traco(MOLDURA_X), *DIAGONAIS_DO_X], textos)
    palavras = contexto.grade_palavras.consultar((-16.0, -16.0, 316.0, 316.0))
    assert [p.inteira for p in palavras] == [True, True]

    assert casa_moldura(contexto, DIAGONAIS, _moldura_em(contexto, MOLDURA_X)) is False


def test_nativo_de_uma_palavra_com_centro_fora_cruzando_a_moldura_nao_recusa() -> None:
    textos = [texto("AB", (154.0, 120.0, 170.0, 130.0), origem="nativo")]
    contexto = _contexto([retangulo_traco(MOLDURA_X), *DIAGONAIS_DO_X], textos)
    assert [p.inteira for p in contexto.grade_palavras.consultar((-16.0, -16.0, 316.0, 316.0))] == [
        False
    ]

    assert casa_moldura(contexto, DIAGONAIS, _moldura_em(contexto, MOLDURA_X)) is True


def test_nativo_com_espacos_nas_pontas_e_inteiro_recusa_a_guarda_cruzando() -> None:
    textos = [texto("  AB ", (154.0, 120.0, 190.0, 130.0), origem="nativo")]
    contexto = _contexto([retangulo_traco(MOLDURA_X), *DIAGONAIS_DO_X], textos)

    assert casa_moldura(contexto, DIAGONAIS, _moldura_em(contexto, MOLDURA_X)) is False


def test_rotulo_nativo_com_espacos_nas_pontas_casa_se_o_span_cabe_na_interna() -> None:
    rotulo = {"kind": "label_in_frame", "frame": "rectangle", "label": "CT", "max_span": 72}
    for caixa, casa in (
        ((115.0, 118.0, 153.0, 152.0), True),
        ((115.0, 118.0, 160.0, 152.0), False),
    ):
        contexto = _contexto([retangulo_traco(MOLDURA_X)], [texto(" CT ", caixa)])
        assert casa_moldura(contexto, rotulo, _moldura_em(contexto, MOLDURA_X)) is casa


def test_palavra_nao_inteira_mesmo_cruzando_a_moldura() -> None:
    """Contraste: o span horizontal é repartido e cada palavra vale pelo centro, como no motor."""
    textos = [
        texto("AB CD", (154.0, 120.0, 194.0, 130.0), origem="glifo")
    ]  # "AB" cruza a borda, com o centro fora
    contexto = _contexto([retangulo_traco(MOLDURA_X), *DIAGONAIS_DO_X], textos)
    palavras = contexto.grade_palavras.consultar((-16.0, -16.0, 316.0, 316.0))
    assert [p.inteira for p in palavras] == [False, False]
    assert palavras[0].caixa[2] > MOLDURA_X[2] > palavras[0].caixa[0]
    centro_ab = (palavras[0].caixa[0] + palavras[0].caixa[2]) / 2
    assert centro_ab > MOLDURA_X[2]

    assert casa_moldura(contexto, DIAGONAIS, _moldura_em(contexto, MOLDURA_X)) is True


@pytest.mark.parametrize(
    ("caixa_do_span", "casa"),
    [
        pytest.param((115.0, 118.0, 153.0, 152.0), True, id="span-cabe-na-interna"),
        pytest.param((115.0, 118.0, 153.0, 156.0), False, id="span-passa-da-interna-embaixo"),
        pytest.param((112.0, 118.0, 153.0, 152.0), False, id="span-passa-da-interna-a-esquerda"),
        pytest.param((115.0, 118.0, 160.0, 152.0), False, id="span-passa-da-moldura"),
    ],
)
def test_rotulo_em_span_inteiro_exige_o_span_todo_dentro_da_caixa_interna(
    caixa_do_span: Caixa, casa: bool
) -> None:
    rotulo = {"kind": "label_in_frame", "frame": "rectangle", "label": "CT", "max_span": 72}
    textos = [texto("CT 12", caixa_do_span, rotacao=90.0)]
    contexto = _contexto([retangulo_traco(MOLDURA_X)], textos)

    assert casa_moldura(contexto, rotulo, _moldura_em(contexto, MOLDURA_X)) is casa


def _caminho_denso(itens: int, ordem: int) -> Caminho:
    """Um caminho de `itens` segmentos curtos (nunca uma marca) dentro de toda a moldura."""
    pontos = [(105.0 + 0.001 * i, 120.0 + (i % 2) * 0.5) for i in range(itens + 1)]
    return _cadeia(pontos, ordem)


def _cadeia(pontos: list[Ponto], ordem: int) -> Caminho:
    itens = tuple(ItemCaminho("l", (a, b)) for a, b in pairwise(pontos))
    estilo = Estilo(camada="", cor=PRETO, preenchimento=None, espessura=1.0, tracejado="")
    return Caminho((itens,), estilo, "traco", ordem)


def _gasto_de_casar_todas(molduras_com_rotulo: int, itens: int) -> tuple[int, int]:
    """(gasto do `casa_moldura` em todas as molduras, gasto só de montar o contexto)."""
    caixas = [(100.0 + 0.1 * i, 100.0, 150.0 + 0.1 * i, 150.0) for i in range(molduras_com_rotulo)]
    caminhos = [retangulo_traco(caixa, i) for i, caixa in enumerate(caixas)]
    caminhos.append(_caminho_denso(itens, len(caminhos)))
    textos = [texto("CT", (120.0, 120.0, 130.0, 130.0))]
    contexto = _contexto(caminhos, textos)
    montagem = contexto.orcamento.gasto
    for moldura in contexto.molduras:
        assert casa_moldura(contexto, CT_VAZIO, moldura) is True
    return contexto.orcamento.gasto - montagem, montagem


@pytest.mark.parametrize("itens", [50, 400])
def test_caminho_denso_paga_os_itens_a_cada_moldura_que_o_consulta(itens: int) -> None:
    molduras = 6

    gasto, _ = _gasto_de_casar_todas(molduras, itens)

    assert gasto >= molduras * (itens + 1)


def test_custo_de_casar_cresce_linearmente_com_os_itens_do_caminho_denso() -> None:
    pequeno, _ = _gasto_de_casar_todas(6, 100)
    grande, _ = _gasto_de_casar_todas(6, 1100)

    assert grande - pequeno == 6 * 1000


def test_caminho_denso_estoura_o_orcamento_sem_varrer_tudo() -> None:
    molduras, itens = 40, 2_000
    caixas = [(100.0 + 0.1 * i, 100.0, 150.0 + 0.1 * i, 150.0) for i in range(molduras)]
    caminhos = [retangulo_traco(caixa, i) for i, caixa in enumerate(caixas)]
    caminhos.append(_caminho_denso(itens, len(caminhos)))
    textos = [texto("CT", (120.0, 120.0, 130.0, 130.0))]
    montagem = _contexto(caminhos, textos).orcamento.gasto
    limite = montagem + 3 * (itens + 1)
    contexto = contexto_gramaticas(pagina_gramatica(caminhos, textos), limite=limite)

    avaliadas = 0
    with pytest.raises(TetoGramaticasExcedido):
        for moldura in contexto.molduras:
            casa_moldura(contexto, CT_VAZIO, moldura)
            avaliadas += 1

    assert avaliadas <= 3
    assert contexto.orcamento.gasto <= limite + itens + 1 + molduras + 1


# --- custo por contagem em página hostil -----------------------------------------------------


def _pagina_hostil(grupos: int) -> PaginaGramatica:
    """Molduras de todas as formas e tudo o que as guardas varrem, empilhado na mesma região."""
    caminhos: list[Caminho] = []
    textos = []
    for i in range(grupos):
        d = i * 0.05
        caminhos.append(retangulo_traco((100 + d, 100 + d, 150 + d, 150 + d), len(caminhos)))
        cantos = [(101 + d, 101 + d), (139 + d, 101 + d), (139 + d, 139 + d), (101 + d, 139 + d)]
        caminhos.append(poligono(cantos, len(caminhos), CINZA))
        triangulo = [(125 + d, 102 + d), (148 + d, 148 + d), (102 + d, 148 + d)]
        caminhos.append(poligono(triangulo, len(caminhos)))
        losango = [(125 + d, 100 + d), (150 + d, 125 + d), (125 + d, 150 + d), (100 + d, 125 + d)]
        caminhos.append(poligono(losango, len(caminhos)))
        for k in range(3):
            caminhos.append(circulo_bezier((117 + d + 8 * k, 125 + d), 3.0, len(caminhos)))
        caminhos.append(linha((100 + d, 100 + d), (150 + d, 150 + d), len(caminhos)))
        caminhos.append(linha((150 + d, 100 + d), (100 + d, 150 + d), len(caminhos)))
        caminhos.append(linha((111 + d, 125 + d), (139 + d, 125 + d), len(caminhos)))
        for palavra in ("CT", "EH"):
            textos.append(texto(palavra, (120 + d, 120 + d, 130 + d, 130 + d)))
    return pagina_gramatica(caminhos, textos)


TODAS = [
    pytest.param(CT_VAZIO, id="rotulo-com-interior-vazio"),
    pytest.param(EH_CINZA, id="moldura-interna-cinza"),
    pytest.param(TRIANGULO_VAZIO, id="triangulo"),
    pytest.param(DIAGONAIS, id="diagonais"),
    pytest.param(BARRA, id="barra"),
    pytest.param(LOSANGO, id="losango"),
]


@pytest.mark.parametrize("gramatica", TODAS)
def test_nenhuma_conferencia_geometrica_escapa_do_orcamento(
    gramatica: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cada chamada de `contem`/`intersecta`/`ponto_em` sai de um item que a grade já cobrou."""
    chamadas = {"n": 0}

    def contar(funcao: Callable[..., bool]) -> Callable[..., bool]:
        def contada(*argumentos: Any) -> bool:
            chamadas["n"] += 1
            return funcao(*argumentos)

        return contada

    for nome in ("contem", "intersecta", "ponto_em"):
        monkeypatch.setattr(grammar_frames, nome, contar(getattr(grammar_frames, nome)))
    contexto = contexto_gramaticas(_pagina_hostil(12))
    montagem = contexto.orcamento.gasto
    chamadas["n"] = 0

    for moldura in contexto.molduras:
        casa_moldura(contexto, gramatica, moldura)

    gasto = contexto.orcamento.gasto - montagem
    assert gasto > 0
    assert chamadas["n"] > 0
    assert chamadas["n"] <= gasto


@pytest.mark.parametrize("gramatica", TODAS)
def test_pagina_hostil_estoura_o_teto_e_para_perto_do_limite(gramatica: dict[str, Any]) -> None:
    pagina = _pagina_hostil(12)
    total = contexto_gramaticas(pagina)
    montagem = total.orcamento.gasto
    for moldura in total.molduras:
        casa_moldura(total, gramatica, moldura)
    custo = total.orcamento.gasto - montagem
    limite = montagem + custo // 2
    contexto = contexto_gramaticas(pagina, limite=limite)

    with pytest.raises(TetoGramaticasExcedido):
        for moldura in contexto.molduras:
            casa_moldura(contexto, gramatica, moldura)

    # Uma consulta passa do limite por, no máximo, o tamanho do que ela devolveu.
    assert contexto.orcamento.gasto <= limite + len(contexto.molduras) * 8
