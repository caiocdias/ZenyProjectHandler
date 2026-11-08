# mypy: disable-error-code="no-untyped-call"
"""Costuras da E06.3.3.2.2 (transformador) com os pacotes reais, testador de etapa.

- agrupamento (Task 2) x gramática (Task 3) x pacotes reais (Task 4): dois transformadores de
  grupos diferentes lado a lado dão duas observações do modelo, cada uma com a lista do seu
  grupo, sem agrupar uma com a outra;
- transformador ao lado de PARA_RAIOS_BT e de haste: cada classe lê na página composta o mesmo
  que lê sozinha, e as marcas da página (contornos) são pagas uma vez pelas três gramáticas.
"""

from __future__ import annotations

import itertools
import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from tests.fixtures.symbol_grammars import rect_diagonal as bt
from tests.fixtures.symbol_grammars import stem_bars as haste
from tests.fixtures.symbol_grammars.pdf_temporario import salvar_pagina
from tests.fixtures.symbol_grammars.rect_diagonal import CASOS_RECT_DIAGONAL
from tests.fixtures.symbol_grammars.stem_bars import CASOS_HASTE
from tests.fixtures.symbol_grammars.triangulo import (
    CASOS_TRIANGULO,
    GRUPOS,
    Grupo,
    desenhar_grupo,
    variantes_do_grupo,
)
from tests.integration.test_model_symbols_runner import _METODO_NOVO, _fonte, _settings

