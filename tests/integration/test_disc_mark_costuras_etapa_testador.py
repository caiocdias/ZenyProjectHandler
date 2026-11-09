# mypy: disable-error-code="no-untyped-call"
"""Costuras da E06.3.5 (disc_mark) com os pacotes reais, testador de etapa.

- página real de ponta a ponta com v017 e v019 e as demais classes juntas (ESTAI, ATERRAMENTO,
  PARA_RAIOS_BT, PONTO_CONEXAO) perto do disco: cada classe lê na página composta o mesmo que lê
  sozinha;
- `disc_mark` e `terminal_disc` no mesmo disco / no mesmo lugar;
- ordem de pintura em PDF real (conteúdo antes do disco, capa opaca depois);
- a assinatura do runner muda com o módulo `grammar_disc_mark` e com a habilitação de v017/v019;
- orçamento com os pacotes reais (54 variantes habilitadas): o gasto de `disc_mark` não depende
  das outras 52, e uma página hostil termina dentro do teto;
- `max_span` do pacote contra o `vao_maximo=72` do código e contra o teto do schema.
"""

from __future__ import annotations

import copy
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from tests.fixtures.symbol_grammars import rect_diagonal as bt
from tests.fixtures.symbol_grammars import stem_bars as haste
from tests.fixtures.symbol_grammars.disc_mark import (
    CENTRO,
    VAO,
    VERMELHO,
    conteudo_caixa_dupla,
    conteudo_fusivel,
    disco,
)
from tests.fixtures.symbol_grammars.estai import estai_com_circulo
from tests.fixtures.symbol_grammars.paginas import circulo_bezier
from tests.fixtures.symbol_grammars.pdf_temporario import salvar_pagina
from tests.integration.test_model_symbols_disc_mark_runner import _desenhar_caminho
from tests.integration.test_model_symbols_runner import _METODO_NOVO, _fonte, _settings

from zeny_project_handler.adapters.analysis import declarative_symbols
from zeny_project_handler.adapters.analysis.declarative_symbols import _enabled
from zeny_project_handler.adapters.analysis.drawing_model import grammar_disc_mark
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import carregar_tabela_glifos
from zeny_project_handler.adapters.analysis.drawing_model.model import Caminho, Ponto
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    LIMITE_CONSULTAS_PAGINA,
    TetoGramaticasExcedido,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import gasto_por_fase
from zeny_project_handler.adapters.analysis.model_symbols import observar_pacotes_modelo
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_para_gramaticas
from zeny_project_handler.application.symbol_reconciliation import SymbolReconciliation
from zeny_project_handler.domain.symbols import ObservacaoSimbolo
from zeny_project_handler_server import symbol_execution
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

pytestmark = pytest.mark.integration

_RAIZ = Path(__file__).resolve().parents[2]
_FUSIVEL = "cemig-eo-r3-s20-v017"
_CAIXA_DUPLA = "cemig-eo-r3-s20-v019"
_INTERRUPCAO = "EQUIPAMENTO_INTERRUPCAO"
_ROXO = (0.5, 0.0, 0.5)
_HASTE_ID = "cemig-eo-r3-s19-v001"
_BT_ID = "cemig-eo-r3-s21-v001"
Desenho = Callable[[pymupdf.Page], object]


def _rodar(tmp_path: Path, desenhar: Desenho) -> tuple[SymbolReconciliation, str, dict[str, str]]:
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


def _do_modelo(composto: SymbolReconciliation, novo: str) -> list[ObservacaoSimbolo]:
    return [o for o in _observacoes(composto) if o.metodo_assinatura == novo]


def _leitura(observacao: ObservacaoSimbolo) -> tuple[object, ...]:
    primitivas = sorted(
        tuple((round(float(x), 2), round(float(y), 2)) for x, y in p.pontos_originais)
        for p in observacao.primitivas
    )
    return (
        tuple((str(a.classe), a.subtipo) for a in observacao.alternativas),
        tuple(sorted((chave, str(valor)) for chave, valor in observacao.atributos)),
        tuple(primitivas),
    )


def _desenhar_todos(pagina: pymupdf.Page, caminhos: list[Caminho]) -> None:
    for caminho in caminhos:
        _desenhar_caminho(pagina, caminho)


def _fusivel(pagina: pymupdf.Page, centro: Ponto, vao: float = VAO) -> None:
    _desenhar_caminho(pagina, disco(vao, VERMELHO, 0, centro))
    _desenhar_todos(pagina, conteudo_fusivel(vao, 1, centro))


