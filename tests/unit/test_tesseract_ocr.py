from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

import pytest

from zeny_project_handler.adapters.analysis import tesseract_ocr as ocr_module
from zeny_project_handler.adapters.analysis.tesseract_ocr import (
    _best_available_language,
    _parse_tsv,
    _ppm_bytes,
)
from zeny_project_handler.ports.analysis import PaginaRasterOcr


def test_ppm_encoder_removes_stride_padding() -> None:
    page = PaginaRasterOcr(
        pagina_numero=1,
        largura_pixels=2,
        altura_pixels=2,
        stride=8,
        dados_rgb=b"abcdef__ghijkl__",
        dpi=200,
    )

    encoded = _ppm_bytes(page)

    assert encoded == b"P6\n2 2\n255\nabcdefghijkl"


def test_tsv_parser_groups_words_into_normalized_lines() -> None:
    tsv = "\n".join(
        (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t90\tPOSTE",
            "5\t1\t1\t1\t1\t2\t45\t20\t35\t10\t80\t11-300",
            "5\t1\t1\t1\t2\t1\t5\t60\t20\t10\t-1\t",
        )
    )

    result = _parse_tsv(tsv, width=100, height=100)

    assert len(result) == 1
    assert result[0].texto == "POSTE 11-300"
    assert result[0].caixa_normalizada == (0.1, 0.2, 0.8, 0.3)
    assert result[0].confianca == 0.85


def test_tsv_parser_does_not_treat_literal_quotes_as_csv_quoting() -> None:
    tsv = "\n".join(
        (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            '5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t90\t"Seu',
            "5\t1\t1\t1\t1\t2\t45\t20\t35\t10\t80\tdia",
            '5\t1\t2\t1\t1\t1\t10\t40\t30\t10\t90\tASTA"',
        )
    )

    result = _parse_tsv(tsv, width=100, height=100)

    assert [item.texto for item in result] == ['"Seu dia', 'ASTA"']


def test_ocr_prefers_portuguese_and_keeps_english(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_language_run(
        *_args: object,
        **_kwargs: object,
    ) -> CompletedProcess[str]:
        return CompletedProcess(
            args=[],
            returncode=0,
            stdout="List of available languages:\neng\npor\n",
        )

    monkeypatch.setattr(
        "zeny_project_handler.adapters.analysis.tesseract_ocr.subprocess.run",
        fake_language_run,
    )

    assert _best_available_language(Path("tesseract.exe")) == "por+eng"


def test_identifier_ocr_uses_single_character_mode_and_whitelist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "tesseract.exe"
    executable.write_bytes(b"stub")
    captured: list[tuple[str, ...]] = []
    tsv = "\n".join(
        (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t1\t1\t10\t10\t95\tP7",
        )
    )

    def fake_run(
        arguments: list[str],
        **_kwargs: object,
    ) -> CompletedProcess[bytes]:
        captured.append(tuple(arguments))
        return CompletedProcess(args=arguments, returncode=0, stdout=tsv.encode())

    monkeypatch.setattr(
        "zeny_project_handler.adapters.analysis.tesseract_ocr.subprocess.run",
        fake_run,
    )
    engine = ocr_module.TesseractCliOcr(executable, language="eng")
    page = PaginaRasterOcr(
        pagina_numero=1,
        largura_pixels=1,
        altura_pixels=1,
        stride=3,
        dados_rgb=b"\xff\xff\xff",
        dpi=1200,
    )

    result = engine.reconhecer_identificador(page)

    assert [item.texto for item in result] == ["P7"]
    assert "--psm" in captured[0] and "10" in captured[0]
    assert "tessedit_char_whitelist=P0123456789" in captured[0]


def test_operational_label_ocr_uses_single_line_mode_and_technical_whitelist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "tesseract.exe"
    executable.write_bytes(b"stub")
    captured: list[tuple[str, ...]] = []
    tsv = "\n".join(
        (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t1\t1\t30\t10\t95\tCM2(1)",
        )
    )

    def fake_run(
        arguments: list[str],
        **_kwargs: object,
    ) -> CompletedProcess[bytes]:
        captured.append(tuple(arguments))
        return CompletedProcess(args=arguments, returncode=0, stdout=tsv.encode())

    monkeypatch.setattr(
        "zeny_project_handler.adapters.analysis.tesseract_ocr.subprocess.run",
        fake_run,
    )
    engine = ocr_module.TesseractCliOcr(executable, language="eng")
    page = PaginaRasterOcr(
        pagina_numero=1,
        largura_pixels=1,
        altura_pixels=1,
        stride=3,
        dados_rgb=b"\xff\xff\xff",
        dpi=1200,
    )

    result = engine.reconhecer_rotulo_operacional(page)

    assert [item.texto for item in result] == ["CM2(1)"]
    assert "--psm" in captured[0] and "7" in captured[0]
    assert 'tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789()-/".,:' in captured[0]


def test_operational_block_ocr_uses_uniform_block_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "tesseract.exe"
    executable.write_bytes(b"stub")
    captured: list[tuple[str, ...]] = []
    tsv = "\n".join(
        (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t1\t1\t30\t10\t95\t11-300",
        )
    )

    def fake_run(
        arguments: list[str],
        **_kwargs: object,
    ) -> CompletedProcess[bytes]:
        captured.append(tuple(arguments))
        return CompletedProcess(args=arguments, returncode=0, stdout=tsv.encode())

    monkeypatch.setattr(
        "zeny_project_handler.adapters.analysis.tesseract_ocr.subprocess.run",
        fake_run,
    )
    engine = ocr_module.TesseractCliOcr(executable, language="eng")
    page = PaginaRasterOcr(
        pagina_numero=1,
        largura_pixels=1,
        altura_pixels=1,
        stride=3,
        dados_rgb=b"\xff\xff\xff",
        dpi=1200,
    )

    result = engine.reconhecer_bloco_operacional(page)

    assert [item.texto for item in result] == ["11-300"]
    assert "--psm" in captured[0] and "6" in captured[0]
