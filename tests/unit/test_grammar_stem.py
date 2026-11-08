"""Gramática `stem_bars` (haste com barras) pelo núcleo: positivos, negativos, caixa e sinal."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.paginas import linha, pagina_gramatica, texto
from tests.fixtures.symbol_grammars.stem_bars import (
    ALTERNADAS,
    CASOS_HASTE,
    CIRCULO_POLIGONAL,
    DECRESCENTES,
    ESTRELA,
    HEXAGONO,
    LACUNA,
    NEGATIVOS,
    DesenhoHaste,
    desenhar_haste,
    desenhar_positivo,
    pagina_desenhada,
)

from zeny_project_handler.adapters.analysis.drawing_model.grammar_stem import (
    casa_hastes,
    origem_predominante,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa, Ponto
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    PaginaGramatica,
    TetoGramaticasExcedido,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import (
    CasamentoGramatica,
    casar_variantes,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_para_gramaticas

_VARIANTES: Final = [variante for variante, _ in CASOS_HASTE]
_AZUL: Final = (0.0, 0.0, 1.0)
_EPSILON: Final = 1e-3  # PyMuPDF devolve coordenadas em float32


def _pares() -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    return [
        (
            {"family_id": "autoral"},
            {"id": variante, "recognition": {"status": "enabled", "grammar": gramatica}},
        )
        for variante, gramatica in CASOS_HASTE
    ]


def _casamentos(pagina: PaginaGramatica) -> tuple[CasamentoGramatica, ...]:
    return casar_variantes(pagina, _pares())


def _variantes(pagina: PaginaGramatica) -> list[str]:
    return [str(casamento.variante["id"]) for casamento in _casamentos(pagina)]


def _contem(caixa: Caixa, ponto: Ponto) -> bool:
    return (
        caixa[0] - _EPSILON <= ponto[0] <= caixa[2] + _EPSILON
        and caixa[1] - _EPSILON <= ponto[1] <= caixa[3] + _EPSILON
    )


def _desenhada(variante: str, graus: float = 0.0, **opcoes: Any) -> tuple[PaginaGramatica, Any]:
    desenhos: list[DesenhoHaste] = []

    def desenhar(pagina: pymupdf.Page) -> None:
        desenhos.append(desenhar_positivo(pagina, variante, graus=graus, **opcoes))

    pagina = pagina_desenhada(desenhar)
    return pagina, desenhos[0]


@pytest.mark.parametrize("graus", [0.0, 90.0, 45.0], ids=["0", "90", "45"])
@pytest.mark.parametrize("variante", _VARIANTES)
def test_positivo_casa_so_a_variante_certa(variante: str, graus: float) -> None:
    pagina, _ = _desenhada(variante, graus)

    assert _variantes(pagina) == [variante]


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
        desenho = desenhar_positivo(pagina, variante, centro=(100.0, 80.0))
        pagina.set_rotation(90)
        matriz = pagina.rotation_matrix
        exibida = pagina_para_gramaticas(pagina, 0)

    [casamento] = _casamentos(exibida)
    assert casamento.variante["id"] == variante
    for ponto in (desenho.ponta, *(p for barra in desenho.barras for p in barra)):
        assert _contem(casamento.caixa, _exibido(ponto, matriz))


@pytest.mark.parametrize("variante", _VARIANTES)
def test_caixa_e_o_pictograma(variante: str) -> None:
    pagina, desenho = _desenhada(variante)

    [casamento] = _casamentos(pagina)
    caixa = casamento.caixa
    assert _contem(caixa, desenho.ponta)
    for a, b in desenho.barras:
        assert _contem(caixa, a) and _contem(caixa, b)
    if desenho.envolvente is not None:
        assert _contem(caixa, desenho.envolvente[:2]) and _contem(caixa, desenho.envolvente[2:])
    assert not _contem(caixa, desenho.base)
    if desenho.envolvente is None:
        assert not any(_contem(caixa, p) for braco in desenho.bracos_x for p in braco)


@pytest.mark.parametrize("variante", _VARIANTES)
def test_caixa_com_a_haste_encostada_na_linha_longa_e_a_da_haste_curta(variante: str) -> None:
    curta, _ = _desenhada(variante)
    encostada, _ = _desenhada(variante, linha_longa=120.0)

    [esperado] = _casamentos(curta)
    [obtido] = _casamentos(encostada)
    assert obtido.variante["id"] == variante
    assert obtido.caixa == pytest.approx(esperado.caixa, abs=0.5)


@pytest.mark.parametrize("nome", sorted(NEGATIVOS))
def test_negativo_nao_casa(nome: str) -> None:
    assert _variantes(pagina_desenhada(NEGATIVOS[nome])) == []


@pytest.mark.parametrize(
    ("variante", "esperados"),
    [
        ("cemig-eo-r3-s19-v004", (1, 2, 3, 4, 5)),
        ("cemig-eo-r3-s19-v003", (1, 2, 3, 4, 5, 6)),
        ("cemig-eo-r3-s21-v005", (1, 2, 3, 4)),
    ],
)
def test_componentes_listam_haste_barras_e_x(variante: str, esperados: tuple[int, ...]) -> None:
    """Ordem do desenho: haste (0), barras, envolvente, braços do X; a âncora é a haste."""
    pagina, _ = _desenhada(variante)

    [casamento] = _casamentos(pagina)
    assert casamento.caminho == 0
    assert casamento.componentes == esperados


def test_casa_hastes_devolve_caixa_ancora_e_componentes() -> None:
    pagina, _ = _desenhada("cemig-eo-r3-s19-v001")
    contexto = contexto_gramaticas(pagina)
    antes = contexto.orcamento.gasto

    [(caixa, ancora, componentes)] = casa_hastes(contexto, dict(CASOS_HASTE)[_VARIANTES[0]])

    assert ancora == 0
    assert componentes == (1, 2, 3)
    assert caixa[3] - caixa[1] == pytest.approx(2 * LACUNA + max(DECRESCENTES))
    assert contexto.orcamento.gasto > antes


def test_kind_desconhecido_recusa() -> None:
    variante = {"id": "x", "recognition": {"status": "enabled", "grammar": {"kind": "inexistente"}}}

    with pytest.raises(ValueError, match="inexistente"):
        casar_variantes(pagina_gramatica(()), [({}, variante)])


def _pequena(origem: Any) -> PaginaGramatica:
    """Haste de 4 pt com barras proporcionais, abaixo da haste mínima absoluta de 6 pt."""
    fator = 0.4
    cx, cy, meia = 100.0, 100.0, 5.0 * fator
    caminhos = [linha((cx, cy + meia), (cx, cy - meia))]
    for i, comprimento in enumerate(DECRESCENTES):
        y, meio = cy - meia - i * LACUNA * fator, comprimento * fator / 2
        caminhos.append(linha((cx - meio, y), (cx + meio, y)))
    textos = () if origem is None else (texto("LIVRE", (5.0, 5.0, 30.0, 12.0), origem),)
    return pagina_gramatica(caminhos, textos)


def test_simbolo_pequeno_so_casa_na_pagina_de_texto_em_glifo() -> None:
    assert _variantes(_pequena("glifo")) == ["cemig-eo-r3-s19-v001"]
    assert _variantes(_pequena("nativo")) == []
    assert _variantes(_pequena("shx")) == []
    assert _variantes(_pequena(None)) == []


def test_origem_predominante_da_pagina() -> None:
    def com(*origens: Any) -> Any:
        textos = [texto("A", (5.0, 5.0 + i, 9.0, 9.0 + i), o) for i, o in enumerate(origens)]
        return pagina_gramatica((), textos).modelo

    assert origem_predominante(com()) == "nativo"
    assert origem_predominante(com("glifo", "glifo", "nativo")) == "glifo"
    assert origem_predominante(com("shx", "nativo", "nativo")) == "nativo"
    assert origem_predominante(com("glifo", "nativo")) == "nativo"


@pytest.mark.parametrize(("comprimentos", "esperada"), [(DECRESCENTES, 0), (ALTERNADAS, 4)])
def test_x_com_braco_em_contorno_de_outro_desenho_nao_e_marca_de_retirada(
    comprimentos: tuple[float, ...], esperada: int
) -> None:
    """Braço do X é um traço só, como a haste e as barras: lado de contorno não forma X."""
    pagina = pagina_desenhada(lambda p: desenhar_haste(p, comprimentos, x=True, x_em_contorno=True))

    assert _variantes(pagina) == [_VARIANTES[esperada]]


@pytest.mark.parametrize("x", [False, True], ids=["sem_x", "com_x"])
@pytest.mark.parametrize(
    ("comprimentos", "contorno", "esperada"),
    [
        (DECRESCENTES, CIRCULO_POLIGONAL, 1),
        (ALTERNADAS, CIRCULO_POLIGONAL, 5),
        (DECRESCENTES, HEXAGONO, 0),
        (ALTERNADAS, HEXAGONO, 4),
        (DECRESCENTES, ESTRELA, 0),
        (ALTERNADAS, ESTRELA, 4),
    ],
    ids=[
        "3-circulo-poligonal",
        "4-circulo-poligonal",
        "3-hexagono",
        "4-hexagono",
        "3-estrela",
        "4-estrela",
    ],
)
def test_envolvente_poligonal_so_vale_quando_e_eliptica(
    comprimentos: tuple[float, ...], contorno: tuple[float, ...], esperada: int, x: bool
) -> None:
    """Círculo achatado em muitos segmentos é envolvente; hexágono e estrela não são."""
    desenhos: list[DesenhoHaste] = []
    pagina = pagina_desenhada(
        lambda p: desenhos.append(
            desenhar_haste(p, comprimentos, envolvente=True, contorno=contorno, x=x)
        )
    )
    # Com X, a variante com marca de retirada é a seguinte em CASOS_HASTE (v002 -> v003...).
    variante = _VARIANTES[esperada + (1 if esperada % 4 == 1 else 3) * x]

    [casamento] = _casamentos(pagina)
    assert casamento.variante["id"] == variante
    envolvente = desenhos[0].envolvente
    assert envolvente is not None
    tem_envolvente = esperada % 4 == 1
    assert _contem(casamento.caixa, envolvente[:2]) is tem_envolvente


def test_quatro_alternadas_nao_casam_como_tres_decrescentes() -> None:
    pagina = pagina_desenhada(lambda p: desenhar_haste(p, ALTERNADAS))

    assert _variantes(pagina) == ["cemig-eo-r3-s21-v005"]


def test_cada_semente_paga_do_orcamento() -> None:
    """Muitos traços de comprimento de haste: o teto vem do orçamento, sem laço sem limite."""
    caminhos = [
        linha((10.0 + (i % 40) * 7.0, 10.0 + (i // 40) * 0.5), (16.5 + (i % 40) * 7.0, 10.0))
        for i in range(2000)
    ]
    pagina = pagina_gramatica(caminhos)
    so_indices = contexto_gramaticas(pagina).orcamento.gasto
    contexto = contexto_gramaticas(pagina, limite=so_indices + 100)

    with pytest.raises(TetoGramaticasExcedido):
        casa_hastes(contexto, dict(CASOS_HASTE)[_VARIANTES[0]])


def test_quatro_barras_decrescentes_nao_sao_forma_do_inventario() -> None:
    """Fail-closed: nem aterramento (3 decrescentes) nem para-raios (4 alternadas)."""
    pagina = pagina_desenhada(lambda p: desenhar_haste(p, (8.0, 6.0, 4.5, 3.0)))

    assert _variantes(pagina) == []


def test_quarta_barra_maior_que_a_terceira_nao_impede_o_aterramento() -> None:
    pagina = pagina_desenhada(lambda p: desenhar_haste(p, (8.0, 5.5, 3.0, 6.0)))

    assert _variantes(pagina) == ["cemig-eo-r3-s19-v001"]


def test_x_com_vermelhos_quase_iguais_e_marca_de_retirada() -> None:
    """A cor não decide nada: 1,0 e 0,996 de vermelho são a mesma cor canônica."""

    def desenhar(p: pymupdf.Page) -> None:
        desenho = desenhar_haste(p, DECRESCENTES)
        mx, my = desenho.ponta[0], desenho.ponta[1] - LACUNA
        p.draw_line((mx - 7.2, my - 7.2), (mx + 7.2, my + 7.2), color=(1.0, 0.0, 0.0))
        p.draw_line((mx - 7.2, my + 7.2), (mx + 7.2, my - 7.2), color=(0.996, 0.0, 0.0))

    assert _variantes(pagina_desenhada(desenhar)) == ["cemig-eo-r3-s19-v004"]


def _haste_com_diagonais(diagonais: int) -> PaginaGramatica:
    """Uma haste válida e `diagonais` traços paralelos a 45° que não se cruzam, na janela do X.

    Azuis, fora das cores do legado: não são sementes nem barras, só candidatos a braço.
    """
    cx, cy = 150.0, 150.0
    caminhos = [linha((cx, cy + 5.0), (cx, cy - 5.0))]
    for i, comprimento in enumerate(DECRESCENTES):
        y, meio = cy - 5.0 - i * LACUNA, comprimento / 2
        caminhos.append(linha((cx - meio, y), (cx + meio, y)))
    for i in range(diagonais):
        d = -6.0 + 12.0 * i / max(diagonais - 1, 1)
        caminhos.append(linha((cx - 5.0 + d, cy - 12.0), (cx + 5.0 + d, cy - 2.0), cor=_AZUL))
    return pagina_gramatica(caminhos)


def _gasto_das_hastes(pagina: PaginaGramatica, limite: int | None = None) -> int:
    contexto = (
        contexto_gramaticas(pagina)
        if limite is None
        else contexto_gramaticas(pagina, limite=limite)
    )
    antes = contexto.orcamento.gasto
    casa_hastes(contexto, dict(CASOS_HASTE)[_VARIANTES[0]])
    return contexto.orcamento.gasto - antes


def test_pares_de_bracos_do_x_pagam_do_orcamento() -> None:
    sem = _gasto_das_hastes(_haste_com_diagonais(0))
    com = _gasto_das_hastes(_haste_com_diagonais(80))

    assert com - sem >= 80 * 79 // 2
    pagina = _haste_com_diagonais(80)
    so_indices = contexto_gramaticas(pagina).orcamento.gasto
    with pytest.raises(TetoGramaticasExcedido):
        _gasto_das_hastes(pagina, limite=so_indices + 80 * 79 // 4)


def test_deduplicacao_paga_as_comparacoes() -> None:
    """Muitas leituras da mesma haste: cada comparação com uma leitura escolhida gasta 1."""
    from zeny_project_handler.adapters.analysis.drawing_model.grammar_stem import (
        Haste,
        _deduplicar,
    )
    from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
        OrcamentoConsultas,
        Segmento,
    )

    def leitura(i: int) -> Haste:
        haste = Segmento((0.0, 0.0), (0.0, 10.0), 0)
        barras = tuple(
            Segmento((-1.0, 10.0 + j + i), (1.0, 10.0 + j + i), 10 + i) for j in (0, 1, 2)
        )
        return Haste(haste, barras, (0.0, 10.0), (0.0, 0.0), 2.0, (-1.0, 10.0, 1.0, 12.0))

    orcamento = OrcamentoConsultas(10**9)
    escolhidas = _deduplicar([leitura(i) for i in range(50)], orcamento)
    assert len(escolhidas) == 1
    assert orcamento.gasto >= 50
    with pytest.raises(TetoGramaticasExcedido):
        _deduplicar([leitura(i) for i in range(50)], OrcamentoConsultas(10))