def _caixa_dupla(pagina: pymupdf.Page, vao: float = VAO) -> None:
    """Sempre em `CENTRO`: a fixture da caixa dupla não recebe centro."""
    _desenhar_caminho(pagina, disco(vao, VERMELHO, 0))
    _desenhar_todos(pagina, conteudo_caixa_dupla(vao, 1))


def _ponto_de_conexao(pagina: pymupdf.Page, centro: Ponto, de: Ponto) -> None:
    """Disco roxo de 3 pt com uma linha vinda de `de` que termina no centro dele."""
    pagina.draw_line(de, centro, color=(0, 0, 0), width=0.3)
    _desenhar_caminho(pagina, circulo_bezier(centro, 1.5, 0, cor=_ROXO, preenchimento=_ROXO))


# --- a página composta: cada classe lê na página o mesmo que lê sozinha ---------------------------

# Deslocamentos do vizinho em relação ao disco da caixa dupla (CENTRO): colado, perto, longe.
_AFASTAMENTOS = (22.0, 35.0, 60.0)


def _partes(afastamento: float) -> dict[str, Desenho]:
    x, y = CENTRO
    return {
        "caixa_dupla": lambda p: _caixa_dupla(p),
        "fusivel": lambda p: _fusivel(p, (x + afastamento, y - 70.0)),
        "estai": lambda p: _desenhar_todos(
            p, estai_com_circulo(180.0, base=(x - afastamento - 14.0, y + afastamento))
        ),
        "haste": lambda p: haste.desenhar_positivo(p, _HASTE_ID, (x, y + afastamento + 22.0)),
        "bt": lambda p: bt.desenhar_positivo(p, _BT_ID, (x + afastamento + 30.0, y + 30.0)),
        "conexao": lambda p: _ponto_de_conexao(
            p, (x - 20.0, y - afastamento - 30.0), (x - 20.0, y - afastamento - 60.0)
        ),
    }


def _todas(partes: dict[str, Desenho]) -> Desenho:
    def desenhar(pagina: pymupdf.Page) -> None:
        for parte in partes.values():
            parte(pagina)

    return desenhar


@pytest.mark.parametrize("afastamento", _AFASTAMENTOS, ids=lambda a: f"afastamento-{a}")
def test_classes_vizinhas_do_disco_leem_na_pagina_composta_o_que_leem_sozinhas(
    tmp_path: Path, afastamento: float
) -> None:
    partes = _partes(afastamento)
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

    do_modelo = Counter(str(_classe(o)) for o in juntas if o.metodo_assinatura == novo)
    assert do_modelo[_INTERRUPCAO] == 2, do_modelo
    for classe in ("ESTAI", "ATERRAMENTO", "PARA_RAIOS_BT", "PONTO_CONEXAO"):
        assert do_modelo[classe] == 1, (classe, do_modelo)
    assert leituras_juntas == sorted(leituras_sozinhas)
    assert contagem_junta == contagem_sozinha


def test_v017_e_v019_na_pagina_composta_saem_com_a_variante_de_cada_um(tmp_path: Path) -> None:
    composto, novo, _ = _rodar(tmp_path, _todas(_partes(35.0)))

    variantes = sorted(
        str(dict(o.atributos)["variante_inventario"])
        for o in _do_modelo(composto, novo)
        if _classe(o) == _INTERRUPCAO
    )

    assert variantes == [_FUSIVEL, _CAIXA_DUPLA]


# --- disc_mark e terminal_disc no mesmo disco -----------------------------------------------------


def test_disco_roxo_concentrico_ao_fusivel_gera_uma_observacao_de_cada_classe(
    tmp_path: Path,
) -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        _fusivel(pagina, CENTRO)
        _ponto_de_conexao(pagina, CENTRO, (CENTRO[0], CENTRO[1] - 60.0))

    composto, novo, _ = _rodar(tmp_path, desenhar)

    classes = sorted(str(_classe(o)) for o in _do_modelo(composto, novo))
    assert classes == [_INTERRUPCAO, "PONTO_CONEXAO"]


