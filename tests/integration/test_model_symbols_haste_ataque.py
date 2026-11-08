# mypy: disable-error-code="no-untyped-call"
"""Ataque à observação com componentes, à fusão com o legado e ao digest (Task 3)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.stem_bars import CASOS_HASTE, desenhar_positivo
from tests.integration.test_model_symbols_runner import (
    _METODO_NOVO,
    _fonte,
    _pacotes_com_haste,
    _pdf_de_haste,
    _settings,
)

from zeny_project_handler.application.symbol_reconciliation import _same_occurrence
from zeny_project_handler.domain.symbols import ObservacaoSimbolo
from zeny_project_handler_server import symbol_execution
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

_SRC = Path(symbol_execution.__file__).parents[1]
_VARIANTES = [variante for variante, _ in CASOS_HASTE]


def _achatar(pontos: Any) -> list[float]:
    """Caixa dos pontos: o modelo grava dois cantos e o legado, quatro."""
    xs, ys = [float(x) for x, _ in pontos], [float(y) for _, y in pontos]
    return [min(xs), min(ys), max(xs), max(ys)]


def _observacoes(
    tmp_path: Path, variante: str, rotacao: int, *, linha_longa: float = 0.0
) -> tuple[tuple[ObservacaoSimbolo, ...], tuple[ObservacaoSimbolo, ...]]:
    """(do modelo, do legado) de uma haste desenhada, antes da reconciliação."""
    _pdf_de_haste(tmp_path / "h.pdf", variante, rotacao, linha_longa)
    documento, fonte = _fonte(tmp_path / "h.pdf")
    runner = SymbolCompositionRunner(
        _settings(tmp_path / "dados"), packages=_pacotes_com_haste(tmp_path / "pacotes")
    )
    composto = runner.run(documento, fonte)
    novo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO).assinatura()
    todas = [obs for ocorrencia in composto.occurrences for obs in ocorrencia.observations]
    return (
        tuple(o for o in todas if o.metodo_assinatura == novo),
        tuple(o for o in todas if o.metodo_assinatura != novo),
    )


@pytest.mark.parametrize("rotacao", [0, 90, 180, 270])
@pytest.mark.parametrize("variante", _VARIANTES)
def test_primitivas_do_modelo_sao_unicas_e_cada_uma_tem_a_forma_do_legado(
    tmp_path: Path, variante: str, rotacao: int
) -> None:
    modelo, legado = _observacoes(tmp_path, variante, rotacao)

    (obs_modelo,) = modelo
    indices = [p.indice for p in obs_modelo.primitivas]
    assert len(indices) == len(set(indices))
    assert len(indices) >= 4
    formas_legado = {(p.indice, p.camada): p.pontos_originais for o in legado for p in o.primitivas}
    for primitiva in obs_modelo.primitivas:
        chave = (primitiva.indice, primitiva.camada)
        if chave in formas_legado:
            assert _achatar(primitiva.pontos_originais) == pytest.approx(
                _achatar(formas_legado[chave]), abs=1e-3
            )


def test_legado_cujo_unico_traco_e_um_componente_funde_com_o_modelo(tmp_path: Path) -> None:
    """Só funde com as primitivas por componente: a âncora do modelo não é o traço do legado."""
    (obs_modelo,), _ = _observacoes(tmp_path, "cemig-eo-r3-s19-v001", 0)
    ancora, *componentes = obs_modelo.primitivas
    assert componentes
    for componente in componentes:
        legado = replace(
            obs_modelo,
            metodo_assinatura="c" * 64,
            primitivas=(componente,),
        )
        assert _same_occurrence(obs_modelo, legado)
        sem_componentes = replace(obs_modelo, primitivas=(ancora,))
        assert not _same_occurrence(sem_componentes, legado)


def test_traco_alheio_nao_funde_com_o_modelo(tmp_path: Path) -> None:
    (obs_modelo,), _ = _observacoes(tmp_path, "cemig-eo-r3-s19-v001", 0)
    alheio = replace(
        obs_modelo,
        metodo_assinatura="c" * 64,
        primitivas=(
            replace(
                obs_modelo.primitivas[0],
                indice="999",
                pontos_originais=((Decimal(1), Decimal(1)), (Decimal(2), Decimal(2))),
            ),
        ),
    )

    assert not _same_occurrence(obs_modelo, alheio)


def test_haste_em_camada_opcional_funde_com_o_legado(tmp_path: Path) -> None:
    class _EmOcg:
        """Página que desenha tudo na camada `REDE`."""

        def __init__(self, pagina: pymupdf.Page, oc: int) -> None:
            self._pagina, self._oc = pagina, oc

        def draw_line(self, *args: Any, **kwargs: Any) -> Any:
            return self._pagina.draw_line(*args, **{**kwargs, "oc": self._oc})

        def draw_oval(self, *args: Any, **kwargs: Any) -> Any:
            return self._pagina.draw_oval(*args, **{**kwargs, "oc": self._oc})

    with pymupdf.open() as documento:
        oc = documento.add_ocg("REDE")
        pagina = documento.new_page(width=300, height=300)
        desenhar_positivo(_EmOcg(pagina, oc), "cemig-eo-r3-s19-v001")  # type: ignore[arg-type]
        documento.save(tmp_path / "o.pdf")
    documento_projeto, fonte = _fonte(tmp_path / "o.pdf")
    runner = SymbolCompositionRunner(
        _settings(tmp_path / "dados"), packages=_pacotes_com_haste(tmp_path / "pacotes")
    )
    novo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO).assinatura()

    composto = runner.run(documento_projeto, fonte)

    com_o_novo = [
        o
        for o in composto.occurrences
        if any(obs.metodo_assinatura == novo for obs in o.observations)
    ]
    assert len(com_o_novo) == 1
    assert len({obs.metodo_assinatura for obs in com_o_novo[0].observations}) >= 2


def test_assinatura_do_runner_muda_com_a_versao_do_metodo(tmp_path: Path) -> None:
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    perfil = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO)

    assert perfil.versao == "1.3.0"
    assert replace(perfil, versao="1.1.0").assinatura() != perfil.assinatura()
