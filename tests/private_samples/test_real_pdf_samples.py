from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from functools import cache
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from zeny_project_handler.adapters.analysis import PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.application.analysis_regions import agrupar_regioes_da_analise
from zeny_project_handler.application.automatic_promotion import (
    promover_resultado_automatico,
)
from zeny_project_handler.application.spans import detectar_vaos
from zeny_project_handler.domain.enums import TipoEvidencia, TipoOrigemPdf
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.ports.analysis import (
    ConfiguracaoAnaliseDocumento,
    SolicitacaoAnaliseDocumento,
)
from zeny_project_handler.ports.interpretation import SolicitacaoInterpretacao
from zeny_project_handler.ports.pdf import OrcamentoRenderizacaoPdf, ReferenciaFontePdf

PRIVATE_RENDER_BUDGET = OrcamentoRenderizacaoPdf(
    limite_pixels=8_000_000,
    limite_bytes=64 * 1024 * 1024,
)

EXAMPLES_DIRECTORY = Path(__file__).parents[2] / "examples"
MANIFEST_PATH = Path(__file__).parents[2] / "evaluation" / "manifesto-amostras.json"

pytestmark = [pytest.mark.integration, pytest.mark.private_samples]


def _samples() -> list[dict[str, Any]]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return list(payload["samples"])


@cache
def _pdf_inventory() -> tuple[dict[str, Path], int]:
    result = {}
    unreadable = 0
    for path in EXAMPLES_DIRECTORY.glob("*.pdf"):
        try:
            result[sha256(path.read_bytes()).hexdigest()] = path
        except OSError:
            unreadable += 1
    return result, unreadable


def _pdfs_by_hash() -> dict[str, Path]:
    return _pdf_inventory()[0]


def _unregistered_pdf_hashes() -> tuple[str, ...]:
    registered = {str(sample["sha256"]) for sample in _samples()}
    return tuple(sorted(set(_pdfs_by_hash()) - registered))


def _required_pdf(sample: dict[str, Any]) -> Path:
    source = _pdfs_by_hash().get(str(sample["sha256"]))
    assert source is not None, (
        f"Amostra privada {sample['id']} ausente ou com SHA-256 divergente; "
        "execute primeiro a pré-condição do gate privado"
    )
    return source


def test_private_corpus_is_complete_and_authentic() -> None:
    pdfs_by_hash, unreadable = _pdf_inventory()
    samples = _samples()
    missing = tuple(
        str(sample["id"]) for sample in samples if str(sample["sha256"]) not in pdfs_by_hash
    )
    inconsistent_sizes = tuple(
        str(sample["id"])
        for sample in samples
        if (source := pdfs_by_hash.get(str(sample["sha256"]))) is not None
        and source.stat().st_size != int(sample["bytes"])
    )
    problems = []
    if missing:
        problems.append(f"ausentes ou com hash divergente: {', '.join(missing)}")
    if inconsistent_sizes:
        problems.append(f"tamanho divergente: {', '.join(inconsistent_sizes)}")
    if unreadable:
        problems.append(f"arquivos PDF locais ilegíveis: {unreadable}")

    assert not problems, "Corpus privado ausente ou inválido; " + "; ".join(problems)


@pytest.mark.integration
@pytest.mark.parametrize("sample", _samples(), ids=lambda item: str(item["id"]))
def test_registered_real_pdf_smoke_by_anonymous_hash(sample: dict[str, Any]) -> None:
    source = _required_pdf(sample)
    reader = PyMuPdfReader()
    before = source.stat()

    inspection = reader.inspecionar(source)
    thumbnail = reader.renderizar_miniatura(
        source,
        1,
        orcamento=PRIVATE_RENDER_BUDGET,
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
    if "visible-images-in-annotation-appearance-streams" in sample.get("known_edge_cases", []):
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
    source = _required_pdf(sample)
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
    if sample["id"] == "amostra-004":
        symbolic_types = {
            item.conteudo_bruto
            for item in result.evidencias
            if dict(item.atributos_extraidos).get("reconhecido_por_simbologia") is True
        }
        assert {"ATERRAMENTO", "PARA RAIOS MT", "PARA RAIOS BT"} <= symbolic_types
    if "visible-images-in-annotation-appearance-streams" in sample.get("known_edge_cases", []):
        assert any(
            item.tipo is TipoEvidencia.IMAGEM
            and item.origem_pdf.tipo is TipoOrigemPdf.APARENCIA_ANOTACAO
            for item in result.evidencias
        )
    catalog = carregar_catalogo_inicial()
    registry = carregar_registro_regras_inicial()
    interpretation = InterpretadorRegrasExplicitas(registry).interpretar(
        SolicitacaoInterpretacao(
            projeto_id=project_id,
            execucao_id=uuid4(),
            execucao_extracao_id=request.execucao_id,
            catalogo=catalog,
            evidencias=result.evidencias,
            registro=registry,
        )
    )
    if sample["id"] == "amostra-004":
        proposed_symbol_classes = {
            dict(item.atributos_sugeridos).get("classe_equipamento")
            for item in interpretation.elementos
            if dict(item.atributos_sugeridos).get("reconhecido_por_simbologia") is True
        }
        assert {"ATERRAMENTO", "PARA_RAIOS_MT", "PARA_RAIOS_BT"} <= proposed_symbol_classes
    regions = agrupar_regioes_da_analise(
        (*interpretation.elementos, *interpretation.relacoes),
        result.evidencias,
        (inspection.documento,),
    )
    grouped_element_ids = {element_id for region in regions for element_id in region.elemento_ids}
    assert grouped_element_ids == {item.id for item in interpretation.elementos}
    if expected_spans := sample.get("expected_spans"):
        project = Projeto(
            id=project_id,
            nome=f"validação-{sample['id']}",
            catalogo_versao_id=catalog.id,
            criado_em=request.criada_em,
            documentos=(inspection.documento,),
        )
        promoted = promover_resultado_automatico(
            project,
            catalog,
            interpretation.elementos,
            interpretation.relacoes,
            promovido_em=request.criada_em,
        )
        spans = detectar_vaos(promoted.projeto)
        actual = Counter(
            (span.situacao.value, span.comprimento_m)
            for span in spans
            if span.comprimento_m is not None
        )
        expected = Counter(
            (situation, Decimal(str(length)))
            for situation, lengths in expected_spans.items()
            for length in lengths
        )
        assert actual == expected
    after = source.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)


def test_unregistered_local_pdfs_are_read_only_smoke_samples() -> None:
    for pdf_hash in _unregistered_pdf_hashes():
        source = _pdfs_by_hash()[pdf_hash]
        before = source.stat()

        inspection = PyMuPdfReader().inspecionar(source)
        thumbnail = PyMuPdfReader().renderizar_miniatura(
            source,
            1,
            orcamento=PRIVATE_RENDER_BUDGET,
            sha256_esperado=pdf_hash,
        )

        after = source.stat()
        assert inspection.documento.sha256 == pdf_hash
        assert inspection.documento.paginas
        assert thumbnail.dados_rgb
        assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
