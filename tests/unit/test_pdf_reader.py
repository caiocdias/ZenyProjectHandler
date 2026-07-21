from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.pdf_fixtures import create_feature_pdf, create_golden_pdf, create_protected_pdf

import zeny_project_handler.adapters.pdf.pymupdf_reader as reader_module
from zeny_project_handler.adapters.pdf import (
    PdfArquivoInvalidoError,
    PdfOrigemAlteradaError,
    PdfPaginaInvalidaError,
    PdfProtegidoError,
    PyMuPdfReader,
)


def test_inspection_covers_native_pdf_resources_without_changing_source(tmp_path: Path) -> None:
    source = create_feature_pdf(tmp_path / "recursos.pdf")
    original = source.read_bytes()

    inspection = PyMuPdfReader().inspecionar(source)

    assert source.read_bytes() == original
    assert inspection.caminho_origem == source.resolve()
    assert inspection.adaptador == "PyMuPDF 1.28.0"
    assert len(inspection.paginas) == 3
    first = inspection.paginas[0]
    assert any("POSTE P1" in fragment.texto for fragment in first.textos)
    assert first.vetores
    assert first.imagens
    assert first.anotacoes
    assert first.anotacoes[0].aparencias_xrefs
    assert first.forms_xobjects
    assert inspection.grupos_conteudo_opcional[0].nome == "Camada de teste"
    assert inspection.documento.tamanho_bytes == source.stat().st_size
    assert len(first.pagina.matriz_pdf_para_pagina) == 6
    assert len(first.pagina.matriz_rotacao_pagina) == 6

    rotated = inspection.paginas[1].pagina
    assert rotated.rotacao_graus == 90
    assert rotated.media_box != rotated.crop_box
    assert inspection.paginas[2].textos == ()
    assert inspection.paginas[2].imagens


def test_rendering_golden_rgb_rotation_crop_and_thumbnail(tmp_path: Path) -> None:
    source = create_golden_pdf(tmp_path / "golden.pdf")
    reader = PyMuPdfReader()
    inspection = reader.inspecionar(source)

    rendered = reader.renderizar_pagina(
        source,
        1,
        dpi=72,
        sha256_esperado=inspection.documento.sha256,
    )

    assert (rendered.largura_pixels, rendered.altura_pixels) == (72, 48)
    assert _rgb_at(rendered, 2, 2) == pytest.approx((255, 255, 255), abs=8)
    assert _rgb_at(rendered, 30, 24) == pytest.approx((255, 0, 0), abs=8)

    rotated = reader.renderizar_pagina(source, 1, dpi=72, rotacao_adicional_graus=90)
    assert (rotated.largura_pixels, rotated.altura_pixels) == (48, 72)
    cropped = reader.renderizar_pagina(
        source,
        1,
        dpi=72,
        recorte_normalizado=(0.25, 0.25, 0.75, 0.75),
    )
    assert (cropped.largura_pixels, cropped.altura_pixels) == (36, 24)
    thumbnail = reader.renderizar_miniatura(source, 1)
    assert (thumbnail.largura_pixels, thumbnail.altura_pixels) == (36, 24)


def test_invalid_corrupt_and_protected_inputs_are_controlled(tmp_path: Path) -> None:
    reader = PyMuPdfReader()
    missing = tmp_path / "ausente.pdf"
    text_file = tmp_path / "arquivo.txt"
    text_file.write_text("não é PDF", encoding="utf-8")
    corrupt = tmp_path / "corrompido.pdf"
    corrupt.write_bytes(b"%PDF-1.7\nobjeto incompleto")
    protected = create_protected_pdf(tmp_path / "protegido.pdf")

    with pytest.raises(PdfArquivoInvalidoError):
        reader.inspecionar(missing)
    with pytest.raises(PdfArquivoInvalidoError):
        reader.inspecionar(text_file)
    with pytest.raises(PdfArquivoInvalidoError):
        reader.inspecionar(corrupt)
    with pytest.raises(PdfProtegidoError):
        reader.inspecionar(protected)
    with pytest.raises(PdfProtegidoError):
        reader.inspecionar(protected, senha="errada")

    assert reader.inspecionar(protected, senha="senha").documento.paginas


def test_rendering_rejects_invalid_parameters_and_changed_source(tmp_path: Path) -> None:
    source = create_golden_pdf(tmp_path / "origem.pdf")
    reader = PyMuPdfReader()
    inspection = reader.inspecionar(source)

    for kwargs in (
        {"pagina_numero": 0, "dpi": 72},
        {"pagina_numero": 2, "dpi": 72},
        {"pagina_numero": 1, "dpi": 10},
        {"pagina_numero": 1, "dpi": 72, "rotacao_adicional_graus": 45},
        {"pagina_numero": 1, "dpi": 72, "recorte_normalizado": (0.8, 0, 0.2, 1)},
    ):
        with pytest.raises(PdfPaginaInvalidaError):
            reader.renderizar_pagina(source, **kwargs)

    source.write_bytes(source.read_bytes() + b"\n% alterado")
    with pytest.raises(PdfOrigemAlteradaError):
        reader.verificar_origem(inspection)
    with pytest.raises(PdfOrigemAlteradaError):
        reader.renderizar_pagina(
            source,
            1,
            dpi=72,
            sha256_esperado=inspection.documento.sha256,
        )


def test_extractor_failure_is_localized_and_other_resources_survive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = create_feature_pdf(tmp_path / "falha-local.pdf")

    def fail_vectors(_page: Any) -> tuple[object, ...]:
        raise RuntimeError("objeto vetorial não suportado")

    monkeypatch.setattr(reader_module, "_extract_vectors", fail_vectors)
    inspection = PyMuPdfReader().inspecionar(source)

    first = inspection.paginas[0]
    assert first.vetores == ()
    assert any(item.codigo == "pdf.vetor_nao_lido" for item in first.diagnosticos)
    assert first.textos
    assert first.imagens
    assert PyMuPdfReader().renderizar_pagina(source, 1, dpi=72).dados_rgb


def test_mupdf_warning_classification_is_localized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        reader_module,
        "_raw_mupdf_warnings",
        lambda: "missing font resource\nbroken annot object\nunsupported object",
    )

    diagnostics = reader_module._mupdf_diagnostics(2)

    assert [item.codigo for item in diagnostics] == [
        "pdf.fonte_ausente",
        "pdf.anotacao_malformada",
        "pdf.objeto_nao_suportado",
    ]
    assert all(item.pagina_numero == 2 for item in diagnostics)


def _rgb_at(rendered: Any, x: int, y: int) -> tuple[int, int, int]:
    offset = y * rendered.stride + x * 3
    return tuple(rendered.dados_rgb[offset : offset + 3])
