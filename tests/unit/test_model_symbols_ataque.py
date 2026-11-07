# mypy: disable-error-code="no-untyped-call"
"""Ataques ao método sobre o modelo de desenho: custo do resíduo raster e página transformada."""

from __future__ import annotations

import random
from collections.abc import Iterator, Sequence
from dataclasses import replace
from typing import Final

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.paginas import pagina_gramatica

from zeny_project_handler.adapters.analysis import model_symbols
from zeny_project_handler.adapters.analysis.declarative_symbols import carregar_pacotes
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    TabelaGlifos,
    carregar_tabela_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa, ImagemModelo
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    PaginaGramatica,
    ponto_em,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import CasamentoGramatica
from zeny_project_handler.adapters.analysis.model_symbols import (
    observar_pacotes_modelo,
    residuos_raster,
)
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos
from zeny_project_handler.domain.symbols import ResultadoMetodoSimbolos

_SHA: Final = "a" * 64
_MOLDURA_CT: Final[Caixa] = (101.0, 115.0, 169.0, 149.0)
_CAMARA_CT: Final = "cemig-eo-r3-s06-v001"
_PRETO: Final = (0, 0, 0)


@pytest.fixture(scope="module")
def tabela() -> TabelaGlifos:
    return carregar_tabela_glifos()


def _hash(indice: int) -> str:
    return f"{indice:064x}"


def _imagem(caixa: Caixa, indice: int, px: tuple[int, int] = (20, 20)) -> ImagemModelo:
    return ImagemModelo(caixa, px[0], px[1], _hash(indice), False)


def _pagina(imagens: Sequence[ImagemModelo], lado: float = 300.0) -> PaginaGramatica:
    base = pagina_gramatica(())
    modelo = replace(base.modelo, imagens=tuple(imagens), largura=lado, altura=lado)
    return replace(base, modelo=modelo)


def _casamento(caixa: Caixa) -> CasamentoGramatica:
    return CasamentoGramatica({}, {}, caixa, 0)


def _imagens_soltas(quantidade: int) -> tuple[ImagemModelo, ...]:
    """Imagens compactas de hashes e dimensões distintos (nunca mosaico), dentro da folha."""
    return tuple(
        _imagem((10.0 * i, 0.0, 10.0 * i + 5.0, 5.0), i, (10 + i, 20)) for i in range(quantidade)
    )


def _casamentos_longe(quantidade: int) -> tuple[CasamentoGramatica, ...]:
    """Casamentos pequenos que não cobrem imagem nenhuma."""
    return tuple(_casamento((10.0 * i, 50.0, 10.0 * i + 1.0, 51.0)) for i in range(quantidade))


def _trabalho(monkeypatch: pytest.MonkeyPatch, imagens: int, casamentos: int) -> int:
    """Conta as consultas de ponto em caixa de `residuos_raster`: trabalho, não tempo."""
    chamadas = 0
    original = ponto_em

    def contar(caixa: Caixa, ponto: tuple[float, float]) -> bool:
        nonlocal chamadas
        chamadas += 1
        return original(caixa, ponto)

    monkeypatch.setattr(model_symbols, "ponto_em", contar)
    pagina = _pagina(_imagens_soltas(imagens), lado=1_000_000.0)
    resultado = residuos_raster(pagina, _casamentos_longe(casamentos))
    assert len(resultado) == imagens
    return chamadas


