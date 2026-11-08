# mypy: disable-error-code="no-untyped-call"
"""E06.3.4, Task 3: ESTAI (`forked_stem`) no runner opt-in, com os pacotes reais.

`test_uma_observacao_por_forma` prova que cada forma de estai sai como uma única observação do
modelo, sem duplicata do mesmo desenho, com a variante do inventário esperada.

`test_variantes_pendentes_nao_geram_observacao_do_metodo` prova o caso com a habilitação
desligada: sem as três variantes de f02-14 habilitadas, o método não emite nenhum ESTAI.

`test_estai_do_legado_e_do_modelo_nao_fundem` (R-E06.3.4-6) fixa o desfecho medido no laboratório,
sem disjunção: o legado (`pymupdf_guys.observar_estais`) emite só o eixo da haste, em polilinha,
e o modelo emite a caixa do pictograma unida à haste; a caixa do eixo tem área zero e extremos
longe da caixa do modelo, então `_same_occurrence` recusa e cada estai vira duas ocorrências
no runner. Fica aceito até a E07.2 ("Para a E07").
"""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.pdf_temporario import salvar_pagina
from tests.integration.test_model_symbols_runner import _METODO_NOVO, _fonte, _settings

from zeny_project_handler.adapters.analysis import declarative_symbols
from zeny_project_handler.adapters.analysis.pymupdf_guys import perfil_estais
from zeny_project_handler.application.symbol_reconciliation import (
    SymbolReconciliation,
    _same_occurrence,
)
from zeny_project_handler.domain.symbols import ObservacaoSimbolo
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

pytestmark = pytest.mark.integration

_CLASSE = "ESTAI"
_PRETO = (0.0, 0.0, 0.0)
_CINZA = (0.2, 0.2, 0.2)
_VERDE = (0.0, 0.5, 0.0)
_VERMELHO = (1.0, 0.0, 0.0)
_BASE = (150.0, 130.0)
_HASTE = 16.0
_DENTE = 12.0
_ABERTURA = 26.0
_ESPESSURA = 0.2
_VARIANTES = ("cemig-eo-r3-s14-v001", "cemig-eo-r3-s14-v002", "cemig-eo-r3-s14-v003")

# (cor do garfo, com círculo, com X) -> variante do inventário.
_FORMAS: dict[str, tuple[tuple[float, float, float], bool, bool, str]] = {
    "preto": (_PRETO, False, False, _VARIANTES[0]),
    "cinza": (_CINZA, False, False, _VARIANTES[0]),
    "verde_com_circulo": (_VERDE, True, False, _VARIANTES[1]),
    "x_sem_circulo": (_VERMELHO, False, True, _VARIANTES[2]),
    "x_com_circulo": (_VERMELHO, True, True, _VARIANTES[2]),
}


def _polar(origem: tuple[float, float], graus: float, comprimento: float) -> tuple[float, float]:
    r = math.radians(graus)
    return origem[0] + comprimento * math.cos(r), origem[1] + comprimento * math.sin(r)


def _desenhar(
    pagina: pymupdf.Page, cor: tuple[float, float, float], circulo: bool, x: bool
) -> None:
    vertice = (_BASE[0] + _HASTE, _BASE[1])
    pagina.draw_line(_BASE, vertice, color=cor, width=_ESPESSURA)
    for sinal in (1, -1):
        pagina.draw_line(
            vertice, _polar(vertice, sinal * _ABERTURA, _DENTE), color=cor, width=_ESPESSURA
        )
    centro = _polar(vertice, 0.0, _DENTE * 0.75)
    if circulo:
        pagina.draw_circle(centro, _DENTE * 0.8, color=cor, width=_ESPESSURA)
    if x:
        for graus in (45, 135):
            pagina.draw_line(
                _polar(centro, graus, 9.0),
                _polar(centro, graus + 180, 9.0),
                color=_VERMELHO,
                width=1.2,
            )


def _rodar(
    tmp_path: Path, forma: str, pacotes: tuple[Any, ...] | None = None
) -> tuple[SymbolReconciliation, str, str]:
    cor, circulo, x, _ = _FORMAS[forma]
    caminho = salvar_pagina(tmp_path, lambda pagina: _desenhar(pagina, cor, circulo, x))
    documento_projeto, fonte = _fonte(caminho)
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"), packages=pacotes)
    novo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO).assinatura()
    legado = perfil_estais().assinatura()
    return runner.run(documento_projeto, fonte), novo, legado


def _de_estai(composto: SymbolReconciliation) -> list[ObservacaoSimbolo]:
    return [
        o
        for occ in composto.occurrences
        for o in occ.observations
        if o.alternativas and str(o.alternativas[0].classe) == _CLASSE
    ]


@pytest.mark.parametrize("forma", list(_FORMAS))
def test_uma_observacao_por_forma(tmp_path: Path, forma: str) -> None:
    composto, novo, _ = _rodar(tmp_path, forma)

    do_modelo = [o for o in _de_estai(composto) if o.metodo_assinatura == novo]

    assert len(do_modelo) == 1, do_modelo
    assert dict(do_modelo[0].atributos)["variante_inventario"] == _FORMAS[forma][3]


@pytest.mark.parametrize("forma", ["preto", "verde_com_circulo", "x_sem_circulo"])
def test_variantes_pendentes_nao_geram_observacao_do_metodo(tmp_path: Path, forma: str) -> None:
    pacotes = copy.deepcopy(declarative_symbols.carregar_pacotes())
    for pacote in pacotes:
        for variante in pacote.get("variants", []):
            if variante["id"] in _VARIANTES:
                variante["recognition"] = {
                    "status": "pending",
                    "reason": "desligada no teste",
                    "negative_examples": variante["recognition"]["negative_examples"],
                }

    composto, novo, _ = _rodar(tmp_path, forma, tuple(pacotes))

    assert [o for o in _de_estai(composto) if o.metodo_assinatura == novo] == []


@pytest.mark.parametrize("forma", ["preto", "verde_com_circulo"])
def test_estai_do_legado_e_do_modelo_nao_fundem(tmp_path: Path, forma: str) -> None:
    composto, novo, legado = _rodar(tmp_path, forma)
    de_estai = _de_estai(composto)
    do_modelo = [o for o in de_estai if o.metodo_assinatura == novo]
    do_legado = [o for o in de_estai if o.metodo_assinatura == legado]

    # Primeiro: as duas assinaturas observaram ESTAI na página.
    assert len(do_modelo) == 1, do_modelo
    assert len(do_legado) == 1, do_legado

    # Só então o julgamento, fixado pelo resultado medido: não funde, duas ocorrências.
    assert _same_occurrence(do_modelo[0], do_legado[0]) is False
    ocorrencias = [
        occ for occ in composto.occurrences if any(o in de_estai for o in occ.observations)
    ]
    assert sorted(len(occ.observations) for occ in ocorrencias) == [1, 1]
