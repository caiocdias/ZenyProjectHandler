# mypy: disable-error-code="no-untyped-call"
"""OCR subprocess failures remain visible through the analyzer and its cache."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from uuid import uuid4

import pymupdf
import pytest

from zeny_project_handler.adapters.analysis import JsonAnalysisCache, PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.analysis import pymupdf_analyzer as analyzer_module
from zeny_project_handler.adapters.analysis import tesseract_ocr as tesseract_module
from zeny_project_handler.adapters.analysis.tesseract_ocr import TesseractCliOcr
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.domain.analysis import DiagnosticoAnalise
from zeny_project_handler.domain.catalog import ExtraAttributes
from zeny_project_handler.domain.enums import TipoEvidencia
from zeny_project_handler.ports.analysis import (
    ConfiguracaoAnaliseDocumento,
    ExtracaoDocumentoNormalizada,
    SolicitacaoAnaliseDocumento,
    chave_cache_analise,
)
from zeny_project_handler.ports.pdf import ReferenciaFontePdf


def _request(path: Path, *, dense: bool = False) -> SolicitacaoAnaliseDocumento:
    with pymupdf.open() as document:
        for label in ("NATIVO A", "NATIVO B"):
            page = document.new_page(width=200, height=200)
            page.insert_text((20, 30), label)
            if dense:
                page.draw_line((40, 40), (50, 50))
        document.save(path)
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
        criada_em=datetime(2026, 9, 10, tzinfo=UTC),
        configuracao=ConfiguracaoAnaliseDocumento(
            dpi_ocr=72,
            minimo_vetores_para_ocr=1 if dense else 1000,
            divisoes_ocr_conteudo_denso=2,
        ),
    )


def _install_stub(root: Path) -> tuple[Path, Path]:
    executable = root / "tesseract.exe"
    executable.write_bytes(b"stub: never executed")
    tessdata = root / "tessdata"
    tessdata.mkdir()
    (tessdata / "eng.traineddata").write_bytes(b"synthetic language identity")
    return executable, tessdata


def _metadata(arguments: tuple[str, ...], tessdata: Path) -> CompletedProcess[str] | None:
    if "--version" in arguments:
        return CompletedProcess(arguments, 0, "tesseract 5.4.0\n")
    if "--list-langs" in arguments:
        return CompletedProcess(
            arguments, 0, f'List of available languages in "{tessdata}" (1):\neng\n'
        )
    return None


@pytest.mark.parametrize("failure", ("plain_text", "timeout"))
def test_ocr_failure_preserves_native_and_prior_page_evidence_in_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    request = _request(tmp_path / "partial.pdf")
    executable, tessdata = _install_stub(tmp_path)
    calls = 0
    tsv = "\t".join(tesseract_module._TSV_COLUMNS) + "\n5\t1\t1\t1\t1\t1\t40\t50\t30\t10\t90\tP7\n"

    def fake_run(
        arguments: tuple[str, ...],
        **kwargs: object,
    ) -> CompletedProcess[str] | CompletedProcess[bytes]:
        nonlocal calls
        if metadata := _metadata(arguments, tessdata):
            return metadata
        calls += 1
        assert kwargs["timeout"] == 3
        if calls != 2:
            return CompletedProcess(arguments, 0, tsv.encode())
        if failure == "timeout":
            raise TimeoutExpired(arguments, 3, stderr=b"private runtime path")
        return CompletedProcess(arguments, 0, b"plain text, not TSV", b"Can't open tsv")

    monkeypatch.setattr(subprocess, "run", fake_run)
    cache = JsonAnalysisCache(tmp_path / "cache")
    engine = TesseractCliOcr(executable, recognition_timeout_seconds=3)
    analyzer = PyMuPdfDocumentAnalyzer(cache=cache, motor_ocr=engine)

    first = analyzer.analisar(request)
    replay = PyMuPdfDocumentAnalyzer(cache=cache, motor_ocr=engine).analisar(request)
    cached = PyMuPdfDocumentAnalyzer(cache=cache, motor_ocr=engine).analisar(request)

    assert not first.cache_utilizado
    assert not replay.cache_utilizado
    assert cached.cache_utilizado
    assert calls == 4
    assert cached.evidencias == replay.evidencias
    assert replay.diagnosticos == cached.diagnosticos == ()
    assert len([item for item in replay.evidencias if item.tipo == TipoEvidencia.OCR]) == 2
    assert {
        item.conteudo_bruto for item in first.evidencias if item.tipo == TipoEvidencia.TEXTO
    } == {
        "NATIVO A",
        "NATIVO B",
    }
    recognized = [item for item in first.evidencias if item.tipo == TipoEvidencia.OCR]
    assert len(recognized) == 1
    assert recognized[0].conteudo_bruto == "P7"
    assert recognized[0].pagina_id == request.documento.paginas[0].id
    assert dict(recognized[0].atributos_extraidos)["confianca"] == Decimal("0.9")
    assert [item.codigo for item in first.diagnosticos] == ["analise.ocr_falhou"]
    diagnostic = first.diagnosticos[0]
    assert diagnostic.pagina_numero == 2
    assert diagnostic.extrator == "ocr"
    assert "private" not in diagnostic.mensagem


class _LegacyTesseract(TesseractCliOcr):
    def _semantic_parameters(self) -> ExtraAttributes:
        return tuple(
            (key, value)
            for key, value in super()._semantic_parameters()
            if key not in ("geracao_tsv", "validacao_tsv")
        )


class _LegacyAnalyzer(PyMuPdfDocumentAnalyzer):
    versao = "1.11.0"


@pytest.mark.parametrize("changed_component", ("tesseract", "analyzer"))
def test_old_success_cache_cannot_hide_current_ocr_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_component: str,
) -> None:
    request = _request(tmp_path / "cached.pdf")
    executable, tessdata = _install_stub(tmp_path)
    calls = 0

    def fake_run(
        arguments: tuple[str, ...],
        **_kwargs: object,
    ) -> CompletedProcess[str] | CompletedProcess[bytes]:
        nonlocal calls
        if metadata := _metadata(arguments, tessdata):
            return metadata
        calls += 1
        return CompletedProcess(arguments, 0, b"unexpected plain text")

    monkeypatch.setattr(subprocess, "run", fake_run)
    cache = JsonAnalysisCache(tmp_path / "cache")
    old_engine = (_LegacyTesseract if changed_component == "tesseract" else TesseractCliOcr)(
        executable
    )
    old_analyzer = (
        _LegacyAnalyzer if changed_component == "analyzer" else PyMuPdfDocumentAnalyzer
    )(motor_ocr=old_engine)
    legacy_key = chave_cache_analise(
        documento_sha256=request.documento.sha256,
        configuracao=request.configuracao,
        analisador=old_analyzer.assinatura_capacidade,
    )
    cache.salvar(legacy_key, ExtracaoDocumentoNormalizada(candidatos=(), diagnosticos=()))
    current = PyMuPdfDocumentAnalyzer(cache=cache, motor_ocr=TesseractCliOcr(executable))

    result = current.analisar(request)

    assert current.assinatura_capacidade != old_analyzer.assinatura_capacidade
    assert not result.cache_utilizado
    assert calls == 2
    assert len(result.evidencias) == 2
    assert [item.codigo for item in result.diagnosticos] == ["analise.ocr_falhou"] * 2


@pytest.mark.parametrize("failure", ("plain_text", "timeout", "cancel"))
def test_dense_ocr_retains_completed_tiles_and_stops_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    request = _request(tmp_path / "dense.pdf", dense=True)
    executable, tessdata = _install_stub(tmp_path)
    calls = 0
    tsv = "\t".join(tesseract_module._TSV_COLUMNS) + "\n5\t1\t1\t1\t1\t1\t40\t50\t30\t10\t90\tP7\n"

    def fake_run(
        arguments: tuple[str, ...],
        **_kwargs: object,
    ) -> CompletedProcess[str] | CompletedProcess[bytes]:
        nonlocal calls
        if metadata := _metadata(arguments, tessdata):
            return metadata
        calls += 1
        if calls not in (2, 3):
            return CompletedProcess(arguments, 0, tsv.encode())
        if failure == "cancel":
            raise KeyboardInterrupt
        if failure == "timeout":
            raise TimeoutExpired(arguments, 3)
        return CompletedProcess(arguments, 0, b"plain text")

    monkeypatch.setattr(subprocess, "run", fake_run)
    cache = JsonAnalysisCache(tmp_path / "cache")
    analyzer = PyMuPdfDocumentAnalyzer(cache=cache, motor_ocr=TesseractCliOcr(executable))
    if failure == "cancel":
        with pytest.raises(KeyboardInterrupt):
            analyzer.analisar(request)
        assert calls == 2
        assert not tuple((tmp_path / "cache").glob("*.json"))
        return

    result = analyzer.analisar(request)
    assert calls == 3  # page 1: first tile succeeds, second fails; page 2: first fails.
    replay = analyzer.analisar(request)
    cached = analyzer.analisar(request)

    assert calls == 11  # The next analysis retries all eight tiles, then can cache success.
    recognized = [item for item in result.evidencias if item.tipo == TipoEvidencia.OCR]
    assert len(recognized) == 1
    assert recognized[0].conteudo_bruto == "P7"
    assert recognized[0].pagina_id == request.documento.paginas[0].id
    assert len([item for item in result.evidencias if item.tipo == TipoEvidencia.TEXTO]) == 2
    assert [item.codigo for item in result.diagnosticos] == ["analise.ocr_falhou"] * 2
    assert "linha 1, coluna 2; 3 recorte(s)" in result.diagnosticos[0].mensagem
    assert "linha 1, coluna 1; 4 recorte(s)" in result.diagnosticos[1].mensagem
    assert not replay.cache_utilizado
    assert cached.cache_utilizado
    assert replay.evidencias == cached.evidencias
    assert replay.diagnosticos == cached.diagnosticos == ()


def test_structural_coverage_diagnostic_remains_cacheable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(tmp_path / "structural.pdf")
    diagnostic = DiagnosticoAnalise(
        codigo="analise.ocr_cobertura_parcial",
        mensagem="Um recorte elegível não foi selecionado para OCR.",
        extrator="ocr",
        pagina_numero=1,
    )
    calls = 0

    def extract(*_args: object) -> ExtracaoDocumentoNormalizada:
        nonlocal calls
        calls += 1
        return ExtracaoDocumentoNormalizada(candidatos=(), diagnosticos=(diagnostic,))

    monkeypatch.setattr(analyzer_module, "_extract_document", extract)
    analyzer = PyMuPdfDocumentAnalyzer(cache=JsonAnalysisCache(tmp_path / "cache"))

    first = analyzer.analisar(request)
    second = analyzer.analisar(request)

    assert not first.cache_utilizado
    assert second.cache_utilizado
    assert calls == 1
    assert first.diagnosticos == second.diagnosticos == (diagnostic,)