def test_linha_terminal_no_centro_do_disco_vermelho_nao_vira_ponto_de_conexao(
    tmp_path: Path,
) -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        pagina.draw_line((CENTRO[0], CENTRO[1] - 60.0), CENTRO, color=(0, 0, 0), width=0.3)
        _fusivel(pagina, CENTRO)

    composto, novo, _ = _rodar(tmp_path, desenhar)

    assert [str(_classe(o)) for o in _do_modelo(composto, novo)] == [_INTERRUPCAO]


def test_disco_roxo_de_14_pt_com_o_conteudo_do_fusivel_nao_gera_nada(tmp_path: Path) -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        _desenhar_caminho(
            pagina, circulo_bezier(CENTRO, VAO / 2, 0, cor=_ROXO, preenchimento=_ROXO)
        )
        _desenhar_todos(pagina, conteudo_fusivel(VAO, 1))
        pagina.draw_line((CENTRO[0], CENTRO[1] - 60.0), CENTRO, color=(0, 0, 0), width=0.3)

    composto, novo, _ = _rodar(tmp_path, desenhar)

    assert _do_modelo(composto, novo) == []


def test_disco_vermelho_de_3_pt_com_linha_terminal_nao_vira_nenhuma_das_duas(
    tmp_path: Path,
) -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        pagina.draw_line((CENTRO[0], CENTRO[1] - 60.0), CENTRO, color=(0, 0, 0), width=0.3)
        _desenhar_caminho(
            pagina, circulo_bezier(CENTRO, 1.5, 0, cor=VERMELHO, preenchimento=VERMELHO)
        )

    composto, novo, _ = _rodar(tmp_path, desenhar)

    assert _do_modelo(composto, novo) == []


# --- ordem de pintura em PDF real -----------------------------------------------------------------


def test_conteudo_pintado_antes_do_disco_no_pdf_real_nao_gera_observacao(tmp_path: Path) -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        _desenhar_todos(pagina, conteudo_fusivel(VAO, 0))
        _desenhar_caminho(pagina, disco(VAO, VERMELHO, 9))

    composto, novo, _ = _rodar(tmp_path, desenhar)

    assert _do_modelo(composto, novo) == []


def test_capa_branca_opaca_pintada_depois_esconde_o_disco_no_pdf_real(tmp_path: Path) -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        _fusivel(pagina, CENTRO)
        pagina.draw_rect(
            pymupdf.Rect(CENTRO[0] - 20, CENTRO[1] - 20, CENTRO[0] + 20, CENTRO[1] + 20),
            color=None,
            fill=(1, 1, 1),
        )

    composto, novo, _ = _rodar(tmp_path, desenhar)

    assert _do_modelo(composto, novo) == []


def test_capa_pintada_antes_do_disco_nao_o_esconde_no_pdf_real(tmp_path: Path) -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        pagina.draw_rect(
            pymupdf.Rect(CENTRO[0] - 20, CENTRO[1] - 20, CENTRO[0] + 20, CENTRO[1] + 20),
            color=None,
            fill=(1, 1, 1),
        )
        _fusivel(pagina, CENTRO)

    composto, novo, _ = _rodar(tmp_path, desenhar)

    assert [str(_classe(o)) for o in _do_modelo(composto, novo)] == [_INTERRUPCAO]


# --- assinatura do runner -------------------------------------------------------------------------


def test_assinatura_do_runner_muda_com_o_digest_de_grammar_disc_mark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuracao = _settings(tmp_path / "dados")
    original = SymbolCompositionRunner(configuracao).signature
    digest_original = symbol_execution._module_digest
    visto: list[str] = []

    def digest(alvo: Any) -> str:
        if alvo is grammar_disc_mark:
            visto.append(alvo.__name__)
            return "alterado"
        return str(digest_original(alvo))

    monkeypatch.setattr(symbol_execution, "_module_digest", digest)

    assert SymbolCompositionRunner(configuracao).signature != original
    assert visto == [grammar_disc_mark.__name__]


def test_assinatura_do_runner_muda_ao_desligar_v017_e_v019(tmp_path: Path) -> None:
    configuracao = _settings(tmp_path / "dados")
    pacotes = copy.deepcopy(declarative_symbols.carregar_pacotes())
    for pacote in pacotes:
        for variante in pacote.get("variants", []):
            if variante["id"] in (_FUSIVEL, _CAIXA_DUPLA):
                variante["recognition"] = {
                    "status": "pending",
                    "reason": "desligada",
                    "negative_examples": variante["recognition"]["negative_examples"],
                }

    ligado = SymbolCompositionRunner(configuracao).signature
    desligado = SymbolCompositionRunner(configuracao, packages=tuple(pacotes)).signature

    assert ligado != desligado