def test_trabalho_do_residuo_nao_cresce_com_o_produto_de_imagens_e_casamentos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Em PDF hostil, N imagens e M casamentos não podem custar N*M consultas.

    `residuos_raster` não gasta o orçamento de consultas da página. Dobrar os dois deve, no
    máximo, dobrar o trabalho (com folga até 3x); o produto o quadruplica.
    """
    pequeno = _trabalho(monkeypatch, 200, 200)
    grande = _trabalho(monkeypatch, 400, 400)

    assert pequeno > 0
    assert grande <= 3 * pequeno, f"{pequeno} consultas com 200x200; {grande} com 400x400"


def test_trabalho_do_residuo_e_linear_so_nas_imagens(monkeypatch: pytest.MonkeyPatch) -> None:
    """Controle: com casamentos fixos, dobrar as imagens dobra o trabalho."""
    pequeno = _trabalho(monkeypatch, 200, 50)
    grande = _trabalho(monkeypatch, 400, 50)

    assert grande <= 2 * pequeno + 1


def test_imagem_com_caixa_nao_finita_nao_levanta_nem_vira_residuo() -> None:
    nan, inf = float("nan"), float("inf")
    imagens = (
        _imagem((nan, 10.0, 20.0, 20.0), 1),
        _imagem((10.0, 10.0, inf, 20.0), 2),
        _imagem((10.0, 10.0, 30.0, 30.0), 3),
    )

    obtidos = residuos_raster(_pagina(imagens), ())

    assert [r.sha256 for r in obtidos] == [_hash(3)]


def test_residuo_nao_depende_da_ordem_dos_casamentos() -> None:
    imagens = tuple(_imagem((10.0 + 30 * i, 10.0, 25.0 + 30 * i, 25.0), i) for i in range(6))
    casamentos = [_casamento((12.0 + 30 * i, 12.0, 14.0 + 30 * i, 14.0)) for i in (0, 2, 4)]
    esperado = residuos_raster(_pagina(imagens), casamentos)
    embaralhados = list(casamentos)
    random.Random(7).shuffle(embaralhados)

    assert residuos_raster(_pagina(imagens), embaralhados) == esperado
    assert [r.sha256 for r in esperado] == [_hash(1), _hash(3), _hash(5)]


# --- página real, transformada --------------------------------------------------------------


def _pixmap() -> pymupdf.Pixmap:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), False)
    pixmap.clear_with(128)
    return pixmap


@pytest.fixture
def pagina_ct() -> Iterator[pymupdf.Page]:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        pagina.draw_rect(pymupdf.Rect(_MOLDURA_CT), color=_PRETO, width=1)
        pagina.insert_text((_MOLDURA_CT[0] + 6, _MOLDURA_CT[1] + 25), "CT", fontsize=11)
        yield pagina


def _observar(pagina: pymupdf.Page, tabela: TabelaGlifos) -> ResultadoMetodoSimbolos:
    return observar_pacotes_modelo(
        pagina,
        documento_id="ataque",
        documento_sha256=_SHA,
        pagina_numero=1,
        pacotes=carregar_pacotes(),
        tabela=tabela,
    )


@pytest.mark.parametrize(
    ("rotacao", "recorte", "contagem"),
    [
        pytest.param(90, False, 2, id="rotacao-90"),
        pytest.param(180, False, 2, id="rotacao-180"),
        pytest.param(270, False, 2, id="rotacao-270"),
        pytest.param(0, True, 1, id="cropbox"),
        pytest.param(90, True, 1, id="cropbox-rotacao-90"),
        pytest.param(270, True, 1, id="cropbox-rotacao-270"),
    ],
)
def test_residuo_em_pagina_transformada_usa_o_espaco_visual(
    pagina_ct: pymupdf.Page, tabela: TabelaGlifos, rotacao: int, recorte: bool, contagem: int
) -> None:
    """Duas imagens soltas; com CropBox 50,60..250,280 a de (10,10) cai fora da página."""
    pagina_ct.insert_image(pymupdf.Rect(10, 10, 30, 30), pixmap=_pixmap())
    pagina_ct.insert_image(pymupdf.Rect(200, 200, 220, 220), pixmap=_pixmap())
    if recorte:
        pagina_ct.set_cropbox(pymupdf.Rect(50, 60, 250, 280))
    pagina_ct.set_rotation(rotacao)

    resultado = _observar(pagina_ct, tabela)

    assert resultado.coberturas[0].estado is EstadoMetodoSimbolos.CONCLUIDO
    assert resultado.coberturas[0].motivo == f"residuo_raster:{contagem}"
    assert [o.template for o in resultado.observacoes] == [_CAMARA_CT]


@pytest.mark.parametrize("rotacao", [90, 180, 270], ids=lambda r: f"rotacao-{r}")
def test_imagem_sob_o_casamento_em_pagina_rotacionada_nao_e_residuo(
    pagina_ct: pymupdf.Page, tabela: TabelaGlifos, rotacao: int
) -> None:
    pagina_ct.insert_image(pymupdf.Rect(_MOLDURA_CT), pixmap=_pixmap())
    pagina_ct.set_rotation(rotacao)

    resultado = _observar(pagina_ct, tabela)

    assert resultado.coberturas[0].motivo == "residuo_raster:0"
    assert [o.template for o in resultado.observacoes] == [_CAMARA_CT]


def test_resultado_e_identico_em_duas_execucoes(
    pagina_ct: pymupdf.Page, tabela: TabelaGlifos
) -> None:
    pagina_ct.insert_image(pymupdf.Rect(10, 10, 30, 30), pixmap=_pixmap())
    pagina_ct.set_rotation(90)

    assert _observar(pagina_ct, tabela) == _observar(pagina_ct, tabela)
