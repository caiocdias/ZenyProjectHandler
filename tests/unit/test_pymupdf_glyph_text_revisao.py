# mypy: disable-error-code="no-untyped-call"
"""Ataques às correções da revisão (3b03d77): quadrilátero, total de desenhos, cobertura."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pymupdf
import pytest
from tests.fixtures.glyphs.fonte_livre import (
    LinhaTexto,
    caminhos_do_pdf,
    pdf_texto_contorno,
    tabela_do_alfabeto,
)

from zeny_project_handler.adapters.analysis import (
    JsonAnalysisCache,
    PyMuPdfDocumentAnalyzer,
    pymupdf_drawing_model,
)
from zeny_project_handler.adapters.analysis import pymupdf_analyzer as analyzer_module
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import TabelaGlifos
from zeny_project_handler.adapters.analysis.drawing_model.glyph_text import (
    TextoGlifo,
    ler_texto_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import extrair_modelo_desenho
from zeny_project_handler.adapters.analysis.pymupdf_glyph_text import (
    _resolver_cobertura,
    ler_glifos_da_pagina,
)
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
_TODAS = sorted(linha.texto for linha in _LINHAS)
_SEM_A_ULTIMA = sorted(linha.texto for linha in _LINHAS[:2])
_SEM_A_PRIMEIRA = sorted(linha.texto for linha in _LINHAS[1:])
_SEM_OCR = ConfiguracaoAnaliseDocumento(habilitar_ocr_condicional=False)


@pytest.fixture(scope="module")
def tabela(tmp_path_factory: pytest.TempPathFactory) -> TabelaGlifos:
    return tabela_do_alfabeto(tmp_path_factory.mktemp("alfabeto-revisao"))


def _analisar(
    pdf: Path, configuracao: ConfiguracaoAnaliseDocumento = _SEM_OCR, **kwargs: Any
) -> ResultadoAnaliseDocumento:
    inspection = PyMuPdfReader().inspecionar(pdf)
    project_id = uuid4()
    pedido = SolicitacaoAnaliseDocumento(
        projeto_id=project_id,
        documento=inspection.documento,
        fonte=ReferenciaFontePdf(
            documento_id=inspection.documento.id,
            projeto_id=project_id,
            caminho_canonico=pdf,
            sha256=inspection.documento.sha256,
            tamanho_bytes=inspection.tamanho_bytes,
            modificado_em_ns=inspection.modificado_em_ns,
        ),
        execucao_id=uuid4(),
        criada_em=datetime(2026, 11, 4, 9, tzinfo=UTC),
        configuracao=configuracao,
    )
    return PyMuPdfDocumentAnalyzer(**kwargs).analisar(pedido)


def _glifos(resultado: ResultadoAnaliseDocumento) -> list[EvidenciaDocumento]:
    return [
        e
        for e in resultado.evidencias
        if e.tipo is TipoEvidencia.TEXTO
        and dict(e.atributos_extraidos).get("origem_texto") == "contorno_glifo"
    ]


def _codigos(resultado: ResultadoAnaliseDocumento) -> list[str]:
    return [d.codigo for d in resultado.diagnosticos]


# --- I1: texto girado, quadrilátero e canto vazio ---------------------------------------------

_ALTURA = 0.02
_LARGURA_GLIFO = 0.012


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


def _leitura(texto: str, caixa: Caixa) -> CandidatoEvidenciaDocumento:
    x0, y0, x1, y1 = (Decimal(str(round(v, 6))) for v in caixa)
    return CandidatoEvidenciaDocumento(
        chave_estavel="p1:ocr",
        pagina_numero=1,
        tipo=TipoEvidencia.OCR,
        geometria=GeometriaNormalizada(
            tipo=TipoGeometria.CAIXA,
            pontos=(PontoNormalizado(x0, y0), PontoNormalizado(x1, y1)),
        ),
        origem_pdf=OrigemObjetoPdf(),
        conteudo_bruto=texto,
        atributos_extraidos=(("motor_ocr", "tesseract-pagina"),),
    )


def _uniao(texto: TextoGlifo, inicio: int, fim: int) -> Caixa:
    caixas = [c for _, c in texto.glifos[inicio:fim]]
    return (
        min(c[0] for c in caixas),
        min(c[1] for c in caixas),
        max(c[2] for c in caixas),
        max(c[3] for c in caixas),
    )


def _lidos_da_pagina(
    tmp_path: Path, tabela: TabelaGlifos, linhas: Sequence[LinhaTexto]
) -> list[TextoGlifo]:
    pdf = pdf_texto_contorno(tmp_path / "g.pdf", linhas)
    with pymupdf.open(pdf) as documento:
        return list(ler_glifos_da_pagina(documento[0], 1, tabela).textos)


@pytest.mark.parametrize("angulo", [15.0, 30.0, 45.0, 90.0])
def test_texto_girado_ocr_inteiro_concordante_tira_o_glifo_e_divergente_mantem_os_dois(
    tmp_path: Path, tabela: TabelaGlifos, angulo: float
) -> None:
    linhas = [LinhaTexto("P7 U4(1)", (100.0, 200.0), 5.0, angulo)]
    (texto,) = _lidos_da_pagina(tmp_path, tabela, linhas)
    assert texto.texto == "P7 U4(1)"
    caixa = _uniao(texto, 0, len(texto.glifos))
    certo = _leitura("P7 U4(1)", caixa)
    errado = _leitura("P1 U4(1)", caixa)

    cobertura = _resolver_cobertura([certo], [texto])
    assert (cobertura.mantidos, cobertura.glifos, cobertura.divergentes) == ((certo,), (), 0)
    cobertura = _resolver_cobertura([errado], [texto])
    assert (cobertura.mantidos, cobertura.glifos, cobertura.divergentes) == ((errado,), (0,), 1)


@pytest.mark.parametrize("angulo", [15.0, 30.0, 45.0, 90.0])
def test_texto_girado_fragmento_nunca_perde_as_duas_leituras(
    tmp_path: Path, tabela: TabelaGlifos, angulo: float
) -> None:
    linhas = [LinhaTexto("P7 U4(1)", (100.0, 200.0), 5.0, angulo)]
    (texto,) = _lidos_da_pagina(tmp_path, tabela, linhas)
    fragmento = _leitura("P7", _uniao(texto, 0, 2))

    cobertura = _resolver_cobertura([fragmento], [texto])

    assert cobertura.divergentes == 0
    assert cobertura.glifos == (0,) or cobertura.mantidos == (fragmento,)
    if angulo == 90.0:
        assert cobertura.mantidos == () and cobertura.glifos == (0,)


@pytest.mark.parametrize("angulo", [30.0, 45.0])
def test_ocr_que_cobre_um_texto_e_o_canto_vazio_de_outro_nao_toca_o_outro(
    tmp_path: Path, tabela: TabelaGlifos, angulo: float
) -> None:
    achado = None
    for deslocamento in range(8, 60, 2):
        a, b = (math.cos(math.radians(angulo)), -math.sin(math.radians(angulo)))
        origem_b = (100.0 - b * deslocamento, 200.0 + a * deslocamento)
        textos = _lidos_da_pagina(
            tmp_path,
            tabela,
            [
                LinhaTexto("P7 U4(1)", (100.0, 200.0), 5.0, angulo),
                LinhaTexto("11-300", origem_b, 5.0, angulo),
            ],
        )
        por_texto = {t.texto: t for t in textos}
        if set(por_texto) != {"P7 U4(1)", "11-300"}:
            continue
        caixa = _uniao(por_texto["P7 U4(1)"], 0, 7)
        outro = por_texto["11-300"]
        interseta = not (
            outro.bbox[2] < caixa[0]
            or outro.bbox[0] > caixa[2]
            or outro.bbox[3] < caixa[1]
            or outro.bbox[1] > caixa[3]
        )
        centro_sob = any(
            caixa[0] <= (c[0] + c[2]) / 2 <= caixa[2] and caixa[1] <= (c[1] + c[3]) / 2 <= caixa[3]
            for _, c in outro.glifos
        )
        if interseta and not centro_sob:
            achado = (por_texto["P7 U4(1)"], outro, caixa)
            break
    assert achado is not None, "sem posição com canto vazio sobreposto"
    primeiro, segundo, caixa = achado
    ocr = _leitura("P7 U4(1)", caixa)

    cobertura = _resolver_cobertura([ocr], [primeiro, segundo])

    assert cobertura.mantidos == (ocr,)
    assert cobertura.glifos == (1,)
    assert cobertura.divergentes == 0


def test_ocr_concordante_que_removeu_um_texto_nunca_e_fragmento_do_outro() -> None:
    a = _texto_glifo("P7 U4(1)", 0.10)
    b = _texto_glifo("11-300", 0.30)
    base = _uniao(a, 0, 7)
    caixa = (base[0], base[1], _uniao(b, 0, 3)[2], base[3])
    ocr = _leitura("P7 U4(1) 11-", caixa)

    cobertura = _resolver_cobertura([ocr], [a, b])

    assert cobertura.mantidos == (ocr,)
    assert cobertura.glifos == (1,)


# --- I2: total_desenhos -----------------------------------------------------------------------


def _caminhos(tmp_path: Path) -> tuple[Any, ...]:
    return caminhos_do_pdf(pdf_texto_contorno(tmp_path / "t.pdf", _LINHAS))


def _lidos(caminhos: Sequence[Any], tabela: TabelaGlifos, total: int | None) -> list[str]:
    return sorted(t.texto for t in ler_texto_glifos(caminhos, tabela, total).textos)


def test_total_igual_ao_numero_de_caminhos_ou_ausente_le_tudo(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    caminhos = _caminhos(tmp_path)
    assert [c.ordem for c in caminhos] == list(range(len(caminhos)))

    assert _lidos(caminhos, tabela, len(caminhos)) == _TODAS
    assert _lidos(caminhos, tabela, None) == _TODAS


@pytest.mark.parametrize("total", [0, -1, -1000, 1, 5])
def test_total_menor_que_o_numero_de_caminhos_ou_negativo_nao_derruba_nem_envenena(
    tmp_path: Path, tabela: TabelaGlifos, total: int
) -> None:
    assert _lidos(_caminhos(tmp_path), tabela, total) == _TODAS


def test_total_maior_envenena_so_o_trecho_do_fim(tmp_path: Path, tabela: TabelaGlifos) -> None:
    caminhos = _caminhos(tmp_path)

    assert _lidos(caminhos, tabela, len(caminhos) + 1) == _SEM_A_ULTIMA
    assert _lidos(caminhos, tabela, len(caminhos) + 10**6) == _SEM_A_ULTIMA
    assert _lidos(caminhos, tabela, None) == _TODAS


def test_descarte_no_fim_so_e_visto_com_o_total(tmp_path: Path, tabela: TabelaGlifos) -> None:
    caminhos = _caminhos(tmp_path)

    com_total = _lidos(caminhos[:-1], tabela, len(caminhos))

    assert com_total == _SEM_A_ULTIMA
    assert "E=612345 N=780123" not in com_total


def test_descarte_no_inicio_envenena_com_ou_sem_total(tmp_path: Path, tabela: TabelaGlifos) -> None:
    caminhos = _caminhos(tmp_path)

    assert _lidos(caminhos[1:], tabela, None) == _SEM_A_PRIMEIRA
    assert _lidos(caminhos[1:], tabela, len(caminhos)) == _SEM_A_PRIMEIRA


def test_descarte_no_meio_de_uma_linha_envenena_a_linha_com_ou_sem_total(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    caminhos = _caminhos(tmp_path)
    sem_um_do_meio = (*caminhos[:13], *caminhos[14:])  # um glifo de "11-300"

    for total in (None, len(caminhos)):
        lidos = _lidos(sem_um_do_meio, tabela, total)
        assert "11-300" not in lidos and "11-" not in lidos and "300" not in lidos
        assert "E=612345 N=7801234" in lidos


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


def test_desenho_descartado_no_fim_da_pagina_nao_vira_texto_parcial_na_analise_e_no_modelo(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    original = pymupdf_drawing_model._desenhos
    monkeypatch.setattr(
        pymupdf_drawing_model,
        "_desenhos",
        lambda pagina: [*original(pagina), _desenho_nao_finito()],
    )

    resultado = _analisar(contorno, tabela_glifos=tabela)
    (pagina,) = extrair_modelo_desenho(contorno, tabela).paginas

    assert sorted(e.conteudo_bruto or "" for e in _glifos(resultado)) == _SEM_A_ULTIMA
    assert sorted(t.texto for t in pagina.textos) == _SEM_A_ULTIMA


# --- M1: falha da cobertura -------------------------------------------------------------------


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


def test_falha_na_cobertura_ocr_x_glifo_mantem_as_duas_leituras_e_nao_grava_cache(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("P7 U4(1)", (40.0, 60.0), 5.0)])
    (glifo,) = _glifos(_analisar(contorno, tabela_glifos=tabela))
    xs = [float(p.x) for p in glifo.geometria.pontos]
    ys = [float(p.y) for p in glifo.geometria.pontos]
    caixa = (min(xs) - 0.002, min(ys) - 0.002, max(xs) + 0.002, max(ys) + 0.002)
    original = _resolver_cobertura

    def _quebra(leituras: Any, glifos: Any, *, nativo: bool = False) -> Any:
        if nativo:
            return original(leituras, glifos, nativo=nativo)
        raise RuntimeError("cobertura quebrou")

    monkeypatch.setattr(analyzer_module, "_resolver_cobertura", _quebra)
    cache = JsonAnalysisCache(tmp_path / "cache-analise")

    def rodar() -> ResultadoAnaliseDocumento:
        return _analisar(
            contorno,
            ConfiguracaoAnaliseDocumento(),
            tabela_glifos=tabela,
            motor_ocr=_OcrFixo("P7 U4(1)", caixa),
            cache=cache,
        )

    resultado = rodar()
    de_novo = rodar()

    assert "analise.cobertura_glifo_ocr_falhou" in _codigos(resultado)
    assert [e.conteudo_bruto for e in resultado.evidencias if e.tipo is TipoEvidencia.OCR] == [
        "P7 U4(1)"
    ]
    assert [e.conteudo_bruto for e in _glifos(resultado)] == ["P7 U4(1)"]
    assert not de_novo.cache_utilizado
