# mypy: disable-error-code="no-untyped-call"
"""Ataques ao texto de glifo no analisador PyMuPDF 1.21.0 e no modelo de desenho v2."""

from __future__ import annotations

import ast
import json
import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pymupdf
import pytest
from tests.fixtures.glyphs.fonte_livre import (
    LinhaTexto,
    pdf_texto_contorno,
    pdf_texto_nativo,
    tabela_do_alfabeto,
)

from zeny_project_handler.adapters.analysis import (
    JsonAnalysisCache,
    PyMuPdfDocumentAnalyzer,
    pymupdf_drawing_model,
    pymupdf_glyph_text,
)
from zeny_project_handler.adapters.analysis import pymupdf_analyzer as analyzer_module
from zeny_project_handler.adapters.analysis.drawing_model.cache import (
    JsonDrawingModelCache,
    chave_modelo_desenho,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    TabelaGlifos,
    carregar_tabela_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_text import TextoGlifo
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    VERSAO_MODELO_DESENHO,
    Caixa,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import (
    _DesenhosFiltrados,
    extrair_modelo_desenho,
    obter_modelo_desenho,
)
from zeny_project_handler.adapters.analysis.pymupdf_glyph_text import (
    _resolver_cobertura,
    candidatos_texto_glifos,
    ler_glifos_da_pagina,
)
from zeny_project_handler.adapters.analysis.pymupdf_ocr import _conditional_ocr
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.domain.analysis import EvidenciaDocumento, OrigemObjetoPdf
from zeny_project_handler.domain.enums import TipoEvidencia, TipoGeometria
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ports.analysis import (
    CandidatoEvidenciaDocumento,
    CapacidadeMotorOcr,
    ConfiguracaoAnaliseDocumento,
    GeometriaNormalizada,
    IdentidadeDadosTreinadosOcr,
    PaginaRasterOcr,
    ResultadoAnaliseDocumento,
    ResultadoConsultaCapacidadeOcr,
    SolicitacaoAnaliseDocumento,
    TrechoTextoOcr,
)
from zeny_project_handler.ports.pdf import ReferenciaFontePdf

_LINHAS = (
    LinhaTexto("P7 U4(1) S1N", (40.0, 60.0), 5.0),
    LinhaTexto("11-300", (40.0, 120.0), 5.0),
    LinhaTexto("E=612345 N=7801234", (40.0, 180.0), 5.0),
)
_SEM_OCR = ConfiguracaoAnaliseDocumento(habilitar_ocr_condicional=False)
_RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def tabela(tmp_path_factory: pytest.TempPathFactory) -> TabelaGlifos:
    return tabela_do_alfabeto(tmp_path_factory.mktemp("alfabeto-ataque"))


def _request(
    path: Path, configuracao: ConfiguracaoAnaliseDocumento = _SEM_OCR
) -> SolicitacaoAnaliseDocumento:
    inspection = PyMuPdfReader().inspecionar(path)
    project_id = uuid4()
    return SolicitacaoAnaliseDocumento(
        projeto_id=project_id,
        documento=inspection.documento,
        fonte=ReferenciaFontePdf(
            documento_id=inspection.documento.id,
            projeto_id=project_id,
            caminho_canonico=path,
            sha256=inspection.documento.sha256,
            tamanho_bytes=inspection.tamanho_bytes,
            modificado_em_ns=inspection.modificado_em_ns,
        ),
        execucao_id=uuid4(),
        criada_em=datetime(2026, 11, 4, 9, tzinfo=UTC),
        configuracao=configuracao,
    )


def _analisar(
    pdf: Path, configuracao: ConfiguracaoAnaliseDocumento = _SEM_OCR, **kwargs: Any
) -> ResultadoAnaliseDocumento:
    return PyMuPdfDocumentAnalyzer(**kwargs).analisar(_request(pdf, configuracao))


def _de_glifo(evidencia: EvidenciaDocumento) -> bool:
    return dict(evidencia.atributos_extraidos).get("origem_texto") == "contorno_glifo"


def _textos(resultado: ResultadoAnaliseDocumento) -> list[EvidenciaDocumento]:
    return [e for e in resultado.evidencias if e.tipo is TipoEvidencia.TEXTO]


def _glifos(resultado: ResultadoAnaliseDocumento) -> list[EvidenciaDocumento]:
    return [e for e in _textos(resultado) if _de_glifo(e)]


def _codigos(resultado: ResultadoAnaliseDocumento) -> list[str]:
    return [d.codigo for d in resultado.diagnosticos]


def _centro(evidencia: EvidenciaDocumento) -> tuple[float, float]:
    xs = [float(p.x) for p in evidencia.geometria.pontos]
    ys = [float(p.y) for p in evidencia.geometria.pontos]
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)


def _rotacao(evidencia: EvidenciaDocumento) -> float:
    return float(str(dict(evidencia.atributos_extraidos)["rotacao_graus"]))


