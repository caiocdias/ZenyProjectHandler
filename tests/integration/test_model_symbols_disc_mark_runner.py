# mypy: disable-error-code="no-untyped-call"
"""E06.3.5, Task 4: `disc_mark` (v017 e v019 de f02-20) no runner opt-in, com os pacotes reais.

`test_uma_observacao_por_desenho` prova que cada desenho sai como uma única observação do
modelo, da variante esperada, sem uma segunda observação para a curva dentro do disco.

`test_variantes_desligadas_nao_geram_observacao_do_metodo` prova a opção desligada: com v017 e
v019 `pending`, o método não emite nenhuma observação para o mesmo desenho.

`test_disco_do_legado_de_outra_classe_*` (R-E06.3.5-6): `_same_occurrence` não olha classe. Sobre
o disco de 7,2 pt da folha 006 o legado lê ATERRAMENTO; o teste monta essa observação com a
primitiva que o legado emitiria (o círculo do disco, o mesmo índice e a mesma forma que o modelo
usa como âncora) e fixa o desfecho observado de `reconcile_symbols`, sem disjunção.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.disc_mark import (
    VAO,
    VERMELHO,
    conteudo_caixa_dupla,
    conteudo_fusivel,
    disco,
)
from tests.fixtures.symbol_grammars.pdf_temporario import salvar_pagina
from tests.integration.test_model_symbols_runner import _METODO_NOVO, _fonte, _settings

from zeny_project_handler.adapters.analysis import declarative_symbols
from zeny_project_handler.adapters.analysis.drawing_model.model import Caminho
from zeny_project_handler.application.symbol_reconciliation import (
    CalibrationPolicy,
    SymbolReconciliation,
    _same_occurrence,
    reconcile_symbols,
)
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos
from zeny_project_handler.domain.symbols import (
    AlternativaClasseSimbolo,
    CoberturaMetodoSimbolos,
    ObservacaoSimbolo,
    ResultadoMetodoSimbolos,
)
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

pytestmark = pytest.mark.integration

_CLASSE = "EQUIPAMENTO_INTERRUPCAO"
_FUSIVEL = "cemig-eo-r3-s20-v017"
_CAIXA_DUPLA = "cemig-eo-r3-s20-v019"
_DESENHOS: dict[str, tuple[Callable[[float, int], list[Caminho]], str]] = {
    "fuse_curve": (conteudo_fusivel, _FUSIVEL),
    "double_box": (conteudo_caixa_dupla, _CAIXA_DUPLA),
}


def _desenhar_caminho(pagina: pymupdf.Page, caminho: Caminho) -> None:
    forma = pagina.new_shape()
    for subcaminho in caminho.subcaminhos:
        for item in subcaminho:
            if item.tipo == "l":
                forma.draw_line(*item.pontos)
            else:
                forma.draw_bezier(*item.pontos)
    forma.finish(
        color=caminho.estilo.cor,
        fill=caminho.estilo.preenchimento,
        width=caminho.estilo.espessura,
        closePath=False,
    )
    forma.commit()


def _desenhar(pagina: pymupdf.Page, conteudo: str) -> None:
    """O disco vermelho e, por cima dele, o conteúdo autoral da fixture."""
    montar, _ = _DESENHOS[conteudo]
    _desenhar_caminho(pagina, disco(VAO, VERMELHO, 0))
    for caminho in montar(VAO, 1):
        _desenhar_caminho(pagina, caminho)


def _rodar(
    tmp_path: Path, conteudo: str, pacotes: tuple[declarative_symbols.Package, ...] | None = None
) -> tuple[SymbolReconciliation, str]:
    caminho = salvar_pagina(tmp_path, lambda pagina: _desenhar(pagina, conteudo))
    documento_projeto, fonte = _fonte(caminho)
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"), packages=pacotes)
    novo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO).assinatura()
    return runner.run(documento_projeto, fonte), novo


def _do_modelo(composto: SymbolReconciliation, novo: str) -> list[ObservacaoSimbolo]:
    return [
        o for occ in composto.occurrences for o in occ.observations if o.metodo_assinatura == novo
    ]


@pytest.mark.parametrize("conteudo", list(_DESENHOS))
def test_uma_observacao_por_desenho(tmp_path: Path, conteudo: str) -> None:
    composto, novo = _rodar(tmp_path, conteudo)

    do_modelo = _do_modelo(composto, novo)

    assert len(do_modelo) == 1, do_modelo
    (observacao,) = do_modelo
    assert str(observacao.alternativas[0].classe) == _CLASSE
    assert dict(observacao.atributos)["variante_inventario"] == _DESENHOS[conteudo][1]


@pytest.mark.parametrize("conteudo", list(_DESENHOS))
def test_variantes_desligadas_nao_geram_observacao_do_metodo(tmp_path: Path, conteudo: str) -> None:
    pacotes = copy.deepcopy(declarative_symbols.carregar_pacotes())
    for pacote in pacotes:
        for variante in pacote.get("variants", []):
            if variante["id"] in (_FUSIVEL, _CAIXA_DUPLA):
                variante["recognition"] = {
                    "status": "pending",
                    "reason": "desligada no teste",
                    "negative_examples": variante["recognition"]["negative_examples"],
                }

    composto, novo = _rodar(tmp_path, conteudo, tuple(pacotes))

    assert _do_modelo(composto, novo) == []


def _legado_de_aterramento(
    modelo: ResultadoMetodoSimbolos, observacao: ObservacaoSimbolo
) -> ResultadoMetodoSimbolos:
    """O legado lendo o disco como ATERRAMENTO: a primitiva âncora do modelo, outra classe."""
    perfil = replace(
        modelo.perfil, metodo_id="legado-aterramento-no-teste", classes_suportadas=("ATERRAMENTO",)
    )
    ancora = observacao.primitivas[0]
    lida = replace(
        observacao,
        metodo_assinatura=perfil.assinatura(),
        alternativas=(AlternativaClasseSimbolo(classe="ATERRAMENTO"),),
        primitivas=(ancora,),
        atributos=(),
    )
    cobertura = CoberturaMetodoSimbolos(
        fonte=observacao.fonte,
        regiao_normalizada=modelo.coberturas[0].regiao_normalizada,
        classes_avaliadas=("ATERRAMENTO",),
        estado=EstadoMetodoSimbolos.CONCLUIDO,
    )
    return ResultadoMetodoSimbolos(perfil=perfil, coberturas=(cobertura,), observacoes=(lida,))


def _resultado_do_modelo(tmp_path: Path) -> ResultadoMetodoSimbolos:
    caminho = salvar_pagina(tmp_path, lambda pagina: _desenhar(pagina, "fuse_curve"))
    documento_projeto, fonte = _fonte(caminho)
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    runner.run(documento_projeto, fonte)
    agregados = runner._read_cache(documento_projeto)
    assert agregados is not None
    (modelo,) = [r for r in agregados if r.perfil.metodo_id == _METODO_NOVO]
    return modelo


def test_disco_do_legado_de_outra_classe_funde_com_o_do_modelo(tmp_path: Path) -> None:
    """Desfecho observado (R-E06.3.5-6): FUNDE, em uma ocorrência de duas observações.

    `_same_occurrence` não olha a classe: o disco do legado (ATERRAMENTO) e o do modelo
    (EQUIPAMENTO_INTERRUPCAO) têm a mesma primitiva e a mesma caixa. A ocorrência fundida vai a
    `review` com `ambiguous_class_or_id`. Vai ao "Para a E07.2.2".
    """
    modelo = _resultado_do_modelo(tmp_path)
    (observacao,) = modelo.observacoes
    legado = _legado_de_aterramento(modelo, observacao)

    # Primeiro: as duas assinaturas observaram o mesmo disco.
    assert _same_occurrence(observacao, legado.observacoes[0]) is True

    (ocorrencia,) = reconcile_symbols((modelo, legado), CalibrationPolicy()).occurrences

    assert sorted(o.metodo_assinatura for o in ocorrencia.observations) == sorted(
        [modelo.perfil.assinatura(), legado.perfil.assinatura()]
    )
    assert sorted(str(a.classe) for a in ocorrencia.alternatives) == [
        "ATERRAMENTO",
        _CLASSE,
    ]
    assert ocorrencia.decision == "review"
    assert ocorrencia.reasons == ("ambiguous_class_or_id",)


def test_ocorrencia_fundida_de_duas_classes_nao_tem_classe_no_pipeline(tmp_path: Path) -> None:
    """Efeito à parte no pipeline: `_assess_symbol_occurrence` só fixa `symbol_class` quando a
    ocorrência tem uma única classe (`interpretation_pipeline.py:601-602`); com duas fica `None`.
    """
    modelo = _resultado_do_modelo(tmp_path)
    (observacao,) = modelo.observacoes
    legado = _legado_de_aterramento(modelo, observacao)
    (ocorrencia,) = reconcile_symbols((modelo, legado), CalibrationPolicy()).occurrences

    classes = {alternativa.classe for alternativa in ocorrencia.alternatives}

    assert len(classes) == 2
    assert (next(iter(classes)) if len(classes) == 1 else None) is None
