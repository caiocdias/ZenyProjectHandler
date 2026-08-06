from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from tests.factories import complete_project
from tests.pdf_fixtures import create_golden_pdf

from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.application.mvp_workflow import _extraction_id
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.ports.analysis import (
    CapacidadeMotorOcr,
    ConfiguracaoAnaliseDocumento,
    IdentidadeDadosTreinadosOcr,
    ResultadoConsultaCapacidadeOcr,
    SolicitacaoAnaliseDocumento,
    chave_cache_analise,
    validar_fonte_solicitacao,
)
from zeny_project_handler.ports.pdf import ReferenciaFontePdf


def _request(path: Path) -> SolicitacaoAnaliseDocumento:
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
        criada_em=datetime(2026, 7, 21, tzinfo=UTC),
    )


def test_analysis_configuration_is_stable_and_validated() -> None:
    configuration = ConfiguracaoAnaliseDocumento()

    assert configuration.assinatura() == configuration.assinatura()
    parameters = dict(configuration.parametros())
    assert parameters["minimo_caracteres_texto_nativo"] == 20
    assert parameters["area_imagem_minima_para_ocr"] == Decimal("0.10")
    assert parameters["area_imagem_regional_minima_para_ocr"] == Decimal("0.0025")
    assert parameters["minimo_vetores_para_ocr"] == 1000
    assert parameters["dpi_ocr"] == 450
    assert parameters["dpi_ocr_identificadores"] == 1200
    assert parameters["dpi_ocr_rotulos_inclinados"] == 1800
    assert parameters["divisoes_ocr_conteudo_denso"] == 3
    assert parameters["sobreposicao_ocr_conteudo_denso"] == Decimal("0.025")
    assert (
        len(
            chave_cache_analise(
                documento_sha256="a" * 64,
                configuracao=configuration,
                analisador="fake:1",
            )
        )
        == 64
    )

    with pytest.raises(ValueError, match="caracteres"):
        ConfiguracaoAnaliseDocumento(minimo_caracteres_texto_nativo=-1)
    with pytest.raises(ValueError, match="Área"):
        ConfiguracaoAnaliseDocumento(area_imagem_minima_para_ocr=Decimal("1.1"))
    with pytest.raises(ValueError, match="regional"):
        ConfiguracaoAnaliseDocumento(area_imagem_regional_minima_para_ocr=Decimal("0.2"))
    with pytest.raises(ValueError, match="vetores"):
        ConfiguracaoAnaliseDocumento(minimo_vetores_para_ocr=0)
    with pytest.raises(ValueError, match="DPI"):
        ConfiguracaoAnaliseDocumento(dpi_ocr=40)
    with pytest.raises(ValueError, match="identificadores"):
        ConfiguracaoAnaliseDocumento(dpi_ocr_identificadores=200)
    with pytest.raises(ValueError, match="inclinados"):
        ConfiguracaoAnaliseDocumento(dpi_ocr_rotulos_inclinados=500)
    with pytest.raises(ValueError, match="Divisões"):
        ConfiguracaoAnaliseDocumento(divisoes_ocr_conteudo_denso=1)
    with pytest.raises(ValueError, match="Sobreposição"):
        ConfiguracaoAnaliseDocumento(sobreposicao_ocr_conteudo_denso=Decimal("0.20"))
    with pytest.raises(ValueError, match="Profundidade"):
        ConfiguracaoAnaliseDocumento(profundidade_maxima_xobject=0)


def test_ocr_capability_signature_is_canonical_and_path_free() -> None:
    traineddata = (
        IdentidadeDadosTreinadosOcr(idioma="por", sha256="1" * 64),
        IdentidadeDadosTreinadosOcr(idioma="eng", sha256="2" * 64),
    )
    first = CapacidadeMotorOcr(
        implementacao="tesseract-cli",
        versao="5.4.1",
        idiomas=("por", "eng"),
        dados_treinados=traineddata,
        parametros=(("psm", 11), ("oem", 3)),
    )
    second = CapacidadeMotorOcr(
        implementacao="tesseract-cli",
        versao="5.4.1",
        idiomas=("por", "eng"),
        dados_treinados=traineddata,
        parametros=(("oem", 3), ("psm", 11)),
    )

    assert first.assinatura() == second.assinatura()
    assert len(first.assinatura()) == 64


def test_ocr_capability_rejects_incomplete_or_ambiguous_identity() -> None:
    valid_traineddata = IdentidadeDadosTreinadosOcr(idioma="eng", sha256="1" * 64)
    with pytest.raises(ValueError, match="Idioma"):
        IdentidadeDadosTreinadosOcr(idioma=" ", sha256="1" * 64)
    with pytest.raises(ValueError, match="SHA-256"):
        IdentidadeDadosTreinadosOcr(idioma="eng", sha256="invalid")
    with pytest.raises(ValueError, match="Implementação"):
        CapacidadeMotorOcr(
            implementacao=" ",
            versao="5.4.1",
            idiomas=("eng",),
            dados_treinados=(valid_traineddata,),
            parametros=(),
        )
    with pytest.raises(ValueError, match="ao menos um"):
        CapacidadeMotorOcr(
            implementacao="tesseract-cli",
            versao="5.4.1",
            idiomas=(),
            dados_treinados=(),
            parametros=(),
        )
    with pytest.raises(ValueError, match="únicos"):
        CapacidadeMotorOcr(
            implementacao="tesseract-cli",
            versao="5.4.1",
            idiomas=("eng", "eng"),
            dados_treinados=(valid_traineddata, valid_traineddata),
            parametros=(),
        )
    with pytest.raises(ValueError, match="corresponder"):
        CapacidadeMotorOcr(
            implementacao="tesseract-cli",
            versao="5.4.1",
            idiomas=("por",),
            dados_treinados=(valid_traineddata,),
            parametros=(),
        )
    with pytest.raises(ValueError, match="chaves únicas"):
        CapacidadeMotorOcr(
            implementacao="tesseract-cli",
            versao="5.4.1",
            idiomas=("eng",),
            dados_treinados=(valid_traineddata,),
            parametros=(("oem", 3), ("oem", 1)),
        )
    with pytest.raises(ValueError, match="diagnóstico"):
        ResultadoConsultaCapacidadeOcr(capacidade=None)


def test_persisted_extraction_identity_changes_with_analyzer_version(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    document = project.documentos[0]
    configuration = ConfiguracaoAnaliseDocumento()

    first = _extraction_id(
        project,
        document.id,
        document.sha256,
        configuration,
        "pymupdf-nativo:1.5.1",
    )
    second = _extraction_id(
        project,
        document.id,
        document.sha256,
        configuration,
        "pymupdf-nativo:1.7.0",
    )

    assert first != second


def test_analysis_request_validates_source_links(tmp_path: Path) -> None:
    request = _request(create_golden_pdf(tmp_path / "source.pdf"))

    assert validar_fonte_solicitacao(request) == request.fonte.caminho_canonico
    with pytest.raises(ValueError, match="documento"):
        validar_fonte_solicitacao(
            replace(request, fonte=replace(request.fonte, documento_id=uuid4()))
        )
    with pytest.raises(ValueError, match="projeto"):
        validar_fonte_solicitacao(
            replace(request, fonte=replace(request.fonte, projeto_id=uuid4()))
        )
    with pytest.raises(ValueError, match="Hash"):
        validar_fonte_solicitacao(replace(request, fonte=replace(request.fonte, sha256="f" * 64)))
    with pytest.raises(ValueError, match="fuso"):
        validar_fonte_solicitacao(replace(request, criada_em=datetime(2026, 7, 21)))
