from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from tests.pdf_fixtures import create_golden_pdf

from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.ports.analysis import (
    ConfiguracaoAnaliseDocumento,
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
    with pytest.raises(ValueError, match="Profundidade"):
        ConfiguracaoAnaliseDocumento(profundidade_maxima_xobject=0)


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
