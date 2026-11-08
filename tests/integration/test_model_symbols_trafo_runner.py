# mypy: disable-error-code="no-untyped-call"
"""E06.3.3.2.2, Task 4: TRANSFORMADOR triangular no runner opt-in, com os pacotes reais.

`test_uma_observacao_por_forma` prova, com os pacotes reais, o agrupamento de formas comuns
(R-E06.3.3.2.2-2): as variantes de um grupo da R-1 casam o mesmo desenho e saem como uma
observação do modelo, com a lista do grupo em `referencias_possiveis`.

`test_fusao_com_o_e05` (R-E06.3.3.2.2-5) desenha o pictograma no estilo que o E05 também lê
(`desenhar_trafo_e05`), afirma primeiro que as duas assinaturas observaram TRANSFORMADOR e só
então fixa o resultado medido da fusão, grupo a grupo, sem disjunção: se a fusão mudar, o teste
falha de propósito.

Resultado medido (R-E06.3.3.2.2-5), na página 300 x 300 da fixture:
- sem X (base e envolvente, nos dois `fill`): FUNDE. As caixas são iguais (centro e tamanho com
  diferença 0, IoU 1,0) e o E05 usa só primitivas que o modelo também usa;
- com X (`half_cyan` e `outline`): NÃO funde, duas ocorrências. A caixa do E05 soma os extremos do
  X e a do modelo não: centro deslocado 0,0058 contra o limite de 0,0040 (10% da escala 0,04),
  tamanho 0,0160 x 0,0214 contra 0,0080, IoU 0,44. Fica aceito até a E09 e vai a "Para a E07".
"""

from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.triangulo import (
    GRUPOS,
    Grupo,
    desenhar_grupo,
    desenhar_trafo_e05,
    variantes_do_grupo,
)
from tests.integration.test_model_symbols_runner import _METODO_NOVO, _fonte, _settings

from zeny_project_handler.application.symbol_reconciliation import (
    SymbolReconciliation,
    _bounds,
    _same_occurrence,
)
from zeny_project_handler.domain.symbols import ObservacaoSimbolo
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

pytestmark = pytest.mark.integration

_CLASSE = "TRANSFORMADOR"


def _id_grupo(grupo: Grupo) -> str:
    fill, enclosure, removal = grupo
    return f"{fill}-{enclosure}-{'x' if removal else 'sem_x'}"


Desenho = Callable[[pymupdf.Page, Grupo], object]


def _rodar(
    tmp_path: Path, desenhar: Desenho, grupo: Grupo
) -> tuple[SymbolReconciliation, str, set[str]]:
    caminho = tmp_path / "trafo.pdf"
    with pymupdf.open() as documento:
        desenhar(documento.new_page(width=300, height=300), grupo)
        documento.save(caminho)
    documento_projeto, fonte = _fonte(caminho)
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    novo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO).assinatura()
    legados = {p.assinatura() for p in runner._profiles if p.metodo_id != _METODO_NOVO}
    return runner.run(documento_projeto, fonte), novo, legados


def _de_trafo(composto: SymbolReconciliation) -> list[ObservacaoSimbolo]:
    return [
        o
        for occ in composto.occurrences
        for o in occ.observations
        if o.alternativas and str(o.alternativas[0].classe) == _CLASSE
    ]


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_uma_observacao_por_forma(tmp_path: Path, grupo: Grupo) -> None:
    composto, novo, _ = _rodar(tmp_path, desenhar_grupo, grupo)

    do_modelo = [o for o in _de_trafo(composto) if o.metodo_assinatura == novo]

    assert len(do_modelo) == 1, do_modelo
    (observacao,) = do_modelo
    atributos = dict(observacao.atributos)
    esperadas = sorted(variantes_do_grupo(grupo))
    assert json.loads(str(atributos["referencias_possiveis"])) == esperadas
    assert atributos["variante_inventario"] == esperadas[0]


# Resultado medido da fusão por grupo (R-E06.3.3.2.2-5): número de ocorrências do runner que
# levam as observações de TRANSFORMADOR das duas assinaturas. Só o X separa.
_OCORRENCIAS_MEDIDAS: dict[Grupo, int] = {
    ("half_cyan", "ellipse", False): 1,
    ("half_cyan", "none", False): 1,
    ("half_cyan", "none", True): 2,
    ("outline", "ellipse", False): 1,
    ("outline", "none", False): 1,
    ("outline", "none", True): 2,
}


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_fusao_com_o_e05(tmp_path: Path, grupo: Grupo) -> None:
    composto, novo, legados = _rodar(tmp_path, desenhar_trafo_e05, grupo)
    de_trafo = _de_trafo(composto)
    do_modelo = [o for o in de_trafo if o.metodo_assinatura == novo]
    do_e05 = [o for o in de_trafo if o.metodo_assinatura in legados]

    # Primeiro: as duas assinaturas observaram TRANSFORMADOR na página.
    assert len(do_modelo) == 1, do_modelo
    assert len(do_e05) == 1, do_e05
    modelo, e05 = do_modelo[0], do_e05[0]

    # Só então o julgamento, fixado pelo resultado medido.
    ocorrencias = [
        occ for occ in composto.occurrences if any(o in de_trafo for o in occ.observations)
    ]
    assert len(ocorrencias) == _OCORRENCIAS_MEDIDAS[grupo]
    assert _same_occurrence(modelo, e05) == (_OCORRENCIAS_MEDIDAS[grupo] == 1)
    assert sorted(len(occ.observations) for occ in ocorrencias) == (
        [1, 1] if _OCORRENCIAS_MEDIDAS[grupo] == 2 else [2]
    )
    a, b = _bounds(modelo), _bounds(e05)
    deslocamento = max(abs(a[0] + a[2] - b[0] - b[2]), abs(a[1] + a[3] - b[1] - b[3])) / 2
    escala = min(max(a[2] - a[0], a[3] - a[1]), max(b[2] - b[0], b[3] - b[1]))
    # A razão medida: com X o centro da caixa do E05 sai do limite; sem X as caixas coincidem.
    assert (deslocamento > escala * Decimal("0.10")) == grupo[2]
    assert (a == b) == (not grupo[2])
