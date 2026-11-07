# mypy: disable-error-code="no-untyped-call"
"""Método sobre o modelo de desenho: paridade com o motor, tradução de falha e resíduo raster."""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Final

import pymupdf
import pytest
from tests.fixtures.declarative_symbols.corpus import ENABLED_CASES, build_enabled_corpus
from tests.fixtures.symbol_grammars.paginas import pagina_gramatica

from zeny_project_handler.adapters.analysis import model_symbols, pymupdf_drawing_model
from zeny_project_handler.adapters.analysis.declarative_symbols import (
    _enabled,
    carregar_pacotes,
    observar_pacotes,
    perfil_pacotes,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    TabelaGlifos,
    carregar_tabela_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    VERSAO_MODELO_DESENHO,
    Caixa,
    ImagemModelo,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    LIMITE_CONSULTAS_PAGINA,
    PaginaGramatica,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import CasamentoGramatica
from zeny_project_handler.adapters.analysis.model_symbols import (
    ResiduoRaster,
    observar_pacotes_modelo,
    perfil_pacotes_modelo,
    residuos_raster,
)
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos
from zeny_project_handler.domain.symbols import (
    ObservacaoSimbolo,
    PerfilMetodoSimbolos,
    ResultadoMetodoSimbolos,
)

Pacotes = tuple[dict[str, Any], ...]
Corpus = tuple[Path, list[dict[str, Any]]]

_SHA: Final = "a" * 64
_TOLERANCIA: Final = 1e-3
_TIPO_DA_VARIANTE: Final = {caso.variant_id: caso.kind for caso in ENABLED_CASES}
_TRIANGULO_VAZIO: Final = "cemig-eo-r3-s07-v001"
_CAMARA_CT: Final = "cemig-eo-r3-s06-v001"
_MOLDURA_CT: Final[Caixa] = (101.0, 115.0, 169.0, 149.0)
_PRETO: Final = (0, 0, 0)

_CAMINHOS_FALHOU: Final = "modelo.caminhos_falhou"
_IMAGENS_FALHOU: Final = "modelo.imagens_falhou"
_IMAGENS_ANOTACAO_FALHOU: Final = "modelo.imagens_anotacao_falhou"
_GLIFOS_LIMITADOS: Final = "modelo.glifos_limitados"
_FONTES_NOVAS: Final = (
    "modelo.primitivas_falhou",
    "modelo.textos_nativos_falhou",
    "modelo.textos_shx_falhou",
    "modelo.glifos_falhou",
)


@pytest.fixture(scope="module")
def pacotes() -> Pacotes:
    return carregar_pacotes()


@pytest.fixture(scope="module")
def tabela() -> TabelaGlifos:
    return carregar_tabela_glifos()


@pytest.fixture(scope="module")
def perfil(pacotes: Pacotes, tabela: TabelaGlifos) -> PerfilMetodoSimbolos:
    return perfil_pacotes_modelo(pacotes, tabela)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> Corpus:
    caminho = tmp_path_factory.mktemp("corpus") / "c.pdf"
    return caminho, build_enabled_corpus(caminho)["cases"]


def _desenhar_ct(pagina: pymupdf.Page, moldura: Caixa = _MOLDURA_CT, *, oc: int = 0) -> None:
    pagina.draw_rect(pymupdf.Rect(moldura), color=_PRETO, width=1, oc=oc)
    pagina.insert_text((moldura[0] + 6, moldura[1] + 25), "CT", fontsize=11)


@pytest.fixture
def pagina_ct() -> Iterator[pymupdf.Page]:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        _desenhar_ct(pagina)
        yield pagina


@pytest.fixture
def pagina_vazia() -> Iterator[pymupdf.Page]:
    with pymupdf.open() as documento:
        yield documento.new_page(width=300, height=300)


def _metodo(
    pagina: pymupdf.Page, pacotes: Pacotes, tabela: TabelaGlifos, **opcoes: Any
) -> ResultadoMetodoSimbolos:
    return observar_pacotes_modelo(
        pagina,
        documento_id="paridade",
        documento_sha256=_SHA,
        pagina_numero=pagina.number + 1,
        pacotes=pacotes,
        tabela=tabela,
        **opcoes,
    )


def _motor(pagina: pymupdf.Page, pacotes: Pacotes) -> ResultadoMetodoSimbolos:
    return observar_pacotes(
        pagina,
        documento_id="paridade",
        documento_sha256=_SHA,
        pagina_numero=pagina.number + 1,
        pacotes=pacotes,
    )


def _sem_assinatura(observacoes: Sequence[ObservacaoSimbolo]) -> list[ObservacaoSimbolo]:
    return [replace(observacao, metodo_assinatura=_SHA) for observacao in observacoes]


def _rotulo(row: Mapping[str, Any]) -> str:
    return f"page={row['page']} variant_id={row['variant_id']} stratum={row['stratum']}"


def _invariante_em_qualquer_rotacao(row: Mapping[str, Any]) -> bool:
    if not str(row["stratum"]).startswith("positive"):
        return False
    tipo = _TIPO_DA_VARIANTE[row["variant_id"]]
    if tipo == "terminal_disc":
        return row["stratum"] in {"positive", "positive_split"}
    return tipo in {"label_in_frame", "framed_diagonals", "diamond_three_dots"}


def _unica_cobertura(resultado: ResultadoMetodoSimbolos) -> Any:
    assert len(resultado.coberturas) == 1
    return resultado.coberturas[0]


def _adulterar_pagina(
    monkeypatch: pytest.MonkeyPatch,
    diagnosticos: Sequence[str] = (),
    imagens: Sequence[ImagemModelo] = (),
) -> None:
    """A leitura real da página, com diagnósticos e imagens a mais."""
    original = pymupdf_drawing_model.pagina_para_gramaticas

    def adulterada(
        pagina: pymupdf.Page, indice: int, tabela: TabelaGlifos | None = None
    ) -> PaginaGramatica:
        lida = original(pagina, indice, tabela)
        modelo = replace(
            lida.modelo,
            diagnosticos=(*lida.modelo.diagnosticos, *diagnosticos),
            imagens=(*lida.modelo.imagens, *imagens),
        )
        return replace(lida, modelo=modelo)

    monkeypatch.setattr(model_symbols, "pagina_para_gramaticas", adulterada)


# --- paridade com o motor -------------------------------------------------------------------


def test_paridade_de_observacao_com_o_motor_no_corpus(
    corpus: Corpus, pacotes: Pacotes, tabela: TabelaGlifos, perfil: PerfilMetodoSimbolos
) -> None:
    caminho, linhas = corpus
    divergencias: list[str] = []
    positivas = 0
    with pymupdf.open(caminho) as documento:
        for row in linhas:
            pagina = documento[row["page"] - 1]
            nossas = _metodo(pagina, pacotes, tabela, perfil=perfil).observacoes
            dele = _motor(pagina, pacotes)
            positivas += bool(nossas)
            if _sem_assinatura(nossas) != _sem_assinatura(dele.observacoes):
                divergencias.append(f"{_rotulo(row)}: {nossas} != {dele.observacoes}")
            assert all(o.metodo_assinatura == perfil.assinatura() for o in nossas)
            assert not {o.id for o in nossas} & {o.id for o in dele.observacoes}
    assert divergencias == []
    assert positivas > 0


@pytest.mark.parametrize(
    ("nome_ocg", "camada"),
    [pytest.param(None, None, id="sem-ocg"), pytest.param("REDE", "REDE", id="com-ocg")],
)
def test_paridade_de_camada_com_e_sem_ocg(
    pacotes: Pacotes, tabela: TabelaGlifos, nome_ocg: str | None, camada: str | None
) -> None:
    """`Estilo.camada` é "" sem OCG e o motor grava None: "" duplicaria toda ocorrência."""
    with pymupdf.open() as documento:
        oc = 0 if nome_ocg is None else documento.add_ocg(nome_ocg)
        pagina = documento.new_page(width=300, height=300)
        _desenhar_ct(pagina, oc=oc)
        nossas = _metodo(pagina, pacotes, tabela).observacoes
        dele = _motor(pagina, pacotes).observacoes

    assert [o.primitivas[0].camada for o in nossas] == [camada]
    assert _sem_assinatura(nossas) == _sem_assinatura(dele)


def _difere(a: Sequence[Sequence[Any]], b: Sequence[Sequence[Any]]) -> bool:
    return len(a) != len(b) or any(
        abs(float(x) - float(y)) > _TOLERANCIA
        for ponto_a, ponto_b in zip(a, b, strict=True)
        for x, y in zip(ponto_a, ponto_b, strict=True)
    )


def _divergencias_de_geometria(nossa: ObservacaoSimbolo, dele: ObservacaoSimbolo) -> list[str]:
    a, b = nossa.geometria, dele.geometria
    achados: list[str] = []
    normalizados_a = [(p.x, p.y) for p in a.pontos_normalizados]
    normalizados_b = [(p.x, p.y) for p in b.pontos_normalizados]
    if _difere(a.pontos_originais, b.pontos_originais):
        achados.append(f"originais {a.pontos_originais} != {b.pontos_originais}")
    if _difere(normalizados_a, normalizados_b):
        achados.append(f"normalizados {normalizados_a} != {normalizados_b}")
    if a.transformacao != b.transformacao or a.tipo != b.tipo:
        achados.append(f"transformação {a.transformacao} != {b.transformacao}")
    primitiva_a, primitiva_b = nossa.primitivas[0], dele.primitivas[0]
    if _difere(primitiva_a.pontos_originais, primitiva_b.pontos_originais):
        achados.append(f"primitiva {primitiva_a} != {primitiva_b}")
    if (primitiva_a.indice, primitiva_a.camada) != (primitiva_b.indice, primitiva_b.camada):
        achados.append(f"primitiva {primitiva_a} != {primitiva_b}")
    return achados


@pytest.mark.parametrize(
    ("rotacao", "recorte"),
    [
        pytest.param(90, False, id="rotacao-90"),
        pytest.param(180, False, id="rotacao-180"),
        pytest.param(270, False, id="rotacao-270"),
        pytest.param(0, True, id="cropbox"),
        pytest.param(90, True, id="cropbox-rotacao-90"),
    ],
)
def test_geometria_com_rotacao_e_cropbox(
    corpus: Corpus,
    pacotes: Pacotes,
    tabela: TabelaGlifos,
    perfil: PerfilMetodoSimbolos,
    rotacao: int,
    recorte: bool,
) -> None:
    caminho, linhas = corpus
    selecionadas = [row for row in linhas if _invariante_em_qualquer_rotacao(row)]
    assert selecionadas
    divergencias: list[str] = []
    with pymupdf.open(caminho) as documento:
        for row in selecionadas:
            pagina = documento[row["page"] - 1]
            if recorte:
                pagina.set_cropbox(pymupdf.Rect(50, 60, 250, 280))
            pagina.set_rotation(rotacao)
            nossas = _metodo(pagina, pacotes, tabela, perfil=perfil).observacoes
            dele = _motor(pagina, pacotes).observacoes
            assert dele, _rotulo(row)
            if [o.template for o in nossas] != [o.template for o in dele]:
                divergencias.append(f"{_rotulo(row)}: variantes")
                continue
            for nossa, do_motor in zip(nossas, dele, strict=True):
                achados = _divergencias_de_geometria(nossa, do_motor)
                divergencias.extend(f"{_rotulo(row)}: {achado}" for achado in achados)
    assert divergencias == []


def test_divergencia_de_orientacao_continua_explicita(
    corpus: Corpus, pacotes: Pacotes, tabela: TabelaGlifos, perfil: PerfilMetodoSimbolos
) -> None:
    """R-E06.2.1-7: o triângulo em pé só em coordenadas cruas está de cabeça para baixo na folha."""
    caminho, linhas = corpus
    row = next(
        row
        for row in linhas
        if row["variant_id"] == _TRIANGULO_VAZIO and row["stratum"] == "positive"
    )
    with pymupdf.open(caminho) as documento:
        pagina = documento[row["page"] - 1]
        pagina.set_rotation(180)
        nosso = _metodo(pagina, pacotes, tabela, perfil=perfil)
        dele = _motor(pagina, pacotes)

    assert _TRIANGULO_VAZIO in {o.template for o in dele.observacoes}
    assert _TRIANGULO_VAZIO not in {o.template for o in nosso.observacoes}
    assert _unica_cobertura(nosso).estado is EstadoMetodoSimbolos.NAO_DETECCAO


# --- tradução da falha (R-E06.2.2.1-3) ------------------------------------------------------


def test_teto_vira_fora_de_dominio_sem_observacao(
    pagina_ct: pymupdf.Page, pacotes: Pacotes, tabela: TabelaGlifos
) -> None:
    resultado = _metodo(pagina_ct, pacotes, tabela, limite=1)

    cobertura = _unica_cobertura(resultado)
    assert cobertura.estado is EstadoMetodoSimbolos.FORA_DOMINIO
    assert cobertura.motivo == "teto_consultas"
    assert cobertura.classes_avaliadas == resultado.perfil.classes_suportadas
    assert cobertura.classes_avaliadas
    assert resultado.observacoes == ()


def _menor_limite_que_conclui(
    pagina: pymupdf.Page, pacotes: Pacotes, tabela: TabelaGlifos, perfil: PerfilMetodoSimbolos
) -> int:
    sem_teto, com_teto = LIMITE_CONSULTAS_PAGINA, 0
    while sem_teto - com_teto > 1:
        meio = (sem_teto + com_teto) // 2
        resultado = _metodo(pagina, pacotes, tabela, perfil=perfil, limite=meio)
        if _unica_cobertura(resultado).estado is EstadoMetodoSimbolos.FORA_DOMINIO:
            com_teto = meio
        else:
            sem_teto = meio
    return sem_teto


def test_teto_por_uma_consulta_nao_deixa_observacao_parcial(
    pagina_ct: pymupdf.Page, pacotes: Pacotes, tabela: TabelaGlifos, perfil: PerfilMetodoSimbolos
) -> None:
    """O casamento da primeira variante já saiu quando o teto chega, e mesmo assim não fica."""
    limite = _menor_limite_que_conclui(pagina_ct, pacotes, tabela, perfil)

    com_folga = _metodo(pagina_ct, pacotes, tabela, perfil=perfil, limite=limite)
    sem_folga = _metodo(pagina_ct, pacotes, tabela, perfil=perfil, limite=limite - 1)

    assert [o.template for o in com_folga.observacoes] == [_CAMARA_CT]
    assert sem_folga.observacoes == ()
    assert _unica_cobertura(sem_folga).motivo == "teto_consultas"


@pytest.mark.parametrize("codigo", _FONTES_NOVAS)
def test_fonte_nova_vira_fora_de_dominio(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    pacotes: Pacotes,
    tabela: TabelaGlifos,
    codigo: str,
) -> None:
    pdf = tmp_path / "folha-sigilosa.pdf"
    with pymupdf.open() as novo:
        _desenhar_ct(novo.new_page(width=300, height=300))
        novo.save(pdf)
    _adulterar_pagina(monkeypatch, (codigo,))

    with pymupdf.open(pdf) as documento:
        resultado = _metodo(documento[0], pacotes, tabela)

    cobertura = _unica_cobertura(resultado)
    assert cobertura.estado is EstadoMetodoSimbolos.FORA_DOMINIO
    assert cobertura.motivo == f"fonte_falhou:{codigo}"
    assert cobertura.classes_avaliadas == resultado.perfil.classes_suportadas
    assert resultado.observacoes == ()


def test_glifos_limitados_tem_motivo_proprio(
    monkeypatch: pytest.MonkeyPatch,
    pagina_ct: pymupdf.Page,
    pacotes: Pacotes,
    tabela: TabelaGlifos,
) -> None:
    _adulterar_pagina(monkeypatch, (_GLIFOS_LIMITADOS,))

    resultado = _metodo(pagina_ct, pacotes, tabela)

    cobertura = _unica_cobertura(resultado)
    assert cobertura.estado is EstadoMetodoSimbolos.FORA_DOMINIO
    assert cobertura.motivo == "glifos_limitados"
    assert resultado.observacoes == ()


def test_caminhos_falhou_vira_falha(
    monkeypatch: pytest.MonkeyPatch,
    pagina_ct: pymupdf.Page,
    pacotes: Pacotes,
    tabela: TabelaGlifos,
) -> None:
    def falhar(_pagina: Any) -> Any:
        raise RuntimeError("C:/segredo/folha.pdf")

    monkeypatch.setattr(pymupdf_drawing_model, "_caminhos_e_glifos", falhar)

    resultado = _metodo(pagina_ct, pacotes, tabela)

    cobertura = _unica_cobertura(resultado)
    assert cobertura.estado is EstadoMetodoSimbolos.FALHA
    assert cobertura.motivo == f"fonte_falhou:{_CAMINHOS_FALHOU}"
    assert cobertura.classes_avaliadas == resultado.perfil.classes_suportadas
    assert resultado.observacoes == ()
    assert not resultado.completo


@pytest.mark.parametrize(
    "diagnosticos",
    [
        pytest.param((_FONTES_NOVAS[0], _CAMINHOS_FALHOU), id="caminhos-depois"),
        pytest.param((_CAMINHOS_FALHOU, _FONTES_NOVAS[3]), id="caminhos-antes"),
        pytest.param((_GLIFOS_LIMITADOS, _CAMINHOS_FALHOU), id="com-glifos-limitados"),
    ],
)
def test_caminhos_e_outra_fonte_falham_juntos_vira_falha(
    monkeypatch: pytest.MonkeyPatch,
    pagina_ct: pymupdf.Page,
    pacotes: Pacotes,
    tabela: TabelaGlifos,
    diagnosticos: tuple[str, ...],
) -> None:
    """`FonteGramaticaFalhou` traz só o primeiro código: quem decide é a lista de diagnósticos."""
    _adulterar_pagina(monkeypatch, diagnosticos)

    resultado = _metodo(pagina_ct, pacotes, tabela)

    cobertura = _unica_cobertura(resultado)
    assert cobertura.estado is EstadoMetodoSimbolos.FALHA
    assert cobertura.motivo == f"fonte_falhou:{_CAMINHOS_FALHOU}"
    assert resultado.observacoes == ()


@pytest.mark.parametrize("codigo", ["modelo.grupos_falhou", "modelo.glifos_desconhecidos"])
def test_diagnostico_que_o_nucleo_nao_consome_nao_muda_o_estado(
    monkeypatch: pytest.MonkeyPatch,
    pagina_ct: pymupdf.Page,
    pacotes: Pacotes,
    tabela: TabelaGlifos,
    codigo: str,
) -> None:
    _adulterar_pagina(monkeypatch, (codigo,))

    resultado = _metodo(pagina_ct, pacotes, tabela)

    assert _unica_cobertura(resultado).estado is EstadoMetodoSimbolos.CONCLUIDO
    assert _unica_cobertura(resultado).motivo == "residuo_raster:0"
    assert [o.template for o in resultado.observacoes] == [_CAMARA_CT]


def test_excecao_inesperada_nao_e_capturada(
    monkeypatch: pytest.MonkeyPatch,
    pagina_ct: pymupdf.Page,
    pacotes: Pacotes,
    tabela: TabelaGlifos,
) -> None:
    def falhar(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("defeito")

    monkeypatch.setattr(model_symbols, "casar_variantes", falhar)

    with pytest.raises(RuntimeError, match="defeito"):
        _metodo(pagina_ct, pacotes, tabela)


def test_pagina_de_tamanho_invalido_levanta(pacotes: Pacotes, tabela: TabelaGlifos) -> None:
    pagina = SimpleNamespace(rect=SimpleNamespace(width=0.0, height=10.0), number=0)

    with pytest.raises(ValueError, match="width"):
        _metodo(pagina, pacotes, tabela)  # type: ignore[arg-type]


# --- estados como `_coverage_state` ---------------------------------------------------------


def test_sem_casamento_e_nao_deteccao(
    pagina_vazia: pymupdf.Page, pacotes: Pacotes, tabela: TabelaGlifos
) -> None:
    pagina_vazia.draw_line((10, 10), (200, 200), color=_PRETO, width=1)

    resultado = _metodo(pagina_vazia, pacotes, tabela)
    motor = _motor(pagina_vazia, pacotes)

    cobertura = _unica_cobertura(resultado)
    assert cobertura.estado is _unica_cobertura(motor).estado is EstadoMetodoSimbolos.NAO_DETECCAO
    assert cobertura.classes_avaliadas == resultado.perfil.classes_suportadas
    assert cobertura.regiao_normalizada == _unica_cobertura(motor).regiao_normalizada
    assert cobertura.fonte == _unica_cobertura(motor).fonte
    assert cobertura.motivo == "residuo_raster:0"
    assert resultado.observacoes == ()


def test_com_casamento_e_concluido(
    pagina_ct: pymupdf.Page, pacotes: Pacotes, tabela: TabelaGlifos
) -> None:
    resultado = _metodo(pagina_ct, pacotes, tabela)

    assert _unica_cobertura(resultado).estado is EstadoMetodoSimbolos.CONCLUIDO
    assert [o.template for o in resultado.observacoes] == [_CAMARA_CT]


def _so_pendentes(pacotes: Pacotes) -> Pacotes:
    copia = copy.deepcopy(pacotes)
    for pacote in copia:
        pacote["variants"] = [
            variante
            for variante in pacote["variants"]
            if variante["recognition"]["status"] != "enabled"
        ]
    return copia


def test_sem_variante_habilitada_e_fora_de_dominio(
    pagina_ct: pymupdf.Page, pacotes: Pacotes, tabela: TabelaGlifos
) -> None:
    pendentes = _so_pendentes(pacotes)
    assert _enabled(pendentes) == ()

    resultado = _metodo(pagina_ct, pendentes, tabela)
    motor = _motor(pagina_ct, pendentes)

    cobertura = _unica_cobertura(resultado)
    assert cobertura.estado is _unica_cobertura(motor).estado is EstadoMetodoSimbolos.FORA_DOMINIO
    assert cobertura.motivo == _unica_cobertura(motor).motivo
    assert cobertura.classes_avaliadas == ()
    assert resultado.observacoes == ()


# --- perfil ---------------------------------------------------------------------------------


def test_perfil_declara_o_metodo(
    pacotes: Pacotes, tabela: TabelaGlifos, perfil: PerfilMetodoSimbolos
) -> None:
    motor = perfil_pacotes(pacotes)

    assert perfil.metodo_id == "declarative-drawing-model"
    assert perfil.versao == "1.0.0"
    assert perfil.familia == motor.familia
    assert perfil.classes_suportadas == motor.classes_suportadas
    assert perfil.camadas_suportadas == motor.camadas_suportadas
    assert perfil.perfil_referencia == motor.perfil_referencia
    assert (
        perfil.dominio_aplicacao
        == "PDF vetorial lido pelo modelo de desenho; contexto não inferido"
    )
    assert perfil.fontes_compartilhadas == tuple(
        sorted(
            (
                "pymupdf:get_drawings:extended",
                "pymupdf:get_text:rawdict",
                "pymupdf:annotations",
                "modelo-desenho:glifos",
            )
        )
    )
    assert dict(perfil.parametros) == {
        "modelo_desenho": VERSAO_MODELO_DESENHO,
        "package_sha256": dict(motor.parametros)["package_sha256"],
        "tabela_glifos_versao": tabela.versao,
        "tabela_glifos_sha256": tabela.sha256,
        "limite_consultas": LIMITE_CONSULTAS_PAGINA,
        "enabled_variants": dict(motor.parametros)["enabled_variants"],
    }


def _outro_pacote(pacotes: Pacotes) -> Pacotes:
    copia = copy.deepcopy(pacotes)
    copia[0]["variants"][0]["visual_note"] += " alterada"
    return copia


def test_perfil_muda_com_pacote_tabela_e_limite(
    monkeypatch: pytest.MonkeyPatch,
    pacotes: Pacotes,
    tabela: TabelaGlifos,
    perfil: PerfilMetodoSimbolos,
) -> None:
    base = perfil.assinatura()
    assert perfil_pacotes_modelo(pacotes, tabela).assinatura() == base

    outras = {
        "pacote": perfil_pacotes_modelo(_outro_pacote(pacotes), tabela).assinatura(),
        "tabela": perfil_pacotes_modelo(pacotes, replace(tabela, sha256="b" * 64)).assinatura(),
        "limite": perfil_pacotes_modelo(pacotes, tabela, limite=10).assinatura(),
    }
    monkeypatch.setattr(model_symbols, "VERSAO_MODELO_DESENHO", "outra")
    outras["modelo"] = perfil_pacotes_modelo(pacotes, tabela).assinatura()

    assert base not in outras.values()
    assert len(set(outras.values())) == len(outras)


def test_perfil_recebido_nao_e_recalculado(
    monkeypatch: pytest.MonkeyPatch,
    pagina_ct: pymupdf.Page,
    pacotes: Pacotes,
    tabela: TabelaGlifos,
    perfil: PerfilMetodoSimbolos,
) -> None:
    def falhar(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("recalculou o perfil")

    monkeypatch.setattr(model_symbols, "perfil_pacotes_modelo", falhar)

    assert _metodo(pagina_ct, pacotes, tabela, perfil=perfil).perfil is perfil


def test_assinatura_calculada_uma_vez_por_chamada(
    monkeypatch: pytest.MonkeyPatch,
    pagina_vazia: pymupdf.Page,
    pacotes: Pacotes,
    tabela: TabelaGlifos,
    perfil: PerfilMetodoSimbolos,
) -> None:
    """O `Resultado` real confere a assinatura de cada observação; aqui só o método conta."""
    _desenhar_ct(pagina_vazia, (20.0, 20.0, 88.0, 54.0))
    _desenhar_ct(pagina_vazia, (120.0, 120.0, 188.0, 154.0))
    chamadas: list[str] = []
    assinatura = PerfilMetodoSimbolos.assinatura

    def contada(self: PerfilMetodoSimbolos) -> str:
        chamadas.append(self.metodo_id)
        return assinatura(self)

    monkeypatch.setattr(PerfilMetodoSimbolos, "assinatura", contada)
    monkeypatch.setattr(model_symbols, "ResultadoMetodoSimbolos", SimpleNamespace)

    resultado = _metodo(pagina_vazia, pacotes, tabela, perfil=perfil)

    assert len(resultado.observacoes) == 2
    assert chamadas == [perfil.metodo_id]


def test_tabela_e_indice_chegam_a_leitura(
    monkeypatch: pytest.MonkeyPatch, pagina_ct: pymupdf.Page, pacotes: Pacotes, tabela: TabelaGlifos
) -> None:
    recebidos: list[tuple[int, TabelaGlifos | None]] = []
    original = pymupdf_drawing_model.pagina_para_gramaticas

    def espia(
        pagina: pymupdf.Page, indice: int, recebida: TabelaGlifos | None = None
    ) -> PaginaGramatica:
        recebidos.append((indice, recebida))
        return original(pagina, indice, recebida)

    monkeypatch.setattr(model_symbols, "pagina_para_gramaticas", espia)

    observar_pacotes_modelo(
        pagina_ct,
        documento_id="d",
        documento_sha256=_SHA,
        pagina_numero=7,
        pacotes=pacotes,
        tabela=tabela,
    )

    assert recebidos == [(6, tabela)]


# --- resíduo raster (R-E06.2.2.1-4) ---------------------------------------------------------

_CAIXA_IMAGEM: Final[Caixa] = (100.0, 100.0, 120.0, 120.0)


def _imagem(
    caixa: Caixa = _CAIXA_IMAGEM,
    sha: str = _SHA,
    px: tuple[int, int] = (20, 20),
    *,
    de_anotacao: bool = False,
) -> ImagemModelo:
    return ImagemModelo(caixa, px[0], px[1], sha, de_anotacao)


def _hash(indice: int) -> str:
    return f"{indice:064x}"


def _caixa_da_grade(indice: int) -> Caixa:
    """Caixas de 10 pt sem sobreposição, todas dentro da página de 300 pt."""
    x0, y0 = 10.0 + 20.0 * (indice % 10), 10.0 + 20.0 * (indice // 10)
    return (x0, y0, x0 + 10.0, y0 + 10.0)


def _ladrilhos(quantidade: int, px: tuple[int, int] = (20, 20)) -> tuple[ImagemModelo, ...]:
    return tuple(_imagem(_caixa_da_grade(i), _hash(i), px) for i in range(quantidade))


def _carimbos(quantidade: int) -> tuple[ImagemModelo, ...]:
    return tuple(_imagem(_caixa_da_grade(i), _SHA) for i in range(quantidade))


def _pagina_com_imagens(imagens: Sequence[ImagemModelo]) -> PaginaGramatica:
    base = pagina_gramatica(())
    return replace(base, modelo=replace(base.modelo, imagens=tuple(imagens)))


def _casamento(caixa: Caixa) -> CasamentoGramatica:
    return CasamentoGramatica({}, {}, caixa, 0)


def _residuo(imagem: ImagemModelo) -> ResiduoRaster:
    return ResiduoRaster(imagem.bbox, imagem.sha256, imagem.de_anotacao)


def _uma_caixa(x0: float, y0: float, x1: float, y1: float) -> tuple[ImagemModelo, ...]:
    return (_imagem((x0, y0, x1, y1)),)


_NENHUM: Final[tuple[int, ...]] = ()


@pytest.mark.parametrize(
    ("imagens", "casamentos", "restantes"),
    [
        pytest.param((_imagem(),), (), (0,), id="compacta-de-pagina"),
        pytest.param((_imagem(de_anotacao=True),), (), (0,), id="compacta-de-anotacao"),
        pytest.param(_uma_caixa(10.0, 10.0, 14.0, 82.0), (), (0,), id="lados-4-e-72-contam"),
        pytest.param(_uma_caixa(10.0, 10.0, 13.9, 82.0), (), _NENHUM, id="lado-abaixo-de-4"),
        pytest.param(_uma_caixa(10.0, 10.0, 14.0, 82.1), (), _NENHUM, id="lado-acima-de-72"),
        pytest.param(_uma_caixa(10.0, 10.0, 200.0, 200.0), (), _NENHUM, id="imagem-grande"),
        pytest.param(_uma_caixa(400.0, 400.0, 420.0, 420.0), (), _NENHUM, id="fora-da-pagina"),
        pytest.param(_uma_caixa(290.0, 100.0, 310.0, 120.0), (), _NENHUM, id="vaza-a-pagina"),
        pytest.param(_uma_caixa(280.0, 280.0, 300.0, 300.0), (), (0,), id="encosta-na-borda"),
        pytest.param(
            (_imagem(),),
            (_casamento((105.0, 105.0, 115.0, 115.0)),),
            _NENHUM,
            id="centro-de-casamento-dentro",
        ),
        pytest.param(
            (_imagem(),),
            (_casamento((90.0, 90.0, 130.0, 130.0)),),
            _NENHUM,
            id="casamento-maior-com-centro-nela",
        ),
        pytest.param(
            (_imagem(),),
            (_casamento((115.0, 100.0, 135.0, 120.0)),),
            (0,),
            id="casamento-encosta-sem-centro",
        ),
        pytest.param(
            (_imagem(),),
            (_casamento((200.0, 200.0, 210.0, 210.0)),),
            (0,),
            id="casamento-longe",
        ),
        pytest.param(_ladrilhos(9), (), _NENHUM, id="mosaico-9-hashes"),
        pytest.param(_ladrilhos(8), (), tuple(range(8)), id="8-hashes-nao-e-mosaico"),
        pytest.param(_carimbos(9), (), tuple(range(9)), id="mesmo-hash-9-vezes"),
        pytest.param(
            tuple(_imagem(_caixa_da_grade(i), _hash(i), (20 + i, 20)) for i in range(9)),
            (),
            tuple(range(9)),
            id="9-hashes-em-dimensoes-diferentes",
        ),
        pytest.param(_ladrilhos(9, (0, 0)), (), tuple(range(9)), id="dimensao-0-nao-e-mosaico"),
        pytest.param(_ladrilhos(9, (0, 20)), (), tuple(range(9)), id="largura-0-nao-e-mosaico"),
        pytest.param(
            (*_ladrilhos(8), _imagem((10.0, 200.0, 200.0, 290.0), _hash(8))),
            (),
            _NENHUM,
            id="ladrilho-grande-conta-para-o-mosaico",
        ),
        pytest.param(
            (*_ladrilhos(9), _imagem(_CAIXA_IMAGEM, _hash(50), (30, 30))),
            (),
            (9,),
            id="outra-dimensao-ao-lado-do-mosaico",
        ),
        pytest.param((_imagem(), _imagem()), (), (0,), id="mesma-imagem-mesma-caixa"),
        pytest.param(
            (_imagem(), _imagem((100.0001, 100.0, 120.0, 120.0))),
            (),
            (0,),
            id="mesma-imagem-caixa-igual-a-3-casas",
        ),
        pytest.param(
            (_imagem(), _imagem((100.01, 100.0, 120.0, 120.0))),
            (),
            (0, 1),
            id="mesma-imagem-outra-caixa",
        ),
        pytest.param(
            (_imagem(), _imagem(_CAIXA_IMAGEM, _hash(1))),
            (),
            (0, 1),
            id="outra-imagem-mesma-caixa",
        ),
        pytest.param(
            (
                _imagem((10.0, 10.0, 20.0, 20.0), _hash(1)),
                _imagem((5.0, 5.0, 15.0, 15.0), _hash(2)),
            ),
            (),
            (0, 1),
            id="ordem-do-modelo",
        ),
    ],
)
def test_residuo_raster(
    imagens: tuple[ImagemModelo, ...],
    casamentos: tuple[CasamentoGramatica, ...],
    restantes: tuple[int, ...],
) -> None:
    obtidos = residuos_raster(_pagina_com_imagens(imagens), casamentos)

    assert obtidos == tuple(_residuo(imagens[indice]) for indice in restantes)


def test_residuo_raster_e_deterministico() -> None:
    pagina = _pagina_com_imagens((*_carimbos(3), _imagem(sha=_hash(1), de_anotacao=True)))

    assert residuos_raster(pagina, ()) == residuos_raster(pagina, ())
    assert [r.de_anotacao for r in residuos_raster(pagina, ())] == [False, False, False, True]


def _pixmap() -> pymupdf.Pixmap:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), False)
    pixmap.clear_with(128)
    return pixmap


def test_residuo_nao_vira_observacao(
    pagina_ct: pymupdf.Page, pacotes: Pacotes, tabela: TabelaGlifos
) -> None:
    sem_imagem = _metodo(pagina_ct, pacotes, tabela)

    pagina_ct.insert_image(pymupdf.Rect(10, 10, 30, 30), pixmap=_pixmap())
    com_imagem = _metodo(pagina_ct, pacotes, tabela)

    assert _unica_cobertura(sem_imagem).motivo == "residuo_raster:0"
    assert _unica_cobertura(com_imagem).motivo == "residuo_raster:1"
    assert _sem_assinatura(com_imagem.observacoes) == _sem_assinatura(sem_imagem.observacoes)
    assert [o.template for o in com_imagem.observacoes] == [_CAMARA_CT]


def test_imagem_sob_o_casamento_nao_e_residuo(
    pagina_ct: pymupdf.Page, pacotes: Pacotes, tabela: TabelaGlifos
) -> None:
    pagina_ct.insert_image(pymupdf.Rect(_MOLDURA_CT), pixmap=_pixmap())

    resultado = _metodo(pagina_ct, pacotes, tabela)

    assert _unica_cobertura(resultado).motivo == "residuo_raster:0"
    assert [o.template for o in resultado.observacoes] == [_CAMARA_CT]


def test_residuo_na_pagina_sem_casamento_mantem_a_nao_deteccao(
    pagina_vazia: pymupdf.Page, pacotes: Pacotes, tabela: TabelaGlifos
) -> None:
    pagina_vazia.insert_image(pymupdf.Rect(10, 10, 30, 30), pixmap=_pixmap())

    resultado = _metodo(pagina_vazia, pacotes, tabela)

    assert _unica_cobertura(resultado).estado is EstadoMetodoSimbolos.NAO_DETECCAO
    assert _unica_cobertura(resultado).motivo == "residuo_raster:1"
    assert resultado.observacoes == ()


_DUAS_IMAGENS: Final = (
    _imagem((10.0, 10.0, 30.0, 30.0), _hash(1)),
    _imagem((40.0, 10.0, 60.0, 30.0), _hash(2)),
)


@pytest.mark.parametrize(
    ("diagnosticos", "imagens", "opcoes", "esperado"),
    [
        pytest.param((), (), {}, "residuo_raster:0", id="medido-zero"),
        pytest.param((), _DUAS_IMAGENS, {}, "residuo_raster:2", id="dois"),
        pytest.param(
            (_IMAGENS_FALHOU,), _DUAS_IMAGENS, {}, "residuo_raster:2;imagens_falhou", id="pagina"
        ),
        pytest.param(
            (_IMAGENS_ANOTACAO_FALHOU,),
            _DUAS_IMAGENS,
            {},
            "residuo_raster:2;imagens_falhou",
            id="anotacao",
        ),
        pytest.param(
            (_IMAGENS_FALHOU, _IMAGENS_ANOTACAO_FALHOU),
            (),
            {},
            "residuo_raster:0;imagens_falhou",
            id="as-duas-uma-vez-so",
        ),
        pytest.param((), _DUAS_IMAGENS, {"limite": 1}, "teto_consultas", id="teto-sem-contagem"),
        pytest.param(
            (_GLIFOS_LIMITADOS,), _DUAS_IMAGENS, {}, "glifos_limitados", id="glifos-sem-contagem"
        ),
        pytest.param(
            (_FONTES_NOVAS[0], _IMAGENS_FALHOU),
            _DUAS_IMAGENS,
            {},
            f"fonte_falhou:{_FONTES_NOVAS[0]}",
            id="fonte-sem-contagem",
        ),
    ],
)
def test_formato_do_motivo(
    monkeypatch: pytest.MonkeyPatch,
    pagina_ct: pymupdf.Page,
    pacotes: Pacotes,
    tabela: TabelaGlifos,
    diagnosticos: tuple[str, ...],
    imagens: tuple[ImagemModelo, ...],
    opcoes: dict[str, Any],
    esperado: str,
) -> None:
    _adulterar_pagina(monkeypatch, diagnosticos, imagens)

    resultado = _metodo(pagina_ct, pacotes, tabela, **opcoes)

    assert _unica_cobertura(resultado).motivo == esperado


@pytest.mark.parametrize("codigo", [_IMAGENS_FALHOU, _IMAGENS_ANOTACAO_FALHOU])
def test_imagens_falhou_mantem_casamentos_e_marca_motivo(
    monkeypatch: pytest.MonkeyPatch,
    pagina_ct: pymupdf.Page,
    pacotes: Pacotes,
    tabela: TabelaGlifos,
    codigo: str,
) -> None:
    _adulterar_pagina(monkeypatch, (codigo,))

    resultado = _metodo(pagina_ct, pacotes, tabela)

    cobertura = _unica_cobertura(resultado)
    assert cobertura.estado is EstadoMetodoSimbolos.CONCLUIDO
    assert cobertura.motivo == "residuo_raster:0;imagens_falhou"
    assert [o.template for o in resultado.observacoes] == [_CAMARA_CT]


def test_imagens_falhou_de_verdade_na_leitura(
    monkeypatch: pytest.MonkeyPatch,
    pagina_ct: pymupdf.Page,
    pacotes: Pacotes,
    tabela: TabelaGlifos,
) -> None:
    falhar: Callable[[Any], Any] = lambda _pagina: 1 / 0  # noqa: E731

    monkeypatch.setattr(pymupdf_drawing_model, "_imagens_da_pagina", falhar)

    resultado = _metodo(pagina_ct, pacotes, tabela)

    assert _unica_cobertura(resultado).motivo == "residuo_raster:0;imagens_falhou"
    assert [o.template for o in resultado.observacoes] == [_CAMARA_CT]