def _angulo(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


# --- Review Focus 1: /Rotate 0, 90, 180 e 270 ----------------------------------------------


@pytest.mark.parametrize("rotacao_pagina", [0, 90, 180, 270])
@pytest.mark.parametrize("rotacao_linha", [0.0, 90.0, 30.0])
def test_posicao_e_rotacao_iguais_ao_nativo_em_toda_rotacao_de_pagina(
    tmp_path: Path, tabela: TabelaGlifos, rotacao_pagina: int, rotacao_linha: float
) -> None:
    linhas = [
        LinhaTexto("P10 N1", (80.0, 110.0), 5.0, rotacao_linha),
        LinhaTexto("11-300", (80.0, 210.0), 5.0, rotacao_linha),
    ]
    nativo = pdf_texto_nativo(tmp_path / "n.pdf", linhas, rotacao_pagina=rotacao_pagina)
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", linhas, rotacao_pagina=rotacao_pagina)

    lidos = _glifos(_analisar(contorno, tabela_glifos=tabela))
    referencia = _textos(_analisar(nativo))

    assert Counter(e.conteudo_bruto for e in lidos) == Counter(e.conteudo_bruto for e in referencia)
    for lido in lidos:
        (par,) = (n for n in referencia if n.conteudo_bruto == lido.conteudo_bruto)
        assert math.dist(_centro(lido), _centro(par)) <= 0.01
        assert _angulo(_rotacao(lido), _rotacao(par)) <= 2.0


@pytest.mark.parametrize("rotacao_pagina", [180, 270])
def test_modelo_v2_em_pagina_180_e_270_posiciona_igual_ao_nativo(
    tmp_path: Path, tabela: TabelaGlifos, rotacao_pagina: int
) -> None:
    linhas = [LinhaTexto("P10 N1", (60.0, 80.0), 5.0), LinhaTexto("11-300", (60.0, 200.0), 5.0)]
    nativo = pdf_texto_nativo(tmp_path / "n.pdf", linhas, rotacao_pagina=rotacao_pagina)
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", linhas, rotacao_pagina=rotacao_pagina)

    (glifo,) = extrair_modelo_desenho(contorno, tabela).paginas
    (referencia,) = extrair_modelo_desenho(nativo).paginas

    assert {t.origem for t in glifo.textos} == {"glifo"}
    assert sorted(t.texto for t in glifo.textos) == sorted(t.texto for t in referencia.textos)
    for texto in glifo.textos:
        (par,) = (t for t in referencia.textos if t.texto == texto.texto)
        a = ((texto.bbox[0] + texto.bbox[2]) / 2, (texto.bbox[1] + texto.bbox[3]) / 2)
        b = ((par.bbox[0] + par.bbox[2]) / 2, (par.bbox[1] + par.bbox[3]) / 2)
        assert math.dist(a, b) <= 0.01 * max(glifo.largura, glifo.altura)
        assert _angulo(texto.rotacao, par.rotacao) <= 2.0


# --- chave estável com várias páginas ------------------------------------------------------


def _pdf_de_duas_paginas(tmp_path: Path) -> Path:
    primeiro = pdf_texto_contorno(tmp_path / "um.pdf", _LINHAS[:2])
    segundo = pdf_texto_contorno(tmp_path / "dois.pdf", _LINHAS[1:])
    destino = tmp_path / "duas.pdf"
    with pymupdf.open(primeiro) as a, pymupdf.open(segundo) as b:
        a.insert_pdf(b)
        a.save(destino)
    return destino


def test_evidencias_de_glifo_de_varias_paginas_tem_ids_unicos_e_ficam_na_pagina_certa(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    resultado = _analisar(_pdf_de_duas_paginas(tmp_path), tabela_glifos=tabela)

    por_pagina: dict[Any, list[str]] = {}
    for evidencia in _glifos(resultado):
        por_pagina.setdefault(evidencia.pagina_id, []).append(evidencia.conteudo_bruto or "")
    assert sorted(sorted(v) for v in por_pagina.values()) == sorted(
        [sorted(linha.texto for linha in _LINHAS[:2]), sorted(linha.texto for linha in _LINHAS[1:])]
    )
    ids = [e.id for e in resultado.evidencias]
    assert len(ids) == len(set(ids))


def test_chaves_estaveis_do_texto_de_glifo_nao_repetem_entre_paginas(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    chaves: list[str] = []
    with pymupdf.open(_pdf_de_duas_paginas(tmp_path)) as documento:
        for numero, pagina in enumerate(documento, start=1):
            candidatos, _ = candidatos_texto_glifos(pagina, numero, tabela)
            assert all(c.pagina_numero == numero for c in candidatos)
            chaves.extend(c.chave_estavel for c in candidatos)

    assert len(chaves) == 4
    assert len(set(chaves)) == len(chaves)
    assert all(re.fullmatch(r"p[12]:texto_glifo:\d+", c) for c in chaves)


def test_analise_de_glifos_e_deterministica(tmp_path: Path, tabela: TabelaGlifos) -> None:
    pdf = _pdf_de_duas_paginas(tmp_path)

    def assinatura(r: ResultadoAnaliseDocumento) -> list[tuple[Any, ...]]:
        return sorted(
            (e.conteudo_bruto, e.geometria.pontos, e.atributos_extraidos) for e in _glifos(r)
        )

    primeira = _analisar(pdf, tabela_glifos=tabela)
    segunda = _analisar(pdf, tabela_glifos=tabela)

    assert assinatura(primeira) == assinatura(segunda)
    assert assinatura(primeira)


def test_texto_de_glifo_colorido_usa_o_formato_de_cor_do_ocr(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    linhas = [
        LinhaTexto("P7", (40.0, 60.0), 5.0, cor=(1.0, 0.0, 0.0)),
        LinhaTexto("N1", (40.0, 120.0), 5.0, cor=(0.0, 0.5, 0.0)),
    ]
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", linhas)

    cores = {
        e.conteudo_bruto: dict(e.atributos_extraidos)["cor"]
        for e in _glifos(_analisar(contorno, tabela_glifos=tabela))
    }

    assert cores["P7"] == "#FF0000"
    assert cores["N1"] == "#008000"


def test_texto_de_glifo_na_borda_da_pagina_fica_dentro_de_0_a_1(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    linhas = [LinhaTexto("P7 U4(1) S1N", (385.0, 60.0), 5.0), LinhaTexto("N1", (40.0, 120.0), 5.0)]
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", linhas)

    resultado = _analisar(contorno, tabela_glifos=tabela)

    assert "N1" in {e.conteudo_bruto for e in _glifos(resultado)}
    for evidencia in _glifos(resultado):
        assert all(Decimal(0) <= p.x <= Decimal(1) for p in evidencia.geometria.pontos)
        assert all(Decimal(0) <= p.y <= Decimal(1) for p in evidencia.geometria.pontos)


# --- Review Focus 5: página hostil ---------------------------------------------------------


def _acrescentar_ao_conteudo(pdf: Path, destino: Path, extra: bytes) -> Path:
    with pymupdf.open(pdf) as documento:
        xref = documento[0].get_contents()[0]
        documento.update_stream(xref, documento.xref_stream(xref) + extra)
        documento.save(destino)
    return destino


def test_pagina_com_dezenas_de_milhares_de_preenchimentos_minusculos_nao_derruba_a_analise(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    poeira = "".join(f"{(i % 300) + 20} {(i // 300) + 20} 0.4 0.4 re f\n" for i in range(30_000))
    hostil = _acrescentar_ao_conteudo(
        contorno, tmp_path / "hostil.pdf", ("0 0 0 rg\n" + poeira).encode("ascii")
    )

    resultado = _analisar(hostil, tabela_glifos=tabela)

    assert "analise.glifos_limitados" in _codigos(resultado)
    assert not _glifos(resultado)
    assert any(e.tipo is TipoEvidencia.VETOR for e in resultado.evidencias)


def test_subcaminhos_degenerados_e_coordenadas_enormes_nao_derrubam_a_pagina(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    lixo = (
        b"0 0 0 rg\n"
        b"50 50 m 50 50 l f\n"
        b"60 60 m f\n"
        b"10 10 m 99999999999999999999 99999999999999999999 l 30 10 l f\n"
        b"20 20 0 0 re f\n"
    )
    hostil = _acrescentar_ao_conteudo(contorno, tmp_path / "hostil.pdf", lixo)

    resultado = _analisar(hostil, tabela_glifos=tabela)

    assert sorted(e.conteudo_bruto or "" for e in _glifos(resultado)) == sorted(
        linha.texto for linha in _LINHAS
    )


def _desenho_nao_finito() -> dict[str, Any]:
    nan = float("nan")
    return {
        "type": "f",
        "items": [("l", pymupdf.Point(nan, 0.0), pymupdf.Point(1.0, 1.0))],
        "rect": pymupdf.Rect(0.0, 0.0, 1.0, 1.0),
        "fill": (0.0, 0.0, 0.0),
        "color": None,
        "width": 0.0,
    }


def _injetar_desenho(
    monkeypatch: pytest.MonkeyPatch, posicao: int, desenho: dict[str, Any]
) -> None:
    original = pymupdf_drawing_model._desenhos

    def _desenhos(pagina: Any) -> _DesenhosFiltrados:
        desenhos = original(pagina)
        return _DesenhosFiltrados(enumerate([*desenhos[:posicao], desenho, *desenhos[posicao:]]))

    monkeypatch.setattr(pymupdf_drawing_model, "_desenhos", _desenhos)


def test_desenho_descartado_no_meio_da_linha_nunca_vira_texto_parcial(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    _injetar_desenho(monkeypatch, 3, _desenho_nao_finito())  # dentro de "P7 U4(1) S1N"

    resultado = _analisar(contorno, tabela_glifos=tabela)

    assert sorted(e.conteudo_bruto or "" for e in _glifos(resultado)) == sorted(
        linha.texto for linha in _LINHAS[1:]
    )
    assert any(e.tipo is TipoEvidencia.VETOR for e in resultado.evidencias)


def test_desenho_descartado_antes_do_primeiro_caminho_anula_so_a_linha_que_o_segue(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    _injetar_desenho(monkeypatch, 0, _desenho_nao_finito())

    resultado = _analisar(contorno, tabela_glifos=tabela)

    assert sorted(e.conteudo_bruto or "" for e in _glifos(resultado)) == sorted(
        linha.texto for linha in _LINHAS[1:]
    )


def test_desenho_descartado_entre_duas_linhas_nao_apaga_a_linha_distante(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    _injetar_desenho(monkeypatch, 10, _desenho_nao_finito())  # entre "P7 U4(1) S1N" e "11-300"

    resultado = _analisar(contorno, tabela_glifos=tabela)

    lidos = {e.conteudo_bruto for e in _glifos(resultado)}
    assert "E=612345 N=7801234" in lidos
    assert not any(t in lidos for t in ("P7 U4(1) S1N", "P7", "U4(1)", "S1N", "11", "300", "11-"))


def test_desenho_descartado_no_meio_da_linha_tambem_nao_vira_texto_parcial_no_modelo(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    _injetar_desenho(monkeypatch, 3, _desenho_nao_finito())

    (pagina,) = extrair_modelo_desenho(contorno, tabela).paginas

    assert sorted(t.texto for t in pagina.textos) == sorted(linha.texto for linha in _LINHAS[1:])


# --- Review Focus 5: tabela ausente, inválida ou indisponível ------------------------------


def _tabela_corrompida(tmp_path: Path, conteudo: str | None) -> Any:
    real = carregar_tabela_glifos
    arquivo = tmp_path / "tabela.json"
    if conteudo is not None:
        arquivo.write_text(conteudo, encoding="utf-8")

    def _carregar(_caminho: Path | None = None) -> TabelaGlifos:
        return real(arquivo)

    return _carregar


@pytest.mark.parametrize(
    "conteudo",
    [None, "", "{não é json", "[]", '{"versao": "tabela-glifos-v999", "glifos": []}'],
    ids=["ausente", "vazio", "json-invalido", "tipo-errado", "versao-desconhecida"],
)
def test_tabela_do_pacote_ausente_ou_invalida_nao_derruba_e_muda_a_assinatura(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch, conteudo: str | None
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    monkeypatch.setattr(
        analyzer_module, "carregar_tabela_glifos", _tabela_corrompida(tmp_path, conteudo)
    )
    analisador = PyMuPdfDocumentAnalyzer(tabela_glifos="pacote")

    resultado = analisador.analisar(_request(contorno))

    assert "analise.tabela_glifos_indisponivel" in _codigos(resultado)
    assert not _glifos(resultado)
    assert any(e.tipo is TipoEvidencia.VETOR for e in resultado.evidencias)
    assert str(analisador._capacidade()["tabela_glifos"]).startswith("indisponivel:")
    assinaturas = {
        analisador.assinatura_capacidade,
        PyMuPdfDocumentAnalyzer().assinatura_capacidade,
        PyMuPdfDocumentAnalyzer(tabela_glifos=tabela).assinatura_capacidade,
    }
    assert len(assinaturas) == 3


@pytest.mark.parametrize("erro", [FileNotFoundError, PermissionError, KeyError, RuntimeError])
def test_qualquer_falha_ao_carregar_o_pacote_desativa_a_leitura(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, erro: type[Exception]
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)

    def _quebra(_caminho: Path | None = None) -> TabelaGlifos:
        raise erro("falha ao carregar")

    monkeypatch.setattr(analyzer_module, "carregar_tabela_glifos", _quebra)
    analisador = PyMuPdfDocumentAnalyzer(tabela_glifos="pacote")

    resultado = analisador.analisar(_request(contorno))

    assert resultado.evidencias
    assert "analise.tabela_glifos_indisponivel" in _codigos(resultado)
    assert not _glifos(resultado)


def test_tabela_indisponivel_tambem_nao_derruba_a_leitura_do_modelo_e_do_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)

    def _quebra(_caminho: Path | None = None) -> TabelaGlifos:
        raise ValueError("sem tabela")

    monkeypatch.setattr(analyzer_module, "carregar_tabela_glifos", _quebra)
    analisador = PyMuPdfDocumentAnalyzer(tabela_glifos="pacote")

    # a assinatura é pedida antes da análise (chave de cache do caso de uso) e não pode levantar
    assert analisador.assinatura_capacidade
    assert analisador.assinatura_capacidade == analisador.assinatura_capacidade
    assert _analisar(contorno).evidencias


def test_tabela_empacotada_real_na_analise_conclui_sem_diagnostico_de_indisponivel(
    tmp_path: Path,
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    analisador = PyMuPdfDocumentAnalyzer(tabela_glifos="pacote")

    resultado = analisador.analisar(_request(contorno))

    assert "analise.tabela_glifos_indisponivel" not in _codigos(resultado)
    assert analisador._capacidade()["tabela_glifos"] == carregar_tabela_glifos().sha256
    assert any(e.tipo is TipoEvidencia.VETOR for e in resultado.evidencias)


# --- cache da análise ----------------------------------------------------------------------


def test_cache_da_analise_devolve_o_mesmo_texto_de_glifo_e_nao_cruza_tabelas(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    cache = JsonAnalysisCache(tmp_path / "cache-analise")
    outra = replace(tabela, sha256="0" * 64)

    primeira = _analisar(contorno, tabela_glifos=tabela, cache=cache)
    repetida = _analisar(contorno, tabela_glifos=tabela, cache=cache)
    com_outra_tabela = _analisar(contorno, tabela_glifos=outra, cache=cache)
    sem_tabela = _analisar(contorno, cache=cache)

    def conteudo(r: ResultadoAnaliseDocumento) -> list[tuple[Any, ...]]:
        return sorted(
            (e.conteudo_bruto, e.geometria.pontos, e.atributos_extraidos) for e in _glifos(r)
        )

    assert not primeira.cache_utilizado and repetida.cache_utilizado
    assert conteudo(primeira) and conteudo(repetida) == conteudo(primeira)
    assert not com_outra_tabela.cache_utilizado
    assert not sem_tabela.cache_utilizado and not _glifos(sem_tabela)


def test_leitura_de_glifos_que_falha_nao_grava_cache(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    cache = JsonAnalysisCache(tmp_path / "cache-analise")

    def _falha(*_args: object) -> object:
        raise RuntimeError("leitura de glifos quebrou")

    monkeypatch.setattr(pymupdf_glyph_text, "ler_texto_glifos", _falha)
    quebrada = _analisar(contorno, tabela_glifos=tabela, cache=cache)
    monkeypatch.undo()
    refeita = _analisar(contorno, tabela_glifos=tabela, cache=cache)

    assert "analise.texto_glifos_falhou" in _codigos(quebrada)
    assert not refeita.cache_utilizado
    assert len(_glifos(refeita)) == len(_LINHAS)


# --- cobertura em página com /Rotate e configuração -----------------------------------------


def _com_nativo_por_cima(
    tmp_path: Path, linhas: Sequence[LinhaTexto], nativas: Sequence[LinhaTexto], rotacao: int
) -> Path:
    """Contorno e texto nativo nos mesmos lugares, depois girados juntos pela página."""
    base = pdf_texto_contorno(tmp_path / "base.pdf", linhas)
    destino = tmp_path / "sobreposto.pdf"
    with pymupdf.open(base) as documento:
        pagina = documento[0]
        for linha in nativas:
            pagina.insert_text(linha.origem, linha.texto, fontsize=linha.tamanho, fontname="helv")
        pagina.set_rotation(rotacao)
        documento.save(destino)
    return destino


@pytest.mark.parametrize("rotacao_pagina", [0, 90, 180, 270])
def test_glifo_coberto_por_nativo_concordante_sai_em_pagina_com_rotate(
    tmp_path: Path, tabela: TabelaGlifos, rotacao_pagina: int
) -> None:
    pdf = _com_nativo_por_cima(tmp_path, _LINHAS, _LINHAS, rotacao_pagina)

    resultado = _analisar(pdf, tabela_glifos=tabela)

    assert not _glifos(resultado)
    assert sorted(e.conteudo_bruto or "" for e in _textos(resultado)) == sorted(
        linha.texto for linha in _LINHAS
    )


@pytest.mark.parametrize("rotacao_pagina", [90, 180, 270])
def test_glifo_so_parcialmente_coberto_por_nativo_fica_em_pagina_com_rotate(
    tmp_path: Path, tabela: TabelaGlifos, rotacao_pagina: int
) -> None:
    parcial = [LinhaTexto("11", (40.0, 120.0), 5.0)]
    pdf = _com_nativo_por_cima(tmp_path, _LINHAS[:2], [_LINHAS[0], *parcial], rotacao_pagina)

    resultado = _analisar(pdf, tabela_glifos=tabela)

    assert [e.conteudo_bruto for e in _glifos(resultado)] == ["11-300"]


class _OcrFixo:
    nome = "ocr-fixo"

    def __init__(self, texto: str, caixa: tuple[float, float, float, float]) -> None:
        self._texto = texto
        self._caixa = caixa

    def consultar_capacidade(self) -> ResultadoConsultaCapacidadeOcr:
        return ResultadoConsultaCapacidadeOcr(
            capacidade=CapacidadeMotorOcr(
                implementacao=self.nome,
                versao="1",
                idiomas=("eng",),
                dados_treinados=(IdentidadeDadosTreinadosOcr(idioma="eng", sha256="1" * 64),),
                parametros=(("oem", 3),),
            )
        )

    def reconhecer(self, _pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]:
        return (TrechoTextoOcr(texto=self._texto, caixa_normalizada=self._caixa, confianca=0.9),)


@pytest.mark.parametrize("rotacao_pagina", [90, 180, 270])
@pytest.mark.parametrize(("lido", "glifo_fica"), [("P7 U4(1)", False), ("P1 U4(1)", True)])
def test_ocr_sobre_o_glifo_segue_a_regra_de_cobertura_em_pagina_com_rotate(
    tmp_path: Path, tabela: TabelaGlifos, rotacao_pagina: int, lido: str, glifo_fica: bool
) -> None:
    linhas = [LinhaTexto("P7 U4(1)", (60.0, 120.0), 5.0)]
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", linhas, rotacao_pagina=rotacao_pagina)
    (glifo,) = _glifos(_analisar(contorno, tabela_glifos=tabela))
    xs = [float(p.x) for p in glifo.geometria.pontos]
    ys = [float(p.y) for p in glifo.geometria.pontos]
    caixa = (min(xs) - 0.002, min(ys) - 0.002, max(xs) + 0.002, max(ys) + 0.002)

    resultado = _analisar(
        contorno,
        ConfiguracaoAnaliseDocumento(),
        tabela_glifos=tabela,
        motor_ocr=_OcrFixo(lido, caixa),
    )

    assert [e.conteudo_bruto for e in resultado.evidencias if e.tipo is TipoEvidencia.OCR] == [lido]
    assert [e.conteudo_bruto for e in _glifos(resultado)] == (["P7 U4(1)"] if glifo_fica else [])


def test_sem_extrair_texto_nao_le_glifos(tmp_path: Path, tabela: TabelaGlifos) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)

    resultado = _analisar(
        contorno,
        ConfiguracaoAnaliseDocumento(extrair_texto=False, habilitar_ocr_condicional=False),
        tabela_glifos=tabela,
    )

    assert not _textos(resultado)
    assert not any(c.startswith("analise.glifos") for c in _codigos(resultado))
    assert any(e.tipo is TipoEvidencia.VETOR for e in resultado.evidencias)


def test_tabela_indisponivel_emite_o_diagnostico_uma_vez_por_analise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)

    def _quebra(_caminho: Path | None = None) -> TabelaGlifos:
        raise ValueError("sem tabela")

    monkeypatch.setattr(analyzer_module, "carregar_tabela_glifos", _quebra)
    analisador = PyMuPdfDocumentAnalyzer(tabela_glifos="pacote")

    for _ in range(2):
        resultado = analisador.analisar(_request(contorno))
        assert _codigos(resultado).count("analise.tabela_glifos_indisponivel") == 1


# --- native_characters sem glifo ------------------------------------------------------------


def test_texto_nativo_curto_ao_lado_de_glifos_decide_o_ocr_so_pelo_nativo(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    misto = tmp_path / "misto.pdf"
    with pymupdf.open(contorno) as documento:
        documento[0].insert_text((40.0, 260.0), "NOTA", fontsize=8)
        documento.save(misto)
    vistos: list[int] = []
    original = _conditional_ocr

    def _espiao(*args: Any) -> Any:
        vistos.append(args[4])
        return original(*args)

    monkeypatch.setattr(analyzer_module, "_conditional_ocr", _espiao)

    _analisar(
        misto, ConfiguracaoAnaliseDocumento(habilitar_ocr_condicional=True), tabela_glifos=tabela
    )

    assert vistos == [len("NOTA")]


# --- regra de cobertura: casos de borda ----------------------------------------------------

_ALTURA = 0.02
_LARGURA_GLIFO = 0.012
_CONTORNOS = "tesseract-contornos-vetoriais"


def _texto_glifo(texto: str, x: float, y: float = 0.30) -> TextoGlifo:
    glifos: list[tuple[str, Caixa]] = []
    for posicao, caractere in enumerate(texto):
        if caractere == " ":
            continue
        x0 = x + posicao * (_LARGURA_GLIFO + 0.004)
        glifos.append((caractere, (x0, y, x0 + _LARGURA_GLIFO, y + _ALTURA)))
    x1 = glifos[-1][1][2]
    cantos = ((x, y + _ALTURA), (x1, y + _ALTURA), (x1, y), (x, y))
    return TextoGlifo(
        texto, (x, y, x1, y + _ALTURA), cantos, 0.0, _ALTURA, len(glifos), None, tuple(glifos)
    )


def _leitura(
    texto: str | None,
    caixa: Caixa,
    *,
    motor: str = "tesseract-pagina",
    chave: str = "ocr",
    tipo: TipoEvidencia = TipoEvidencia.OCR,
) -> CandidatoEvidenciaDocumento:
    x0, y0, x1, y1 = (Decimal(str(round(v, 6))) for v in caixa)
    return CandidatoEvidenciaDocumento(
        chave_estavel=f"p1:{chave}",
        pagina_numero=1,
        tipo=tipo,
        geometria=GeometriaNormalizada(
            tipo=TipoGeometria.CAIXA,
            pontos=(PontoNormalizado(x0, y0), PontoNormalizado(x1, y1)),
        ),
        origem_pdf=OrigemObjetoPdf(),
        conteudo_bruto=texto,
        atributos_extraidos=(("motor_ocr", motor),),
    )


def _caixa(texto: TextoGlifo, inicio: int, fim: int) -> Caixa:
    caixas = [c for _, c in texto.glifos[inicio:fim]]
    return (
        min(c[0] for c in caixas),
        min(c[1] for c in caixas),
        max(c[2] for c in caixas),
        max(c[3] for c in caixas),
    )


_A = _texto_glifo("P7 U4(1)", 0.10)
_B = _texto_glifo("11-300", 0.30)


def test_dois_fragmentos_concordantes_que_cobrem_o_glifo_inteiro_deixam_o_ocr_e_tiram_o_glifo() -> (
    None
):
    p7 = _leitura("P7", _caixa(_A, 0, 2), chave="a")
    u4 = _leitura("U4(1)", _caixa(_A, 2, 7), chave="b")

    cobertura = _resolver_cobertura([p7, u4], [_A])

    assert cobertura.mantidos == (p7, u4)
    assert cobertura.glifos == ()
    assert cobertura.divergentes == 0


def test_dois_fragmentos_concordantes_que_deixam_um_glifo_de_fora_saem_e_o_glifo_fica() -> None:
    p7 = _leitura("P7", _caixa(_A, 0, 2), chave="a")
    u4 = _leitura("U4", _caixa(_A, 2, 4), chave="b")

    cobertura = _resolver_cobertura([p7, u4], [_A])

    assert cobertura.mantidos == ()
    assert cobertura.glifos == (0,)
    assert cobertura.divergentes == 0


def test_fragmento_errado_dentro_do_glifo_nao_apaga_nada_e_conta_divergencia() -> None:
    errado = _leitura("P1", _caixa(_A, 0, 2))

    cobertura = _resolver_cobertura([errado], [_A])

    assert cobertura.mantidos == (errado,)
    assert cobertura.glifos == (0,)
    assert cobertura.divergentes == 1


def test_fragmento_errado_do_motor_de_contornos_tambem_fica_e_conta() -> None:
    errado = _leitura("P1", _caixa(_A, 0, 2), motor=_CONTORNOS)

    cobertura = _resolver_cobertura([errado], [_A])

    assert cobertura.mantidos == (errado,)
    assert cobertura.glifos == (0,)
    assert cobertura.divergentes == 1


def test_leitura_certa_e_leitura_errada_sobre_o_mesmo_glifo_so_a_certa_e_tratada() -> None:
    certa = _leitura("P7 U4(1)", _caixa(_A, 0, 7), chave="certa")
    errada = _leitura("P1", _caixa(_A, 0, 2), chave="errada")

    cobertura = _resolver_cobertura([certa, errada], [_A])

    assert cobertura.mantidos == (certa, errada)
    assert cobertura.glifos == ()
    assert cobertura.divergentes == 1


@pytest.mark.parametrize("conteudo", [None, ""])
def test_leitura_sem_texto_e_ignorada(conteudo: str | None) -> None:
    vazia = _leitura(conteudo, _caixa(_A, 0, 7))

    cobertura = _resolver_cobertura([vazia], [_A])

    assert cobertura.mantidos == (vazia,)
    assert cobertura.glifos == (0,)
    assert cobertura.divergentes == 0


def test_leitura_so_de_espacos_e_ignorada_como_a_vazia() -> None:
    vazia = _leitura("   ", _caixa(_A, 0, 7))

    cobertura = _resolver_cobertura([vazia], [_A])

    assert cobertura.mantidos == (vazia,)
    assert cobertura.glifos == (0,)
    assert cobertura.divergentes == 0


@pytest.mark.parametrize(
    "conteudo",
    ["\u00a0", "\u2003\u3000", "\n", "\t", " \r\n\t "],
    ids=["nbsp", "espacos-unicode", "quebra", "tab", "mistura"],
)
def test_leitura_so_de_espacos_nao_ascii_quebra_ou_tab_nao_conta_divergencia(
    conteudo: str,
) -> None:
    vazia = _leitura(conteudo, _caixa(_A, 0, 7))

    cobertura = _resolver_cobertura([vazia], [_A])

    assert cobertura.mantidos == (vazia,)
    assert cobertura.glifos == (0,)
    assert cobertura.divergentes == 0


def test_sem_leituras_ou_sem_glifos_nada_muda() -> None:
    leitura = _leitura("X", (0.7, 0.7, 0.72, 0.72))

    assert _resolver_cobertura([], [_A]).glifos == (0,)
    sem_glifos = _resolver_cobertura([leitura], [])
    assert (
        sem_glifos.mantidos == (leitura,)
        and sem_glifos.glifos == ()
        and sem_glifos.divergentes == 0
    )


def test_resultado_da_cobertura_nao_depende_da_ordem_das_leituras() -> None:
    caixa = (
        min(_caixa(_A, 0, 7)[0], _caixa(_B, 0, 6)[0]),
        _caixa(_A, 0, 7)[1],
        _caixa(_B, 0, 6)[2],
        _caixa(_A, 0, 7)[3],
    )
    leituras = [
        _leitura("P7 U4(1) 11-300", caixa, chave="linha"),
        _leitura("N1", (0.7, 0.7, 0.72, 0.72), chave="fora"),
        _leitura("P1", _caixa(_A, 0, 2), chave="errada"),
    ]

    a = _resolver_cobertura(leituras, [_A, _B])
    b = _resolver_cobertura(list(reversed(leituras)), [_B, _A])

    assert {c.chave_estavel for c in a.mantidos} == {c.chave_estavel for c in b.mantidos}
    assert a.divergentes == b.divergentes
    assert [(_A, _B)[i].texto for i in a.glifos] == [(_B, _A)[i].texto for i in b.glifos]


def test_cobertura_nativa_com_superconjunto_tira_os_dois_glifos_e_mantem_o_nativo() -> None:
    caixa = (
        _caixa(_A, 0, 7)[0],
        _caixa(_A, 0, 7)[1],
        _caixa(_B, 0, 6)[2],
        _caixa(_A, 0, 7)[3],
    )
    nativo = _leitura("P7 U4(1) 11-300", caixa, tipo=TipoEvidencia.TEXTO)

    cobertura = _resolver_cobertura([nativo], [_A, _B], nativo=True)

    assert cobertura.mantidos == (nativo,)
    assert cobertura.glifos == ()
    assert cobertura.divergentes == 0


def test_cobertura_nativa_divergente_mantem_o_glifo_sem_contar() -> None:
    nativo = _leitura("P1 U4(1)", _caixa(_A, 0, 7), tipo=TipoEvidencia.TEXTO)

    cobertura = _resolver_cobertura([nativo], [_A], nativo=True)

    assert cobertura.mantidos == (nativo,)
    assert cobertura.glifos == (0,)
    assert cobertura.divergentes == 0


def test_cobertura_nativa_de_fragmento_nao_tira_o_glifo() -> None:
    nativo = _leitura("U4(1)", _caixa(_A, 2, 7), tipo=TipoEvidencia.TEXTO)

    cobertura = _resolver_cobertura([nativo], [_A], nativo=True)

    assert cobertura.mantidos == (nativo,)
    assert cobertura.glifos == (0,)


@pytest.mark.parametrize("rotacao_pagina", [0, 90, 180, 270])
@pytest.mark.parametrize("rotacao_linha", [0.0, 90.0])
def test_ocr_de_linha_cobre_dois_glifos_em_qualquer_rotacao(
    tmp_path: Path, tabela: TabelaGlifos, rotacao_pagina: int, rotacao_linha: float
) -> None:
    linhas = [
        LinhaTexto("P7 U4(1)", (80.0, 150.0), 5.0, rotacao_linha),
        LinhaTexto("11-300", (80.0, 150.0), 5.0, rotacao_linha),
    ]
    # as duas linhas na mesma base: o segundo texto começa onde o primeiro termina
    linhas = [
        replace(linhas[0], origem=(80.0, 150.0)),
        replace(
            linhas[1], origem=(80.0 + 28.0, 150.0) if rotacao_linha == 0.0 else (80.0, 150.0 - 28.0)
        ),
    ]
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", linhas, rotacao_pagina=rotacao_pagina)
    with pymupdf.open(contorno) as documento:
        lidos = ler_glifos_da_pagina(documento[0], 1, tabela)
    assert sorted(t.texto for t in lidos.textos) == sorted(["P7 U4(1)", "11-300"]), lidos.textos

    caixas = [t.bbox for t in lidos.textos]
    uniao = (
        min(c[0] for c in caixas),
        min(c[1] for c in caixas),
        max(c[2] for c in caixas),
        max(c[3] for c in caixas),
    )
    # ordem de leitura = ordem em que os textos aparecem ao longo da direção do primeiro
    (ax, ay), (bx, by) = lidos.textos[0].cantos[:2]
    projecao = {
        t.texto: (t.cantos[0][0] * (bx - ax) + t.cantos[0][1] * (by - ay)) for t in lidos.textos
    }
    ordem = sorted(projecao, key=lambda texto: projecao[texto])
    ocr = _leitura(" ".join(ordem), uniao)

    cobertura = _resolver_cobertura([ocr], list(lidos.textos))

    assert cobertura.mantidos == (ocr,)
    assert cobertura.glifos == ()
    assert cobertura.divergentes == 0


# --- cache do modelo v2 --------------------------------------------------------------------


def _salvar_modelo(
    cache: JsonDrawingModelCache, pdf: Path, tabela: TabelaGlifos | None
) -> tuple[str, Path]:
    modelo = extrair_modelo_desenho(pdf, tabela)
    leitor = f"pymupdf-{pymupdf.VersionBind}"
    if tabela is not None:
        leitor += f":glifos-{tabela.sha256}"
    chave = chave_modelo_desenho(modelo.documento_sha256, leitor)
    cache.salvar(chave, modelo)
    return chave, cache._alvo(chave)


def test_cache_de_modelo_v1_antigo_e_ignorado_e_o_modelo_e_reextraido(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    cache = JsonDrawingModelCache(tmp_path / "cache")
    chave, arquivo = _salvar_modelo(cache, pdf, tabela)
    envelope = json.loads(arquivo.read_text(encoding="utf-8"))
    envelope["modelo"]["versao"] = "modelo-desenho-v1"
    # um v1 não tinha texto de glifo
    for pagina in envelope["modelo"]["paginas"]:
        pagina["textos"] = []
    arquivo.write_text(json.dumps(envelope), encoding="utf-8")

    assert cache.obter(chave) is None
    modelo = obter_modelo_desenho(pdf, cache, tabela)

    assert modelo.versao == VERSAO_MODELO_DESENHO == "modelo-desenho-v2"
    assert {t.origem for t in modelo.paginas[0].textos} == {"glifo"}
    assert cache.obter(chave) is not None


def test_cache_com_origem_de_texto_desconhecida_vale_como_ausente(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    cache = JsonDrawingModelCache(tmp_path / "cache")
    _, arquivo = _salvar_modelo(cache, pdf, tabela)
    arquivo.write_text(
        arquivo.read_text(encoding="utf-8").replace('"glifo"', '"glyph"'), encoding="utf-8"
    )

    modelo = obter_modelo_desenho(pdf, cache, tabela)

    assert {t.origem for t in modelo.paginas[0].textos} == {"glifo"}


def test_modelo_do_cache_sem_tabela_nao_devolve_texto_de_glifo_gravado_com_tabela(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    cache = JsonDrawingModelCache(tmp_path / "cache")
    com_tabela = obter_modelo_desenho(pdf, cache, tabela)

    sem_tabela = obter_modelo_desenho(pdf, cache, None)
    de_novo = obter_modelo_desenho(pdf, cache, tabela)

    assert com_tabela.paginas[0].textos
    assert sem_tabela.paginas[0].textos == ()
    assert de_novo == com_tabela


def test_pagina_sem_glifos_nao_gera_diagnostico_de_glifos_no_modelo(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    nativo = pdf_texto_nativo(tmp_path / "n.pdf", _LINHAS)

    (pagina,) = extrair_modelo_desenho(nativo, tabela).paginas

    assert not any(d.startswith("modelo.glifos") for d in pagina.diagnosticos)
    assert {t.origem for t in pagina.textos} == {"nativo"}


# --- scripts e fronteiras ------------------------------------------------------------------


def _chamadas(script: str, nome: str) -> list[ast.Call]:
    arvore = ast.parse((_RAIZ / "scripts" / script).read_text(encoding="utf-8"))
    return [
        n
        for n in ast.walk(arvore)
        if isinstance(n, ast.Call)
        and (getattr(n.func, "id", None) == nome or getattr(n.func, "attr", None) == nome)
    ]


@pytest.mark.parametrize("script", ["smoke_examples.py", "benchmark_network_pdf.py"])
def test_scripts_de_medicao_constroem_o_analisador_com_a_tabela_do_pacote(script: str) -> None:
    chamadas = _chamadas(script, "PyMuPdfDocumentAnalyzer")

    assert chamadas
    for chamada in chamadas:
        palavras = {k.arg: k.value for k in chamada.keywords}
        valor = palavras.get("tabela_glifos")
        assert isinstance(valor, ast.Constant) and valor.value == "pacote"


@pytest.mark.parametrize("script", ["drawing_model_dxf.py", "drawing_model_report.py"])
def test_scripts_do_modelo_carregam_a_tabela_empacotada(script: str) -> None:
    fonte = (_RAIZ / "scripts" / script).read_text(encoding="utf-8")

    assert _chamadas(script, "carregar_tabela_glifos")
    assert "obter_modelo_desenho" in fonte or "extrair_modelo_desenho" in fonte


def test_composicao_do_servidor_passa_a_tabela_do_pacote() -> None:
    arvore = ast.parse(
        (_RAIZ / "src" / "zeny_project_handler_server" / "composition.py").read_text(
            encoding="utf-8"
        )
    )
    chamadas = [
        n
        for n in ast.walk(arvore)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "PyMuPdfDocumentAnalyzer"
    ]

    assert chamadas
    for chamada in chamadas:
        palavras = {k.arg: k.value for k in chamada.keywords}
        valor = palavras.get("tabela_glifos")
        assert isinstance(valor, ast.Constant) and valor.value == "pacote"


def test_dominio_e_aplicacao_nao_importam_o_leitor_de_glifos_nem_pymupdf() -> None:
    proibidos = {"pymupdf", "fitz", "pymupdf_glyph_text", "pymupdf_drawing_model"}
    base = _RAIZ / "src" / "zeny_project_handler"
    for pasta in ("domain", "application", "ports"):
        for arquivo in (base / pasta).rglob("*.py"):
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
            importados: set[str] = set()
            for no in ast.walk(arvore):
                if isinstance(no, ast.Import):
                    importados.update(a.name.split(".")[-1] for a in no.names)
                    importados.update(a.name.split(".")[0] for a in no.names)
                elif isinstance(no, ast.ImportFrom) and no.module:
                    importados.update(no.module.split("."))
                    importados.update(a.name for a in no.names)
            assert not importados & proibidos, (arquivo, importados & proibidos)
