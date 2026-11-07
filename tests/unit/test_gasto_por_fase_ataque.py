# mypy: disable-error-code="no-untyped-call"
"""Ataque ao gasto por fase: equivalência com o `casar_variantes` anterior e invariantes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

import pytest
from tests.fixtures.symbol_grammars.paginas import (
    circulo_bezier,
    linha,
    pagina_gramatica,
    retangulo_traco,
    texto,
)

from zeny_project_handler.adapters.analysis.drawing_model import symbol_grammars, symbol_matcher
from zeny_project_handler.adapters.analysis.drawing_model.grammar_disc import (
    _caixa_arredondada,
    discos_candidatos,
    pontas_terminais,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    ContextoGramatica,
    FonteGramaticaFalhou,
    PaginaGramatica,
    TetoGramaticasExcedido,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import (
    CasamentoGramatica,
    casar_variantes,
    gasto_por_fase,
)

Par = tuple[Mapping[str, Any], Mapping[str, Any]]

_ROXO: Final = (0.31, 0.10, 0.30)
_CINZA: Final = (0.5, 0.5, 0.5)
_DISCO: Final[dict[str, Any]] = {
    "kind": "terminal_disc",
    "fill": "purple",
    "min_span": 1.0,
    "max_span": 4.0,
    "terminal_line": True,
}
_ROTULO: Final[dict[str, Any]] = {
    "kind": "label_in_frame",
    "frame": "rectangle",
    "label": "CT",
    "max_span": 96,
}


def _par(identificador: str, gramatica: Mapping[str, Any]) -> Par:
    return {"family_id": "p"}, {
        "id": identificador,
        "recognition": {"status": "enabled", "grammar": gramatica},
    }


def _casar_antigo(
    contexto: ContextoGramatica, variantes: Sequence[Par]
) -> tuple[CasamentoGramatica, ...]:
    """Corpo de `casar_variantes` em 787e4c9, antes da extração de `_casar_no_contexto`."""
    m = symbol_matcher
    tem_disco = any(m._gramatica(v)["kind"] == m._DISCO_TERMINAL for _, v in variantes)
    discos = discos_candidatos(contexto) if tem_disco else ()
    pontas = pontas_terminais(contexto) if discos else None
    casamentos: list[CasamentoGramatica] = []
    vistos: set[tuple[str, Any]] = set()
    for pacote, variante in variantes:
        gramatica = m._gramatica(variante)
        if gramatica["kind"] != m._DISCO_TERMINAL:
            achados = m._achados_em_molduras(contexto, gramatica)
        elif pontas is None:
            achados = []
        else:
            achados = m._achados_em_discos(contexto, gramatica, discos, pontas)
        for caixa, caminho in achados:
            chave = (str(variante["id"]), _caixa_arredondada(caixa))
            if chave not in vistos:
                vistos.add(chave)
                casamentos.append(CasamentoGramatica(pacote, variante, caixa, caminho))
    return tuple(casamentos)


def _com_disco(centro: tuple[float, float]) -> tuple[Any, ...]:
    cx, cy = centro
    return (
        linha((cx - 90.0, cy), centro, cor=_CINZA),
        circulo_bezier(centro, 1.4, cor=None, preenchimento=_ROXO),
    )


def _p_disco() -> PaginaGramatica:
    return pagina_gramatica(_com_disco((150.0, 150.0)))


def _p_moldura() -> PaginaGramatica:
    return pagina_gramatica(
        (retangulo_traco((101.0, 115.0, 169.0, 149.0)),),
        (texto("CT", (107.0, 130.0, 125.0, 142.0)),),
    )


def _p_varias_molduras() -> PaginaGramatica:
    caixas = [(10.0 + 70.0 * i, 20.0, 70.0 + 70.0 * i, 60.0) for i in range(3)]
    return pagina_gramatica(
        tuple(retangulo_traco(c) for c in caixas),
        tuple(texto("CT", (c[0] + 5.0, c[1] + 5.0, c[0] + 25.0, c[1] + 15.0)) for c in caixas),
    )


def _p_muitos_textos() -> PaginaGramatica:
    return pagina_gramatica(
        (retangulo_traco((101.0, 115.0, 169.0, 149.0)), *_com_disco((250.0, 250.0))),
        (
            texto("CT", (107.0, 130.0, 125.0, 142.0)),
            *(texto("A", (10.0, 5.0 + 10.0 * i, 20.0, 10.0 + 10.0 * i)) for i in range(40)),
        ),
    )


def _p_vazia() -> PaginaGramatica:
    return pagina_gramatica(())


def _p_so_texto() -> PaginaGramatica:
    return pagina_gramatica((), (texto("CT", (10.0, 10.0, 30.0, 20.0)),))


_PAGINAS: Final = {
    "disco": _p_disco,
    "moldura": _p_moldura,
    "varias_molduras": _p_varias_molduras,
    "muitos_textos": _p_muitos_textos,
    "vazia": _p_vazia,
    "so_texto": _p_so_texto,
}
_CONJUNTOS: Final = {
    "rotulo": (_par("m", _ROTULO),),
    "disco": (_par("d", _DISCO),),
    "ambos": (_par("m", _ROTULO), _par("d", _DISCO)),
    "disco_primeiro_e_repetido": (_par("d", _DISCO), _par("m", _ROTULO), _par("d", _DISCO)),
    "vazio": (),
}


@pytest.mark.parametrize("conjunto", sorted(_CONJUNTOS))
@pytest.mark.parametrize("nome", sorted(_PAGINAS))
def test_nova_implementacao_equivale_a_antiga_em_saida_e_gasto(nome: str, conjunto: str) -> None:
    pagina = _PAGINAS[nome]()
    variantes = _CONJUNTOS[conjunto]

    antigo = contexto_gramaticas(pagina)
    esperado = _casar_antigo(antigo, variantes)

    novo_contexto = contexto_gramaticas(pagina)
    obtido = symbol_matcher._casar_no_contexto(novo_contexto, variantes)

    assert obtido == esperado
    assert casar_variantes(pagina, variantes) == esperado
    assert novo_contexto.orcamento.gasto == antigo.orcamento.gasto
    assert gasto_por_fase(pagina, variantes).total == antigo.orcamento.gasto


@pytest.mark.parametrize("conjunto", sorted(_CONJUNTOS))
@pytest.mark.parametrize("nome", sorted(_PAGINAS))
def test_fases_nao_negativas_e_somam_o_gasto_do_orcamento(nome: str, conjunto: str) -> None:
    pagina = _PAGINAS[nome]()
    variantes = _CONJUNTOS[conjunto]
    contexto = contexto_gramaticas(pagina)
    antes_das_gramaticas = contexto.orcamento.gasto
    symbol_matcher._casar_no_contexto(contexto, variantes)

    gasto = gasto_por_fase(pagina, variantes)

    assert min(gasto.colagem, gasto.indices, gasto.gramaticas) >= 0
    assert gasto.total == gasto.colagem + gasto.indices + gasto.gramaticas
    assert gasto.total == contexto.orcamento.gasto
    assert gasto.colagem + gasto.indices == antes_das_gramaticas
    assert gasto.gramaticas == contexto.orcamento.gasto - antes_das_gramaticas


def test_colagem_e_a_do_contexto_e_nao_passa_dos_indices() -> None:
    contexto = contexto_gramaticas(_p_muitos_textos())

    assert 0 < contexto.gasto_colagem <= contexto.orcamento.gasto


def test_pagina_vazia_nao_gasta_em_nenhuma_fase() -> None:
    gasto = gasto_por_fase(_p_vazia(), _CONJUNTOS["ambos"])

    assert (gasto.colagem, gasto.indices, gasto.gramaticas) == (0, 0, 0)


def test_pagina_sem_texto_tem_colagem_zero() -> None:
    assert gasto_por_fase(pagina_gramatica(_com_disco((150.0, 150.0))), ()).colagem == 0


def test_pagina_sem_moldura_nem_disco_nao_paga_gramaticas() -> None:
    gasto = gasto_por_fase(_p_so_texto(), _CONJUNTOS["ambos"])

    assert gasto.gramaticas == 0
    assert gasto.indices > 0


def test_gasto_por_fase_repetido_devolve_o_mesmo_valor() -> None:
    pagina = _p_muitos_textos()
    variantes = _CONJUNTOS["ambos"]

    primeiro = gasto_por_fase(pagina, variantes)

    assert gasto_por_fase(pagina, variantes) == primeiro
    assert gasto_por_fase(pagina, variantes) == primeiro


def test_gasto_por_fase_nao_altera_gasto_colagem_de_contexto_proprio() -> None:
    pagina = _p_muitos_textos()
    contexto = contexto_gramaticas(pagina)
    antes = contexto.gasto_colagem

    gasto_por_fase(pagina, _CONJUNTOS["ambos"])
    gasto_por_fase(pagina, _CONJUNTOS["ambos"])

    assert contexto.gasto_colagem == antes
    assert contexto_gramaticas(pagina).gasto_colagem == antes


def test_gasto_por_fase_usa_um_contexto_novo_por_chamada(monkeypatch: pytest.MonkeyPatch) -> None:
    contextos: list[ContextoGramatica] = []
    original = symbol_grammars.contexto_gramaticas

    def espiao(pagina: PaginaGramatica, **kwargs: Any) -> ContextoGramatica:
        contexto = original(pagina, **kwargs)
        contextos.append(contexto)
        return contexto

    monkeypatch.setattr(symbol_matcher, "contexto_gramaticas", espiao)
    pagina = _p_muitos_textos()

    gasto_por_fase(pagina, _CONJUNTOS["ambos"])
    gasto_por_fase(pagina, _CONJUNTOS["ambos"])

    assert len(contextos) == 2
    assert contextos[0] is not contextos[1]
    assert contextos[0].orcamento is not contextos[1].orcamento


def test_limite_pequeno_estoura_na_fase_dos_indices() -> None:
    pagina = _p_muitos_textos()
    colagem = contexto_gramaticas(pagina).gasto_colagem

    with pytest.raises(TetoGramaticasExcedido):
        gasto_por_fase(pagina, (), limite=colagem - 1)


def test_limite_que_so_cobre_os_indices_estoura_nas_gramaticas() -> None:
    pagina = _p_muitos_textos()
    gasto = gasto_por_fase(pagina, _CONJUNTOS["ambos"])
    so_indices = gasto.colagem + gasto.indices

    assert gasto.gramaticas > 0
    assert gasto_por_fase(pagina, (), limite=so_indices).total == so_indices
    with pytest.raises(TetoGramaticasExcedido):
        gasto_por_fase(pagina, _CONJUNTOS["ambos"], limite=so_indices)


@pytest.mark.parametrize("limite", [0, 1, 10, 10**12])
@pytest.mark.parametrize("diagnostico", ["modelo.glifos_falhou", "modelo.glifos_limitados"])
def test_diagnosticos_de_glifos_levantam_com_qualquer_limite_e_pagina_cheia(
    diagnostico: str, limite: int
) -> None:
    pagina = pagina_gramatica(_com_disco((150.0, 150.0)), diagnosticos=(diagnostico,))
    esperado = FonteGramaticaFalhou if diagnostico.endswith("falhou") else TetoGramaticasExcedido

    with pytest.raises(esperado):
        gasto_por_fase(pagina, _CONJUNTOS["ambos"], limite=limite)
    with pytest.raises(esperado):
        casar_variantes(pagina, _CONJUNTOS["ambos"], limite=limite)
