# mypy: disable-error-code="no-untyped-call"
"""Ataque à habilitação de v017 e v019: faixa de vão, cor, desenhos vizinhos, motor, R-E06.3.5-6.

Os pacotes são os reais; as variações (faixa, desligamento) vêm de cópias profundas deles.
`test_legado_*` mede a premissa do teste da R-6 do desenvolvedor: o legado sintético dele tem
exatamente a primitiva âncora e a mesma caixa do modelo; aqui o legado nasce do `get_drawings` do
próprio PDF e, depois, com a forma de um aterramento de verdade (vários desenhos, envelope maior).
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.disc_mark import (
    CENTRO,
    VAO,
    VERDE,
    VERMELHO,
    conteudo_caixa_dupla,
    conteudo_fusivel,
    disco,
)
from tests.fixtures.symbol_grammars.pdf_temporario import salvar_pagina
from tests.integration.test_model_symbols_disc_mark_runner import (
    _desenhar_caminho,
    _legado_de_aterramento,
    _resultado_do_modelo,
)
from tests.integration.test_model_symbols_runner import _METODO_NOVO, _fonte, _settings

from zeny_project_handler.adapters.analysis import declarative_symbols
from zeny_project_handler.adapters.analysis.declarative_symbols import observar_pacotes
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import carregar_tabela_glifos
from zeny_project_handler.adapters.analysis.drawing_model.model import Caminho, Ponto
from zeny_project_handler.adapters.analysis.model_symbols import observar_pacotes_modelo
from zeny_project_handler.adapters.analysis.pymupdf_symbols import _drawing_points
from zeny_project_handler.application.interpretation_pipeline import (
    _assess_symbol_occurrence,
    _symbol_occurrence_proposal,
)
from zeny_project_handler.application.symbol_reconciliation import (
    CalibrationPolicy,
    _same_occurrence,
    reconcile_symbols,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.symbols import (
    ObservacaoSimbolo,
    PrimitivaObservadaSimbolo,
    ResultadoMetodoSimbolos,
)
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

pytestmark = pytest.mark.integration

_FUSIVEL = "cemig-eo-r3-s20-v017"
_CAIXA_DUPLA = "cemig-eo-r3-s20-v019"
_SHA = "d" * 64
_CLASSE = "EQUIPAMENTO_INTERRUPCAO"
_MONTAGENS: dict[str, Callable[..., list[Caminho]]] = {
    _FUSIVEL: conteudo_fusivel,
    _CAIXA_DUPLA: conteudo_caixa_dupla,
}


def _desenhar_disco(
    pagina: pymupdf.Page, variante: str, vao: float, *, centro: Ponto = CENTRO, cor: Any = VERMELHO
) -> None:
    """O disco e, por cima, o conteúdo autoral da variante, tudo na escala de `vao`."""
    _desenhar_caminho(pagina, disco(vao, cor, 0, centro))
    montar = _MONTAGENS[variante]
    caminhos = montar(vao, 1, centro) if variante == _FUSIVEL else montar(vao, 1)
    for caminho in caminhos:
        _desenhar_caminho(pagina, caminho)


def _pelo_modelo(
    pagina: pymupdf.Page, pacotes: tuple[declarative_symbols.Package, ...] | None = None
) -> ResultadoMetodoSimbolos:
    return observar_pacotes_modelo(
        pagina,
        documento_id="d",
        documento_sha256=_SHA,
        pagina_numero=1,
        pacotes=pacotes or declarative_symbols.carregar_pacotes(),
        tabela=carregar_tabela_glifos(),
    )


def _variantes(resultado: ResultadoMetodoSimbolos) -> list[str]:
    return sorted(str(dict(o.atributos)["variante_inventario"]) for o in resultado.observacoes)


def _pagina_com(montar: Callable[[pymupdf.Page], None]) -> ResultadoMetodoSimbolos:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        montar(pagina)
        return _pelo_modelo(pagina)


@pytest.mark.parametrize("variante", [_FUSIVEL, _CAIXA_DUPLA])
@pytest.mark.parametrize("vao", [4.5, 5.0, 7.2, 10.0, 14.9, 15.0], ids=lambda v: f"vao-{v}")
def test_vao_dentro_da_faixa_gera_uma_observacao(variante: str, vao: float) -> None:
    resultado = _pagina_com(lambda p: _desenhar_disco(p, variante, vao))

    assert _variantes(resultado) == [variante]


@pytest.mark.parametrize("variante", [_FUSIVEL, _CAIXA_DUPLA])
@pytest.mark.parametrize("vao", [4.2, 15.5, 20.0, 40.0], ids=lambda v: f"vao-{v}")
def test_vao_fora_da_faixa_nao_sai(variante: str, vao: float) -> None:
    resultado = _pagina_com(lambda p: _desenhar_disco(p, variante, vao))

    assert resultado.observacoes == ()


def _pacotes_com_faixa(minimo: float, maximo: float) -> tuple[declarative_symbols.Package, ...]:
    pacotes = copy.deepcopy(declarative_symbols.carregar_pacotes())
    for pacote in pacotes:
        for variante in pacote["variants"]:
            gramatica = variante["recognition"].get("grammar", {})
            if gramatica.get("kind") == "disc_mark":
                gramatica["min_span"], gramatica["max_span"] = minimo, maximo
    return tuple(pacotes)


@pytest.mark.parametrize("variante", [_FUSIVEL, _CAIXA_DUPLA])
@pytest.mark.parametrize(("minimo", "maximo"), [(16.0, 40.0), (2.0, 10.0)], ids=["acima", "abaixo"])
def test_faixa_da_variante_e_a_que_filtra_nao_um_valor_fixo(
    variante: str, minimo: float, maximo: float
) -> None:
    """O disco de 14,4 sai com a faixa real e some quando a faixa do pacote o exclui."""
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        _desenhar_disco(pagina, variante, VAO)
        com_faixa_real = _pelo_modelo(pagina)
        com_faixa_alterada = _pelo_modelo(pagina, _pacotes_com_faixa(minimo, maximo))

    assert _variantes(com_faixa_real) == [variante]
    assert com_faixa_alterada.observacoes == ()


@pytest.mark.parametrize("variante", [_FUSIVEL, _CAIXA_DUPLA])
def test_disco_verde_com_o_mesmo_conteudo_nao_vira_equipamento_fechado(variante: str) -> None:
    """v018/v020 (abertas, em verde) seguem pendentes: o verde não pode ser lido como v017/v019."""
    resultado = _pagina_com(lambda p: _desenhar_disco(p, variante, VAO, cor=VERDE))

    assert resultado.observacoes == ()


def test_disco_vermelho_sem_conteudo_nao_gera_observacao() -> None:
    resultado = _pagina_com(lambda p: _desenhar_caminho(p, disco(VAO, VERMELHO, 0)))

    assert resultado.observacoes == ()


def test_dois_desenhos_distintos_na_mesma_pagina_geram_uma_observacao_cada() -> None:
    def montar(pagina: pymupdf.Page) -> None:
        _desenhar_disco(pagina, _FUSIVEL, 10.0, centro=(60.0, 60.0))
        _desenhar_disco(pagina, _CAIXA_DUPLA, 10.0)  # a fixture da caixa dupla é sempre em CENTRO
        _desenhar_disco(pagina, _FUSIVEL, 7.2, centro=(60.0, 220.0))

    resultado = _pagina_com(montar)

    assert _variantes(resultado) == [_FUSIVEL, _FUSIVEL, _CAIXA_DUPLA]
    assert len({o.geometria.pontos_normalizados for o in resultado.observacoes}) == 3
    assert {a.classe for o in resultado.observacoes for a in o.alternativas} == {_CLASSE}


@pytest.mark.parametrize("variante", [_FUSIVEL, _CAIXA_DUPLA])
@pytest.mark.parametrize("rotacao", [90, 180, 270])
def test_pagina_girada_mantem_uma_observacao_por_desenho(variante: str, rotacao: int) -> None:
    def montar(pagina: pymupdf.Page) -> None:
        _desenhar_disco(pagina, variante, VAO)
        pagina.set_rotation(rotacao)

    resultado = _pagina_com(montar)

    assert _variantes(resultado) == [variante]


@pytest.mark.parametrize("variante", [_FUSIVEL, _CAIXA_DUPLA])
def test_motor_antigo_nao_executa_o_tipo(variante: str) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        _desenhar_disco(pagina, variante, VAO)
        pelo_motor = observar_pacotes(
            pagina,
            documento_id="d",
            documento_sha256=_SHA,
            pagina_numero=1,
            pacotes=declarative_symbols.carregar_pacotes(),
        )
        pelo_modelo = _pelo_modelo(pagina)

    assert [o for o in pelo_motor.observacoes if o.template in (_FUSIVEL, _CAIXA_DUPLA)] == []
    assert _CLASSE not in {a.classe for o in pelo_motor.observacoes for a in o.alternativas}
    assert _variantes(pelo_modelo) == [variante]


def test_opcao_desligada_nao_muda_a_saida_dos_demais_metodos(tmp_path: Path) -> None:
    """Com v017 e v019 `pending`, só o método do modelo perde a observação do disco."""

    def rodar(
        pasta: Path, pacotes: tuple[declarative_symbols.Package, ...] | None
    ) -> tuple[Any, str]:
        pasta.mkdir()
        caminho = salvar_pagina(pasta, lambda p: _desenhar_disco(p, _FUSIVEL, VAO))
        documento_projeto, fonte = _fonte(caminho)
        runner = SymbolCompositionRunner(_settings(pasta / "dados"), packages=pacotes)
        novo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO).assinatura()
        return runner.run(documento_projeto, fonte), novo

    desligados = copy.deepcopy(declarative_symbols.carregar_pacotes())
    for pacote in desligados:
        for variante in pacote["variants"]:
            if variante["id"] in (_FUSIVEL, _CAIXA_DUPLA):
                variante["recognition"] = {
                    "status": "pending",
                    "reason": "desligada no teste",
                    "negative_examples": variante["recognition"]["negative_examples"],
                }
    ligado, novo_ligado = rodar(tmp_path / "ligado", None)
    desligado, novo_desligado = rodar(tmp_path / "desligado", tuple(desligados))

    def dos_demais(composto: Any, novo: str) -> list[tuple[str, ...]]:
        return sorted(
            (o.metodo_assinatura, str(o.template), str(o.geometria.pontos_normalizados))
            for occ in composto.occurrences
            for o in occ.observations
            if o.metodo_assinatura != novo
        )

    assert dos_demais(ligado, novo_ligado) == dos_demais(desligado, novo_desligado)
    assert len(ligado.occurrences) == 1
    assert desligado.occurrences == ()


def test_segunda_execucao_com_cache_devolve_a_mesma_ocorrencia(tmp_path: Path) -> None:
    caminho = salvar_pagina(tmp_path, lambda p: _desenhar_disco(p, _CAIXA_DUPLA, VAO))
    documento_projeto, fonte = _fonte(caminho)
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))

    primeira = runner.run(documento_projeto, fonte)
    segunda = runner.run(documento_projeto, fonte)

    assert len(primeira.occurrences) == len(segunda.occurrences) == 1
    assert primeira.occurrences[0].id == segunda.occurrences[0].id


# --- R-E06.3.5-6: o legado sintético do desenvolvedor representa o legado real? ---------------


def _legado_do_get_drawings(
    caminho_pdf: Path, modelo: ResultadoMetodoSimbolos, observacao: ObservacaoSimbolo
) -> ResultadoMetodoSimbolos:
    """Legado com a primitiva e a caixa que o motor/legado montam a partir do `get_drawings`."""
    sintetico = _legado_de_aterramento(modelo, observacao)
    base = sintetico.observacoes[0]
    with pymupdf.open(caminho_pdf) as documento:
        pagina = documento[0]
        desenhos = pagina.get_drawings()
        indice = int(observacao.primitivas[0].indice)
        desenho = desenhos[indice]
        geometria = declarative_symbols._geometry(pagina, pymupdf.Rect(desenho["rect"]))
        pontos = _drawing_points(tuple(desenho["items"]))
    primitiva = PrimitivaObservadaSimbolo(
        indice=str(indice),
        camada=None,
        pontos_originais=tuple((Decimal(str(x)), Decimal(str(y))) for x, y in pontos),
    )
    lida = replace(base, geometria=geometria, primitivas=(primitiva,))
    return replace(sintetico, observacoes=(lida,))


def test_legado_montado_do_get_drawings_tambem_funde_com_o_disco_do_modelo(tmp_path: Path) -> None:
    caminho = salvar_pagina(tmp_path, lambda p: _desenhar_disco(p, _FUSIVEL, VAO))
    documento_projeto, fonte = _fonte(caminho)
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    runner.run(documento_projeto, fonte)
    agregados = runner._read_cache(documento_projeto)
    assert agregados is not None
    (modelo,) = [r for r in agregados if r.perfil.metodo_id == _METODO_NOVO]
    (observacao,) = modelo.observacoes

    legado = _legado_do_get_drawings(caminho, modelo, observacao)

    assert _same_occurrence(observacao, legado.observacoes[0]) is True
    (ocorrencia,) = reconcile_symbols((modelo, legado), CalibrationPolicy()).occurrences
    assert len(ocorrencia.observations) == 2
    assert ocorrencia.reasons == ("ambiguous_class_or_id",)


@pytest.mark.parametrize("fator_do_envelope", [1, 3], ids=["envelope-igual", "envelope-3x"])
@pytest.mark.parametrize("desenhos_a_mais", [0, 1, 4], ids=lambda n: f"{n}-desenhos-a-mais")
def test_o_envelope_do_legado_decide_a_fusao_nunca_as_primitivas(
    tmp_path: Path, desenhos_a_mais: int, fator_do_envelope: int
) -> None:
    """Contraste da R-6: o formato do legado decide o desfecho; só a folha 006 real o confirma.

    O corte de primitivas de `_same_occurrence` usa `min(tamanhos)` e o modelo tem 1 primitiva,
    então primitivas a mais no legado nunca impedem a fusão. Quem decide é o envelope: com a caixa
    do disco funde, com envelope 3x maior (diferença de largura e altura acima de 20% da escala e
    IoU baixo) não funde, para qualquer número de primitivas.
    """
    modelo = _resultado_do_modelo(tmp_path)
    (observacao,) = modelo.observacoes
    legado = _legado_de_aterramento(modelo, observacao)
    base = legado.observacoes[0]
    ancora = base.primitivas[0]
    extras = tuple(
        PrimitivaObservadaSimbolo(
            indice=str(900 + n), camada=None, pontos_originais=ancora.pontos_originais
        )
        for n in range(desenhos_a_mais)
    )
    normalizados = base.geometria.pontos_normalizados
    xs = [p.x for p in normalizados]
    ys = [p.y for p in normalizados]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    ampliado = tuple(
        type(p)(cx + (p.x - cx) * fator_do_envelope, cy + (p.y - cy) * fator_do_envelope)
        for p in normalizados
    )
    envelope = replace(base.geometria, pontos_normalizados=ampliado)
    real = replace(base, geometria=envelope, primitivas=(ancora, *extras))

    funde = fator_do_envelope == 1
    assert _same_occurrence(observacao, real) is funde
    ocorrencias = reconcile_symbols(
        (modelo, replace(legado, observacoes=(real,))), CalibrationPolicy()
    )
    assert len(ocorrencias.occurrences) == (1 if funde else 2)


# --- R-E06.3.5-6 pelo pipeline real -------------------------------------------------------------


def _proposta(catalogo: CatalogoTecnico, resultados: tuple[ResultadoMetodoSimbolos, ...]) -> Any:
    simbolos = reconcile_symbols(resultados, CalibrationPolicy())
    (ocorrencia,) = simbolos.occurrences
    pagina = uuid5(NAMESPACE_URL, "fixture:disc-mark:pagina")
    execucao = uuid5(NAMESPACE_URL, "fixture:disc-mark:execucao")
    avaliacao = _assess_symbol_occurrence(ocorrencia, "base", pagina, catalogo, ())
    ids = [uuid5(execucao, f"simbolo:{o.id}") for o in ocorrencia.observations]
    proposta = _symbol_occurrence_proposal(simbolos, ocorrencia, execucao, ids, avaliacao)
    return avaliacao, proposta


def test_pipeline_ocorrencia_fundida_de_duas_classes_fica_sem_classe_e_pendente(
    tmp_path: Path, catalogo_inicial: CatalogoTecnico
) -> None:
    modelo = _resultado_do_modelo(tmp_path)
    (observacao,) = modelo.observacoes
    legado = _legado_de_aterramento(modelo, observacao)

    avaliacao, proposta = _proposta(catalogo_inicial, (modelo, legado))

    assert avaliacao.decision == "review"
    assert avaliacao.symbol_class is None
    assert avaliacao.class_resolved is False
    assert avaliacao.pending is True
    assert proposta.codigo_observado is None
    assert proposta.estado_revisao.value != "proposta"
    razoes = dict(proposta.atributos_sugeridos)
    assert "classe_pendente" in str(razoes)


def test_pipeline_ocorrencia_so_do_modelo_fixa_a_classe_de_interrupcao(
    tmp_path: Path, catalogo_inicial: CatalogoTecnico
) -> None:
    """Controle: sem o legado, a mesma ocorrência sai com a classe e como candidata a ativo."""
    modelo = _resultado_do_modelo(tmp_path)

    avaliacao, proposta = _proposta(catalogo_inicial, (modelo,))

    assert avaliacao.symbol_class == _CLASSE
    assert avaliacao.class_resolved is True
    assert avaliacao.asset_candidate is True
    assert proposta.codigo_observado == _CLASSE