def test_opcao_desligada_deixa_a_pagina_composta_so_sem_o_disco(tmp_path: Path) -> None:
    pacotes = copy.deepcopy(declarative_symbols.carregar_pacotes())
    for pacote in pacotes:
        for variante in pacote.get("variants", []):
            if variante["id"] in (_FUSIVEL, _CAIXA_DUPLA):
                variante["recognition"] = {
                    "status": "pending",
                    "reason": "desligada",
                    "negative_examples": variante["recognition"]["negative_examples"],
                }
    desenhar = _todas(_partes(35.0))

    ligado, novo_ligado, metodos_ligado = _rodar(tmp_path / "ligado", desenhar)
    (tmp_path / "desligado").mkdir()
    documento, fonte = _fonte(salvar_pagina(tmp_path / "desligado", desenhar))
    runner = SymbolCompositionRunner(
        _settings(tmp_path / "desligado" / "dados"), packages=tuple(pacotes)
    )
    novo_desligado = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO).assinatura()
    desligado = runner.run(documento, fonte)

    esperado = sorted(
        _leitura(o) for o in _do_modelo(ligado, novo_ligado) if _classe(o) != _INTERRUPCAO
    )
    obtido = sorted(_leitura(o) for o in _do_modelo(desligado, novo_desligado))
    assert esperado == obtido
    assert not any(_classe(o) == _INTERRUPCAO for o in _observacoes(desligado))
    assert metodos_ligado[novo_ligado] == _METODO_NOVO


# --- orçamento com os pacotes reais (54 variantes habilitadas) ------------------------------------


