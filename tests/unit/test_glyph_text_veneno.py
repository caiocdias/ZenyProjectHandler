# mypy: disable-error-code="no-untyped-call"
"""Ataques ao envenenamento por vizinho reprovado, ao orçamento de pontos e ao quadro incerto."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from tests.fixtures.glyphs.fonte_livre import (
    LinhaTexto,
    caminhos_do_pdf,
    pdf_texto_contorno,
    tabela_do_alfabeto,
)

from zeny_project_handler.adapters.analysis.drawing_model import glyph_text
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import TabelaGlifos
from zeny_project_handler.adapters.analysis.drawing_model.glyph_text import (
    LeituraGlifos,
    extrair_trechos,
    ler_texto_glifos,
)

_VALOR = LinhaTexto("P10", (60.0, 100.0), 5.0)
_RESTO = LinhaTexto("N1", (73.5, 100.0), 5.0)
_GRANDE = LinhaTexto("(", (70.0, 100.0), 7.5)  # 7,06 pt de altura: reprovado (limite 7,0)


@pytest.fixture(scope="module")
def tabela(tmp_path_factory: pytest.TempPathFactory) -> TabelaGlifos:
    return tabela_do_alfabeto(tmp_path_factory.mktemp("alfabeto-veneno"))


def _caminhos(
    tmp_path: Path,
    linhas: Sequence[LinhaTexto],
    extra: Callable[[Any], None] | None = None,
) -> tuple[Any, ...]:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", linhas)
    if extra is not None:
        with pymupdf.open(pdf) as documento:
            extra(documento[0])
            destino = tmp_path / "extra.pdf"
            documento.save(destino)
        pdf = destino
    return caminhos_do_pdf(pdf)


def test_parenteses_grande_reprovado_no_meio_anula_os_dois_trechos(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    caminhos = _caminhos(tmp_path, [_VALOR, _GRANDE, _RESTO])

    leitura = ler_texto_glifos(caminhos, tabela)

    assert [len(t.glifos) for t in extrair_trechos(caminhos)] == [3, 2]
    assert leitura == LeituraGlifos((), 1, 0, limitada=False)


def test_parenteses_grande_colado_depois_do_valor_anula_o_trecho(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    leitura = ler_texto_glifos(_caminhos(tmp_path, [_VALOR, _GRANDE]), tabela)

    assert leitura == LeituraGlifos((), 1, 0, limitada=False)


def test_parenteses_em_tamanho_aceito_no_meio_do_valor_e_lido_junto(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    linhas = [LinhaTexto("P10(N1", (60.0, 100.0), 6.5)]

    leitura = ler_texto_glifos(_caminhos(tmp_path, linhas), tabela)

    assert [t.texto for t in leitura.textos] == ["P10(N1"]
    assert (leitura.desconhecidos, leitura.ambiguos) == (0, 0)


def test_reprovado_de_outra_cor_ou_longe_nao_envenena(tmp_path: Path, tabela: TabelaGlifos) -> None:
    def distantes(pagina: Any) -> None:
        pagina.draw_rect(pymupdf.Rect(200, 90, 212, 102), color=None, fill=(0, 0, 0))

    def colado_de_outra_cor(pagina: Any) -> None:
        pagina.draw_rect(pymupdf.Rect(69.5, 90, 81.5, 102), color=None, fill=(1, 0, 0))

    for extra in (distantes, colado_de_outra_cor):
        leitura = ler_texto_glifos(_caminhos(tmp_path, [_VALOR], extra), tabela)
        assert [t.texto for t in leitura.textos] == ["P10"]
        assert leitura.desconhecidos == 0


def test_veneno_de_um_trecho_nao_anula_trecho_distante_da_pagina(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    linhas = [_VALOR, _GRANDE, LinhaTexto("E=612345", (200.0, 200.0), 5.0)]

    leitura = ler_texto_glifos(_caminhos(tmp_path, linhas), tabela)

    assert [t.texto for t in leitura.textos] == ["E=612345"]
    assert leitura.desconhecidos == 1


def test_limitacao_conhecida_reprovado_a_duas_posicoes_nao_envenena(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    # Caracteriza o alcance do veneno: só o vizinho IMEDIATO na ordem de desenho conta. Com uma
    # forma de outra cor desenhada entre o valor e o "(" grande, "P10" sai como valor completo
    # ao lado do "(" que a regra de C1 quer proteger. Se o desenvolvedor ampliar o alcance,
    # este teste deve ser atualizado para esperar `textos == ()`.
    linhas = [_VALOR, LinhaTexto("X", (300.0, 250.0), 5.0, cor=(1.0, 0.0, 0.0)), _GRANDE]

    leitura = ler_texto_glifos(_caminhos(tmp_path, linhas), tabela)

    assert [t.texto for t in leitura.textos] == ["P10"]


def _total_de_pontos(caminhos: Sequence[Any]) -> int:
    return sum(glyph_text._pontos_achatados(c) for c in caminhos if glyph_text._eh_candidato(c))


def test_orcamento_de_pontos_e_inclusivo_na_fronteira(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    caminhos = _caminhos(tmp_path, [_VALOR, _RESTO])
    total = _total_de_pontos(caminhos)
    assert total > 10

    monkeypatch.setattr(glyph_text, "LIMITE_PONTOS_PAGINA", total)
    no_limite = ler_texto_glifos(caminhos, tabela)
    monkeypatch.setattr(glyph_text, "LIMITE_PONTOS_PAGINA", total - 1)
    acima = ler_texto_glifos(caminhos, tabela)

    assert not no_limite.limitada and no_limite.textos
    assert acima == LeituraGlifos((), 0, 0, limitada=True)


def test_orcamento_de_pontos_nao_conta_o_que_nao_e_candidato(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    def retangulos(pagina: Any) -> None:
        for i in range(20):
            pagina.draw_rect(pymupdf.Rect(10, 150 + 6 * i, 150, 154 + 6 * i), fill=(0, 0, 0))

    caminhos = _caminhos(tmp_path, [_VALOR], retangulos)
    glifos = [c for c in caminhos if glyph_text._eh_candidato(c)]
    monkeypatch.setattr(glyph_text, "LIMITE_PONTOS_PAGINA", _total_de_pontos(glifos))

    leitura = ler_texto_glifos(caminhos, tabela)

    assert not leitura.limitada
    assert [t.texto for t in leitura.textos] == ["P10"]


@pytest.mark.parametrize("rotacao", [0.0, 13.0, 90.0, 200.0])
@pytest.mark.parametrize("texto", ["P1", "N7", "P10", "S1N", "U4(1)"])
def test_trecho_curto_legitimo_continua_lido_com_rotacao_proxima(
    tmp_path: Path, tabela: TabelaGlifos, texto: str, rotacao: float
) -> None:
    caminhos = _caminhos(tmp_path, [LinhaTexto(texto, (150.0, 150.0), 5.0, rotacao)])

    leitura = ler_texto_glifos(caminhos, tabela)
    (trecho,) = extrair_trechos(caminhos)

    assert [t.texto for t in leitura.textos] == [texto]
    erro = abs((trecho.rotacao - (-rotacao) % 360.0 + 180.0) % 360.0 - 180.0)
    assert erro <= 1.5


def test_trecho_longo_limpo_nao_e_marcado_como_quadro_incerto(tmp_path: Path) -> None:
    caminhos = _caminhos(tmp_path, [LinhaTexto("E=612345 N=7801234", (40.0, 60.0), 5.0)])

    (trecho,) = extrair_trechos(caminhos)

    assert trecho.quadro_incerto is False


def test_trecho_de_um_glifo_de_corpo_inteiro_e_quadro_incerto_e_nada_e_lido(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    caminhos = _caminhos(tmp_path, [LinhaTexto("-1", (40.0, 60.0), 5.0)])

    (trecho,) = extrair_trechos(caminhos)

    assert trecho.quadro_incerto is True
    assert ler_texto_glifos(caminhos, tabela).textos == ()
