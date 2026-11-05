# mypy: disable-error-code="no-untyped-call"
"""Teto de resoluções distintas por página na leitura de texto por contorno de glifo."""

from __future__ import annotations

import random
import time
from collections import Counter
from collections.abc import Callable
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
    ler_texto_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caminho,
    Estilo,
    ItemCaminho,
)
from zeny_project_handler.adapters.analysis.pymupdf_glyph_text import candidatos_texto_glifos

_LIMITADA = LeituraGlifos((), 0, 0, limitada=True)
# Um trecho tem até 64 glifos, resolvidos em até 3 quadros, mais uma confirmação de forma por
# glifo: o teto é conferido entre trechos, então a página passa dele por no máximo isso.
_EXCESSO_POR_TRECHO = 64 * 3 + 64


@pytest.fixture(scope="module")
def tabela(tmp_path_factory: pytest.TempPathFactory) -> TabelaGlifos:
    return tabela_do_alfabeto(tmp_path_factory.mktemp("alfabeto-orcamento"))


def _contar(monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    """Conta as chamadas que varrem a tabela: resolução e confirmação de forma."""
    chamadas: Counter[str] = Counter()

    def contando(nome: str, funcao: Callable[..., Any]) -> Callable[..., Any]:
        def chamar(*args: Any) -> Any:
            chamadas[nome] += 1
            return funcao(*args)

        return chamar

    for nome in ("resolver_glifo", "forma_sem_escala_confirma"):
        monkeypatch.setattr(glyph_text, nome, contando(nome, getattr(glyph_text, nome)))
    return chamadas


def _distintas(caminhos: Any, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch) -> int:
    with monkeypatch.context() as contexto:
        chamadas = _contar(contexto)
        ler_texto_glifos(caminhos, tabela)
    return sum(chamadas.values())


def test_teto_padrao_cobre_as_folhas_reais_com_folga_e_limita_o_custo() -> None:
    # nas 16 folhas reais a mais pesada faz 2 277 resoluções distintas (~5 ms cada)
    assert 3_000 <= glyph_text.LIMITE_RESOLUCOES_PAGINA <= 5_000


def test_pagina_ate_o_teto_de_resolucoes_e_lida_inteira(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("P10N1 E=612", (40.0, 60.0), 5.0)])
    caminhos = caminhos_do_pdf(pdf)
    distintas = _distintas(caminhos, tabela, monkeypatch)
    assert distintas > 1

    monkeypatch.setattr(glyph_text, "LIMITE_RESOLUCOES_PAGINA", distintas)
    no_limite = ler_texto_glifos(caminhos, tabela)
    monkeypatch.setattr(glyph_text, "LIMITE_RESOLUCOES_PAGINA", distintas - 1)
    acima = ler_texto_glifos(caminhos, tabela)

    assert [t.texto for t in no_limite.textos] == ["P10N1 E=612"]
    assert not no_limite.limitada
    assert acima == _LIMITADA


def test_confirmacao_de_forma_conta_no_teto_e_e_memorizada(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    # "11" sozinho: trecho de um caractere só, que pede a confirmação da forma sem escala
    um = caminhos_do_pdf(pdf_texto_contorno(tmp_path / "um.pdf", [LinhaTexto("11", (40, 60), 5)]))
    with monkeypatch.context() as contexto:
        chamadas = _contar(contexto)
        ler_texto_glifos(um, tabela)
    assert chamadas["forma_sem_escala_confirma"] >= 1
    distintas = sum(chamadas.values())
    linhas = [LinhaTexto("11", (40.0, 20.0 + 9.0 * i), 5.0) for i in range(20)]
    varios = caminhos_do_pdf(pdf_texto_contorno(tmp_path / "varios.pdf", linhas))

    monkeypatch.setattr(glyph_text, "LIMITE_RESOLUCOES_PAGINA", distintas)
    repetidos = ler_texto_glifos(varios, tabela)
    monkeypatch.setattr(glyph_text, "LIMITE_RESOLUCOES_PAGINA", distintas - 1)

    assert [t.texto for t in repetidos.textos] == ["11"] * 20 and not repetidos.limitada
    assert ler_texto_glifos(um, tabela) == _LIMITADA


def _pagina_hostil(quantidade: int) -> list[Caminho]:
    """Trechos de 8 glifos de corpo inteiro, cada glifo uma forma diferente (nada se repete na
    memória), abaixo do teto de candidatos e do orçamento de pontos."""
    sorteio = random.Random(20261104)
    estilo = Estilo("", None, (0.0, 0.0, 0.0), 0.0, "")
    caminhos: list[Caminho] = []
    for ordem in range(quantidade):
        trecho, posicao = divmod(ordem, 8)
        x = 1.0 * posicao + 15.0 * (trecho % 40)
        y = 3.0 * (trecho // 40)
        largura = 0.5 + 0.3 * sorteio.random()
        meio = (x + largura * sorteio.random(), y + 0.2 + 0.6 * sorteio.random())
        pontos = [(x, y), (x + largura, y), meio, (x + largura, y + 1.0), (x, y + 1.0)]
        itens = tuple(
            ItemCaminho("l", (a, b)) for a, b in zip(pontos, pontos[1:] + pontos[:1], strict=True)
        )
        caminhos.append(Caminho((itens,), estilo, "preenchimento", ordem))
    return caminhos


def test_pagina_hostil_acima_do_teto_de_resolucoes_e_limitada_em_tempo_limitado(
    tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    caminhos = _pagina_hostil(glyph_text.LIMITE_GLIFOS_PAGINA)
    assert glyph_text._candidatos_limitados(caminhos) is not None  # os outros tetos não pegam
    chamadas = _contar(monkeypatch)
    inicio = time.perf_counter()

    leitura = ler_texto_glifos(caminhos, tabela)

    assert leitura == _LIMITADA
    assert sum(chamadas.values()) <= glyph_text.LIMITE_RESOLUCOES_PAGINA + _EXCESSO_POR_TRECHO
    assert time.perf_counter() - inicio < 20.0


def test_pagina_acima_do_teto_de_resolucoes_gera_o_diagnostico(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("P10N1", (40.0, 60.0), 5.0)])
    monkeypatch.setattr(glyph_text, "LIMITE_RESOLUCOES_PAGINA", 1)

    with pymupdf.open(pdf) as documento:
        candidatos, diagnosticos = candidatos_texto_glifos(documento[0], 1, tabela)

    assert candidatos == ()
    assert [d.codigo for d in diagnosticos] == ["analise.glifos_limitados"]