def _pagina_com_discos(quantidade: int) -> Any:
    colunas = 40
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=900, height=900)
        for i in range(quantidade):
            centro = (20.0 + (i % colunas) * 20.0, 20.0 + (i // colunas) * 20.0)
            _desenhar_caminho(pagina, disco(10.0, VERMELHO, 0, centro))
            _desenhar_todos(pagina, conteudo_fusivel(10.0, 1, centro))
        return pagina_para_gramaticas(pagina, 0, carregar_tabela_glifos())


def _pares_reais() -> list[tuple[Any, Any]]:
    return list(_enabled(declarative_symbols.carregar_pacotes()))


def test_ha_54_variantes_habilitadas_e_duas_sao_disc_mark() -> None:
    pares = _pares_reais()

    assert len(pares) == 54
    de_disc_mark = [v["id"] for _, v in pares if v["recognition"]["grammar"]["kind"] == "disc_mark"]
    assert sorted(de_disc_mark) == [_FUSIVEL, _CAIXA_DUPLA]


def test_gasto_de_disc_mark_nao_depende_das_outras_52_variantes() -> None:
    pagina = _pagina_com_discos(60)
    pares = _pares_reais()
    so_disc_mark = [(p, v) for p, v in pares if v["recognition"]["grammar"]["kind"] == "disc_mark"]
    sem_disc_mark = [(p, v) for p, v in pares if v["recognition"]["grammar"]["kind"] != "disc_mark"]

    todas = gasto_por_fase(pagina, pares)
    so_dois = gasto_por_fase(pagina, so_disc_mark)
    resto = gasto_por_fase(pagina, sem_disc_mark)
    vazio = gasto_por_fase(pagina, [])

    assert so_dois.gramaticas > 0
    # O que os índices custam não muda; as gramáticas somam, sem cobrança em dobro do disco.
    assert todas.gramaticas == so_dois.gramaticas + resto.gramaticas
    assert todas.indices == vazio.indices


def test_classificacao_do_disco_e_paga_uma_vez_com_as_duas_variantes_ou_com_uma() -> None:
    pagina = _pagina_com_discos(60)
    pares = _pares_reais()
    ambas = [(p, v) for p, v in pares if v["recognition"]["grammar"]["kind"] == "disc_mark"]

    com_duas = gasto_por_fase(pagina, ambas).gramaticas
    com_uma = gasto_por_fase(pagina, ambas[:1]).gramaticas

    assert com_uma > 0
    assert com_duas == com_uma


def test_pagina_com_muitos_discos_e_os_54_pacotes_termina_dentro_do_teto() -> None:
    pagina = _pagina_com_discos(400)

    gasto = gasto_por_fase(pagina, _pares_reais())

    assert gasto.gramaticas > 0
    assert gasto.colagem + gasto.indices + gasto.gramaticas < LIMITE_CONSULTAS_PAGINA


def test_teto_baixo_levanta_com_os_54_pacotes_e_nao_devolve_resultado_parcial() -> None:
    pagina = _pagina_com_discos(60)

    with pytest.raises(TetoGramaticasExcedido):
        gasto_por_fase(pagina, _pares_reais(), limite=500)


def test_runner_le_os_400_discos_da_pagina_hostil_sem_estourar(tmp_path: Path) -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        for i in range(120):
            centro = (20.0 + (i % 12) * 22.0, 20.0 + (i // 12) * 22.0)
            _fusivel(pagina, centro, 10.0)

    composto, novo, _ = _rodar(tmp_path, desenhar)

    classes = Counter(str(_classe(o)) for o in _do_modelo(composto, novo))
    assert classes[_INTERRUPCAO] == 120, classes


# --- max_span do pacote contra o vao_maximo=72 do código ------------------------------------------


def test_max_span_dos_pacotes_cabe_no_teto_de_candidatos_do_codigo() -> None:
    teto = grammar_disc_mark._VAO_MAXIMO_CANDIDATO
    spans = [
        v["recognition"]["grammar"]["max_span"]
        for _, v in _pares_reais()
        if v["recognition"]["grammar"]["kind"] == "disc_mark"
    ]

    assert spans
    assert all(0 < span <= teto for span in spans)


def test_teto_do_codigo_e_o_maximo_do_schema() -> None:
    schema = json.loads((_RAIZ / "docs/schemas/pacotes-simbologia.schema.json").read_text("utf-8"))
    definicao = json.dumps(schema)
    ramos = [
        ramo
        for ramo in _ramos(schema)
        if ramo.get("properties", {}).get("kind", {}).get("const") == "disc_mark"
    ]

    assert len(ramos) == 1, definicao[:200]
    propriedades = ramos[0]["properties"]
    assert propriedades["max_span"]["maximum"] == grammar_disc_mark._VAO_MAXIMO_CANDIDATO
    assert propriedades["min_span"]["maximum"] == grammar_disc_mark._VAO_MAXIMO_CANDIDATO


def _ramos(no: Any) -> list[dict[str, Any]]:
    achados: list[dict[str, Any]] = []
    if isinstance(no, dict):
        if "properties" in no:
            achados.append(no)
        for valor in no.values():
            achados.extend(_ramos(valor))
    elif isinstance(no, list):
        for valor in no:
            achados.extend(_ramos(valor))
    return achados


def _com_faixa(minimo: float, maximo: float) -> tuple[declarative_symbols.Package, ...]:
    pacotes = copy.deepcopy(declarative_symbols.carregar_pacotes())
    for pacote in pacotes:
        for variante in pacote.get("variants", []):
            if variante["id"] == _FUSIVEL:
                variante["recognition"]["grammar"]["min_span"] = minimo
                variante["recognition"]["grammar"]["max_span"] = maximo
    return tuple(pacotes)


@pytest.mark.parametrize(("vao", "sai"), [(71.0, True), (72.5, False), (80.0, False)])
def test_faixa_ate_72_no_pacote_le_discos_grandes_e_o_teto_corta_acima(
    vao: float, sai: bool
) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        _desenhar_caminho(pagina, disco(vao, VERMELHO, 0))
        _desenhar_todos(pagina, conteudo_fusivel(vao, 1))
        resultado = observar_pacotes_modelo(
            pagina,
            documento_id="d",
            documento_sha256="d" * 64,
            pagina_numero=1,
            pacotes=_com_faixa(4.5, 72.0),
            tabela=carregar_tabela_glifos(),
        )

    assert (len(resultado.observacoes) == 1) is sai


@pytest.mark.parametrize("maximo", [72.01, 100.0])
def test_validador_recusa_max_span_acima_do_teto_do_codigo(maximo: float) -> None:
    gramatica = {
        "kind": "disc_mark",
        "fill": "red",
        "content": "fuse_curve",
        "min_span": 4.5,
        "max_span": maximo,
    }

    assert declarative_symbols._disc_mark_grammar_ok(gramatica) is False
    assert declarative_symbols._disc_mark_grammar_ok({**gramatica, "max_span": 72}) is True