from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import MarcasDaPagina
from zeny_project_handler.adapters.analysis.drawing_model.grammar_rect_diagonal import (
    retangulos_candidatos,
)
from zeny_project_handler.adapters.analysis.drawing_model.grammar_stem import hastes_candidatas
from zeny_project_handler.adapters.analysis.drawing_model.grammar_triangulo import (
    triangulos_candidatos,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import gasto_por_fase
from zeny_project_handler.application.symbol_reconciliation import SymbolReconciliation
from zeny_project_handler.domain.symbols import ObservacaoSimbolo
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

pytestmark = pytest.mark.integration

_TRAFO = "TRANSFORMADOR"
Desenho = Callable[[pymupdf.Page], object]


def _id_grupo(grupo: Grupo) -> str:
    fill, enclosure, removal = grupo
    return f"{fill}-{enclosure}-{'x' if removal else 'sem_x'}"


def _rodar(tmp_path: Path, desenhar: Desenho) -> tuple[SymbolReconciliation, str, dict[str, str]]:
    """Runner opt-in com os pacotes reais; devolve também `assinatura -> metodo_id`."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    documento, fonte = _fonte(salvar_pagina(tmp_path, desenhar))
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    novo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO).assinatura()
    metodos = {p.assinatura(): p.metodo_id for p in runner._profiles}
    return runner.run(documento, fonte), novo, metodos


def _observacoes(composto: SymbolReconciliation) -> list[ObservacaoSimbolo]:
    return [o for occ in composto.occurrences for o in occ.observations]


def _classe(observacao: ObservacaoSimbolo) -> str | None:
    return str(observacao.alternativas[0].classe) if observacao.alternativas else None


def _centro_x(observacao: ObservacaoSimbolo) -> float:
    xs = [float(x) for p in observacao.primitivas for x, _ in p.pontos_originais]
    return (min(xs) + max(xs)) / 2


# --- dois transformadores de grupos diferentes lado a lado --------------------------------------

# Centros a 20 pt: as envolventes (raio ~7,8 pt) quase se tocam, sem se sobrepor.
_ESQUERDA = (140.0, 150.0)
_DIREITA = (160.0, 150.0)
_PARES = list(itertools.combinations(GRUPOS, 2))


@pytest.mark.parametrize(
    ("esquerda", "direita"),
    _PARES,
    ids=[f"{_id_grupo(a)}+{_id_grupo(b)}" for a, b in _PARES],
)
def test_dois_transformadores_de_grupos_diferentes_lado_a_lado_dao_uma_observacao_cada(
    tmp_path: Path, esquerda: Grupo, direita: Grupo
) -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        desenhar_grupo(pagina, esquerda, centro=_ESQUERDA)
        desenhar_grupo(pagina, direita, centro=_DIREITA)

    composto, novo, _ = _rodar(tmp_path, desenhar)

    do_modelo = [
        o for o in _observacoes(composto) if o.metodo_assinatura == novo and _classe(o) == _TRAFO
    ]
    assert len(do_modelo) == 2, do_modelo
    for grupo, (cx, _) in ((esquerda, _ESQUERDA), (direita, _DIREITA)):
        (observacao,) = [o for o in do_modelo if abs(_centro_x(o) - cx) < 5.0]
        atributos = dict(observacao.atributos)
        esperadas = sorted(variantes_do_grupo(grupo))
        assert json.loads(str(atributos["referencias_possiveis"])) == esperadas, grupo
        assert atributos["variante_inventario"] == esperadas[0], grupo
    # Cada uma na sua ocorrência: o reconciliador não junta os dois transformadores.
    ocorrencias = [
        occ for occ in composto.occurrences if any(o in do_modelo for o in occ.observations)
    ]
    assert len(ocorrencias) == 2


# --- transformador ao lado de PARA_RAIOS_BT e de haste -------------------------------------------

_CENTRO_BT = (120.0, 150.0)
_CENTRO_TRAFO = (150.0, 150.0)
_CENTRO_HASTE = (180.0, 150.0)
# Vizinhos com o X no estado oposto ao do transformador: o X de um não pode virar o do outro.
_BT_COM_X, _BT_SEM_X = "cemig-eo-r3-s21-v004", "cemig-eo-r3-s21-v001"
_HASTE_COM_X, _HASTE_SEM_X = "cemig-eo-r3-s19-v004", "cemig-eo-r3-s19-v001"


def _partes(grupo: Grupo) -> dict[str, Desenho]:
    com_x = grupo[2]
    bt_id = _BT_SEM_X if com_x else _BT_COM_X
    haste_id = _HASTE_SEM_X if com_x else _HASTE_COM_X
    return {
        "trafo": lambda p: desenhar_grupo(p, grupo, centro=_CENTRO_TRAFO),
        "bt": lambda p: bt.desenhar_positivo(p, bt_id, centro=_CENTRO_BT),
        "haste": lambda p: haste.desenhar_positivo(p, haste_id, centro=_CENTRO_HASTE),
    }


def _todas(partes: Mapping[str, Desenho]) -> Desenho:
    def desenhar(pagina: pymupdf.Page) -> None:
        for parte in partes.values():
            parte(pagina)

    return desenhar


def _leitura(observacao: ObservacaoSimbolo) -> tuple[object, ...]:
    """Classe/subtipo, atributos e primitivas (pontos arredondados) de uma observação."""
    primitivas = sorted(
        tuple((round(float(x), 2), round(float(y), 2)) for x, y in p.pontos_originais)
        for p in observacao.primitivas
    )
    return (
        tuple((str(a.classe), a.subtipo) for a in observacao.alternativas),
        tuple(sorted((chave, str(valor)) for chave, valor in observacao.atributos)),
        tuple(primitivas),
    )


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_transformador_ao_lado_de_bt_e_haste_cada_classe_le_o_que_le_sozinha(
    tmp_path: Path, grupo: Grupo
) -> None:
    partes = _partes(grupo)
    composto, novo, metodos = _rodar(tmp_path / "junto", _todas(partes))

    juntas = _observacoes(composto)
    leituras_juntas = sorted(_leitura(o) for o in juntas if o.metodo_assinatura == novo)
    contagem_junta = Counter((metodos[o.metodo_assinatura], _classe(o)) for o in juntas)

    leituras_sozinhas: list[tuple[object, ...]] = []
    contagem_sozinha: Counter[tuple[str, str | None]] = Counter()
    for nome, parte in partes.items():
        sozinho, novo_sozinho, metodos_sozinho = _rodar(tmp_path / nome, parte)
        observacoes = _observacoes(sozinho)
        leituras_sozinhas += [
            _leitura(o) for o in observacoes if o.metodo_assinatura == novo_sozinho
        ]
        contagem_sozinha.update(
            (metodos_sozinho[o.metodo_assinatura], _classe(o)) for o in observacoes
        )

    classes_do_modelo = sorted(str(_classe(o)) for o in juntas if o.metodo_assinatura == novo)
    assert classes_do_modelo == sorted([_TRAFO, "PARA_RAIOS_BT", "ATERRAMENTO"])
    assert leituras_juntas == sorted(leituras_sozinhas)
    assert contagem_junta == contagem_sozinha


# --- marcas compartilhadas, sem gasto em dobro --------------------------------------------------


def _pagina(grupo: Grupo) -> Any:
    return bt.pagina_desenhada(_todas(_partes(grupo)))


def _pares(
    casos: Sequence[tuple[str, Mapping[str, Any]]],
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    return [
        ({"family_id": "autoral"}, {"id": v, "recognition": {"status": "enabled", "grammar": g}})
        for v, g in casos
    ]


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_tres_gramaticas_na_mesma_pagina_pagam_os_contornos_uma_vez(grupo: Grupo) -> None:
    pagina = _pagina(grupo)

    def gasto(funcao: Callable[[Any], object]) -> int:
        contexto = contexto_gramaticas(pagina)
        antes = contexto.orcamento.gasto
        funcao(contexto)
        return int(contexto.orcamento.gasto - antes)

    def contornos(contexto: Any) -> None:
        assert MarcasDaPagina(contexto).contornos is not None

    compartilhados: dict[str, tuple[Any, ...]] = {}

    def as_tres(contexto: Any) -> None:
        marcas = MarcasDaPagina(contexto)
        compartilhados["hastes"] = hastes_candidatas(contexto, marcas=marcas)
        compartilhados["retangulos"] = retangulos_candidatos(contexto, marcas=marcas)
        compartilhados["triangulos"] = triangulos_candidatos(contexto, marcas=marcas)

    so_hastes = gasto(hastes_candidatas)
    so_retangulos = gasto(retangulos_candidatos)
    so_triangulos = gasto(triangulos_candidatos)
    pago_pelos_contornos = gasto(contornos)
    juntas = gasto(as_tres)

    assert pago_pelos_contornos > 0
    assert juntas == so_hastes + so_retangulos + so_triangulos - 2 * pago_pelos_contornos
    # E o que cada uma acha não muda por dividir as marcas.
    sozinho = contexto_gramaticas(pagina)
    assert compartilhados["triangulos"] == triangulos_candidatos(sozinho)
    assert len(compartilhados["triangulos"]) == 1
    assert len(compartilhados["retangulos"]) == 1
    assert len(compartilhados["hastes"]) == 1


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_gasto_por_fase_das_tres_gramaticas_soma_os_contornos_uma_vez(grupo: Grupo) -> None:
    pagina = _pagina(grupo)
    pares_trafo = _pares(CASOS_TRIANGULO)
    pares_bt = _pares(CASOS_RECT_DIAGONAL)
    pares_haste = _pares(CASOS_HASTE)

    todas = gasto_por_fase(pagina, [*pares_trafo, *pares_bt, *pares_haste])
    so_trafo = gasto_por_fase(pagina, pares_trafo)
    so_bt = gasto_por_fase(pagina, pares_bt)
    so_haste = gasto_por_fase(pagina, pares_haste)
    vazio = gasto_por_fase(pagina, [])

    assert todas.indices == so_trafo.indices == so_bt.indices == so_haste.indices == vazio.indices
    contexto = contexto_gramaticas(pagina)
    antes = contexto.orcamento.gasto
    assert MarcasDaPagina(contexto).contornos is not None
    contornos = contexto.orcamento.gasto - antes
    assert contornos > 0
    assert todas.gramaticas == (
        so_trafo.gramaticas + so_bt.gramaticas + so_haste.gramaticas - 2 * contornos
    )
