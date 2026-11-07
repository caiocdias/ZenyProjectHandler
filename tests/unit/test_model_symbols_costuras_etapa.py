# mypy: disable-error-code="no-untyped-call"
"""Costuras da E06.2.2.1: rótulo em contorno (glifos_lidos), guarda de marca e teto de agrupamento,
todos pelo método sobre o modelo (`observar_pacotes_modelo`) e não só pelo casador."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import pymupdf
import pytest
from tests.fixtures.glyphs.fonte_livre import LinhaTexto, pdf_texto_contorno, tabela_do_alfabeto

from zeny_project_handler.adapters.analysis import pymupdf_drawing_model
from zeny_project_handler.adapters.analysis.declarative_symbols import carregar_pacotes
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import TabelaGlifos
from zeny_project_handler.adapters.analysis.drawing_model.groups import (
    AgrupamentoExcedido,
    agrupar_candidatos,
)
from zeny_project_handler.adapters.analysis.model_symbols import observar_pacotes_modelo
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos
from zeny_project_handler.domain.symbols import ResultadoMetodoSimbolos

_SHA: Final = "b" * 64
_MOLDURA: Final = (97.0, 93.0, 110.0, 103.0)
_CAMARA_CT: Final = "cemig-eo-r3-s06-v001"
_AZUL: Final = (0.0, 0.0, 1.0)


@pytest.fixture(scope="module")
def tabela(tmp_path_factory: pytest.TempPathFactory) -> TabelaGlifos:
    return tabela_do_alfabeto(tmp_path_factory.mktemp("alfabeto"))


def _metodo(
    tmp_path: Path,
    tabela: TabelaGlifos,
    desenhar: Callable[[Any], None] | None = None,
    *,
    rotacao: int = 0,
) -> ResultadoMetodoSimbolos:
    tmp_path.mkdir(parents=True, exist_ok=True)
    contorno = pdf_texto_contorno(
        tmp_path / "c.pdf", [LinhaTexto("CT", (100.0, 100.0), 5.0)], rotacao_pagina=rotacao
    )
    with pymupdf.open(contorno) as documento:
        pagina = documento[0]
        pagina.draw_rect(pymupdf.Rect(*_MOLDURA), color=(0.7, 0.0, 0.0))
        if desenhar is not None:
            desenhar(pagina)
        return observar_pacotes_modelo(
            pagina,
            documento_id="costura",
            documento_sha256=_SHA,
            pagina_numero=1,
            pacotes=carregar_pacotes(),
            tabela=tabela,
        )


def _marca(pagina: Any) -> None:
    pagina.draw_rect(pymupdf.Rect(105.5, 94.0, 109.5, 102.0), fill=_AZUL, color=None)


def _templates(resultado: ResultadoMetodoSimbolos) -> list[str]:
    return [str(o.template) for o in resultado.observacoes]


def test_rotulo_em_contorno_vira_observacao_pelo_metodo(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    resultado = _metodo(tmp_path, tabela)

    assert resultado.coberturas[0].estado is EstadoMetodoSimbolos.CONCLUIDO
    assert _templates(resultado) == [_CAMARA_CT]


def test_marca_real_ao_lado_do_rotulo_em_contorno_nao_vira_observacao(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    resultado = _metodo(tmp_path, tabela, _marca)

    assert _templates(resultado) == []
    assert resultado.coberturas[0].estado is EstadoMetodoSimbolos.NAO_DETECCAO


@pytest.mark.parametrize("rotacao", [90, 270], ids=["r90", "r270"])
def test_pagina_girada_mantem_a_guarda_nos_dois_sentidos(
    tmp_path: Path, tabela: TabelaGlifos, rotacao: int
) -> None:
    """`glifos_lidos` fala de posições do modelo: com a página girada o rótulo ainda não conta
    como marca, e a marca real ainda recusa."""
    sem_marca = _metodo(tmp_path / "a", tabela, rotacao=rotacao)
    com_marca = _metodo(tmp_path / "b", tabela, _marca, rotacao=rotacao)

    assert _templates(com_marca) == []
    assert _templates(sem_marca) == [_CAMARA_CT]


def test_teto_de_agrupamento_estourado_nao_muda_a_leitura_do_rotulo(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`modelo.grupos_falhou` não é fonte consumida pelo método: o mesmo rótulo segue lido."""
    esperado = _templates(_metodo(tmp_path / "ref", tabela))
    original = agrupar_candidatos
    estouros: list[bool] = []

    def com_teto_zero(primitivas: Any, caminhos: Any) -> Any:
        try:
            return original(primitivas, caminhos, limite_visitas=0)
        except AgrupamentoExcedido:
            estouros.append(True)
            raise

    monkeypatch.setattr(pymupdf_drawing_model, "agrupar_candidatos", com_teto_zero)

    resultado = _metodo(tmp_path / "teto", tabela)

    assert estouros == [True]
    assert esperado == [_CAMARA_CT]
    assert _templates(resultado) == esperado
    assert resultado.coberturas[0].estado is EstadoMetodoSimbolos.CONCLUIDO
