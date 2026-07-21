from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from zeny_project_handler.adapters.analysis import PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.domain.enums import TipoEvidencia, TipoOrigemPdf
from zeny_project_handler.ports.analysis import (
    ConfiguracaoAnaliseDocumento,
    SolicitacaoAnaliseDocumento,
)
from zeny_project_handler.ports.pdf import ReferenciaFontePdf

EXAMPLES_DIRECTORY = Path(__file__).parents[2] / "examples"
MANIFEST_PATH = EXAMPLES_DIRECTORY / "manifesto-amostras.json"


def _samples() -> list[dict[str, Any]]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return list(payload["samples"])


def _pdfs_by_hash() -> dict[str, Path]:
    result = {}
    for path in EXAMPLES_DIRECTORY.glob("*.pdf"):
        result[sha256(path.read_bytes()).hexdigest()] = path
    return result


@pytest.mark.integration
@pytest.mark.parametrize("sample", _samples(), ids=lambda item: str(item["id"]))
def test_registered_real_pdf_smoke_by_anonymous_hash(sample: dict[str, Any]) -> None:
    source = _pdfs_by_hash().get(str(sample["sha256"]))
    if source is None:
        pytest.skip("Amostra real privada não está presente neste ambiente")
    reader = PyMuPdfReader()
    before = source.stat()

    inspection = reader.inspecionar(source)
    thumbnail = reader.renderizar_miniatura(
        source,
        1,
        sha256_esperado=str(sample["sha256"]),
    )

    after = source.stat()
    assert inspection.documento.sha256 == sample["sha256"]
    assert len(inspection.paginas) == sample["pages"]
    assert inspection.paginas[0].pagina.largura_pontos > 0
    assert inspection.paginas[0].pagina.altura_pontos > 0
    annotation_counts = Counter(
        annotation.subtipo for page in inspection.paginas for annotation in page.anotacoes
    )
    assert dict(annotation_counts) == sample.get("annotations", {})
    assert len(inspection.grupos_conteudo_opcional) == sample.get("optional_content_groups", 0)
    if "visible_images_in_annotation_appearance_streams" in sample.get("known_edge_cases", []):
        assert any(
            annotation.aparencias_xrefs
            for page in inspection.paginas
            for annotation in page.anotacoes
        )
    assert thumbnail.dados_rgb
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)


@pytest.mark.integration
@pytest.mark.parametrize("sample", _samples(), ids=lambda item: str(item["id"]))
def test_registered_real_pdf_native_evidence_by_anonymous_hash(sample: dict[str, Any]) -> None:
    source = _pdfs_by_hash().get(str(sample["sha256"]))
    if source is None:
        pytest.skip("Amostra real privada não está presente neste ambiente")
    before = source.stat()
    inspection = PyMuPdfReader().inspecionar(source)
    project_id = uuid4()
    request = SolicitacaoAnaliseDocumento(
        projeto_id=project_id,
        documento=inspection.documento,
        fonte=ReferenciaFontePdf(
            documento_id=inspection.documento.id,
            projeto_id=project_id,
            caminho_canonico=source,
            sha256=inspection.documento.sha256,
            tamanho_bytes=inspection.tamanho_bytes,
            modificado_em_ns=inspection.modificado_em_ns,
        ),
        execucao_id=uuid4(),
        criada_em=datetime(2026, 7, 21, tzinfo=UTC),
        configuracao=ConfiguracaoAnaliseDocumento(habilitar_ocr_condicional=False),
    )

    result = PyMuPdfDocumentAnalyzer().analisar(request)

    assert result.evidencias
    assert all(
        item.pagina_id in {page.id for page in inspection.documento.paginas}
        for item in result.evidencias
    )
    assert all(
        0 <= point.x <= 1 and 0 <= point.y <= 1
        for evidence in result.evidencias
        for point in evidence.geometria.pontos
    )
    if "visible_images_in_annotation_appearance_streams" in sample.get("known_edge_cases", []):
        assert any(
            item.tipo is TipoEvidencia.IMAGEM
            and item.origem_pdf.tipo is TipoOrigemPdf.APARENCIA_ANOTACAO
            for item in result.evidencias
        )
    after = source.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
