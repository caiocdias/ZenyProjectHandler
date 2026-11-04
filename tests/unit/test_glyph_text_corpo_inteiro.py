# mypy: disable-error-code="no-untyped-call"
"""Ataques à correção do quadro do trecho só pelos glifos de corpo inteiro (Task 2, E05)."""

from __future__ import annotations

import random
from collections.abc import Sequence
from pathlib import Path

import pytest
from tests.fixtures.glyphs.fonte_livre import (
    ALFABETO,
    LinhaTexto,
    caminhos_do_pdf,
    pdf_texto_contorno,
    tabela_do_alfabeto,
)

from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import TabelaGlifos
from zeny_project_handler.adapters.analysis.drawing_model.glyph_text import (
    LeituraGlifos,
    ler_texto_glifos,
)


@pytest.fixture(scope="module")
def tabela(tmp_path_factory: pytest.TempPathFactory) -> TabelaGlifos:
    return tabela_do_alfabeto(tmp_path_factory.mktemp("alfabeto-corpo"))


def _ler(tmp_path: Path, linhas: Sequence[LinhaTexto], tabela: TabelaGlifos) -> LeituraGlifos:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", linhas)
    return ler_texto_glifos(caminhos_do_pdf(pdf), tabela)


@pytest.mark.parametrize(
    "texto", ["1-1", "-11", "11-", "(11)", "/11/", "P(1)", "1/2", "11/", "1,1,"]
)
def test_pontuacao_e_descendentes_nas_pontas_leem_certo(
    tmp_path: Path, tabela: TabelaGlifos, texto: str
) -> None:
    leitura = _ler(tmp_path, [LinhaTexto(texto, (40.0, 60.0), 5.0)], tabela)

    assert [t.texto for t in leitura.textos] == [texto]


@pytest.mark.parametrize("texto", ["(1)", "()", "(((", "---", "=1", "-1", "(P)(1)"])
def test_trecho_de_pontuacao_alta_ou_sem_corpo_inteiro_falha_fechado(
    tmp_path: Path, tabela: TabelaGlifos, texto: str
) -> None:
    leitura = _ler(tmp_path, [LinhaTexto(texto, (40.0, 60.0), 5.0)], tabela)

    assert [t.texto for t in leitura.textos] in ([], [texto])


def test_tamanhos_misturados_no_mesmo_trecho_nunca_leem_errado(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    casos: tuple[tuple[list[LinhaTexto], tuple[list[str], ...]], ...] = (
        (
            [LinhaTexto("P7", (60.0, 100.0), 6.0), LinhaTexto("N1", (68.0, 100.0), 3.0)],
            ([], ["P7N1"], ["N1", "P7"]),
        ),
        (
            [LinhaTexto("P7N", (60.0, 100.0), 6.0), LinhaTexto("1", (75.0, 100.0), 3.0)],
            ([], ["P7N1"]),
        ),
        (
            [LinhaTexto("P7", (60.0, 100.0), 3.0), LinhaTexto("N1", (66.0, 100.0), 6.0)],
            ([], ["P7N1"], ["N1", "P7"]),
        ),
    )
    for linhas, aceitos in casos:
        lidos = sorted(t.texto for t in _ler(tmp_path, linhas, tabela).textos)
        assert lidos in aceitos


@pytest.mark.parametrize("texto", ["AQ", "QA", "8Q", "DQ", "OQ", "QHZ"])
def test_q_em_trecho_curto_nao_vira_o(tmp_path: Path, tabela: TabelaGlifos, texto: str) -> None:
    # Regressão (corrigida em dbe65e0): a cauda do "Q" desce abaixo da linha de base, mas a altura
    # dele fica dentro dos 15% de "corpo inteiro"; em trechos de 2 a 4 glifos o fundo do "Q"
    # entra no Theil-Sen, o quadro sai ~3 graus torto e o "Q" casa com "O" (distancia ~0,07,
    # dentro da tolerancia 0,08): sai "AO" no lugar de "AQ", sem diagnostico.
    leitura = _ler(tmp_path, [LinhaTexto(texto, (150.0, 150.0), 5.0)], tabela)

    assert [t.texto for t in leitura.textos] in ([], [texto])


@pytest.mark.parametrize("texto", ["..C0", ",-55"])
def test_pontuacao_pequena_vizinha_de_pontuacao_nao_some_em_silencio(
    tmp_path: Path, tabela: TabelaGlifos, texto: str
) -> None:
    # Regressão (corrigida em dbe65e0): dois glifos pequenos seguidos ficam a mais de 1,6 x o
    # maior lado um do outro; o primeiro sai do trecho sem diagnostico e o resto e lido como
    # valor completo: ".C0" no lugar de "..C0", "-55" no lugar de ",-55".
    leitura = _ler(tmp_path, [LinhaTexto(texto, (150.0, 150.0), 5.0)], tabela)

    assert [t.texto for t in leitura.textos] in ([], [texto])


def test_varredura_sem_q_nem_pontuacao_nas_pontas_nunca_le_errado(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    rng = random.Random(11)
    miolo = "".join(c for c in ALFABETO if c != "Q")
    firmes = "".join(c for c in miolo if c.isalnum())
    erros: list[tuple[str, float, float, list[str]]] = []
    for _ in range(120):
        meio = "".join(rng.choice(miolo) for _ in range(rng.randint(0, 5)))
        texto = rng.choice(firmes) + meio + rng.choice(firmes)
        tamanho = rng.choice([3.0, 4.0, 5.0, 6.0])
        rotacao = rng.choice([0.0, 30.0, 90.0, 180.0, 270.0])
        leitura = _ler(tmp_path, [LinhaTexto(texto, (150.0, 150.0), tamanho, rotacao)], tabela)
        lidos = [t.texto for t in leitura.textos]
        if lidos not in ([], [texto]):
            erros.append((texto, tamanho, rotacao, lidos))

    assert erros == []
