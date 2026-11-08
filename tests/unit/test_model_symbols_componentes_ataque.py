# mypy: disable-error-code="no-untyped-call"
"""Ataque às primitivas por componente da observação do modelo (Task 3, R-E06.3.2-3)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Final

import pymupdf
import pytest

from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import carregar_tabela_glifos
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import PaginaGramatica
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import CasamentoGramatica
from zeny_project_handler.adapters.analysis.model_symbols import (
    _observacao,
    perfil_pacotes_modelo,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_para_gramaticas
from zeny_project_handler.domain.symbols import FonteObservacaoSimbolo, ObservacaoSimbolo

_SHA: Final = "b" * 64
_FONTE: Final = FonteObservacaoSimbolo(
    documento_id="ataque", documento_sha256=_SHA, pagina_numero=1, camada="base"
)
_VARIANTE: Final = {
    "id": "v",
    "class_code": "ATERRAMENTO",
    "role": "operational",
    "destination": "network_context",
    "source_ref": {"source_id": "F02", "locator": "autoral"},
    "recognition": {"grammar": {"kind": "stem_bars"}},
}
# Traços inclinados de comprimentos e posições distintos: nenhum é igual a outro por acaso.
_TRECHOS: Final = tuple(
    ((20.0 + 11 * i, 30.0 + 7 * i), (41.0 + 9 * i, 62.0 + 5 * i)) for i in range(8)
)


def _pagina(rotacao: int, *, cropbox: tuple[float, float, float, float] | None, ocg: set[int]):  # type: ignore[no-untyped-def]
    documento = pymupdf.open()
    oc = documento.add_ocg("REDE")
    pagina = documento.new_page(width=400, height=300)
    for i, (a, b) in enumerate(_TRECHOS):
        pagina.draw_line(a, b, color=(0, 0, 0), width=0.5, oc=oc if i in ocg else 0)
    if cropbox is not None:
        pagina.set_cropbox(pymupdf.Rect(cropbox))
    pagina.set_rotation(rotacao)
    return documento, pagina


def _observar(
    pagina: pymupdf.Page, lida: PaginaGramatica, caminho: int, componentes: tuple[int, ...]
) -> ObservacaoSimbolo:
    casamento = CasamentoGramatica(
        {"family_id": "autoral"}, _VARIANTE, (0.0, 0.0, 10.0, 10.0), caminho, componentes
    )
    return _observacao(pagina, _FONTE, _SHA, lida, casamento)


def _caixa(pontos: Any) -> tuple[float, ...]:
    xs, ys = [float(x) for x, _ in pontos], [float(y) for _, y in pontos]
    return (min(xs), min(ys), max(xs), max(ys))


@pytest.mark.parametrize("rotacao", [0, 90, 180, 270])
@pytest.mark.parametrize("cropbox", [None, (30.0, 20.0, 350.0, 260.0)], ids=["sem-crop", "cropbox"])
def test_pontos_originais_de_cada_primitiva_batem_com_o_desenho_cru_do_pymupdf(
    rotacao: int, cropbox: tuple[float, float, float, float] | None
) -> None:
    documento, pagina = _pagina(rotacao, cropbox=cropbox, ocg={4})
    with documento:
        lida = pagina_para_gramaticas(pagina, 0)
        posicoes = (1, 4, 6)
        observacao = _observar(pagina, lida, 1, (4, 6))
        desenhos = pagina.get_drawings(extended=True)  # o espaço cru e o índice do motor legado

        assert [p.indice for p in observacao.primitivas] == [
            str(lida.indices_crus[i]) for i in posicoes
        ]
        for primitiva, posicao in zip(observacao.primitivas, posicoes, strict=True):
            rect = desenhos[lida.indices_crus[posicao]]["rect"]
            esperado = (rect.x0, rect.y0, rect.x1, rect.y1)
            assert _caixa(primitiva.pontos_originais) == pytest.approx(esperado, abs=1e-3)


@pytest.mark.parametrize("rotacao", [0, 90, 180, 270])
def test_camada_de_cada_primitiva_e_a_do_proprio_caminho(rotacao: int) -> None:
    documento, pagina = _pagina(rotacao, cropbox=None, ocg={0, 6})
    with documento:
        lida = pagina_para_gramaticas(pagina, 0)

        observacao = _observar(pagina, lida, 0, (3, 6))

        assert [p.camada for p in observacao.primitivas] == ["REDE", None, "REDE"]


def test_ordem_das_primitivas_e_ancora_primeiro_depois_componentes_como_recebidos() -> None:
    documento, pagina = _pagina(0, cropbox=None, ocg=set())
    with documento:
        lida = pagina_para_gramaticas(pagina, 0)

        observacao = _observar(pagina, lida, 5, (1, 2, 7))

        indices = [p.indice for p in observacao.primitivas]
        assert indices == [str(lida.indices_crus[i]) for i in (5, 1, 2, 7)]
        assert len(set(indices)) == len(indices)


def test_id_da_observacao_e_estavel_e_distingue_o_conjunto_de_componentes() -> None:
    documento, pagina = _pagina(0, cropbox=None, ocg=set())
    with documento:
        lida = pagina_para_gramaticas(pagina, 0)

        primeira = _observar(pagina, lida, 2, (4, 5))
        segunda = _observar(pagina, lida, 2, (4, 5))
        outra = _observar(pagina, lida, 2, (4, 6))

        assert primeira.id == segunda.id
        assert primeira == segunda
        assert outra.primitivas != primeira.primitivas


def test_caixa_de_um_componente_nao_vaza_para_o_outro() -> None:
    """Cada primitiva leva a caixa do próprio caminho, não a do casamento nem a da âncora."""
    documento, pagina = _pagina(0, cropbox=None, ocg=set())
    with documento:
        lida = pagina_para_gramaticas(pagina, 0)

        observacao = _observar(pagina, lida, 0, (7,))

        caixas = [_caixa(p.pontos_originais) for p in observacao.primitivas]
        assert caixas[0] != caixas[1]


def test_assinatura_do_perfil_depende_da_versao_1_4_0() -> None:
    perfil = perfil_pacotes_modelo((), carregar_tabela_glifos())

    assert perfil.versao == "1.5.0"
    assert replace(perfil, versao="1.3.0").assinatura() != perfil.assinatura()
