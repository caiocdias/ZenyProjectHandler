"""Casamento das variantes habilitadas sobre a página do modelo de desenho.

Une o contexto e as gramáticas: é o equivalente puro de `_observe_variant`, do motor
`declarative_symbols`, sem construir observações.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from zeny_project_handler.adapters.analysis.drawing_model.grammar_disc import (
    Disco,
    _caixa_arredondada,
    casa_disco,
    discos_candidatos,
    pontas_terminais,
)
from zeny_project_handler.adapters.analysis.drawing_model.grammar_frames import casa_moldura
from zeny_project_handler.adapters.analysis.drawing_model.grammar_stem import (
    casa_hastes,
    hastes_candidatas,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    LIMITE_CONSULTAS_PAGINA,
    ContextoGramatica,
    GradeEspacial,
    PaginaGramatica,
    Segmento,
    contexto_gramaticas,
)

_DISCO_TERMINAL: Final = "terminal_disc"
_HASTE_COM_BARRAS: Final = "stem_bars"
_MOLDURAS: Final = frozenset(
    {
        "label_in_frame",
        "triangle_in_frame",
        "framed_diagonals",
        "nested_rectangles_bar",
        "diamond_three_dots",
    }
)

_Achado = tuple[Caixa, int, tuple[int, ...]]


@dataclass(frozen=True, slots=True)
class CasamentoGramatica:
    """`caminho` é a posição em `modelo.caminhos`; o índice cru sai de `indices_crus`.

    `componentes` são as posições dos demais caminhos do símbolo, sem `caminho`, em ordem
    crescente; só a haste com barras os preenche (barras, envolvente e braços do X).
    """

    pacote: Mapping[str, Any]
    variante: Mapping[str, Any]
    caixa: Caixa
    caminho: int
    componentes: tuple[int, ...] = ()


def _gramatica(variante: Mapping[str, Any]) -> Mapping[str, Any]:
    gramatica: Mapping[str, Any] = variante["recognition"]["grammar"]
    return gramatica


def _achados_em_molduras(
    contexto: ContextoGramatica, gramatica: Mapping[str, Any]
) -> list[_Achado]:
    """Cada moldura visitada gasta 1, porque `casa_moldura` recusa muitas sem consultar a grade."""
    contexto.orcamento.gastar(len(contexto.molduras))
    return [
        (moldura.caixa, moldura.caminho, ())
        for moldura in contexto.molduras
        if casa_moldura(contexto, gramatica, moldura)
    ]


def _achados_em_discos(
    contexto: ContextoGramatica,
    gramatica: Mapping[str, Any],
    discos: Sequence[Disco],
    pontas: GradeEspacial[Segmento],
) -> list[_Achado]:
    contexto.orcamento.gastar(len(discos))
    return [
        (disco.caixa, disco.caminho, ())
        for disco in discos
        if casa_disco(contexto, gramatica, disco, pontas)
    ]


def _tem_tipo(variantes: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]], tipo: str) -> bool:
    return any(_gramatica(variante)["kind"] == tipo for _, variante in variantes)


def _casar_no_contexto(
    contexto: ContextoGramatica,
    variantes: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> tuple[CasamentoGramatica, ...]:
    """Despacho explícito por `kind`; tipo desconhecido é `ValueError`, nunca uma não detecção."""
    discos = discos_candidatos(contexto) if _tem_tipo(variantes, _DISCO_TERMINAL) else ()
    # Sem disco, ninguém consulta as pontas: a página não paga por elas.
    pontas = pontas_terminais(contexto) if discos else None
    # As hastes da página valem para as 8 variantes: calculadas uma vez, como os discos.
    hastes = hastes_candidatas(contexto) if _tem_tipo(variantes, _HASTE_COM_BARRAS) else ()
    casamentos: list[CasamentoGramatica] = []
    vistos: set[tuple[str, Caixa]] = set()
    for pacote, variante in variantes:
        gramatica = _gramatica(variante)
        tipo = gramatica["kind"]
        achados: list[_Achado]
        if tipo == _DISCO_TERMINAL:
            achados = (
                [] if pontas is None else _achados_em_discos(contexto, gramatica, discos, pontas)
            )
        elif tipo == _HASTE_COM_BARRAS:
            achados = casa_hastes(contexto, gramatica, candidatas=hastes)
        elif tipo in _MOLDURAS:
            achados = _achados_em_molduras(contexto, gramatica)
        else:
            raise ValueError(f"Gramática desconhecida: {tipo!r}.")
        for caixa, caminho, componentes in achados:
            chave = (str(variante["id"]), _caixa_arredondada(caixa))
            if chave not in vistos:
                vistos.add(chave)
                casamentos.append(CasamentoGramatica(pacote, variante, caixa, caminho, componentes))
    return tuple(casamentos)


def casar_variantes(
    pagina: PaginaGramatica,
    variantes: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    *,
    limite: int = LIMITE_CONSULTAS_PAGINA,
) -> tuple[CasamentoGramatica, ...]:
    """Casamentos na ordem de `variantes` e dos candidatos, um por variante e caixa arredondada.

    `variantes` são os pares (pacote, variante) habilitados. Tudo ou nada: levanta
    `TetoGramaticasExcedido` e `FonteGramaticaFalhou`, sem casamento parcial.
    """
    return _casar_no_contexto(contexto_gramaticas(pagina, limite=limite), variantes)


@dataclass(frozen=True, slots=True)
class GastoPagina:
    """Gasto do orçamento da página por fase: colagem de spans, índices e gramáticas."""

    colagem: int
    indices: int
    gramaticas: int

    @property
    def total(self) -> int:
        return self.colagem + self.indices + self.gramaticas


def gasto_por_fase(
    pagina: PaginaGramatica,
    variantes: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    *,
    limite: int = LIMITE_CONSULTAS_PAGINA,
) -> GastoPagina:
    """O gasto que `casar_variantes` faria, repartido por fase; levanta o mesmo que ele."""
    contexto = contexto_gramaticas(pagina, limite=limite)
    depois_dos_indices = contexto.orcamento.gasto
    _casar_no_contexto(contexto, variantes)
    return GastoPagina(
        colagem=contexto.gasto_colagem,
        indices=depois_dos_indices - contexto.gasto_colagem,
        gramaticas=contexto.orcamento.gasto - depois_dos_indices,
    )
