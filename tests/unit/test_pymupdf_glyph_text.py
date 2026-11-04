# mypy: disable-error-code="no-untyped-call"
"""Texto de glifo como evidência do analisador PyMuPDF, sobre PDFs sintéticos de fonte livre."""

from __future__ import annotations

import dataclasses
import math
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
    PyMuPdfDocumentAnalyzer,
    pymupdf_drawing_model,
    pymupdf_glyph_text,
)
from zeny_project_handler.adapters.analysis import pymupdf_analyzer as analyzer_module
from zeny_project_handler.adapters.analysis.drawing_model import glyph_text
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import TabelaGlifos
from zeny_project_handler.adapters.analysis.drawing_model.glyph_text import TextoGlifo
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    VERSAO_MODELO_DESENHO,
    Caixa,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import extrair_modelo_desenho
from zeny_project_handler.adapters.analysis.pymupdf_glyph_text import (
    _resolver_cobertura,
    candidatos_texto_glifos,
)
from zeny_project_handler.adapters.analysis.pymupdf_ocr import _conditional_ocr
from zeny_project_handler.adapters.analysis.pymupdf_revisions import extract_revision_appearances
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.application.method_reconciliation import reconcile_readings
from zeny_project_handler.domain.analysis import EvidenciaDocumento, OrigemObjetoPdf
from zeny_project_handler.domain.enums import TipoEvidencia, TipoGeometria
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ports.analysis import (
    CandidatoEvidenciaDocumento,
    CapacidadeMotorOcr,
    ConfiguracaoAnaliseDocumento,
    ExtracaoDocumentoNormalizada,
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


@pytest.fixture(scope="module")
def tabela(tmp_path_factory: pytest.TempPathFactory) -> TabelaGlifos:
    return tabela_do_alfabeto(tmp_path_factory.mktemp("alfabeto-analisador"))


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
    pdf: Path,
    configuracao: ConfiguracaoAnaliseDocumento = _SEM_OCR,
    **kwargs: Any,
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


def _diferenca_angular(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _assert_pareados(
    contorno: Sequence[EvidenciaDocumento], nativos: Sequence[EvidenciaDocumento]
) -> None:
    assert Counter(e.conteudo_bruto for e in contorno) == Counter(e.conteudo_bruto for e in nativos)
    for lido in contorno:
        (nativo,) = (n for n in nativos if n.conteudo_bruto == lido.conteudo_bruto)
        assert math.dist(_centro(lido), _centro(nativo)) <= 0.01
        assert _diferenca_angular(_rotacao(lido), _rotacao(nativo)) <= 2.0


def _par(
    tmp_path: Path, linhas: Sequence[LinhaTexto], rotacao_pagina: int = 0
) -> tuple[Path, Path]:
    nativo = pdf_texto_nativo(tmp_path / "nativo.pdf", linhas, rotacao_pagina=rotacao_pagina)
    contorno = pdf_texto_contorno(tmp_path / "contorno.pdf", linhas, rotacao_pagina=rotacao_pagina)
    return nativo, contorno


@pytest.mark.parametrize("rotacao", [0.0, 90.0, 30.0])
def test_texto_em_contorno_da_fonte_livre_le_igual_ao_nativo(
    tmp_path: Path, tabela: TabelaGlifos, rotacao: float
) -> None:
    linhas = [
        replace(
            linha, rotacao=rotacao, origem=(100.0 + 90.0 * i, 250.0) if rotacao else linha.origem
        )
        for i, linha in enumerate(_LINHAS)
    ]
    nativo, contorno = _par(tmp_path, linhas)

    lido = _analisar(contorno, tabela_glifos=tabela)
    referencia = _analisar(nativo, tabela_glifos=tabela)

    assert _textos(lido) == _glifos(lido)
    assert not _glifos(referencia)
    _assert_pareados(_glifos(lido), _textos(referencia))
    for evidencia in _glifos(lido):
        atributos = dict(evidencia.atributos_extraidos)
        assert evidencia.geometria.tipo is TipoGeometria.POLIGONO
        assert atributos["tabela_glifos"] == tabela.versao
        assert atributos["tabela_glifos_sha256"] == tabela.sha256
        assert atributos["quantidade_glifos"] == len(
            (evidencia.conteudo_bruto or "").replace(" ", "")
        )
        assert atributos["cor"] == "#000000"
        assert isinstance(atributos["altura"], Decimal) and atributos["altura"] > 0
        assert isinstance(atributos["rotacao_graus"], Decimal)


def test_pagina_com_rotate_90_posiciona_igual_ao_nativo(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    linhas = [LinhaTexto("P10 N1", (60.0, 80.0), 5.0), LinhaTexto("11-300", (60.0, 200.0), 5.0)]
    nativo, contorno = _par(tmp_path, linhas, rotacao_pagina=90)

    _assert_pareados(_glifos(_analisar(contorno, tabela_glifos=tabela)), _textos(_analisar(nativo)))

    (pagina_glifo,) = extrair_modelo_desenho(contorno, tabela).paginas
    (pagina_nativa,) = extrair_modelo_desenho(nativo).paginas
    assert {t.origem for t in pagina_glifo.textos} == {"glifo"}
    assert sorted(t.texto for t in pagina_glifo.textos) == sorted(
        t.texto for t in pagina_nativa.textos
    )
    for texto in pagina_glifo.textos:
        (referencia,) = (t for t in pagina_nativa.textos if t.texto == texto.texto)
        centros = [
            (
                (c.bbox[0] + c.bbox[2]) / 2 / pagina_glifo.largura,
                (c.bbox[1] + c.bbox[3]) / 2 / pagina_glifo.altura,
            )
            for c in (texto, referencia)
        ]
        assert math.dist(*centros) <= 0.01
        assert _diferenca_angular(texto.rotacao, referencia.rotacao) <= 2.0


def test_glifo_ausente_gera_diagnostico_e_nao_produz_caractere(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    sem_tres = dataclasses.replace(
        tabela, glifos=tuple(g for g in tabela.glifos if g.caractere != "3")
    )
    contorno = pdf_texto_contorno(
        tmp_path / "c.pdf",
        [LinhaTexto("P7", (40.0, 60.0), 5.0), LinhaTexto("11-300", (40.0, 120.0), 5.0)],
    )

    resultado = _analisar(contorno, tabela_glifos=sem_tres)

    assert "analise.glifos_desconhecidos" in _codigos(resultado)
    assert [e.conteudo_bruto for e in _glifos(resultado)] == ["P7"]
    assert not any("11-" in (e.conteudo_bruto or "") for e in resultado.evidencias)
    (diagnostico,) = (
        d for d in resultado.diagnosticos if d.codigo == "analise.glifos_desconhecidos"
    )
    assert diagnostico.extrator == "texto_glifos" and diagnostico.pagina_numero == 1


def test_tabela_do_pacote_indisponivel_desativa_com_diagnostico(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)

    def _ausente(_caminho: Path | None = None) -> TabelaGlifos:
        raise ValueError("Tabela de glifos indisponível: sem arquivo.")

    monkeypatch.setattr(analyzer_module, "carregar_tabela_glifos", _ausente)
    analisador = PyMuPdfDocumentAnalyzer(tabela_glifos="pacote")

    resultado = analisador.analisar(_request(contorno))

    assert "analise.tabela_glifos_indisponivel" in _codigos(resultado)
    assert str(analisador._capacidade()["tabela_glifos"]).startswith("indisponivel:")
    assert not _glifos(resultado)
    assert any(e.tipo is TipoEvidencia.VETOR for e in resultado.evidencias)
    assert PyMuPdfDocumentAnalyzer()._capacidade()["tabela_glifos"] == "desativada"


def test_tabela_do_pacote_carrega_na_primeira_analise(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    chamadas: list[Path | None] = []

    def _carregar(caminho: Path | None = None) -> TabelaGlifos:
        chamadas.append(caminho)
        return tabela

    monkeypatch.setattr(analyzer_module, "carregar_tabela_glifos", _carregar)
    analisador = PyMuPdfDocumentAnalyzer(tabela_glifos="pacote")
    assert chamadas == []

    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    resultado = analisador.analisar(_request(contorno))
    analisador.analisar(_request(contorno))

    assert chamadas == [None]
    assert analisador._capacidade()["tabela_glifos"] == tabela.sha256
    assert len(_glifos(resultado)) == len(_LINHAS)


def test_pagina_com_glifos_demais_tem_teto(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    monkeypatch.setattr(glyph_text, "LIMITE_GLIFOS_PAGINA", 3)

    resultado = _analisar(contorno, tabela_glifos=tabela)

    assert "analise.glifos_limitados" in _codigos(resultado)
    assert not _glifos(resultado)
    assert any(e.tipo is TipoEvidencia.VETOR for e in resultado.evidencias)


def _pdf_misto(tmp_path: Path) -> Path:
    """Glifos em contorno, texto nativo e um traço na mesma página."""
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    destino = tmp_path / "misto.pdf"
    with pymupdf.open(contorno) as documento:
        pagina = documento[0]
        pagina.insert_text((40.0, 260.0), "NOTA NATIVA", fontsize=8)
        pagina.draw_line((20, 280), (380, 280), color=(0, 0, 1), width=1)
        documento.save(destino)
    return destino


def test_leitura_de_glifos_que_falha_nao_derruba_a_pagina(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf_misto(tmp_path)

    def _falha(*_args: object) -> object:
        raise RuntimeError("leitura de glifos quebrou")

    monkeypatch.setattr(pymupdf_glyph_text, "ler_texto_glifos", _falha)

    resultado = _analisar(pdf, tabela_glifos=tabela)

    assert "analise.texto_glifos_falhou" in _codigos(resultado)
    assert [e.conteudo_bruto for e in _textos(resultado)] == ["NOTA NATIVA"]
    assert any(e.tipo is TipoEvidencia.VETOR for e in resultado.evidencias)


def test_glifo_nao_conta_como_texto_nativo_para_o_ocr(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    vistos: list[int] = []
    original = _conditional_ocr

    def _espiao(*args: Any) -> Any:
        vistos.append(args[4])
        return original(*args)

    monkeypatch.setattr(analyzer_module, "_conditional_ocr", _espiao)

    resultado = _analisar(
        contorno, ConfiguracaoAnaliseDocumento(habilitar_ocr_condicional=True), tabela_glifos=tabela
    )

    assert vistos == [0]
    assert len(_glifos(resultado)) == len(_LINHAS)
    assert "analise.ocr_indisponivel" in _codigos(resultado)


# --- cobertura OCR x glifo (função pura, coordenadas normalizadas) -------------------------

_ALTURA = 0.02
_LARGURA_GLIFO = 0.012


def _texto_glifo(texto: str, x: float, y: float = 0.30) -> TextoGlifo:
    """Texto de glifo horizontal à mão: um glifo por caractere sem espaço, espaço = uma casa."""
    glifos: list[tuple[str, Caixa]] = []
    for posicao, caractere in enumerate(texto):
        if caractere == " ":
            continue
        x0 = x + posicao * (_LARGURA_GLIFO + 0.004)
        glifos.append((caractere, (x0, y, x0 + _LARGURA_GLIFO, y + _ALTURA)))
    x1 = glifos[-1][1][2]
    bbox = (x, y, x1, y + _ALTURA)
    cantos = ((x, y + _ALTURA), (x1, y + _ALTURA), (x1, y), (x, y))
    return TextoGlifo(texto, bbox, cantos, 0.0, _ALTURA, len(glifos), None, tuple(glifos))


def _ocr(
    texto: str,
    caixa: Caixa,
    motor: str = "tesseract-pagina",
    chave: str = "ocr",
) -> CandidatoEvidenciaDocumento:
    x0, y0, x1, y1 = (Decimal(str(round(v, 6))) for v in caixa)
    return CandidatoEvidenciaDocumento(
        chave_estavel=f"p1:{chave}",
        pagina_numero=1,
        tipo=TipoEvidencia.OCR,
        geometria=GeometriaNormalizada(
            tipo=TipoGeometria.CAIXA,
            pontos=(PontoNormalizado(x0, y0), PontoNormalizado(x1, y1)),
        ),
        origem_pdf=OrigemObjetoPdf(),
        conteudo_bruto=texto,
        atributos_extraidos=(("motor_ocr", motor),),
    )


def _caixa_dos_glifos(texto: TextoGlifo, inicio: int, fim: int, folga: float = 0.0) -> Caixa:
    caixas = [caixa for _, caixa in texto.glifos[inicio:fim]]
    x0, y0 = min(c[0] for c in caixas), min(c[1] for c in caixas)
    x1, y1 = max(c[2] for c in caixas), max(c[3] for c in caixas)
    dx, dy = (x1 - x0) * folga, (y1 - y0) * folga
    return (x0 - dx, y0 - dy, x1 + dx, y1 + dy)


def _uniao(a: Caixa, b: Caixa) -> Caixa:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


_A = _texto_glifo("P7 U4(1)", 0.10)
_B = _texto_glifo("11-300", 0.30)
_CONTORNOS = "tesseract-contornos-vetoriais"


def _caso_fragmento() -> tuple[list[CandidatoEvidenciaDocumento], list[TextoGlifo]]:
    return [_ocr("P7", _caixa_dos_glifos(_A, 0, 2))], [_A]


def _caso_total() -> tuple[list[CandidatoEvidenciaDocumento], list[TextoGlifo]]:
    return [_ocr("P7 U4(1)", _caixa_dos_glifos(_A, 0, 7, folga=0.1))], [_A]


def _caso_superconjunto() -> tuple[list[CandidatoEvidenciaDocumento], list[TextoGlifo]]:
    caixa = _uniao(_caixa_dos_glifos(_A, 0, 7), _caixa_dos_glifos(_B, 0, 6))
    return [_ocr("P7 U4(1) 11-300", caixa)], [_A, _B]


def _caso_contornos_igual() -> tuple[list[CandidatoEvidenciaDocumento], list[TextoGlifo]]:
    return [_ocr("P7 U4(1)", _caixa_dos_glifos(_A, 0, 7), _CONTORNOS)], [_A]


def _caso_contornos_fragmento() -> tuple[list[CandidatoEvidenciaDocumento], list[TextoGlifo]]:
    return [_ocr("P7", _caixa_dos_glifos(_A, 0, 2), _CONTORNOS)], [_A]


def _caso_superconjunto_parcial() -> tuple[list[CandidatoEvidenciaDocumento], list[TextoGlifo]]:
    caixa = _uniao(_caixa_dos_glifos(_A, 0, 7), _caixa_dos_glifos(_B, 0, 3))
    return [_ocr("P7 U4(1) 11-", caixa)], [_A, _B]


def _caso_divergencia() -> tuple[list[CandidatoEvidenciaDocumento], list[TextoGlifo]]:
    p7 = _texto_glifo("P7", 0.10)
    return [_ocr("P1", _caixa_dos_glifos(p7, 0, 2))], [p7]


def _caso_fora() -> tuple[list[CandidatoEvidenciaDocumento], list[TextoGlifo]]:
    return [_ocr("N1", (0.70, 0.70, 0.75, 0.72))], [_A]


@pytest.mark.parametrize(
    ("caso", "ocr_fica", "glifos_ficam", "divergentes"),
    [
        (_caso_fragmento, False, (0,), 0),
        (_caso_total, True, (), 0),
        (_caso_superconjunto, True, (), 0),
        (_caso_contornos_igual, True, (), 0),
        (_caso_contornos_fragmento, True, (0,), 0),
        (_caso_superconjunto_parcial, True, (1,), 0),
        (_caso_divergencia, True, (0,), 1),
        (_caso_fora, True, (0,), 0),
    ],
    ids=[
        "fragmento",
        "cobertura-total",
        "superconjunto",
        "contornos-igual",
        "contornos-fragmento",
        "superconjunto-parcial",
        "divergencia",
        "fora",
    ],
)
def test_cobertura_ocr_x_glifo(
    caso: Any, ocr_fica: bool, glifos_ficam: tuple[int, ...], divergentes: int
) -> None:
    ocr, glifos = caso()

    cobertura = _resolver_cobertura(ocr, glifos)

    assert cobertura.mantidos == (tuple(ocr) if ocr_fica else ())
    assert cobertura.glifos == glifos_ficam
    assert cobertura.divergentes == divergentes


def _texto_diagonal(texto: str, origem: tuple[float, float], angulo: float) -> TextoGlifo:
    """Texto de glifo girado (graus horários visuais), um glifo a cada 0,04 ao longo da linha."""
    dx, dy = math.cos(math.radians(angulo)), math.sin(math.radians(angulo))
    ux, uy = dy, -dx  # "para cima" do texto, com y para baixo
    meio, passo = 0.006, 0.04
    centros = [(origem[0] + i * passo * dx, origem[1] + i * passo * dy) for i in range(len(texto))]
    glifos = tuple(
        (c, (x - meio / 2, y - meio / 2, x + meio / 2, y + meio / 2))
        for c, (x, y) in zip(texto, centros, strict=True)
    )
    (x0, y0), (x1, y1) = centros[0], centros[-1]
    inicio_base = (x0 - dx * meio - ux * meio, y0 - dy * meio - uy * meio)
    fim_base = (x1 + dx * meio - ux * meio, y1 + dy * meio - uy * meio)
    fim_topo = (fim_base[0] + 2 * ux * meio, fim_base[1] + 2 * uy * meio)
    inicio_topo = (inicio_base[0] + 2 * ux * meio, inicio_base[1] + 2 * uy * meio)
    cantos = (inicio_base, fim_base, fim_topo, inicio_topo)
    xs, ys = [p[0] for p in cantos], [p[1] for p in cantos]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    return TextoGlifo(texto, bbox, cantos, angulo, 2 * meio, len(texto), None, glifos)


def test_ocr_no_canto_vazio_da_bbox_de_texto_girado_nao_vira_fragmento_dele() -> None:
    # "11-300" a 45°: o canto superior direito da bbox é vazio e contém o rótulo "P7"
    diagonal = _texto_diagonal("11-300", (0.30, 0.30), 45.0)
    horizontal = _texto_glifo("P7", 0.36, y=0.30)
    caixa = _caixa_dos_glifos(horizontal, 0, 2)
    x0, y0, x1, y1 = diagonal.bbox
    assert x0 <= caixa[0] and y0 <= caixa[1] and caixa[2] <= x1 and caixa[3] <= y1
    leitura = _ocr("P7", caixa)

    cobertura = _resolver_cobertura([leitura], [diagonal, horizontal])

    assert cobertura.mantidos == (leitura,)
    assert cobertura.glifos == (0,)
    assert cobertura.divergentes == 0


def test_ocr_alheio_no_canto_vazio_da_bbox_nao_conta_divergencia() -> None:
    diagonal = _texto_diagonal("11-300", (0.30, 0.30), 45.0)
    leitura = _ocr("N1", (0.36, 0.30, 0.39, 0.32))

    cobertura = _resolver_cobertura([leitura], [diagonal])

    assert (cobertura.mantidos, cobertura.glifos, cobertura.divergentes) == ((leitura,), (0,), 0)


def test_leitura_que_removeu_um_texto_nunca_e_fragmento_de_outro() -> None:
    # "P7" pequeno desenhado no vão de "1  -": a leitura "1P7" cobre "P7" inteiro (que sai) e
    # fica dentro do quadrilátero de "1  -" (que fica); se saísse como fragmento, "P7" sumiria
    externo = _texto_glifo("1  -", 0.10)
    glifos_p7 = (("P", (0.116, 0.303, 0.122, 0.317)), ("7", (0.126, 0.303, 0.132, 0.317)))
    p7 = TextoGlifo(
        "P7",
        (0.116, 0.303, 0.132, 0.317),
        ((0.116, 0.317), (0.132, 0.317), (0.132, 0.303), (0.116, 0.303)),
        0.0,
        0.014,
        2,
        None,
        glifos_p7,
    )
    leitura = _ocr("1P7", _uniao(_caixa_dos_glifos(externo, 0, 1), p7.bbox))

    cobertura = _resolver_cobertura([leitura], [externo, p7])

    assert cobertura.mantidos == (leitura,)
    assert cobertura.glifos == (0,)
    assert cobertura.divergentes == 0


def test_fragmento_de_texto_girado_cuja_caixa_sai_do_quadrilatero_fica() -> None:
    # a caixa alinhada de "11" a 45° sai do quadrilátero estreito do texto: não é fragmento
    # contido, então o OCR fica junto com o glifo (duplicação parcial aceita, nada some)
    diagonal = _texto_diagonal("11-300", (0.30, 0.30), 45.0)
    leitura = _ocr("11", _caixa_dos_glifos(diagonal, 0, 2))

    cobertura = _resolver_cobertura([leitura], [diagonal])

    assert (cobertura.mantidos, cobertura.glifos, cobertura.divergentes) == ((leitura,), (0,), 0)


def test_cobertura_nativa_nunca_descarta_o_nativo_nem_conta_divergencia() -> None:
    nativo = replace(_ocr("P7", _caixa_dos_glifos(_A, 0, 2)), tipo=TipoEvidencia.TEXTO)
    divergente = replace(_ocr("P1", _caixa_dos_glifos(_B, 0, 2)), tipo=TipoEvidencia.TEXTO)

    cobertura = _resolver_cobertura([nativo, divergente], [_A, _B], nativo=True)

    assert cobertura.mantidos == (nativo, divergente)
    assert cobertura.glifos == (0, 1)
    assert cobertura.divergentes == 0


def _sobrepor_nativo(contorno: Path, destino: Path, linhas: Sequence[LinhaTexto]) -> Path:
    with pymupdf.open(contorno) as documento:
        pagina = documento[0]
        for linha in linhas:
            pagina.insert_text(linha.origem, linha.texto, fontsize=linha.tamanho, fontname="helv")
        documento.save(destino)
    return destino


def test_glifo_coberto_por_nativo_concordante_e_descartado(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    linhas = [LinhaTexto("P7 U4(1)", (40.0, 60.0), 5.0), LinhaTexto("11-300", (40.0, 120.0), 5.0)]
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", linhas)
    # "P7 U4(1)" coberto inteiro pelo nativo; de "11-300" o nativo só cobre "11"
    pdf = _sobrepor_nativo(
        contorno,
        tmp_path / "sobreposto.pdf",
        [linhas[0], LinhaTexto("11", (40.0, 120.0), 5.0)],
    )

    resultado = _analisar(pdf, tabela_glifos=tabela)

    assert [e.conteudo_bruto for e in _glifos(resultado)] == ["11-300"]
    assert sorted(e.conteudo_bruto or "" for e in _textos(resultado) if not _de_glifo(e)) == [
        "11",
        "P7 U4(1)",
    ]
    assert "analise.glifo_ocr_divergente" not in _codigos(resultado)


class _OcrFixo:
    """Motor OCR de página que devolve uma leitura fixa numa caixa normalizada."""

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


def _caixa_normalizada(evidencia: EvidenciaDocumento, folga: float) -> tuple[float, ...]:
    xs = [float(p.x) for p in evidencia.geometria.pontos]
    ys = [float(p.y) for p in evidencia.geometria.pontos]
    return (min(xs) - folga, min(ys) - folga, max(xs) + folga, max(ys) + folga)


@pytest.mark.parametrize(("lido", "glifo_fica"), [("P7 U4(1)", False), ("P1 U4(1)", True)])
def test_ocr_da_pagina_sobre_o_glifo_segue_a_regra_de_cobertura(
    tmp_path: Path, tabela: TabelaGlifos, lido: str, glifo_fica: bool
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("P7 U4(1)", (40.0, 60.0), 5.0)])
    (glifo,) = _glifos(_analisar(contorno, tabela_glifos=tabela))
    x0, y0, x1, y1 = _caixa_normalizada(glifo, 0.002)

    resultado = _analisar(
        contorno,
        ConfiguracaoAnaliseDocumento(),
        tabela_glifos=tabela,
        motor_ocr=_OcrFixo(lido, (x0, y0, x1, y1)),
    )

    assert [e.conteudo_bruto for e in resultado.evidencias if e.tipo is TipoEvidencia.OCR] == [lido]
    assert [e.conteudo_bruto for e in _glifos(resultado)] == (["P7 U4(1)"] if glifo_fica else [])
    assert ("analise.glifo_ocr_divergente" in _codigos(resultado)) is glifo_fica


def test_revisoes_e_complementar_nao_veem_texto_de_glifo(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf_misto(tmp_path)
    vistos_revisao: list[tuple[CandidatoEvidenciaDocumento, ...]] = []
    vistos_complementar: list[tuple[CandidatoEvidenciaDocumento, ...]] = []
    revisoes = extract_revision_appearances
    reconciliar = reconcile_readings

    def _revisoes(
        page: Any, page_number: int, sha: str, candidatos: Any, motor: Any
    ) -> tuple[CandidatoEvidenciaDocumento, ...]:
        vistos_revisao.append(tuple(candidatos))
        return revisoes(page, page_number, sha, candidatos, motor)

    def _reconciliar(base: Any, auxiliares: Any) -> tuple[CandidatoEvidenciaDocumento, ...]:
        vistos_complementar.append(tuple(base))
        return reconciliar(base, auxiliares)

    class _Complementar:
        assinatura_capacidade = "complementar-falso-v1"

        def extrair(
            self, _solicitacao: SolicitacaoAnaliseDocumento
        ) -> ExtracaoDocumentoNormalizada:
            return ExtracaoDocumentoNormalizada(candidatos=(), diagnosticos=())

    monkeypatch.setattr(analyzer_module, "extract_revision_appearances", _revisoes)
    monkeypatch.setattr(analyzer_module, "reconcile_readings", _reconciliar)

    resultado = _analisar(pdf, tabela_glifos=tabela, complementar=_Complementar())

    assert len(_glifos(resultado)) == len(_LINHAS)
    assert vistos_revisao and vistos_complementar
    for vistos in (*vistos_revisao, *vistos_complementar):
        assert vistos
        assert not any(
            dict(c.atributos_extraidos).get("origem_texto") == "contorno_glifo" for c in vistos
        )


def test_versao_e_assinatura_de_capacidade(tabela: TabelaGlifos) -> None:
    outra = dataclasses.replace(tabela, sha256="0" * 64)

    com_tabela = PyMuPdfDocumentAnalyzer(tabela_glifos=tabela)
    com_outra = PyMuPdfDocumentAnalyzer(tabela_glifos=outra)
    sem_tabela = PyMuPdfDocumentAnalyzer()

    assert PyMuPdfDocumentAnalyzer.versao == "1.21.0"
    assert com_tabela._capacidade()["tabela_glifos"] == tabela.sha256
    assert com_tabela._capacidade()["modelo_desenho"] == VERSAO_MODELO_DESENHO
    assert len({a.assinatura_capacidade for a in (com_tabela, com_outra, sem_tabela)}) == 3


def test_candidatos_texto_glifos_da_pagina(tmp_path: Path, tabela: TabelaGlifos) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    with pymupdf.open(contorno) as documento:
        candidatos, diagnosticos = candidatos_texto_glifos(documento[0], 3, tabela)

    assert diagnosticos == ()
    assert [c.chave_estavel for c in candidatos] == [f"p3:texto_glifo:{i}" for i in range(3)]
    assert {c.pagina_numero for c in candidatos} == {3}
    assert sorted(c.conteudo_bruto or "" for c in candidatos) == sorted(
        linha.texto for linha in _LINHAS
    )
    assert all(len(c.geometria.pontos) == 4 for c in candidatos)
    assert all(
        Decimal(0) <= p.x <= Decimal(1) and Decimal(0) <= p.y <= Decimal(1)
        for c in candidatos
        for p in c.geometria.pontos
    )


def _ultimo_desenho_malformado(monkeypatch: pytest.MonkeyPatch) -> None:
    """O último desenho da página ganha uma coordenada não finita e `caminhos_da_pagina` o
    descarta: não há caminho seguinte para revelar o salto na ordem."""
    original = pymupdf_drawing_model._desenhos

    def _desenhos(pagina: Any) -> list[dict[str, Any]]:
        desenhos = original(pagina)
        ultimo = dict(desenhos[-1])
        ultimo["items"] = [("l", pymupdf.Point(math.nan, 0.0), pymupdf.Point(1.0, 1.0))]
        return [*desenhos[:-1], ultimo]

    monkeypatch.setattr(pymupdf_drawing_model, "_desenhos", _desenhos)


def test_ultimo_desenho_da_pagina_descartado_envenena_o_trecho(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("11-300", (40.0, 60.0), 5.0)])
    assert [e.conteudo_bruto for e in _glifos(_analisar(contorno, tabela_glifos=tabela))] == [
        "11-300"
    ]
    _ultimo_desenho_malformado(monkeypatch)

    resultado = _analisar(contorno, tabela_glifos=tabela)

    assert not _glifos(resultado)
    assert not any("11-30" in (e.conteudo_bruto or "") for e in resultado.evidencias)
    assert "analise.glifos_desconhecidos" in _codigos(resultado)


def test_cobertura_ocr_x_glifo_que_falha_mantem_os_dois_com_diagnostico(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("P7 U4(1)", (40.0, 60.0), 5.0)])
    (glifo,) = _glifos(_analisar(contorno, tabela_glifos=tabela))
    caixa = _caixa_normalizada(glifo, 0.002)
    original = _resolver_cobertura

    def _quebra_no_ocr(leituras: Any, glifos: Any, *, nativo: bool = False) -> Any:
        if nativo:
            return original(leituras, glifos, nativo=True)
        raise RuntimeError("cobertura quebrou")

    monkeypatch.setattr(analyzer_module, "_resolver_cobertura", _quebra_no_ocr)

    resultado = _analisar(
        contorno,
        ConfiguracaoAnaliseDocumento(),
        tabela_glifos=tabela,
        motor_ocr=_OcrFixo("P7 U4(1)", (caixa[0], caixa[1], caixa[2], caixa[3])),
    )

    assert [e.conteudo_bruto for e in resultado.evidencias if e.tipo is TipoEvidencia.OCR] == [
        "P7 U4(1)"
    ]
    assert [e.conteudo_bruto for e in _glifos(resultado)] == ["P7 U4(1)"]
    (diagnostico,) = (
        d for d in resultado.diagnosticos if d.codigo == "analise.cobertura_glifo_ocr_falhou"
    )
    assert diagnostico.pagina_numero == 1
