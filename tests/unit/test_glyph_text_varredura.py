# mypy: disable-error-code="no-untyped-call"
"""Varreduras aleatórias (semente fixa) e pares frágeis: nunca sai texto errado (Task 2, E05)."""

from __future__ import annotations

import random
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import pymupdf
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

# Sobrecarga medida do rastreamento de cobertura nesta leitura: 6.62 s com `--cov` contra
# 2.14 s sem (~3.1x). Sob rastreador, o orçamento é multiplicado por este fator: o tempo
# medido ali é o do rastreador, não o do código, mas um estouro catastrófico (laço quadrático)
# ainda aparece.
_FATOR_SOB_RASTREADOR = 4.0


def _rastreador_ativo() -> bool:
    """Cobertura, depurador ou profiler: `sys.settrace` (CTracer/PyTracer) ou, no 3.12+, uma
    ferramenta registrada em `sys.monitoring` (coverage com `COVERAGE_CORE=sysmon`)."""
    if sys.gettrace() is not None or sys.getprofile() is not None:
        return True
    monitoramento = getattr(sys, "monitoring", None)
    if monitoramento is None:
        return False
    return any(monitoramento.get_tool(ferramenta) is not None for ferramenta in range(6))


def _orcamento(segundos: float) -> float:
    return segundos * _FATOR_SOB_RASTREADOR if _rastreador_ativo() else segundos


@pytest.fixture(scope="module")
def tabela(tmp_path_factory: pytest.TempPathFactory) -> TabelaGlifos:
    return tabela_do_alfabeto(tmp_path_factory.mktemp("alfabeto-varredura"))


def _ler(tmp_path: Path, linhas: Sequence[LinhaTexto], tabela: TabelaGlifos) -> LeituraGlifos:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", linhas)
    return ler_texto_glifos(caminhos_do_pdf(pdf), tabela)


def _varrer(
    tmp_path: Path,
    tabela: TabelaGlifos,
    *,
    semente: int,
    casos: int,
    minimo: int,
    maximo: int,
    alfabeto: str,
    angulo_livre: bool,
) -> tuple[list[tuple[str, float, float, list[str]]], int]:
    rng = random.Random(semente)
    erros: list[tuple[str, float, float, list[str]]] = []
    lidos_certos = 0
    for _ in range(casos):
        texto = "".join(rng.choice(alfabeto) for _ in range(rng.randint(minimo, maximo)))
        tamanho = rng.choice([3.0, 4.0, 5.0, 6.0])
        rotacao = rng.uniform(0.0, 360.0) if angulo_livre else rng.choice([0.0, 90.0, 180.0, 270.0])
        leitura = _ler(tmp_path, [LinhaTexto(texto, (150.0, 150.0), tamanho, rotacao)], tabela)
        saida = [t.texto for t in leitura.textos]
        if saida == [texto]:
            lidos_certos += 1
        elif saida:
            erros.append((texto, tamanho, rotacao, saida))
    return erros, lidos_certos


@pytest.mark.parametrize("semente", [101, 202, 303])
def test_varredura_alfabeto_inteiro_2_a_6_glifos_angulo_livre_nunca_le_errado(
    tmp_path: Path, tabela: TabelaGlifos, semente: int
) -> None:
    erros, certos = _varrer(
        tmp_path,
        tabela,
        semente=semente,
        casos=300,
        minimo=2,
        maximo=6,
        alfabeto=ALFABETO,
        angulo_livre=True,
    )

    assert erros == []
    assert certos > 60  # a correção não pode simplesmente calar tudo


@pytest.mark.parametrize("semente", [7, 8])
def test_varredura_so_pares_frageis_nunca_le_errado(
    tmp_path: Path, tabela: TabelaGlifos, semente: int
) -> None:
    erros, certos = _varrer(
        tmp_path,
        tabela,
        semente=semente,
        casos=300,
        minimo=2,
        maximo=5,
        alfabeto="QO0IL1S5B8G6CD",
        angulo_livre=True,
    )

    assert erros == []
    assert certos > 30


@pytest.mark.parametrize("par", ["QO", "O0", "0O", "1I", "I1", "5S", "S5", "8B", "B8", "6G", "G6"])
@pytest.mark.parametrize("rotacao", [0.0, 17.0, 90.0, 213.0])
def test_par_fragil_isolado_nunca_vira_o_vizinho(
    tmp_path: Path, tabela: TabelaGlifos, par: str, rotacao: float
) -> None:
    for texto in (par, par + par, "P" + par, par + "7", par[::-1] + par):
        leitura = _ler(tmp_path, [LinhaTexto(texto, (150.0, 150.0), 5.0, rotacao)], tabela)
        assert [t.texto for t in leitura.textos] in ([], [texto])


@pytest.mark.parametrize("par", ["CG", "GC", "QC", "OQ", "QQ", "00", "OO", "II", "11"])
def test_trechos_longos_com_pares_frageis_leem_certo(
    tmp_path: Path, tabela: TabelaGlifos, par: str
) -> None:
    texto = f"P7{par}N{par}1"
    leitura = _ler(tmp_path, [LinhaTexto(texto, (150.0, 150.0), 5.0, 33.0)], tabela)

    assert [t.texto for t in leitura.textos] in ([], [texto])
    if "Q" not in par:
        assert [t.texto for t in leitura.textos] == [texto]


@pytest.mark.parametrize("forma", ["ponto", "barra", "quadrado"])
@pytest.mark.parametrize("lado_do_valor", ["antes", "depois"])
def test_forma_pequena_da_mesma_cor_colada_ao_valor_nunca_cria_texto_errado(
    tmp_path: Path, tabela: TabelaGlifos, forma: str, lado_do_valor: str
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "base.pdf", [LinhaTexto("P10 N1", (60.0, 100.0), 5.0)])
    destino = tmp_path / "com_forma.pdf"
    retangulos = {
        "ponto": (57.0, 100.0, 58.0, 101.0),
        "barra": (50.0, 99.0, 58.0, 99.8),
        "quadrado": (54.0, 94.0, 58.0, 98.0),
    }
    x0, y0, x1, y1 = retangulos[forma]
    deslocamento = 0.0 if lado_do_valor == "antes" else 38.0
    with pymupdf.open(pdf) as documento:
        documento[0].draw_rect(
            pymupdf.Rect(x0 + deslocamento, y0, x1 + deslocamento, y1), color=None, fill=(0, 0, 0)
        )
        documento.save(destino)

    leitura = ler_texto_glifos(caminhos_do_pdf(destino), tabela)

    # o valor pode falhar fechado, mas nunca sair com caractere a mais, a menos ou trocado
    assert all(t.texto in {"P10 N1", "P10", "N1"} for t in leitura.textos)


def test_custo_de_pagina_com_muitos_trechos_curtos_fica_no_orcamento(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    rng = random.Random(5)
    linhas = [
        LinhaTexto(
            "".join(rng.choice(ALFABETO) for _ in range(rng.randint(2, 5))),
            (10.0 + 60.0 * (i % 6), 15.0 + 7.5 * (i // 6)),
            4.0,
            rng.choice([0.0, 90.0]),
        )
        for i in range(240)
    ]
    caminhos = caminhos_do_pdf(pdf_texto_contorno(tmp_path / "c.pdf", linhas))

    inicio = time.perf_counter()
    leitura = ler_texto_glifos(caminhos, tabela)
    duracao = time.perf_counter() - inicio

    assert len(caminhos) >= 700
    assert not leitura.limitada
    assert duracao < _orcamento(5.0)
